#!/usr/bin/env python3
"""Lightweight WCAG-related self-check for the PyQt GUI codebase.

This is an internal quality gate, not a formal certification.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import sys


PROJECT_ROOT = Path(__file__).resolve().parent


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def has_pattern(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.MULTILINE) is not None


def run_checks() -> list[CheckResult]:
    styles = read_text(PROJECT_ROOT / "src/gui/styles_v2.py")
    modern = read_text(PROJECT_ROOT / "src/gui/modern_window.py")
    config = read_text(PROJECT_ROOT / "src/gui/config_tab_v2.py")
    harvest = read_text(PROJECT_ROOT / "src/gui/harvest_tab_v2.py")
    shortcuts = read_text(PROJECT_ROOT / "src/gui/shortcuts_dialog.py")

    results: list[CheckResult] = []

    results.append(
        CheckResult(
            "Visible focus styling",
            has_pattern(styles, r"QPushButton:focus") and has_pattern(styles, r"QLineEdit:focus"),
            "Focus rules found for buttons and form controls.",
        )
    )

    results.append(
        CheckResult(
            "Accessible names/descriptions on core UI",
            "setAccessibleName(" in modern and "setAccessibleName(" in config and "setAccessibleName(" in harvest,
            "Accessible labels present across window/settings/harvest screens.",
        )
    )

    results.append(
        CheckResult(
            "Keyboard shortcut discoverability",
            "ShortcutsDialog" in modern and "search_input" in shortcuts,
            "Searchable shortcuts dialog wired into main modern window.",
        )
    )

    results.append(
        CheckResult(
            "OS-aware shortcut labels",
            "sys.platform == \"darwin\"" in modern and "sys.platform == \"darwin\"" in shortcuts,
            "macOS vs Windows/Linux modifier detection found.",
        )
    )

    results.append(
        CheckResult(
            "Standard text editing shortcuts documented",
            "Ctrl+A" in shortcuts and "Ctrl+C" in shortcuts and "Ctrl+V" in shortcuts,
            "Select/copy/paste documented in shortcuts help.",
        )
    )

    return results


def build_report(results: list[CheckResult]) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    passed = sum(1 for r in results if r.passed)
    total = len(results)

    lines = [
        "# WCAG Self-Check Report",
        "",
        f"- Run at: {timestamp}",
        f"- Result: {passed}/{total} checks passed",
        "- Scope: Static code-level accessibility checks for V2 GUI",
        "",
        "## Checks",
        "",
    ]

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        lines.append(f"- [{status}] {r.name} - {r.detail}")

    lines.extend(
        [
            "",
            "## Note",
            "",
            "This report is an internal self-assessment. It is not a formal WCAG certification.",
            "Formal conformance requires manual assistive-tech testing and third-party audit.",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run internal WCAG self-checks.")
    parser.add_argument(
        "--write",
        type=Path,
        default=None,
        help="Optional path to write a markdown report.",
    )
    args = parser.parse_args()

    results = run_checks()
    report = build_report(results)

    print(report)

    if args.write:
        out = args.write if args.write.is_absolute() else PROJECT_ROOT / args.write
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report + "\n", encoding="utf-8")
        print(f"Report written to: {out}")

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
