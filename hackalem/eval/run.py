"""Run PermitGuard against synthetic ground truth and print acceptance metrics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.orchestrator import run
from core.prooflinks import finding_has_valid_prooflink
from eval.metrics import EvaluatedCase, summarize


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _case_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("cases"), list):
        return [item for item in payload["cases"] if isinstance(item, dict)]
    rows: list[dict[str, Any]] = []
    for case_id, value in payload.items():
        if isinstance(value, dict):
            rows.append({"case_id": case_id, **value})
    return rows


def _violations(row: dict[str, Any]) -> tuple[frozenset[str], bool]:
    raw = row.get("violations", row.get("expected_findings", row.get("rule_ids", [])))
    if not isinstance(raw, list):
        return frozenset(), bool(row.get("critical", False))
    rule_ids: set[str] = set()
    critical = bool(row.get("critical", False))
    for item in raw:
        if isinstance(item, str) and item.strip():
            rule_ids.add(item)
            critical = True
        elif isinstance(item, dict):
            rule_id = item.get("rule_id")
            if isinstance(rule_id, str) and rule_id.strip():
                rule_ids.add(rule_id)
            critical = critical or item.get("severity") in {"P1", "P2"}
    return frozenset(rule_ids), critical


def evaluate(ground_truth_path: Path | None = None) -> dict[str, float | int]:
    truth_path = ground_truth_path or PROJECT_ROOT / "data" / "ground_truth.json"
    if not truth_path.is_file():
        return summarize([]).as_dict()
    payload = json.loads(truth_path.read_text(encoding="utf-8"))
    evaluated: list[EvaluatedCase] = []
    for index, row in enumerate(_case_rows(payload), start=1):
        case_id = str(row.get("case_id") or row.get("permit_id") or row.get("id") or f"case-{index}")
        relative_path = row.get("permit_dir") or row.get("fixture") or case_id
        bundle = PROJECT_ROOT / "data" / "fixtures" / str(relative_path)
        result = run(bundle, run_id=f"eval-{case_id}")
        expected, critical = _violations(row)
        valid_count = sum(finding_has_valid_prooflink(item, bundle) for item in result.findings)
        evaluated.append(
            EvaluatedCase(
                case_id=case_id,
                expected_rule_ids=expected,
                predicted_rule_ids=frozenset(item.rule_id for item in result.findings),
                verdict=result.verdict,
                critical=critical,
                total_findings=len(result.findings),
                findings_with_valid_prooflink=valid_count,
            )
        )
    return summarize(evaluated).as_dict()


def main() -> int:
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

