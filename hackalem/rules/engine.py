"""Deterministic, fail-closed permit rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, Sequence

import yaml

from core.schemas import (
    EvidenceValue,
    ExtractedPermit,
    Finding,
    Prooflink,
    RegistryRecord,
    RegistrySnapshot,
    Severity,
    Validation,
)


@dataclass(frozen=True, slots=True)
class RuleSpec:
    rule_id: str
    description: str
    severity: Severity
    condition: str
    required_sources: tuple[str, ...]
    required_human_decision: str


_MATRIX_PATH = Path(__file__).with_name("matrix.yaml")
_EXPECTED_RULE_IDS = {
    "R-GAS-01",
    "R-EMP-01",
    "R-SIG-01",
    "R-ZONE-01",
    "R-LOTO-01",
    "R-SIMOPS-01",
    "R-SHIFT-01",
    "R-PACK-01",
}


@lru_cache(maxsize=1)
def load_rule_matrix() -> dict[str, RuleSpec]:
    """Load and validate rule metadata once; evaluation itself remains deterministic."""

    try:
        payload = yaml.safe_load(_MATRIX_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid rule matrix: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("rule matrix must have version 1")
    rows = payload.get("rules")
    if not isinstance(rows, list):
        raise ValueError("rule matrix must contain a rules list")

    specs: dict[str, RuleSpec] = {}
    required_keys = {
        "rule_id",
        "description",
        "severity",
        "condition",
        "required_sources",
        "on_missing",
        "on_conflict",
        "on_invalid_format",
        "required_human_decision",
    }
    for row in rows:
        if not isinstance(row, dict) or set(row) != required_keys:
            raise ValueError("every matrix rule must contain the exact required fields")
        rule_id = row["rule_id"]
        if not isinstance(rule_id, str) or not rule_id.strip() or rule_id in specs:
            raise ValueError("rule_id values must be non-empty and unique")
        if row["severity"] not in {"P1", "P2", "P3"}:
            raise ValueError(f"invalid severity for {rule_id}")
        sources = row["required_sources"]
        text_values = (
            row["description"],
            row["condition"],
            row["required_human_decision"],
        )
        if any(not isinstance(value, str) or not value.strip() for value in text_values):
            raise ValueError(f"blank matrix text for {rule_id}")
        if not isinstance(sources, list) or not sources or any(
            not isinstance(value, str) or not value.strip() for value in sources
        ):
            raise ValueError(f"invalid required_sources for {rule_id}")
        if row["on_missing"] != "insufficient_evidence":
            raise ValueError(f"{rule_id} must fail closed on missing data")
        if row["on_conflict"] != "contested":
            raise ValueError(f"{rule_id} must classify conflicts as contested")
        if row["on_invalid_format"] != "insufficient_evidence":
            raise ValueError(f"{rule_id} must fail closed on invalid formats")
        specs[rule_id] = RuleSpec(
            rule_id=rule_id,
            description=row["description"],
            severity=row["severity"],
            condition=row["condition"],
            required_sources=tuple(sources),
            required_human_decision=row["required_human_decision"],
        )
    if set(specs) != _EXPECTED_RULE_IDS:
        raise ValueError("rule matrix must contain exactly the eight supported rules")
    return specs


EvidenceSource = EvidenceValue[object] | RegistryRecord


def _dedupe_prooflinks(sources: Iterable[EvidenceSource]) -> list[Prooflink]:
    result: list[Prooflink] = []
    seen: set[tuple[str, str, str]] = set()
    for source in sources:
        for prooflink in source.prooflinks:
            key = (prooflink.source_id, prooflink.location, prooflink.quote)
            if key not in seen:
                seen.add(key)
                result.append(prooflink)
    result.sort(key=lambda item: item.source_id.startswith("mock://"))
    return result


def _classification_for(evidence: Sequence[EvidenceValue[object]]) -> str:
    statuses = {item.status for item in evidence}
    if "contested" in statuses:
        return "contested"
    if "unknown" in statuses:
        return "unknown"
    return "insufficient_evidence"


def _finding(
    spec: RuleSpec,
    classification: str,
    claim: str,
    *sources: EvidenceSource,
) -> Finding:
    prooflinks = _dedupe_prooflinks(sources)
    if classification == "confirmed" and not any(
        not item.source_id.startswith("mock://") for item in prooflinks
    ):
        classification = "insufficient_evidence"
        claim = f"{claim} Документальное подтверждение отсутствует."
    confidence = 1.0 if classification == "confirmed" else 0.0
    return Finding(
        finding_id=f"F-{spec.rule_id.removeprefix('R-')}",
        rule_id=spec.rule_id,
        severity=spec.severity,
        classification=classification,  # type: ignore[arg-type]
        claim=claim,
        confidence=confidence,
        prooflinks=prooflinks,
        validation=Validation(
            rules_failed=[spec.rule_id],
            unknowns=[] if classification == "confirmed" else [claim],
        ),
        requires_human_review=True,
        required_human_decision=spec.required_human_decision,
    )


def _precheck(
    spec: RuleSpec,
    fields: Sequence[tuple[str, EvidenceValue[object]]],
) -> Finding | None:
    unresolved = [(name, value) for name, value in fields if value.value is None]
    contested = [(name, value) for name, value in fields if value.status == "contested"]
    affected = contested or unresolved
    if affected:
        names = ", ".join(name for name, _ in affected)
        classification = "contested" if contested else _classification_for([value for _, value in affected])
        return _finding(
            spec,
            classification,
            f"Правило нельзя подтвердить: поля {names} отсутствуют или противоречат источникам.",
            *(value for _, value in affected),
        )
    invalid_dates = [
        (name, value)
        for name, value in fields
        if isinstance(value.value, datetime) and value.value.tzinfo is None
    ]
    if invalid_dates:
        names = ", ".join(name for name, _ in invalid_dates)
        return _finding(
            spec,
            "insufficient_evidence",
            f"Правило нельзя вычислить: у полей {names} не указана временная зона.",
            *(value for _, value in invalid_dates),
        )
    return None


def _check_gas(permit: ExtractedPermit, registries: RegistrySnapshot, spec: RuleSpec) -> Finding | None:
    fields = [
        ("permit_id", permit.permit_id),
        ("work_start", permit.work_start),
        ("gas_tested_at", permit.gas_tested_at),
        ("gas_valid_minutes", permit.gas_valid_minutes),
    ]
    if issue := _precheck(spec, fields):
        return issue
    start = permit.work_start.value
    tested_at = permit.gas_tested_at.value
    valid_minutes = permit.gas_valid_minutes.value
    assert isinstance(start, datetime) and isinstance(tested_at, datetime) and isinstance(valid_minutes, int)
    sources: tuple[EvidenceSource, ...] = (
        permit.permit_id,
        permit.work_start,
        permit.gas_tested_at,
        permit.gas_valid_minutes,
        registries.gas_test_status,
    )
    if valid_minutes <= 0:
        return _finding(spec, "confirmed", "Срок действия газоанализа неположительный.", *sources)
    expires_at = tested_at + timedelta(minutes=valid_minutes)
    if tested_at > start or expires_at < start:
        return _finding(spec, "confirmed", "Газоанализ недействителен на момент начала работ.", *sources)

    registry = registries.gas_test_status
    if registry.status == "unknown" or registry.valid is None:
        return _finding(spec, "unknown", "Реестр не подтвердил статус газоанализа.", *sources)
    if registry.queried_id != permit.permit_id.value:
        return _finding(spec, "contested", "Документ и реестр относятся к разным нарядам.", *sources)
    if registry.status == "blocked" or registry.valid is not True:
        return _finding(spec, "confirmed", "Реестр пометил газоанализ как недействительный.", *sources)
    if registry.tested_at is None or registry.valid_until is None:
        return _finding(spec, "insufficient_evidence", "В реестре нет полного интервала газоанализа.", *sources)
    if registry.tested_at.tzinfo is None or registry.valid_until.tzinfo is None:
        return _finding(spec, "insufficient_evidence", "Временная зона реестра газоанализа не указана.", *sources)
    if not registry.tested_at <= start <= registry.valid_until:
        return _finding(spec, "confirmed", "Реестровый газоанализ не покрывает начало работ.", *sources)
    if registry.tested_at != tested_at or registry.valid_until != expires_at:
        return _finding(spec, "contested", "Интервалы газоанализа в документе и реестре расходятся.", *sources)
    return None


def _check_employee(permit: ExtractedPermit, registries: RegistrySnapshot, spec: RuleSpec) -> Finding | None:
    fields = [("employee_id", permit.employee_id), ("work_end", permit.work_end)]
    if issue := _precheck(spec, fields):
        return issue
    employee_id = permit.employee_id.value
    work_end = permit.work_end.value
    assert isinstance(employee_id, str) and isinstance(work_end, datetime)
    registry = registries.employee_clearance
    sources: tuple[EvidenceSource, ...] = (permit.employee_id, permit.work_end, registry)
    if registry.status == "unknown" or registry.cleared is None:
        return _finding(spec, "unknown", "Реестр не подтвердил допуск работника.", *sources)
    if registry.queried_id != employee_id:
        return _finding(spec, "contested", "Идентификатор работника в документе и реестре не совпадает.", *sources)
    if registry.status == "blocked" or registry.cleared is not True:
        return _finding(spec, "confirmed", "У назначенного работника нет действующего допуска.", *sources)
    if registry.valid_until is None or registry.valid_until.tzinfo is None:
        return _finding(spec, "insufficient_evidence", "Срок допуска работника не подтвержден.", *sources)
    if registry.valid_until < work_end:
        return _finding(spec, "confirmed", "Допуск работника истекает до завершения работ.", *sources)
    return None


def _check_signature(permit: ExtractedPermit, _: RegistrySnapshot, spec: RuleSpec) -> Finding | None:
    if issue := _precheck(spec, [("responsible_signature", permit.responsible_signature)]):
        return issue
    if permit.responsible_signature.value is not True:
        return _finding(
            spec,
            "confirmed",
            "Обязательная подпись ответственного лица отсутствует.",
            permit.responsible_signature,
        )
    return None


def _check_zone(permit: ExtractedPermit, registries: RegistrySnapshot, spec: RuleSpec) -> Finding | None:
    if issue := _precheck(spec, [("zone_id", permit.zone_id)]):
        return issue
    zone_id = permit.zone_id.value
    assert isinstance(zone_id, str)
    employee = registries.employee_clearance
    site = registries.site_restrictions
    sources: tuple[EvidenceSource, ...] = (permit.zone_id, employee, site)
    if employee.status == "unknown" or site.status == "unknown" or site.work_allowed is None:
        return _finding(spec, "unknown", "Реестры не подтвердили доступность зоны работ.", *sources)
    if site.queried_id != zone_id:
        return _finding(spec, "contested", "Зона документа не совпадает с запросом реестра площадки.", *sources)
    if zone_id not in employee.allowed_zones:
        return _finding(spec, "confirmed", "Работник не допущен в указанную зону.", *sources)
    if site.status == "blocked" or site.work_allowed is not True:
        return _finding(spec, "confirmed", "Работы в указанной зоне ограничены площадкой.", *sources)
    return None


def _check_loto(permit: ExtractedPermit, registries: RegistrySnapshot, spec: RuleSpec) -> Finding | None:
    fields = [("asset_id", permit.asset_id), ("isolation_id", permit.isolation_id)]
    if issue := _precheck(spec, fields):
        return issue
    asset_id = permit.asset_id.value
    isolation_id = permit.isolation_id.value
    assert isinstance(asset_id, str) and isinstance(isolation_id, str)
    registry = registries.asset_isolation
    sources: tuple[EvidenceSource, ...] = (permit.asset_id, permit.isolation_id, registry)
    if registry.status == "unknown" or registry.isolated is None:
        return _finding(spec, "unknown", "Реестр не подтвердил изоляцию оборудования.", *sources)
    if registry.queried_id != asset_id:
        return _finding(spec, "contested", "Документ и реестр относятся к разному оборудованию.", *sources)
    if registry.status == "blocked" or registry.isolated is not True:
        return _finding(spec, "confirmed", "Изоляция оборудования не подтверждена реестром.", *sources)
    if registry.isolation_id is None:
        return _finding(spec, "insufficient_evidence", "В реестре отсутствует идентификатор изоляции.", *sources)
    if registry.isolation_id != isolation_id:
        return _finding(spec, "contested", "Идентификатор LOTO в документе и реестре не совпадает.", *sources)
    return None


def _check_simops(permit: ExtractedPermit, _: RegistrySnapshot, spec: RuleSpec) -> Finding | None:
    fields = [("zone_id", permit.zone_id), ("concurrent_work_zones", permit.concurrent_work_zones)]
    if issue := _precheck(spec, fields):
        return issue
    zone_id = permit.zone_id.value
    concurrent = permit.concurrent_work_zones.value
    assert isinstance(zone_id, str) and isinstance(concurrent, list)
    if any(not isinstance(value, str) or not value.strip() for value in concurrent):
        return _finding(
            spec,
            "insufficient_evidence",
            "Перечень зон одновременных работ имеет неверный формат.",
            permit.zone_id,
            permit.concurrent_work_zones,
        )
    if zone_id in concurrent:
        return _finding(
            spec,
            "confirmed",
            "В зоне наряда уже выполняются несовместимые одновременные работы.",
            permit.zone_id,
            permit.concurrent_work_zones,
        )
    return None


def _check_shift(permit: ExtractedPermit, _: RegistrySnapshot, spec: RuleSpec) -> Finding | None:
    fields = [
        ("work_start", permit.work_start),
        ("work_end", permit.work_end),
        ("shift_start", permit.shift_start),
        ("shift_end", permit.shift_end),
    ]
    if issue := _precheck(spec, fields):
        return issue
    work_start = permit.work_start.value
    work_end = permit.work_end.value
    shift_start = permit.shift_start.value
    shift_end = permit.shift_end.value
    assert all(isinstance(value, datetime) for value in (work_start, work_end, shift_start, shift_end))
    sources: tuple[EvidenceSource, ...] = (
        permit.work_start,
        permit.work_end,
        permit.shift_start,
        permit.shift_end,
    )
    if shift_start >= shift_end or work_start >= work_end:
        return _finding(spec, "confirmed", "Интервал смены или работ задан некорректно.", *sources)
    if work_start < shift_start or work_end > shift_end:
        return _finding(spec, "confirmed", "Работы выходят за границы разрешенной смены.", *sources)
    return None


def _check_package(permit: ExtractedPermit, _: RegistrySnapshot, spec: RuleSpec) -> Finding | None:
    field = permit.required_documents_present
    if issue := _precheck(spec, [("required_documents_present", field)]):
        return issue
    if field.value is not True:
        return _finding(spec, "confirmed", "В комплекте отсутствуют обязательные документы.", field)
    return None


RuleCheck = Callable[[ExtractedPermit, RegistrySnapshot, RuleSpec], Finding | None]
_CHECKS: dict[str, RuleCheck] = {
    "R-GAS-01": _check_gas,
    "R-EMP-01": _check_employee,
    "R-SIG-01": _check_signature,
    "R-ZONE-01": _check_zone,
    "R-LOTO-01": _check_loto,
    "R-SIMOPS-01": _check_simops,
    "R-SHIFT-01": _check_shift,
    "R-PACK-01": _check_package,
}


def evaluate_rules(permit: ExtractedPermit, registries: RegistrySnapshot) -> list[Finding]:
    """Evaluate all eight rules in stable rule-id order without mutating inputs."""

    specs = load_rule_matrix()
    if set(_CHECKS) != set(specs):
        raise ValueError("rule matrix and engine checks do not match")
    findings: list[Finding] = []
    for rule_id in sorted(specs):
        finding = _CHECKS[rule_id](permit, registries, specs[rule_id])
        if finding is not None:
            findings.append(finding)
    return findings
