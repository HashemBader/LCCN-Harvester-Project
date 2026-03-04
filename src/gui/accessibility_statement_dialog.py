"""
Module: accessibility_statement_dialog.py
Shows the accessibility statement from docs/WCAG_ACCESSIBILITY.md.
"""
from pathlib import Path

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextBrowser, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt

from gui.theme_manager import ThemeManager
from gui.styles_v2 import generate_stylesheet, CATPPUCCIN_DARK, CATPPUCCIN_LIGHT


class AccessibilityStatementDialog(QDialog):
    """Simple read-only dialog for the in-app accessibility statement."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Accessibility Statement")
        self.setMinimumSize(760, 560)
        self._setup_ui()
        self._apply_theme()
        
    def _apply_theme(self):
        theme_mgr = ThemeManager()
        mode = theme_mgr.get_theme()
        palette = CATPPUCCIN_DARK if mode == "dark" else CATPPUCCIN_LIGHT
        self.setStyleSheet(generate_stylesheet(palette))

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel("Accessibility Statement")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setObjectName("DialogHeader")
        layout.addWidget(header)

        sub = QLabel("This information helps users understand keyboard use and accessibility coverage.")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setProperty("class", "HelperText")
        layout.addWidget(sub)

        viewer = QTextBrowser()
        viewer.setReadOnly(True)
        viewer.setOpenExternalLinks(True)
        viewer.setProperty("class", "TerminalViewport")
        viewer.setMarkdown(self._load_statement())
        layout.addWidget(viewer, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setProperty("class", "PrimaryButton")
        close_btn.clicked.connect(self.accept)
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
