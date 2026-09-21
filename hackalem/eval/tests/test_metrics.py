from eval.metrics import EvaluatedCase, summarize


def test_acceptance_metrics() -> None:
    rows = [
        EvaluatedCase(
            case_id="permit_0001",
            expected_rule_ids=frozenset({"R-GAS-01", "R-SIG-01"}),
            predicted_rule_ids=frozenset({"R-GAS-01"}),
            verdict="block_and_escalate",
            critical=True,
            total_findings=1,
            findings_with_valid_prooflink=1,
        ),
        EvaluatedCase(
            case_id="permit_0002",
            expected_rule_ids=frozenset({"R-LOTO-01"}),
            predicted_rule_ids=frozenset(),
            verdict="approve",
            critical=True,
            total_findings=0,
            findings_with_valid_prooflink=0,
        ),
    ]

    summary = summarize(rows)

    assert summary.recall == 1 / 3
    assert summary.false_approves == 1
    assert summary.findings_without_valid_prooflink_rate == 0.0
    assert summary.expected_violations == 3
    assert summary.evaluated_cases == 2


def test_always_blocking_system_is_visible_in_metrics() -> None:
    rows = [EvaluatedCase(
        case_id="clean", expected_rule_ids=frozenset(),
        predicted_rule_ids=frozenset({"R-GAS-01"}), verdict="block_and_escalate",
        critical=False, total_findings=1, findings_with_valid_prooflink=1,
    )]
    summary = summarize(rows)
    assert summary.false_blocks == 1
    assert summary.clean_cases == 1
    assert summary.clean_approval_rate == 0.0
    assert summary.precision == 0.0


def test_missing_ground_truth_is_an_error(tmp_path) -> None:
    import pytest
    from eval.run import evaluate

    with pytest.raises(ValueError, match="Ground truth not found"):
        evaluate(tmp_path / "absent.json")
