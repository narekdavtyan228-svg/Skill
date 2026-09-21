from pathlib import Path

import pytest

from core.orchestrator import run


FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


@pytest.mark.parametrize("case_id", ["permit_0001", "permit_0012", "permit_0040"])
def test_clean_bundles_are_approved(case_id: str) -> None:
    result = run(FIXTURES / case_id, f"test-{case_id}")

    assert result.verdict == "approve"
    assert result.findings == []
    assert result.unknowns == []


@pytest.mark.parametrize(
    ("case_id", "expected_rule"),
    [
        ("permit_0041", "R-GAS-01"),
        ("permit_0045", "R-SIG-01"),
        ("permit_0049", "R-ZONE-01"),
        ("permit_0052", "R-SIMOPS-01"),
        ("permit_0055", "R-EMP-01"),
        ("permit_0058", "R-LOTO-01"),
    ],
)
def test_traps_block_with_the_expected_rule(case_id: str, expected_rule: str) -> None:
    result = run(FIXTURES / case_id, f"test-{case_id}")

    assert result.verdict == "block_and_escalate"
    assert expected_rule in {finding.rule_id for finding in result.findings}
    assert all(finding.prooflinks for finding in result.findings)
