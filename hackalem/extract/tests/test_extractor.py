from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from core.prooflinks import validate_prooflink
from data.generator import build_case_specs, write_case
from extract.extractor import extract_permit


@pytest.fixture
def workspace(request) -> Path:
    name = re.sub(r"[^a-z0-9]+", "-", request.node.name.casefold()).strip("-")
    path = Path(__file__).resolve().parents[2] / "data" / "tmp" / f"extract-{name}"
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _write_spec(tmp_path, spec):
    fixtures = tmp_path / "fixtures"
    write_case(spec, fixtures)
    return fixtures / spec.case_id


def test_clean_bundle_extracts_every_contract_field_with_proof(workspace) -> None:
    case_dir = _write_spec(workspace, build_case_specs()[0])
    permit = extract_permit(case_dir)
    assert permit.missing_fields() == []
    assert permit.contradictions == []
    assert permit.permit_id.value == "PERMIT-001"
    assert permit.employee_id.value == "EMP-001"
    assert permit.responsible_signature.value is True
    assert permit.required_documents_present.value is True
    for name in type(permit).model_fields:
        if name == "contradictions":
            continue
        evidence = getattr(permit, name)
        assert evidence.prooflinks
        assert all(validate_prooflink(link, case_dir).valid for link in evidence.prooflinks)


@pytest.mark.parametrize(
    ("rule_id", "check"),
    [
        ("R-GAS-01", lambda value: value.gas_tested_at.value < value.work_start.value),
        ("R-EMP-01", lambda value: value.employee_id.value.startswith("EMP-EXPIRED-")),
        ("R-SIG-01", lambda value: value.responsible_signature.value is False),
        ("R-ZONE-01", lambda value: value.zone_id.value == "ZONE-X"),
        ("R-LOTO-01", lambda value: value.isolation_id.value is None),
        ("R-SIMOPS-01", lambda value: value.zone_id.value in value.concurrent_work_zones.value),
    ],
)
def test_each_trap_remains_visible_after_extraction(workspace, rule_id, check) -> None:
    spec = next(item for item in build_case_specs() if item.violation_rule_id == rule_id)
    permit = extract_permit(_write_spec(workspace, spec))
    assert check(permit)


def test_missing_document_is_fail_closed(workspace) -> None:
    case_dir = _write_spec(workspace, build_case_specs()[0])
    (case_dir / "gas_log.csv").unlink()
    permit = extract_permit(case_dir)
    assert permit.gas_tested_at.value is None
    assert permit.gas_valid_minutes.value is None
    assert permit.required_documents_present.value is None
    assert any("Missing document" in item for item in permit.contradictions)


def test_conflicting_employee_ids_are_not_guessed(workspace) -> None:
    case_dir = _write_spec(workspace, build_case_specs()[0])
    card_path = case_dir / "employee_card.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    card["employee_id"] = "EMP-CONFLICT"
    card_path.write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    permit = extract_permit(case_dir)
    assert permit.employee_id.value is None
    assert permit.employee_id.status == "insufficient_evidence"
    assert any("Employee ID conflicts" in item for item in permit.contradictions)
