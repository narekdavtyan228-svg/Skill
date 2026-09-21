"""Fail-closed PermitGuard orchestration across extraction, registries and rules."""

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from importlib import import_module
from pathlib import Path
from typing import Callable, Sequence
from uuid import uuid4

from pydantic import ValidationError

from core import mock_api
from core.prooflinks import finding_has_valid_prooflink
from core.schemas import (
    EvidenceValue,
    ExtractedPermit,
    Finding,
    PermitResult,
    RegistrySnapshot,
    Validation,
    Verdict,
)


Extractor = Callable[[str | Path], ExtractedPermit]
RulesEngine = Callable[[ExtractedPermit, RegistrySnapshot], list[Finding]]
VerdictFunction = Callable[[Sequence[Finding], Sequence[str]], Verdict]


def _unknown() -> EvidenceValue[object]:
    return EvidenceValue[object](
        value=None,
        status="insufficient_evidence",
        prooflinks=[],
    )


def _empty_permit() -> ExtractedPermit:
    return ExtractedPermit(
        permit_id=_unknown(),
        employee_id=_unknown(),
        asset_id=_unknown(),
        zone_id=_unknown(),
        work_start=_unknown(),
        work_end=_unknown(),
        gas_tested_at=_unknown(),
        gas_valid_minutes=_unknown(),
        responsible_signature=_unknown(),
        isolation_id=_unknown(),
        concurrent_work_zones=_unknown(),
        shift_start=_unknown(),
        shift_end=_unknown(),
        required_documents_present=_unknown(),
    )


def _fallback_extract(permit_dir: str | Path) -> ExtractedPermit:
    contract_file = Path(permit_dir) / "extracted_permit.json"
    if not contract_file.is_file():
        return _empty_permit()
    return ExtractedPermit.model_validate_json(contract_file.read_text(encoding="utf-8"))


def _load_function(module_name: str, function_name: str) -> Callable[..., object] | None:
    try:
        module = import_module(module_name)
    except (ImportError, ModuleNotFoundError):
        return None
    function = getattr(module, function_name, None)
    return function if callable(function) else None


def _fallback_rules(permit: ExtractedPermit, _: RegistrySnapshot) -> list[Finding]:
    tested_at = permit.gas_tested_at.value
    valid_minutes = permit.gas_valid_minutes.value
    work_start = permit.work_start.value
    if tested_at is None or valid_minutes is None or work_start is None:
        return []
    if tested_at.tzinfo is None or work_start.tzinfo is None:
        return []
    expires_at = tested_at + timedelta(minutes=valid_minutes)
    if expires_at >= work_start:
        return []
    prooflinks = []
    seen_prooflinks: set[tuple[str, str, str]] = set()
    for prooflink in (
        permit.gas_tested_at.prooflinks
        + permit.gas_valid_minutes.prooflinks
        + permit.work_start.prooflinks
    ):
        key = (prooflink.source_id, prooflink.location, prooflink.quote)
        if key not in seen_prooflinks:
            seen_prooflinks.add(key)
            prooflinks.append(prooflink)
    return [
        Finding(
            finding_id="F-GAS-001",
            rule_id="R-GAS-02",
            severity="P1",
            classification="confirmed",
            claim="Gas test validity expires before the planned work starts.",
            confidence=1.0,
            prooflinks=prooflinks,
            validation=Validation(
                rules_passed=[],
                rules_failed=["R-GAS-02"],
                unknowns=[],
            ),
            requires_human_review=True,
            required_human_decision="Require and verify a new gas test before work starts.",
        )
    ]


def _fallback_verdict(findings: Sequence[Finding], unknowns: Sequence[str]) -> Verdict:
    if unknowns or any(item.severity in {"P1", "P2"} for item in findings):
        return "block_and_escalate"
    if findings:
        return "approve_with_conditions"
    return "approve"


def _value_or_unknown(field: EvidenceValue[str]) -> str:
    return field.value if isinstance(field.value, str) and field.value.strip() else "unknown"


def _query_registries(permit: ExtractedPermit) -> RegistrySnapshot:
    return RegistrySnapshot(
        employee_clearance=mock_api.employee_clearance(_value_or_unknown(permit.employee_id)),
        gas_test_status=mock_api.gas_test_status(_value_or_unknown(permit.permit_id)),
        asset_isolation=mock_api.asset_isolation(_value_or_unknown(permit.asset_id)),
        site_restrictions=mock_api.site_restrictions(_value_or_unknown(permit.zone_id)),
        queried_endpoints=(
            "employee_clearance",
            "gas_test_status",
            "asset_isolation",
            "site_restrictions",
        ),
    )


def _safe_extract(permit_dir: Path, audit: list[str], unknowns: list[str]) -> ExtractedPermit:
    candidate = _load_function("extract.extractor", "extract_permit")
    extractor: Extractor = candidate if candidate is not None else _fallback_extract  # type: ignore[assignment]
    audit.append("extractor:real" if candidate is not None else "extractor:fallback")
    if candidate is None:
        unknowns.append("Required extraction module is unavailable")
    try:
        raw = extractor(permit_dir)
        return raw if isinstance(raw, ExtractedPermit) else ExtractedPermit.model_validate(raw)
    except (OSError, ValueError, TypeError, ValidationError) as exc:
        unknowns.append(f"Extraction failed: {type(exc).__name__}: {exc}")
        audit.append("extractor:error")
        return _empty_permit()


def _safe_rules(
    permit: ExtractedPermit,
    registries: RegistrySnapshot,
    audit: list[str],
    unknowns: list[str],
) -> list[Finding]:
    candidate = _load_function("rules.engine", "evaluate_rules")
    engine: RulesEngine = candidate if candidate is not None else _fallback_rules  # type: ignore[assignment]
    audit.append("rules:real" if candidate is not None else "rules:fallback")
    if candidate is None:
        unknowns.append("Required rules engine is unavailable; full validation was not performed")
    try:
        return [item if isinstance(item, Finding) else Finding.model_validate(item) for item in engine(permit, registries)]
    except (ValueError, TypeError, ValidationError, ArithmeticError) as exc:
        unknowns.append(f"Rules evaluation failed: {type(exc).__name__}: {exc}")
        audit.append("rules:error")
        return []


def _safe_verdict(
    findings: Sequence[Finding],
    unknowns: Sequence[str],
    audit: list[str],
) -> Verdict:
    if unknowns:
        audit.append("verdict:forced-fail-closed")
        return "block_and_escalate"
    candidate = _load_function("rules.verdict", "derive_verdict")
    verdict_function: VerdictFunction = candidate if candidate is not None else _fallback_verdict  # type: ignore[assignment]
    audit.append("verdict:real" if candidate is not None else "verdict:fallback")
    try:
        verdict = verdict_function(findings, unknowns)
    except (ValueError, TypeError, ValidationError, ArithmeticError) as exc:
        audit.append(f"verdict:error:{type(exc).__name__}")
        return "block_and_escalate"
    if verdict not in {"approve", "approve_with_conditions", "block_and_escalate"}:
        audit.append("verdict:error:invalid-value")
        return "block_and_escalate"
    return verdict


def run(permit_dir: str | Path, run_id: str | None = None) -> PermitResult:
    """Run one permit bundle and always return a controlled, fail-closed result."""

    root = Path(permit_dir)
    audit: list[str] = []
    unknowns: list[str] = []
    mock_api.reset_call_log()

    permit = _safe_extract(root, audit, unknowns)
    missing = permit.missing_fields()
    if missing:
        unknowns.append(f"Missing required extracted fields: {', '.join(sorted(missing))}")
    unknowns.extend(f"Contradictory extraction: {item}" for item in permit.contradictions)

    registries = _query_registries(permit)
    audit.extend(f"mock_api:{entry}" for entry in mock_api.get_call_log())
    for endpoint in registries.queried_endpoints:
        record = getattr(registries, endpoint)
        if record.status == "unknown":
            unknowns.append(f"Registry {endpoint} has no confirmed record for {record.queried_id}")

    candidate_findings = _safe_rules(permit, registries, audit, unknowns)
    findings: list[Finding] = []
    for finding in candidate_findings:
        if finding_has_valid_prooflink(finding, root):
            findings.append(finding)
        else:
            unknowns.append(f"Finding {finding.finding_id} discarded: no valid document prooflink")
            audit.append(f"prooflink:invalid:{finding.finding_id}")

    unknowns = list(dict.fromkeys(unknowns))
    verdict = _safe_verdict(findings, unknowns, audit)
    if verdict == "approve" and (missing or permit.contradictions):
        verdict = "block_and_escalate"
        audit.append("verdict:fail-closed-override")

    decision = (
        "Уполномоченный руководитель должен устранить указанные барьеры до начала работ."
        if verdict == "block_and_escalate"
        else "Уполномоченный руководитель должен проверить рекомендацию и принять окончательное решение."
    )
    return PermitResult(
        run_id=run_id or f"run-{uuid4().hex[:12]}",
        verdict=verdict,
        findings=findings,
        unknowns=unknowns,
        audit_log=audit,
        requires_human_review=True,
        required_human_decision=decision,
    )


def _main() -> int:
    parser = argparse.ArgumentParser(description="Run PermitGuard on one permit bundle")
    parser.add_argument("--permit", required=True, help="Path to the permit bundle")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--print", action="store_true", dest="print_result")
    args = parser.parse_args()
    result = run(args.permit, args.run_id)
    if args.print_result:
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
