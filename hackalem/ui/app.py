"""Streamlit operations console for PermitGuard."""

from __future__ import annotations

import html
import sys
from pathlib import Path
from typing import Callable

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orchestrator import run  # noqa: E402
from core.schemas import PermitResult  # noqa: E402


REPLAY_DIR = Path(__file__).with_name("replay")

_CSS = """
<style>
:root {
  --pg-bg: #F5F6F7;
  --pg-surface: #FFFFFF;
  --pg-text: #20252B;
  --pg-muted: #5F6872;
  --pg-border: #D9DEE3;
  --pg-orange: #EA580C;
  --pg-red: #DC2626;
}
.stApp { background: var(--pg-bg); color: var(--pg-text); }
[data-testid="stAppViewContainer"] > .main .block-container {
  max-width: 1180px; padding-top: 1.25rem; padding-bottom: 2rem;
}
h1, h2, h3, p { letter-spacing: 0 !important; }
h1 { font-size: 1.75rem !important; margin: 0 !important; }
[data-testid="stCaptionContainer"] { color: var(--pg-muted); }
.pg-kicker { color: var(--pg-orange); font-size: .75rem; font-weight: 700; text-transform: uppercase; }
.pg-status {
  border: 1px solid var(--pg-border); border-left: 8px solid var(--pg-text);
  border-radius: 6px; background: var(--pg-surface); padding: 16px 18px; margin: 12px 0 16px;
}
.pg-status.block { border-color: #F4B4B4; border-left-color: var(--pg-red); background: #FFF7F7; }
.pg-status.condition { border-left-color: var(--pg-orange); background: #FFF9F4; }
.pg-status-title { font-size: 1.35rem; font-weight: 800; line-height: 1.2; }
.pg-status-meta { color: var(--pg-muted); margin-top: 5px; font-size: .9rem; }
.pg-unknown, .pg-hitl {
  border: 1px solid var(--pg-border); border-radius: 6px; background: #EEF1F3;
  padding: 14px 16px; margin: 12px 0;
}
.pg-hitl { background: #FFFFFF; border-left: 5px solid var(--pg-orange); }
.pg-proof { border-left: 3px solid #9AA3AC; padding: 4px 0 4px 12px; margin: 8px 0; }
.pg-proof-source { color: var(--pg-muted); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: .8rem; }
.pg-proof-quote { color: var(--pg-text); margin-top: 2px; }
div.stButton > button[kind="primary"] { background: var(--pg-orange); border-color: var(--pg-orange); min-height: 44px; }
div.stButton > button { border-radius: 6px; min-height: 44px; }
div[data-testid="stExpander"] { background: var(--pg-surface); border-radius: 6px; border-color: var(--pg-border); }
*:focus-visible { outline: 3px solid #9A3412 !important; outline-offset: 2px; }
@media (max-width: 640px) {
  [data-testid="stAppViewContainer"] > .main .block-container { padding: 1rem .75rem 1.5rem; }
  .pg-status-title { font-size: 1.1rem; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; animation: none !important; }
}
</style>
"""


def discover_bundles() -> dict[str, Path]:
    bundles = {"DEMO-001 / контрольный комплект": REPLAY_DIR}
    fixtures = PROJECT_ROOT / "data" / "fixtures"
    if fixtures.is_dir():
        for permit_pdf in sorted(fixtures.glob("*/permit_*.pdf")):
            bundles[f"{permit_pdf.parent.name} / комплект"] = permit_pdf.parent
    return bundles


def run_safely(
    bundle: Path,
    runner: Callable[[str | Path, str | None], PermitResult] = run,
) -> PermitResult:
    try:
        return runner(bundle, f"ui-{bundle.name}")
    except Exception as exc:  # UI boundary must never turn an error into approval.
        return PermitResult(
            run_id=f"ui-error-{bundle.name}",
            verdict="block_and_escalate",
            findings=[],
            unknowns=[f"Проверка не завершена: {type(exc).__name__}"],
            audit_log=["ui:controlled-error"],
            requires_human_review=True,
            required_human_decision="Уполномоченный руководитель должен проверить комплект вручную до начала работ.",
        )


def _status_copy(result: PermitResult) -> tuple[str, str, str]:
    if result.verdict == "block_and_escalate":
        return "block", "РАБОТЫ НЕ НАЧИНАТЬ", "Обнаружены барьеры или недостаточно подтверждений"
    if result.verdict == "approve_with_conditions":
        return "condition", "ТРЕБУЮТСЯ УСЛОВИЯ", "Рекомендация ожидает решения уполномоченного лица"
    return "", "БАРЬЕРЫ НЕ ОБНАРУЖЕНЫ", "Это рекомендация системы, а не разрешение начать работы"


def render_result(result: PermitResult) -> None:
    status_class, title, subtitle = _status_copy(result)
    st.markdown(
        f'<section class="pg-status {status_class}" role="status">'
        f'<div class="pg-status-title">{html.escape(title)}</div>'
        f'<div class="pg-status-meta">{html.escape(subtitle)} · {html.escape(result.run_id)}</div>'
        "</section>",
        unsafe_allow_html=True,
    )

    findings = sorted(result.findings, key=lambda item: ({"P1": 0, "P2": 1, "P3": 2}[item.severity], item.rule_id))
    if findings:
        st.subheader(f"Барьеры ({len(findings)})")
    for finding in findings:
        label = f"{finding.severity} · {finding.rule_id} · {finding.claim}"
        with st.expander(label, expanded=finding.severity == "P1"):
            st.markdown(f"**Классификация:** `{finding.classification}`")
            for proof in finding.prooflinks:
                st.markdown(
                    '<div class="pg-proof">'
                    f'<div class="pg-proof-source">{html.escape(proof.source_id)} · {html.escape(proof.location)}</div>'
                    f'<div class="pg-proof-quote">«{html.escape(proof.quote)}»</div>'
                    "</div>",
                    unsafe_allow_html=True,
                )
            st.markdown(f"**Требуется решение:** {finding.required_human_decision}")

    unresolved = list(dict.fromkeys(result.unknowns + [
        item for finding in result.findings for item in finding.validation.unknowns
    ]))
    if unresolved:
        items = "".join(f"<li>{html.escape(item)}</li>" for item in unresolved)
        st.markdown(
            f'<section class="pg-unknown"><strong>Не подтверждено</strong><ul>{items}</ul></section>',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<section class="pg-hitl"><strong>Решение принимает человек</strong><br>'
        f'{html.escape(result.required_human_decision)}</section>',
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="PermitGuard", page_icon=None, layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown('<div class="pg-kicker">Предсменный контроль</div>', unsafe_allow_html=True)
    st.title("PermitGuard")
    st.caption("Проверка наряда-допуска перед началом работ")

    bundles = discover_bundles()
    labels = list(bundles)
    controls, action, replay = st.columns([5, 2, 2], vertical_alignment="bottom")
    with controls:
        selected = st.selectbox("Комплект документов", labels)
    with action:
        check = st.button("Проверить", type="primary", use_container_width=True)
    with replay:
        demo = st.button("Демо-проверка", use_container_width=True)

    if check or demo:
        target = REPLAY_DIR if demo else bundles[selected]
        with st.spinner("Выполняется проверка"):
            st.session_state["permit_result"] = run_safely(target)
    result = st.session_state.get("permit_result")
    if isinstance(result, PermitResult):
        render_result(result)


if __name__ == "__main__":
    main()
