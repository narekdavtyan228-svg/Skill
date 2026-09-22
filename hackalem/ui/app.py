"""Streamlit operations console for PermitGuard."""

from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

import pymupdf
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orchestrator import run  # noqa: E402
from core.schemas import ExtractedPermit, PermitResult  # noqa: E402
from extract.extractor import extract_permit  # noqa: E402

REPLAY_DIR = Path(__file__).with_name("replay")

_CSS = """
<style>
:root {
  --pg-bg: #F3F4F6; --pg-surface: #FFFFFF; --pg-surface-muted: #F7F8FA;
  --pg-ink: #191C20; --pg-muted: #5C6570; --pg-border: #D7DCE2;
  --pg-border-strong: #B8C0C9; --pg-accent: #C2410C; --pg-accent-hover: #9A3412;
  --pg-danger: #B91C1C; --pg-danger-bg: #FEF2F2; --pg-success: #166534;
  --pg-success-bg: #F0FDF4; --pg-warning: #92400E; --pg-warning-bg: #FFFBEB;
  --pg-focus: #0F6CBD; --pg-radius: 6px;
}
html, body, [class*="css"] { font-family: "Segoe UI", Arial, sans-serif; color: var(--pg-ink); -webkit-font-smoothing: antialiased; }
.stApp { background: var(--pg-bg); }
[data-testid="stHeader"], [data-testid="stToolbar"] { visibility: hidden; height: 0; }
[data-testid="stAppViewContainer"] > .main .block-container { max-width: 1240px; padding: 0 24px 40px; }
h1, h2, h3, p { letter-spacing: 0 !important; }
.pg-brandbar { min-height: 72px; display: flex; align-items: center; justify-content: space-between; gap: 16px; border-bottom: 1px solid var(--pg-border); margin-bottom: 22px; }
.pg-brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
.pg-logo { width: 40px; height: 40px; display: grid; place-items: center; background: var(--pg-ink); color: #FFF; border-radius: 5px; font-size: .82rem; font-weight: 800; }
.pg-brand-name { font-size: 1.02rem; font-weight: 760; line-height: 1.15; }
.pg-brand-sub { color: var(--pg-muted); font-size: .78rem; margin-top: 3px; }
.pg-env { border: 1px solid var(--pg-border-strong); border-radius: 4px; background: var(--pg-surface); color: var(--pg-muted); padding: 5px 8px; font: 600 .72rem/1.2 ui-monospace, Consolas, monospace; white-space: nowrap; }
.pg-heading { margin: 0 0 18px; }
.pg-eyebrow { color: var(--pg-accent); font-size: .72rem; font-weight: 800; text-transform: uppercase; margin-bottom: 5px; }
.pg-heading h1 { margin: 0; font-size: 1.7rem; line-height: 1.18; font-weight: 760; text-wrap: balance; }
.pg-heading p { margin: 7px 0 0; color: var(--pg-muted); font-size: .92rem; line-height: 1.5; text-wrap: pretty; }
[data-testid="stSelectbox"] label, [data-testid="stNumberInput"] label { color: var(--pg-ink) !important; font-weight: 650 !important; }
div[data-baseweb="select"] > div, [data-testid="stNumberInput"] input { min-height: 44px; border-radius: var(--pg-radius) !important; border-color: var(--pg-border-strong) !important; background: var(--pg-surface) !important; }
div.stButton > button, div.stDownloadButton > button { min-height: 44px; border-radius: var(--pg-radius); font-weight: 700; border-color: var(--pg-border-strong); transition-property: background-color, border-color, color, box-shadow, transform; transition-duration: 150ms; transition-timing-function: ease-out; }
div.stButton > button:hover, div.stDownloadButton > button:hover { border-color: var(--pg-ink); color: var(--pg-ink); }
div.stButton > button:active, div.stDownloadButton > button:active { transform: scale(.985); }
div.stButton > button[kind="primary"] { background: var(--pg-accent); border-color: var(--pg-accent); color: #FFF; }
div.stButton > button[kind="primary"]:hover { background: var(--pg-accent-hover); border-color: var(--pg-accent-hover); color: #FFF; }
*:focus-visible { outline: 3px solid var(--pg-focus) !important; outline-offset: 2px; }
[data-testid="stTabs"] { margin-top: 20px; }
[data-baseweb="tab-list"] { gap: 24px; border-bottom: 1px solid var(--pg-border); }
[data-baseweb="tab"] { min-height: 46px; padding-left: 2px !important; padding-right: 2px !important; color: var(--pg-muted); font-weight: 650; }
[aria-selected="true"][data-baseweb="tab"] { color: var(--pg-ink); }
.pg-status { border: 1px solid var(--pg-border); border-left: 7px solid var(--pg-ink); border-radius: var(--pg-radius); background: var(--pg-surface); padding: 18px 20px; margin: 16px 0; }
.pg-status.block { border-color: #E7A7A7; border-left-color: var(--pg-danger); background: var(--pg-danger-bg); }
.pg-status.condition { border-color: #E9C584; border-left-color: var(--pg-warning); background: var(--pg-warning-bg); }
.pg-status.approve { border-color: #A7D7B0; border-left-color: var(--pg-success); background: var(--pg-success-bg); }
.pg-status-kicker { color: var(--pg-muted); font-size: .72rem; font-weight: 800; text-transform: uppercase; }
.pg-status-title { font-size: 1.38rem; font-weight: 820; line-height: 1.2; margin-top: 5px; text-wrap: balance; }
.pg-status-meta { color: var(--pg-muted); margin-top: 7px; font-size: .86rem; line-height: 1.45; }
.pg-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border: 1px solid var(--pg-border); border-radius: var(--pg-radius); background: var(--pg-surface); margin-bottom: 18px; }
.pg-metric { padding: 12px 14px; border-right: 1px solid var(--pg-border); min-width: 0; }
.pg-metric:last-child { border-right: 0; }
.pg-metric-value { font: 750 1.08rem/1.2 ui-monospace, Consolas, monospace; font-variant-numeric: tabular-nums; }
.pg-metric-label { color: var(--pg-muted); font-size: .72rem; margin-top: 4px; }
.pg-section-title { font-size: .98rem; font-weight: 760; margin: 22px 0 10px; }
.pg-finding { background: var(--pg-surface); border: 1px solid var(--pg-border); border-radius: var(--pg-radius); padding: 16px; margin: 0 0 10px; }
.pg-finding-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.pg-finding-code { color: var(--pg-danger); font: 750 .76rem/1.3 ui-monospace, Consolas, monospace; }
.pg-finding-claim { margin-top: 6px; font-size: .98rem; font-weight: 700; line-height: 1.42; text-wrap: pretty; }
.pg-classification { color: var(--pg-muted); border: 1px solid var(--pg-border-strong); border-radius: 4px; padding: 4px 7px; font-size: .7rem; font-weight: 700; white-space: nowrap; }
.pg-proof { background: var(--pg-surface-muted); border-left: 3px solid var(--pg-border-strong); padding: 10px 12px; margin-top: 12px; }
.pg-proof-source { color: var(--pg-muted); font: 650 .72rem/1.35 ui-monospace, Consolas, monospace; overflow-wrap: anywhere; }
.pg-proof-quote { margin-top: 5px; font-size: .86rem; line-height: 1.45; overflow-wrap: anywhere; }
.pg-required { margin-top: 12px; font-size: .84rem; line-height: 1.45; }
.pg-decision { border-top: 3px solid var(--pg-accent); background: var(--pg-surface); padding: 14px 16px; margin: 18px 0 6px; }
.pg-decision-title { font-size: .82rem; font-weight: 800; text-transform: uppercase; }
.pg-decision-text { color: var(--pg-muted); margin-top: 5px; font-size: .86rem; line-height: 1.5; }
.pg-passport { background: var(--pg-surface); border: 1px solid var(--pg-border); border-radius: var(--pg-radius); padding: 16px; margin-top: 16px; }
.pg-passport-title { font-size: .82rem; font-weight: 800; text-transform: uppercase; margin-bottom: 12px; }
.pg-passport-row { padding: 9px 0; border-top: 1px solid var(--pg-border); }
.pg-passport-row:first-of-type { border-top: 0; padding-top: 0; }
.pg-passport-label { color: var(--pg-muted); font-size: .7rem; }
.pg-passport-value { margin-top: 3px; font-size: .86rem; font-weight: 650; overflow-wrap: anywhere; }
.pg-empty { border: 1px dashed var(--pg-border-strong); background: var(--pg-surface-muted); border-radius: var(--pg-radius); padding: 24px; margin-top: 16px; }
.pg-empty-title { font-size: 1.02rem; font-weight: 750; }
.pg-empty-copy { color: var(--pg-muted); font-size: .86rem; line-height: 1.5; margin-top: 6px; }
.pg-checklist { display: grid; gap: 7px; margin-top: 16px; color: var(--pg-muted); font-size: .8rem; }
.pg-check { display: flex; align-items: center; gap: 8px; }
.pg-check-mark { width: 7px; height: 7px; background: var(--pg-success); border-radius: 50%; flex: 0 0 auto; }
.pg-unknown { border: 1px solid #E9C584; background: var(--pg-warning-bg); padding: 12px 14px; margin: 12px 0; font-size: .84rem; }
.pg-unknown li { margin-top: 5px; overflow-wrap: anywhere; }
.pg-document-meta { color: var(--pg-muted); font-size: .78rem; margin: 10px 0 14px; }
[data-testid="stImage"] img { outline: 1px solid rgba(0,0,0,.12); outline-offset: -1px; }
.pg-audit-row { display: grid; grid-template-columns: 34px 1fr; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--pg-border); }
.pg-audit-index { color: var(--pg-muted); font: 650 .72rem/1.5 ui-monospace, Consolas, monospace; }
.pg-audit-text { font: 500 .8rem/1.5 ui-monospace, Consolas, monospace; overflow-wrap: anywhere; }
@media (max-width: 768px) {
  [data-testid="stAppViewContainer"] > .main .block-container { padding: 0 14px 28px; }
  .pg-brandbar { min-height: 64px; margin-bottom: 16px; }
  .pg-brand-sub { display: none; }
  .pg-heading h1 { font-size: 1.42rem; }
  .pg-heading p { font-size: .86rem; }
  [data-baseweb="tab-list"] { gap: 16px; }
  .pg-status { padding: 16px; }
  .pg-status-title { font-size: 1.15rem; }
  .pg-metrics { grid-template-columns: 1fr; }
  .pg-metric { border-right: 0; border-bottom: 1px solid var(--pg-border); }
  .pg-metric:last-child { border-bottom: 0; }
  .pg-finding-head { display: block; }
  .pg-classification { display: inline-block; margin-top: 10px; }
}
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; animation: none !important; } }
</style>
"""


def discover_bundles() -> dict[str, Path]:
    bundles = {"DEMO-001 / контрольный комплект": REPLAY_DIR}
    fixtures = PROJECT_ROOT / "data" / "fixtures"
    if fixtures.is_dir():
        for permit_pdf in sorted(fixtures.glob("*/permit_*.pdf")):
            bundles[f"{permit_pdf.parent.name} / комплект"] = permit_pdf.parent
    return bundles


def run_safely(bundle: Path, runner: Callable[[str | Path, str | None], PermitResult] = run) -> PermitResult:
    try:
        return runner(bundle, f"ui-{bundle.name}")
    except Exception as exc:  # UI boundary must never turn an error into approval.
        return PermitResult(run_id=f"ui-error-{bundle.name}", verdict="block_and_escalate", findings=[], unknowns=[f"Проверка не завершена: {type(exc).__name__}"], audit_log=["ui:controlled-error"], requires_human_review=True, required_human_decision="Уполномоченный руководитель должен проверить комплект вручную до начала работ.")


def _status_copy(result: PermitResult) -> tuple[str, str, str, str]:
    if result.verdict == "block_and_escalate":
        return "block", "Блокирующая рекомендация", "РАБОТЫ НЕ НАЧИНАТЬ", "Обнаружены барьеры или недостаточно подтверждений"
    if result.verdict == "approve_with_conditions":
        return "condition", "Условная рекомендация", "ТРЕБУЮТСЯ УСЛОВИЯ", "До начала работ руководитель должен подтвердить условия"
    return "approve", "Предварительная рекомендация", "БАРЬЕРЫ НЕ ОБНАРУЖЕНЫ", "Окончательное решение остаётся за уполномоченным руководителем"


def _classification_label(value: str) -> str:
    return {"confirmed": "Подтверждено", "contested": "Противоречие", "unknown": "Неизвестно", "insufficient_evidence": "Недостаточно данных"}.get(value, value)


def _display_value(value: object) -> str:
    if value is None:
        return "Не подтверждено"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y · %H:%M")
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    return str(value)


def clear_result() -> None:
    st.session_state.pop("permit_result", None)


def select_demo(label: str) -> None:
    st.session_state["bundle_label"] = label
    clear_result()


def render_passport(bundle: Path) -> None:
    try:
        permit: ExtractedPermit = extract_permit(bundle)
        rows = [("Наряд", permit.permit_id.value), ("Работник", permit.employee_id.value), ("Оборудование", permit.asset_id.value), ("Зона", permit.zone_id.value), ("Начало работ", permit.work_start.value), ("Окончание", permit.work_end.value)]
    except (OSError, ValueError, TypeError):
        rows = [("Комплект", bundle.name), ("Статус", "Не удалось извлечь паспорт")]
    body = "".join('<div class="pg-passport-row">' f'<div class="pg-passport-label">{html.escape(label)}</div>' f'<div class="pg-passport-value">{html.escape(_display_value(value))}</div></div>' for label, value in rows)
    st.markdown('<aside class="pg-passport"><div class="pg-passport-title">Паспорт наряда</div>' f"{body}</aside>", unsafe_allow_html=True)


def render_documents(bundle: Path) -> None:
    documents = sorted(path for path in bundle.iterdir() if path.is_file() and path.suffix.lower() in {".pdf", ".json", ".csv"} and path.resolve().is_relative_to(bundle.resolve()))
    if not documents:
        st.warning("Документы отсутствуют")
        return
    st.markdown(f'<div class="pg-document-meta">В комплекте документов: {len(documents)} · источник: {html.escape(bundle.name)}</div>', unsafe_allow_html=True)
    selected = st.selectbox("Исходный документ", documents, format_func=lambda path: path.name, key=f"document_{bundle.name}")
    try:
        if selected.suffix.lower() == ".pdf":
            with pymupdf.open(selected) as document:
                page = st.number_input("Страница", min_value=1, max_value=max(1, document.page_count), value=1, key=f"page_{bundle.name}_{selected.name}")
                bitmap = document[int(page) - 1].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5))
                st.image(bitmap.tobytes("png"), width="stretch")
        else:
            st.code(selected.read_text(encoding="utf-8-sig"), language="json" if selected.suffix.lower() == ".json" else None, line_numbers=True)
    except (OSError, ValueError, RuntimeError, IndexError) as exc:
        st.error(f"Не удалось открыть документ: {type(exc).__name__}")


def render_result(result: PermitResult) -> None:
    status_class, kicker, title, subtitle = _status_copy(result)
    st.markdown(f'<section class="pg-status {status_class}" role="status"><div class="pg-status-kicker">{html.escape(kicker)}</div><div class="pg-status-title">{html.escape(title)}</div><div class="pg-status-meta">{html.escape(subtitle)} · {html.escape(result.run_id)}</div></section>', unsafe_allow_html=True)
    confirmed = sum(item.classification == "confirmed" for item in result.findings)
    st.markdown('<div class="pg-metrics">' f'<div class="pg-metric"><div class="pg-metric-value">{len(result.findings):02d}</div><div class="pg-metric-label">Барьеры</div></div>' f'<div class="pg-metric"><div class="pg-metric-value">{confirmed:02d}</div><div class="pg-metric-label">Подтверждены документами</div></div>' f'<div class="pg-metric"><div class="pg-metric-value">{len(result.unknowns):02d}</div><div class="pg-metric-label">Не подтверждено</div></div></div>', unsafe_allow_html=True)
    findings = sorted(result.findings, key=lambda item: ({"P1": 0, "P2": 1, "P3": 2}[item.severity], item.rule_id))
    if findings:
        st.markdown(f'<div class="pg-section-title">Выявленные барьеры · {len(findings)}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<section class="pg-empty"><div class="pg-empty-title">Проверка завершена без найденных барьеров</div><div class="pg-empty-copy">Результат остаётся рекомендацией и требует решения уполномоченного руководителя.</div></section>', unsafe_allow_html=True)
    for finding in findings:
        proofs = "".join('<div class="pg-proof">' f'<div class="pg-proof-source">{html.escape(proof.source_id)} · {html.escape(proof.location)}</div>' f'<div class="pg-proof-quote">«{html.escape(proof.quote)}»</div></div>' for proof in finding.prooflinks)
        st.markdown('<article class="pg-finding"><div class="pg-finding-head"><div>' f'<div class="pg-finding-code">{html.escape(finding.severity)} · {html.escape(finding.rule_id)}</div>' f'<div class="pg-finding-claim">{html.escape(finding.claim)}</div></div>' f'<div class="pg-classification">{html.escape(_classification_label(finding.classification))}</div></div>{proofs}' f'<div class="pg-required"><strong>Требуется:</strong> {html.escape(finding.required_human_decision)}</div></article>', unsafe_allow_html=True)
    unresolved = list(dict.fromkeys(result.unknowns + [item for finding in result.findings for item in finding.validation.unknowns]))
    if unresolved:
        items = "".join(f"<li>{html.escape(item)}</li>" for item in unresolved)
        st.markdown(f'<section class="pg-unknown"><strong>Требует дополнительной проверки</strong><ul>{items}</ul></section>', unsafe_allow_html=True)
    st.markdown('<section class="pg-decision"><div class="pg-decision-title">Решение принимает человек</div>' f'<div class="pg-decision-text">{html.escape(result.required_human_decision)}</div></section>', unsafe_allow_html=True)


def render_empty_state() -> None:
    st.markdown('<section class="pg-empty"><div class="pg-empty-title">Комплект готов к проверке</div><div class="pg-empty-copy">Запустите проверку. Система извлечёт поля, сверит четыре реестра и применит восемь правил допуска.</div><div class="pg-checklist"><div class="pg-check"><span class="pg-check-mark"></span>Документы остаются доступными для ручной сверки</div><div class="pg-check"><span class="pg-check-mark"></span>Каждый барьер содержит точную ссылку на источник</div><div class="pg-check"><span class="pg-check-mark"></span>Окончательное решение принимает руководитель</div></div></section>', unsafe_allow_html=True)


def render_audit(result: PermitResult | None) -> None:
    if result is None:
        st.caption("Журнал появится после запуска проверки")
        return
    for index, entry in enumerate(result.audit_log, start=1):
        st.markdown('<div class="pg-audit-row">' f'<div class="pg-audit-index">{index:02d}</div>' f'<div class="pg-audit-text">{html.escape(entry)}</div></div>', unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(page_title="PermitGuard · Предсменный контроль", page_icon=None, layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown('<div class="pg-brandbar"><div class="pg-brand"><div class="pg-logo">PG</div><div><div class="pg-brand-name">PermitGuard</div><div class="pg-brand-sub">Контур предсменного контроля</div></div></div><div class="pg-env">DEMO · SYNTHETIC</div></div><section class="pg-heading"><div class="pg-eyebrow">Наряд-допуск</div><h1>Проверка перед началом работ</h1><p>Выберите комплект. Система покажет барьеры, доказательства и действие для уполномоченного руководителя.</p></section>', unsafe_allow_html=True)
    bundles = discover_bundles()
    labels = list(bundles)
    controls, action, replay = st.columns([5, 2, 2], vertical_alignment="bottom")
    with controls:
        selected = st.selectbox("Комплект документов", labels, key="bundle_label", on_change=clear_result)
    with action:
        check = st.button("Проверить комплект", type="primary", width="stretch", icon=":material/fact_check:")
    with replay:
        demo = st.button("Запустить демо", width="stretch", icon=":material/replay:", on_click=select_demo, args=(labels[0],))
    if check or demo:
        target = REPLAY_DIR if demo else bundles[selected]
        with st.spinner("Проверяем документы и реестры"):
            st.session_state["permit_result"] = run_safely(target)
    result = st.session_state.get("permit_result")
    result = result if isinstance(result, PermitResult) else None
    summary, documents, audit = st.tabs(["Заключение", "Документы", "Журнал проверки"])
    with summary:
        decision, passport = st.columns([1.65, 0.8], gap="large", vertical_alignment="top")
        with decision:
            if result is not None:
                render_result(result)
            else:
                render_empty_state()
            if result is not None:
                st.download_button("Скачать заключение JSON", json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2), file_name=f"{result.run_id}.json", mime="application/json", icon=":material/download:")
        with passport:
            render_passport(bundles[selected])
    with documents:
        render_documents(bundles[selected])
    with audit:
        render_audit(result)


if __name__ == "__main__":
    main()
