"""Accessibility statement helpers and legacy dialog view.

The shared ``load_accessibility_statement`` helper resolves the markdown file
used by both the Help page's embedded statement view and the legacy dialog
class in this module. If the statement file cannot be loaded, a short fallback
message is returned so the UI always has something meaningful to display.
"""
from pathlib import Path

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextBrowser, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt

from .theme_manager import ThemeManager
from .styles import generate_stylesheet, CATPPUCCIN_DARK, CATPPUCCIN_LIGHT


def load_accessibility_statement() -> str:
    """Read and return the accessibility statement Markdown text.

    The preferred source is ``docs/wcag.md``. The legacy packaged path
    ``docs/WCAG_ACCESSIBILITY.md`` is still supported so existing builds and
    packaging rules continue to work without changes.
    """
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


class AccessibilityStatementDialog(QDialog):
    """Modal dialog that renders the project's WCAG accessibility statement.

    The statement is loaded from ``docs/wcag.md`` (or the legacy path
    ``docs/WCAG_ACCESSIBILITY.md``) relative to the project root.  The dialog
    is read-only and external hyperlinks inside the document open in the
    default browser (``setOpenExternalLinks(True)``).
    """

    def __init__(self, parent=None):
        """Initialise the dialog, build the layout, and apply the current theme.

        Args:
            parent: Optional parent widget for modal positioning.
        """
        super().__init__(parent)
        self.setWindowTitle("Accessibility Statement")
        self.setMinimumSize(760, 560)
        self._setup_ui()
        self._apply_theme()

    def _apply_theme(self):
        """Apply the full application stylesheet matching the current theme."""
        theme_mgr = ThemeManager()
        mode = theme_mgr.get_theme()
        palette = CATPPUCCIN_DARK if mode == "dark" else CATPPUCCIN_LIGHT
        self.setStyleSheet(generate_stylesheet(palette))

    def _setup_ui(self):
        """Build the dialog layout: title label, subtitle, scrollable QTextBrowser, close button.

        The ``QTextBrowser`` renders the loaded Markdown content.
        ``setOpenExternalLinks(True)`` allows any hyperlinks inside the
        statement to open the system default browser without additional
        signal handling.
        """
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
        viewer.setOpenExternalLinks(True)   # allow links in the statement to open a browser
        # "TerminalViewport" class applies the monospace terminal-style QSS rule.
        viewer.setProperty("class", "TerminalViewport")
        viewer.setMarkdown(load_accessibility_statement())
        layout.addWidget(viewer, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setProperty("class", "PrimaryButton")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
