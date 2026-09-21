"""Pure acceptance metrics for PermitGuard evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class EvaluatedCase:
    case_id: str
    expected_rule_ids: frozenset[str]
    predicted_rule_ids: frozenset[str]
    verdict: str
    critical: bool
    total_findings: int
    findings_with_valid_prooflink: int


@dataclass(frozen=True, slots=True)
class MetricSummary:
    recall: float
    false_approves: int
    findings_without_valid_prooflink_rate: float
    expected_violations: int
    evaluated_cases: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "recall": self.recall,
            "false_approves": self.false_approves,
            "findings_without_valid_prooflink_rate": self.findings_without_valid_prooflink_rate,
            "expected_violations": self.expected_violations,
            "evaluated_cases": self.evaluated_cases,
        }


def violation_recall(cases: Iterable[EvaluatedCase]) -> float:
    rows = list(cases)
    expected = sum(len(case.expected_rule_ids) for case in rows)
    if expected == 0:
        return 0.0
    true_positives = sum(
        len(case.expected_rule_ids & case.predicted_rule_ids) for case in rows
    )
    return true_positives / expected


def false_approve_count(cases: Iterable[EvaluatedCase]) -> int:
    return sum(case.critical and case.verdict == "approve" for case in cases)


def findings_without_valid_prooflink_rate(cases: Iterable[EvaluatedCase]) -> float:
    rows = list(cases)
    total = sum(case.total_findings for case in rows)
    if total == 0:
        return 0.0
    valid = sum(case.findings_with_valid_prooflink for case in rows)
    return (total - valid) / total


def summarize(cases: Iterable[EvaluatedCase]) -> MetricSummary:
    rows = list(cases)
    return MetricSummary(
        recall=violation_recall(rows),
        false_approves=false_approve_count(rows),
        findings_without_valid_prooflink_rate=findings_without_valid_prooflink_rate(rows),
        expected_violations=sum(len(case.expected_rule_ids) for case in rows),
        evaluated_cases=len(rows),
    )

