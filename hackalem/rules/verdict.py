"""Fail-closed verdict aggregation."""

from __future__ import annotations

from collections.abc import Sequence

from core.schemas import Finding, Verdict


def derive_verdict(findings: Sequence[Finding], unknowns: Sequence[str]) -> Verdict:
    """Derive a recommendation; unknowns and P1/P2 barriers always block."""

    if any(not isinstance(item, str) or not item.strip() for item in unknowns):
        return "block_and_escalate"
    if unknowns:
        return "block_and_escalate"
    if any(finding.classification != "confirmed" for finding in findings):
        return "block_and_escalate"
    if any(finding.severity in {"P1", "P2"} for finding in findings):
        return "block_and_escalate"
    if findings:
        return "approve_with_conditions"
    return "approve"

