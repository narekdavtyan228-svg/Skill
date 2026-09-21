"""Deterministic synthetic document bundles for PermitGuard."""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Final

import pymupdf as fitz
from fpdf import FPDF


RULE_IDS: Final[tuple[str, ...]] = (
    "R-GAS-01",
    "R-EMP-01",
    "R-SIG-01",
    "R-ZONE-01",
    "R-LOTO-01",
    "R-SIMOPS-01",
)
EXPECTED_DOCUMENTS: Final[tuple[str, ...]] = (
    "employee_card.json",
    "gas_log.csv",
    "isolations.csv",
)
REFERENCE_TIME: Final = datetime(2026, 9, 20, 6, 0, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class CaseSpec:
    case_id: str
    permit_id: str
    employee_id: str
    asset_id: str
    zone_id: str
    work_type: str
    work_start: datetime
    work_end: datetime
    shift_start: datetime
    shift_end: datetime
    gas_tested_at: datetime
    gas_valid_minutes: int
    responsible_signature: bool
    clearance_valid_until: datetime
    allowed_zones: tuple[str, ...]
    isolation_id: str
    isolation_status: str
    concurrent_work_zones: tuple[str, ...]
    violation_rule_id: str | None = None


@dataclass(frozen=True, slots=True)
class ViolationDefinition:
    rule_id: str
    violation_type: str
    severity: str
    source_name: str
    location: str
    quote: str


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _base_case(index: int, rng: random.Random) -> CaseSpec:
    day = REFERENCE_TIME + timedelta(days=(index - 1) % 12)
    start_minute = rng.choice((15, 20, 25))
    work_start = day.replace(minute=start_minute)
    work_end = work_start + timedelta(hours=rng.choice((4, 5, 6)))
    shift_start = day.replace(minute=0)
    shift_end = shift_start + timedelta(hours=12)
    work_type = rng.choice(("inspection", "maintenance", "valve_service"))
    return CaseSpec(
        case_id=f"permit_{index:04d}",
        permit_id=f"PERMIT-{index:03d}",
        employee_id="EMP-001",
        asset_id="ASSET-001",
        zone_id="ZONE-A",
        work_type=work_type,
        work_start=work_start,
        work_end=work_end,
        shift_start=shift_start,
        shift_end=shift_end,
        gas_tested_at=work_start - timedelta(minutes=15),
        gas_valid_minutes=30,
        responsible_signature=True,
        clearance_valid_until=datetime(2030, 1, 1, tzinfo=timezone.utc),
        allowed_zones=("ZONE-A", "ZONE-B"),
        isolation_id="LOTO-001",
        isolation_status="CONFIRMED",
        concurrent_work_zones=("ZONE-B",),
    )


def inject_gas_expired(spec: CaseSpec) -> CaseSpec:
    return replace(
        spec,
        gas_tested_at=spec.work_start - timedelta(minutes=45),
        violation_rule_id="R-GAS-01",
    )


def inject_employee_expired(spec: CaseSpec) -> CaseSpec:
    return replace(
        spec,
        employee_id=f"EMP-EXPIRED-{spec.case_id[-4:]}",
        clearance_valid_until=spec.work_start - timedelta(days=1),
        violation_rule_id="R-EMP-01",
    )


def inject_missing_signature(spec: CaseSpec) -> CaseSpec:
    return replace(spec, responsible_signature=False, violation_rule_id="R-SIG-01")


def inject_wrong_zone(spec: CaseSpec) -> CaseSpec:
    return replace(spec, zone_id="ZONE-X", violation_rule_id="R-ZONE-01")


def inject_unconfirmed_loto(spec: CaseSpec) -> CaseSpec:
    return replace(spec, isolation_status="PENDING", violation_rule_id="R-LOTO-01")


def inject_simops_conflict(spec: CaseSpec) -> CaseSpec:
    return replace(
        spec,
        concurrent_work_zones=(spec.zone_id,),
        violation_rule_id="R-SIMOPS-01",
    )


INJECTORS: Final[dict[str, Callable[[CaseSpec], CaseSpec]]] = {
    "R-GAS-01": inject_gas_expired,
    "R-EMP-01": inject_employee_expired,
    "R-SIG-01": inject_missing_signature,
    "R-ZONE-01": inject_wrong_zone,
    "R-LOTO-01": inject_unconfirmed_loto,
    "R-SIMOPS-01": inject_simops_conflict,
}


def build_case_specs(seed: int = 20260920) -> list[CaseSpec]:
    """Return 40 clean cases followed by 20 single-violation cases."""

    rng = random.Random(seed)
    specs = [_base_case(index, rng) for index in range(1, 61)]
    trap_rules = (
        ["R-GAS-01"] * 4
        + ["R-SIG-01"] * 4
        + ["R-ZONE-01"] * 3
        + ["R-SIMOPS-01"] * 3
        + ["R-EMP-01"] * 3
        + ["R-LOTO-01"] * 3
    )
    for offset, rule_id in enumerate(trap_rules, start=40):
        specs[offset] = INJECTORS[rule_id](specs[offset])
    return specs


def _permit_lines(spec: CaseSpec) -> list[str]:
    concurrent = ",".join(spec.concurrent_work_zones) or "NONE"
    return [
        "PERMITGUARD SYNTHETIC WORK PERMIT",
        f"Permit ID: {spec.permit_id}",
        f"Employee ID: {spec.employee_id}",
        f"Asset ID: {spec.asset_id}",
        f"Zone ID: {spec.zone_id}",
        f"Work type: {spec.work_type}",
        f"Work start: {_iso(spec.work_start)}",
        f"Work end: {_iso(spec.work_end)}",
        f"Shift start: {_iso(spec.shift_start)}",
        f"Shift end: {_iso(spec.shift_end)}",
        f"Responsible signature: {'YES' if spec.responsible_signature else 'NO'}",
        f"Concurrent work zones: {concurrent}",
        "Required documents present: YES",
    ]


def _write_pdf(path: Path, lines: list[str]) -> None:
    pdf = FPDF(unit="mm", format="A4")
    pdf.set_creation_date(datetime(2026, 1, 1, tzinfo=timezone.utc))
    pdf.set_title("PermitGuard synthetic permit")
    pdf.set_author("PermitGuard")
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in lines:
        pdf.cell(0, 7, text=line, new_x="LMARGIN", new_y="NEXT")
    pdf.output(path)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_csv(path: Path, fieldnames: tuple[str, ...], row: dict[str, object]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerow(row)


def _violation(spec: CaseSpec) -> ViolationDefinition | None:
    rule_id = spec.violation_rule_id
    if rule_id is None:
        return None
    if rule_id == "R-GAS-01":
        return ViolationDefinition(
            rule_id, "expired_gas_test", "P1", "gas_log.csv", "row:2", _iso(spec.gas_tested_at)
        )
    if rule_id == "R-EMP-01":
        return ViolationDefinition(
            rule_id,
            "expired_employee_clearance",
            "P1",
            "employee_card.json",
            "row:3",
            _iso(spec.clearance_valid_until),
        )
    if rule_id == "R-SIG-01":
        return ViolationDefinition(
            rule_id, "missing_responsible_signature", "P1", f"{spec.case_id}.pdf", "page:1", "Responsible signature: NO"
        )
    if rule_id == "R-ZONE-01":
        return ViolationDefinition(
            rule_id, "unauthorized_work_zone", "P1", f"{spec.case_id}.pdf", "page:1", f"Zone ID: {spec.zone_id}"
        )
    if rule_id == "R-LOTO-01":
        return ViolationDefinition(
            rule_id, "unconfirmed_isolation", "P1", "isolations.csv", "row:2", spec.isolation_status
        )
    return ViolationDefinition(
        rule_id,
        "simultaneous_operations_conflict",
        "P1",
        f"{spec.case_id}.pdf",
        "page:1",
        f"Concurrent work zones: {spec.zone_id}",
    )


def write_case(spec: CaseSpec, fixtures_dir: Path) -> dict[str, object]:
    """Write one case without deleting unrelated paths and return its truth row."""

    case_dir = fixtures_dir / spec.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    known_names = (*EXPECTED_DOCUMENTS, f"{spec.case_id}.pdf")
    for name in known_names:
        target = case_dir / name
        if target.exists():
            target.unlink()

    _write_pdf(case_dir / f"{spec.case_id}.pdf", _permit_lines(spec))
    _write_json(
        case_dir / "employee_card.json",
        {
            "allowed_zones": list(spec.allowed_zones),
            "clearance_valid_until": _iso(spec.clearance_valid_until),
            "employee_id": spec.employee_id,
            "permit_id": spec.permit_id,
        },
    )
    _write_csv(
        case_dir / "gas_log.csv",
        ("permit_id", "tested_at", "valid_minutes"),
        {
            "permit_id": spec.permit_id,
            "tested_at": _iso(spec.gas_tested_at),
            "valid_minutes": spec.gas_valid_minutes,
        },
    )
    _write_csv(
        case_dir / "isolations.csv",
        ("permit_id", "isolation_id", "asset_id", "status"),
        {
            "permit_id": spec.permit_id,
            "isolation_id": spec.isolation_id,
            "asset_id": spec.asset_id,
            "status": spec.isolation_status,
        },
    )

    violation = _violation(spec)
    if violation is not None and violation.rule_id == "R-EMP-01":
        employee_lines = (case_dir / "employee_card.json").read_text(encoding="utf-8").splitlines()
        clearance_row = next(
            index
            for index, line in enumerate(employee_lines, start=1)
            if '"clearance_valid_until"' in line
        )
        violation = replace(violation, location=f"row:{clearance_row}")
    violations: list[dict[str, object]] = []
    if violation is not None:
        violations.append(
            {
                "rule_id": violation.rule_id,
                "type": violation.violation_type,
                "severity": violation.severity,
                "prooflinks": [
                    {
                        "source_id": violation.source_name,
                        "location": violation.location,
                        "quote": violation.quote,
                    }
                ],
            }
        )
    return {
        "case_id": spec.case_id,
        "permit_dir": spec.case_id,
        "permit_id": spec.permit_id,
        "critical": violation is not None,
        "violations": violations,
    }


def _location_text(case_dir: Path, source_id: str, location: str) -> str:
    kind, number_text = location.split(":", maxsplit=1)
    index = int(number_text)
    path = case_dir / source_id
    if kind == "page":
        with fitz.open(path) as document:
            if index > document.page_count:
                raise ValueError(f"missing {location} in {source_id}")
            return document.load_page(index - 1).get_text()
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if index > len(lines):
        raise ValueError(f"missing {location} in {source_id}")
    return lines[index - 1]


def validate_ground_truth(payload: dict[str, object], fixtures_dir: Path) -> None:
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("ground truth must contain a cases list")
    for row in cases:
        if not isinstance(row, dict):
            raise ValueError("ground truth case must be an object")
        case_dir = fixtures_dir / str(row["permit_dir"])
        for violation in row.get("violations", []):
            for prooflink in violation.get("prooflinks", []):
                source = case_dir / prooflink["source_id"]
                if not source.is_file():
                    raise ValueError(f"missing proof source: {source}")
                content = _location_text(case_dir, prooflink["source_id"], prooflink["location"])
                if " ".join(prooflink["quote"].split()).casefold() not in " ".join(content.split()).casefold():
                    raise ValueError(f"quote not found: {prooflink}")


def generate_dataset(output_dir: str | Path | None = None, seed: int = 20260920) -> dict[str, object]:
    root = Path(output_dir) if output_dir is not None else Path(__file__).resolve().parent
    fixtures_dir = root / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    rows = [write_case(spec, fixtures_dir) for spec in build_case_specs(seed)]
    payload: dict[str, object] = {
        "version": 1,
        "seed": seed,
        "distribution": {
            "clean": 40,
            "trap": 20,
            "by_rule": {
                "R-GAS-01": 4,
                "R-EMP-01": 3,
                "R-SIG-01": 4,
                "R-ZONE-01": 3,
                "R-LOTO-01": 3,
                "R-SIMOPS-01": 3,
            },
        },
        "cases": rows,
    }
    validate_ground_truth(payload, fixtures_dir)
    _write_json(root / "ground_truth.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PermitGuard synthetic fixtures")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--seed", type=int, default=20260920)
    args = parser.parse_args()
    payload = generate_dataset(args.output, args.seed)
    print(json.dumps(payload["distribution"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
