"""
Module: accessibility_statement_dialog.py
Shows the accessibility statement from docs/WCAG_ACCESSIBILITY.md.
"""
from pathlib import Path

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextBrowser, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt


class AccessibilityStatementDialog(QDialog):
    """Simple read-only dialog for the in-app accessibility statement."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Accessibility Statement")
        self.setMinimumSize(760, 560)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel("Accessibility Statement")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet(
            "QLabel { color: #c2d07f; font-size: 22px; font-weight: bold; "
            "padding: 8px; background: transparent; }"
        )
        layout.addWidget(header)

        sub = QLabel("This information helps users understand keyboard use and accessibility coverage.")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("QLabel { color: #a7a59b; font-size: 12px; background: transparent; }")
        layout.addWidget(sub)

        viewer = QTextBrowser()
        viewer.setReadOnly(True)
        viewer.setOpenExternalLinks(True)
        viewer.setStyleSheet(
            "QTextBrowser { background: #171716; color: #e8e6df; border: 1px solid #2d2e2b; "
            "border-radius: 8px; padding: 10px; }"
        )
        viewer.setMarkdown(self._load_statement())
        layout.addWidget(viewer, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet(
            "QPushButton { background: #c2d07f; color: #1a1a18; font-size: 13px; font-weight: bold; "
            "padding: 8px 24px; border: none; border-radius: 4px; min-width: 100px; }"
            "QPushButton:hover { background: #d2df8e; }"
            "QPushButton:pressed { background: #b7c66e; }"
        )
        btn_row.addWidget(close_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _load_statement(self) -> str:
        root = Path(__file__).resolve().parent.parent.parent
        statement_paths = [
            root / "docs" / "wcag.md",
            root / "docs" / "WCAG_ACCESSIBILITY.md",
        ]
        for statement_path in statement_paths:
            if not statement_path.exists():
                continue
            try:
                return statement_path.read_text(encoding="utf-8")
            except Exception:
                continue
        return (
            "# Accessibility Statement\n\n"
            "The accessibility statement file could not be loaded.\n\n"
            "Expected file: `docs/wcag.md` or `docs/WCAG_ACCESSIBILITY.md`.\n"
        )
