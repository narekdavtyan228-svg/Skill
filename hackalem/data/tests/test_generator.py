from __future__ import annotations

import copy
import re
import shutil
from collections import Counter
from pathlib import Path

import pytest

from data.generator import (
    EXPECTED_DOCUMENTS,
    INJECTORS,
    RULE_IDS,
    build_case_specs,
    generate_dataset,
    validate_ground_truth,
)


@pytest.fixture
def workspace(request) -> Path:
    name = re.sub(r"[^a-z0-9]+", "-", request.node.name.casefold()).strip("-")
    path = Path(__file__).resolve().parents[1] / "tmp" / f"data-{name}"
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def test_specs_are_deterministic_and_have_expected_distribution() -> None:
    first = build_case_specs(17)
    assert first == build_case_specs(17)
    assert first != build_case_specs(18)
    assert len(first) == 60
    counts = Counter(spec.violation_rule_id for spec in first)
    assert counts[None] == 40
    assert counts == Counter(
        {
            None: 40,
            "R-GAS-01": 4,
            "R-SIG-01": 4,
            "R-ZONE-01": 3,
            "R-SIMOPS-01": 3,
            "R-EMP-01": 3,
            "R-LOTO-01": 3,
        }
    )


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_each_injector_sets_only_one_canonical_violation(rule_id: str) -> None:
    base = build_case_specs()[0]
    changed = INJECTORS[rule_id](base)
    assert base.violation_rule_id is None
    assert changed.violation_rule_id == rule_id
    assert changed.case_id == base.case_id
    assert changed.permit_id == base.permit_id


def test_generated_dataset_has_four_documents_and_valid_prooflinks(workspace) -> None:
    payload = generate_dataset(workspace, seed=17)
    cases = payload["cases"]
    assert len(cases) == 60
    for row in cases:
        case_dir = workspace / "fixtures" / row["permit_dir"]
        expected = {*EXPECTED_DOCUMENTS, f'{row["case_id"]}.pdf'}
        assert {path.name for path in case_dir.iterdir() if path.is_file()} == expected
    validate_ground_truth(payload, workspace / "fixtures")


def test_ground_truth_rejects_fabricated_quote(workspace) -> None:
    payload = generate_dataset(workspace, seed=17)
    damaged = copy.deepcopy(payload)
    trap = next(row for row in damaged["cases"] if row["violations"])
    trap["violations"][0]["prooflinks"][0]["quote"] = "fabricated evidence"
    with pytest.raises(ValueError, match="quote not found"):
        validate_ground_truth(damaged, workspace / "fixtures")
