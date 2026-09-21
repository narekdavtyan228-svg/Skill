from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from core import mock_api
from core.prooflinks import validate_prooflink
from core.schemas import Finding, PermitResult, Prooflink, Validation


def test_confirmed_finding_requires_prooflink() -> None:
    with pytest.raises(ValidationError):
        Finding(
            finding_id="F-001",
            rule_id="R-GAS-01",
            severity="P1",
            classification="confirmed",
            claim="Газоанализ просрочен.",
            confidence=1.0,
            prooflinks=[],
            validation=Validation(rules_failed=["R-GAS-01"]),
            requires_human_review=True,
            required_human_decision="Повторить газоанализ.",
        )


def test_unknowns_force_blocking_verdict() -> None:
    with pytest.raises(ValidationError):
        PermitResult(
            run_id="test-run",
            verdict="approve",
            unknowns=["Нет обязательного источника"],
            requires_human_review=True,
            required_human_decision="Проверить комплект документов.",
        )


def test_mock_registries_are_deterministic_and_logged() -> None:
    mock_api.reset_call_log()
    first = mock_api.employee_clearance("EMP-001")
    second = mock_api.employee_clearance("EMP-001")

    assert first == second
    assert first.cleared is True
    assert mock_api.get_call_log() == (
        "employee_clearance:EMP-001",
        "employee_clearance:EMP-001",
    )
    assert first.valid_until == datetime(2030, 1, 1, tzinfo=timezone.utc)


def test_mock_gas_registry_covers_the_generated_dataset() -> None:
    record = mock_api.gas_test_status("PERMIT-060")

    assert record.status == "clear"
    assert record.valid is True
    assert record.tested_at is not None
    assert record.valid_until is not None
    assert record.valid_until - record.tested_at == timedelta(minutes=30)
    assert mock_api.gas_test_status("PERMIT-061").status == "unknown"


def test_row_prooflink_must_match_real_quote(tmp_path) -> None:
    source = tmp_path / "gas_log.csv"
    source.write_text("permit_id,tested_at\nPERMIT-001,2026-09-20T06:00:00Z\n", encoding="utf-8")

    valid = Prooflink(
        source_id="gas_log.csv",
        location="row:2",
        quote="PERMIT-001,2026-09-20T06:00:00Z",
    )
    invalid = Prooflink(
        source_id="gas_log.csv",
        location="row:2",
        quote="PERMIT-999",
    )

    assert validate_prooflink(valid, tmp_path).valid is True
    assert validate_prooflink(invalid, tmp_path).valid is False


@pytest.mark.parametrize("source_id", ["../gas_log.csv", "missing/gas_log.csv"])
def test_prooflink_rejects_wrong_paths(tmp_path, source_id) -> None:
    (tmp_path / "gas_log.csv").write_text("evidence", encoding="utf-8")
    link = Prooflink(source_id=source_id, location="row:1", quote="evidence")
    assert not validate_prooflink(link, tmp_path).valid


def test_missing_rules_engine_blocks_a_clean_bundle(monkeypatch) -> None:
    from pathlib import Path
    from core import orchestrator

    original = orchestrator._load_function
    monkeypatch.setattr(
        orchestrator, "_load_function",
        lambda module, function: None if module == "rules.engine" else original(module, function),
    )
    bundle = Path(__file__).resolve().parents[2] / "data/fixtures/permit_0001"
    result = orchestrator.run(bundle)
    assert result.verdict == "block_and_escalate"
    assert any("rules engine is unavailable" in item for item in result.unknowns)
