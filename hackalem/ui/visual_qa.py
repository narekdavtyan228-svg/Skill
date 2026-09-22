"""Responsive browser gate for the PermitGuard Streamlit console."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import ConsoleMessage, sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "tmp" / "ui-qa"
DEFAULT_BASELINE = PROJECT_ROOT / "ui" / "tests" / "baselines"
VIEWPORTS = ((375, 812), (768, 900), (1024, 900), (1440, 1000))
MAX_CHANGED_PIXEL_RATIO = 0.02


def _browser_executable() -> str | None:
    configured = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    candidates = [
        configured,
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    return next((path for path in candidates if path and Path(path).is_file()), None)


def _wait_for_health(url: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    health = f"{url.rstrip('/')}/_stcore/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"Streamlit did not become ready: {health}")


def _compare_baselines(
    screenshots: list[Path], baseline_dir: Path, update: bool
) -> tuple[str, list[str]]:
    baseline_dir.mkdir(parents=True, exist_ok=True)
    if update:
        for screenshot in screenshots:
            shutil.copy2(screenshot, baseline_dir / screenshot.name)
        return "updated", []

    differences: list[str] = []
    for screenshot in screenshots:
        baseline = baseline_dir / screenshot.name
        if not baseline.is_file():
            differences.append(f"{screenshot.name}: baseline missing")
            continue
        with Image.open(screenshot).convert("RGB") as current_image:
            with Image.open(baseline).convert("RGB") as baseline_image:
                if current_image.size != baseline_image.size:
                    differences.append(
                        f"{screenshot.name}: size {current_image.size} != {baseline_image.size}"
                    )
                    continue
                histogram = ImageChops.difference(current_image, baseline_image).convert("L").histogram()
                changed = current_image.width * current_image.height - histogram[0]
                ratio = changed / (current_image.width * current_image.height)
                if ratio > MAX_CHANGED_PIXEL_RATIO:
                    differences.append(f"{screenshot.name}: {ratio:.2%} pixels changed")
    return ("passed" if not differences else "failed"), differences


def run_qa(
    url: str, output_dir: Path, baseline_dir: Path, update_baseline: bool
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    overflow: list[str] = []
    accessibility_errors: list[str] = []
    screenshot_paths: list[Path] = []
    with sync_playwright() as playwright:
        executable = _browser_executable()
        launch_options: dict[str, object] = {"headless": True}
        if executable:
            launch_options["executable_path"] = executable
        browser = playwright.chromium.launch(**launch_options)
        for width, height in VIEWPORTS:
            page = browser.new_page(viewport={"width": width, "height": height})

            def record_error(message: ConsoleMessage) -> None:
                if message.type == "error" and "favicon" not in message.text.casefold():
                    console_errors.append(f"{width}px: {message.text}")

            page.on("console", record_error)
            page.goto(url, wait_until="domcontentloaded")
            page.locator(".pg-brand-name").wait_for(state="visible", timeout=20_000)
            page.get_by_text("Комплект готов к проверке", exact=True).wait_for(state="visible")
            page.wait_for_timeout(300)
            if page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"):
                overflow.append(f"{width}px initial")
            initial = output_dir / f"initial-{width}.png"
            page.screenshot(path=initial, full_page=True)
            screenshot_paths.append(initial)

            page.get_by_role("button", name="Запустить демо").click()
            page.get_by_text("РАБОТЫ НЕ НАЧИНАТЬ", exact=True).wait_for(state="visible", timeout=20_000)
            page.locator(".pg-proof").first.wait_for(state="visible")
            page.evaluate(
                """() => {
                    window.scrollTo(0, 0);
                    const main = document.querySelector('[data-testid="stMain"]');
                    if (main) main.scrollTo(0, 0);
                }"""
            )
            page.wait_for_timeout(300)
            if page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"):
                overflow.append(f"{width}px result")
            result = output_dir / f"result-{width}.png"
            page.screenshot(path=result, full_page=True)
            screenshot_paths.append(result)

            if page.get_by_role(
                "heading", name="Проверка перед началом работ", exact=True
            ).count() != 1:
                accessibility_errors.append(f"{width}px: primary heading missing")
            if page.get_by_role(
                "combobox", name="Комплект документов", exact=True
            ).count() != 1:
                accessibility_errors.append(f"{width}px: document selector has no accessible label")
            for index, button in enumerate(page.get_by_role("button").all()):
                name = button.get_attribute("aria-label") or button.inner_text().strip()
                if not name:
                    accessibility_errors.append(f"{width}px: button {index + 1} has no name")

            page.locator("body").focus()
            focused = None
            for _ in range(8):
                page.keyboard.press("Tab")
                focused = page.evaluate("document.activeElement && document.activeElement.tagName")
                if focused in {"A", "BUTTON", "INPUT", "SELECT"}:
                    break
            if focused not in {"A", "BUTTON", "INPUT", "SELECT"}:
                accessibility_errors.append(f"{width}px: keyboard focus did not reach a control")
            page.close()
        browser.close()
    baseline_status, visual_differences = _compare_baselines(
        screenshot_paths, baseline_dir, update_baseline
    )
    return {
        "viewports": [width for width, _ in VIEWPORTS],
        "screenshots": [str(path.relative_to(PROJECT_ROOT)) for path in screenshot_paths],
        "console_errors": console_errors,
        "horizontal_overflow": overflow,
        "accessibility_errors": accessibility_errors,
        "visual_regression": baseline_status,
        "visual_differences": visual_differences,
        "passed": not console_errors
        and not overflow
        and not accessibility_errors
        and not visual_differences,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8510)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()
    url = f"http://127.0.0.1:{args.port}"
    process = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", "ui/app.py",
            "--server.address", "127.0.0.1", "--server.port", str(args.port),
            "--server.headless", "true", "--browser.gatherUsageStats", "false",
        ],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_health(url)
        report = run_qa(url, args.output, args.baseline, args.update_baseline)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
