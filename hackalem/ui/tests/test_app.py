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


def test_operator_can_check_switch_bundles_and_replay() -> None:
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    assert not app.exception
    app.selectbox[0].select("permit_0001 / комплект").run()
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state["permit_result"].verdict == "approve"
    app.selectbox[0].select("permit_0045 / комплект").run()
    assert "permit_result" not in app.session_state
    app.button[1].click().run()
    assert not app.exception
    assert app.selectbox[0].value == "DEMO-001 / контрольный комплект"
    assert app.session_state["permit_result"].verdict == "block_and_escalate"
