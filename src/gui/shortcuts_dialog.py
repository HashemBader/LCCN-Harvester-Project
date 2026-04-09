"""Searchable keyboard shortcuts reference dialog.

``ShortcutsDialog`` is a modal dialog that presents all application keyboard
shortcuts grouped by category.  It includes a live-filter search box so the
user can quickly locate a specific shortcut by key sequence or action name.

Key design points:
- ``_render_shortcuts`` rebuilds the content area from scratch on each
  keystroke using ``deleteLater`` on old widgets rather than hiding them, so
  the layout height recalculates correctly.
- Shortcuts are defined in ``_get_shortcuts_data`` and automatically
  translated from ``Ctrl+`` to ``Cmd+`` notation for macOS users via
  ``_macify``.
- The dialog self-applies the full application stylesheet (``generate_stylesheet``)
  augmented with a ``#CategoryHeader`` rule so category headings are visually
  distinct.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QWidget, QFrame, QPushButton, QLineEdit
)
from PyQt6.QtCore import Qt
import sys

from .theme_manager import ThemeManager
from .styles import generate_stylesheet, CATPPUCCIN_DARK, CATPPUCCIN_LIGHT


class ShortcutItem(QFrame):
    """A single row in the shortcuts list showing a key sequence and its description.

    Uses ``objectName`` values (``"ShortcutKeys"``, ``"ShortcutDesc"``) so the
    application stylesheet can style the key badge and description label
    independently.
    """

    def __init__(self, keys, description, parent=None):
        """Create a shortcut row.

        Args:
            keys: Key sequence string (e.g. ``"Ctrl+H"`` or ``"Cmd+H"``).
            description: Human-readable description of what the shortcut does.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        # "ShortcutItem" class triggers a styled-panel rule in the QSS.
        self.setProperty("class", "ShortcutItem")

        layout = QHBoxLayout()

        # objectName "ShortcutKeys" lets the stylesheet style the key badge.
        keys_label = QLabel(keys)
        keys_label.setObjectName("ShortcutKeys")
        keys_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(keys_label)

        # objectName "ShortcutDesc" lets the stylesheet style the description.
        desc_label = QLabel(description)
        desc_label.setObjectName("ShortcutDesc")
        layout.addWidget(desc_label, stretch=1)

        self.setLayout(layout)


class ShortcutsDialog(QDialog):
    """Searchable modal dialog listing all application keyboard shortcuts.

    The dialog is self-styled: it applies the full application stylesheet from
    ``generate_stylesheet`` plus an additional ``QLabel#CategoryHeader`` rule
    for bold section headings.  Platform detection ensures macOS users see
    ``Cmd+`` notation throughout.
    """

    def __init__(self, parent=None):
        """Initialise the dialog and apply the current theme.

        Args:
            parent: Optional parent widget for modal positioning.
        """
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts Reference")
        self.setMinimumSize(640, 520)
        # Detect platform once so _get_shortcuts_data and _macify use it consistently.
        self.platform = "mac" if sys.platform == "darwin" else "win_linux"
        self._setup_ui()
        self._apply_theme()

    def _apply_theme(self):
        """Apply the current theme stylesheet including the CategoryHeader override.

        Concatenates the global application stylesheet with a dialog-specific
        ``QLabel#CategoryHeader`` rule that sets contrasting text colour for
        category headings (white on dark, black on light).
        """
        theme_mgr = ThemeManager()
        mode = theme_mgr.get_theme()
        palette = CATPPUCCIN_DARK if mode == "dark" else CATPPUCCIN_LIGHT
        # Category headers need high-contrast text; white on dark, black on light.
        category_color = "#ffffff" if mode == "dark" else "#000000"
        self.setStyleSheet(
            generate_stylesheet(palette)
            + f"""
            QLabel#CategoryHeader {{
                color: {category_color};
                font-size: 15px;
                font-weight: 800;
                letter-spacing: 1px;
                text-transform: uppercase;
                padding-top: 8px;
                padding-bottom: 4px;
            }}
            """
        )

    def _setup_ui(self):
        """Build the dialog layout: header, search box, scrollable shortcuts list, close button.

        The scrollable content area uses ``self.content_layout`` (a ``QVBoxLayout``)
        which is rebuilt from scratch by ``_render_shortcuts`` on each search
        keystroke.  The search input, header, and close button live outside the
        scroll area so they remain visible at all times.
        """
        layout = QVBoxLayout()

        header = QLabel("⌨️ Keyboard Shortcuts")
        header.setObjectName("DialogHeader")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        subtitle = QLabel("Quick reference for all available keyboard shortcuts")
        subtitle.setObjectName("DialogSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        platform_row = QHBoxLayout()
        platform_row.addStretch()
        platform_name = "macOS" if self.platform == "mac" else "Windows/Linux"
        platform_label = QLabel(f"Auto-detected platform: {platform_name}")
        platform_label.setStyleSheet("color: #a7a59b; font-size: 12px;")
        platform_row.addWidget(platform_label)
        platform_row.addStretch()
        layout.addLayout(platform_row)

        edit_tip = QLabel("Most used: Cmd/Ctrl+A select all, Cmd/Ctrl+C copy, Cmd/Ctrl+V paste.")
        edit_tip.setStyleSheet("QLabel { color: #c2d07f; font-size: 12px; padding-bottom: 8px; background: transparent; border: none; }")
        edit_tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(edit_tip)

        search_row = QHBoxLayout()
        search_label = QLabel("Search:")
        search_label.setStyleSheet("color: #a7a59b; font-size: 12px;")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type keys or action, e.g. harvest, Cmd+H, results")

        self.search_input.textChanged.connect(self._render_shortcuts)
        search_row.addWidget(search_label)
        search_row.addWidget(self.search_input, stretch=1)
        layout.addLayout(search_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setProperty("class", "TransparentScroll")

        content_widget = QWidget()
        self.content_layout = QVBoxLayout()
        self.content_layout.setSpacing(15)
        content_widget.setLayout(self.content_layout)
        scroll.setWidget(content_widget)
        layout.addWidget(scroll)

        close_layout = QHBoxLayout()
        close_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setProperty("class", "PrimaryButton")
        close_btn.clicked.connect(self.accept)
        close_layout.addWidget(close_btn)

        close_layout.addStretch()
        layout.addLayout(close_layout)

        self.setLayout(layout)
        self._render_shortcuts()

    def _render_shortcuts(self):
        """Rebuild the scrollable content area to reflect the current search query.

        Called on every keystroke in the search box.  All existing widgets are
        removed and scheduled for deletion via ``deleteLater`` so the layout
        height recalculates correctly; then matching categories and items are
        re-added from scratch.
        """
        # Remove all existing rows before rebuilding — this keeps the layout
        # height accurate and avoids stale widgets accumulating behind the scenes.
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        shortcuts_data = self._get_shortcuts_data()
        # Guard with hasattr because _render_shortcuts is called from _setup_ui
        # before self.search_input is assigned.
        query = self.search_input.text().strip().lower() if hasattr(self, "search_input") else ""
        shown = 0

        for category, shortcuts in shortcuts_data:
            matched = []
            for keys, description in shortcuts:
                # Build a haystack from keys, description, and category so the
                # user can search by action name or by category label.
                hay = f"{keys} {description} {category}".lower()
                if not query or query in hay:
                    matched.append((keys, description))

            if not matched:
                continue

            category_label = QLabel(category)
            category_label.setObjectName("CategoryHeader")
            self.content_layout.addWidget(category_label)
            shown += 1

            for keys, description in matched:
                item = ShortcutItem(keys, description)
                self.content_layout.addWidget(item)

        if shown == 0:
            no_results = QLabel("No shortcuts match your search.")
            no_results.setStyleSheet("QLabel { color: #a7a59b; font-size: 13px; padding: 10px; }")
            no_results.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.content_layout.addWidget(no_results)

        self.content_layout.addStretch()

    def _get_shortcuts_data(self):
        """Return all shortcuts grouped by category, with macOS key notation applied.

        Returns:
            A list of ``(category_name, [(keys_str, description), ...])`` tuples.
            On macOS all ``Ctrl+`` prefixes are replaced with ``Cmd+`` via
            ``_macify``.
        """
        shortcuts_data = [
            ("General", [
                ("Ctrl+A", "Select all text in the current input box"),
                ("Ctrl+C", "Copy selected text"),
                ("Ctrl+V", "Paste text"),
                ("Ctrl+/", "Show this shortcuts help"),
                ("Ctrl+Shift+A", "Open accessibility statement"),
                ("F1", "Show this shortcuts help"),
                ("Ctrl+B", "Toggle sidebar collapse"),
                ("Ctrl+R", "Refresh dashboard"),
            ]),
            ("Navigation", [
                ("Ctrl+1", "Configure tab (Targets + Settings)"),
                ("Ctrl+2", "Harvest tab"),
                ("Ctrl+3", "Dashboard tab"),
                ("Ctrl+4", "Help tab"),
                ("Ctrl+Shift+D", "Jump to Dashboard"),
                ("Ctrl+Shift+H", "Jump to Harvest"),
            ]),
            ("Harvest", [
                ("Ctrl+H", "Start harvest"),
                ("Esc", "Stop harvest"),
                ("Ctrl+.", "Stop harvest (alternative)"),
                ("Ctrl+O", "Browse input file"),
                ("Ctrl+Enter", "Start harvest from Harvest tab"),
            ]),
            ("Form Navigation", [
                ("Tab", "Next field"),
                ("Shift+Tab", "Previous field"),
                ("Enter", "Activate focused button"),
            ]),
        ]

        if self.platform == "mac":
            return [(cat, [(self._macify(keys), desc) for keys, desc in shortcuts])
                    for cat, shortcuts in shortcuts_data]

        return shortcuts_data

    def _macify(self, keys):
        """Replace ``Ctrl`` prefixes with ``Cmd`` for macOS key-sequence display.

        The ``Ctrl+Enter`` case must be handled first to avoid a double-replace
        when the generic ``Ctrl+`` rule runs.

        Args:
            keys: Key-sequence string as defined in the shortcuts data table.

        Returns:
            The same string with ``Ctrl`` replaced by ``Cmd`` throughout.
        """
        return keys.replace("Ctrl+Enter", "Cmd+Enter").replace("Ctrl+", "Cmd+").replace("Ctrl", "Cmd")
