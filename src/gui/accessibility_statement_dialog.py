"""Read-only dialog that displays the application's WCAG accessibility statement.

``AccessibilityStatementDialog`` loads a Markdown file from the project's
``docs/`` directory (``wcag.md`` or ``WCAG_ACCESSIBILITY.md``) and renders it
inside a ``QTextBrowser``.  If neither file can be found or read, a brief
fallback message is shown instead so the dialog always opens successfully.

The dialog is opened from ``HelpTab`` via a signal so the help page does not
hold a direct reference to it.
"""
from pathlib import Path

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextBrowser, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt

from .theme_manager import ThemeManager
from .styles import generate_stylesheet, CATPPUCCIN_DARK, CATPPUCCIN_LIGHT


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
        """Read and return the accessibility statement Markdown text.

        Tries two candidate file paths in priority order.  If both fail (file
        missing or unreadable), returns a short fallback string so the dialog
        always has content to display.

        Returns:
            Markdown text of the accessibility statement, or a fallback message.
        """
        # Resolve the project root by walking three levels up from this source file.
        root = Path(__file__).resolve().parent.parent.parent
        statement_paths = [
            root / "docs" / "wcag.md",              # preferred path
            root / "docs" / "WCAG_ACCESSIBILITY.md", # legacy path
        ]
        for statement_path in statement_paths:
            if not statement_path.exists():
                continue
            try:
                return statement_path.read_text(encoding="utf-8")
            except Exception:
                continue
        # Neither file could be read — return a brief inline fallback.
        return (
            "# Accessibility Statement\n\n"
            "The accessibility statement file could not be loaded.\n\n"
            "Expected file: `docs/wcag.md` or `docs/WCAG_ACCESSIBILITY.md`.\n"
        )
