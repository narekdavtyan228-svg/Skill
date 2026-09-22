"""Cross-platform delivery gate for PermitGuard."""

from __future__ import annotations

import subprocess
import sys


STEPS = (
    (
        "Smoke",
        [
            sys.executable,
            "-m",
            "core.orchestrator",
            "--permit",
            "data/fixtures/permit_0001",
            "--print",
        ],
    ),
    ("Evaluation", [sys.executable, "-m", "eval.run"]),
    ("Tests", [sys.executable, "-m", "pytest", "-q"]),
    ("Browser UI QA", [sys.executable, "-m", "ui.visual_qa"]),
)


def main() -> int:
    for name, command in STEPS:
        print(f"\n== {name} ==", flush=True)
        result = subprocess.run(command, check=False)
        if result.returncode:
            print(f"\nFAILED: {name} (exit {result.returncode})", file=sys.stderr)
            return result.returncode
    print("\nAll delivery gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
