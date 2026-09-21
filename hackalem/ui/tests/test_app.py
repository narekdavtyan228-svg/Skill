from pathlib import Path

from ui.app import REPLAY_DIR, discover_bundles, run_safely


def test_discover_bundles_includes_replay_and_fixtures() -> None:
    bundles = discover_bundles()

    assert bundles["DEMO-001 / контрольный комплект"] == REPLAY_DIR
    assert any(path.name == "permit_0001" for path in bundles.values())


def test_ui_boundary_fails_closed() -> None:
    def broken_runner(_: str | Path, __: str | None):
        raise RuntimeError("boom")

    result = run_safely(REPLAY_DIR, broken_runner)

    assert result.verdict == "block_and_escalate"
    assert result.unknowns == ["Проверка не завершена: RuntimeError"]
    assert result.requires_human_review is True
