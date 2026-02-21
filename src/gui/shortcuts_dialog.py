"""
Module: shortcuts_dialog.py
Visual keyboard shortcuts reference dialog.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QWidget, QFrame, QPushButton, QLineEdit
)
from PyQt6.QtCore import Qt
import sys


class ShortcutItem(QFrame):
    """A single shortcut display item."""

    def __init__(self, keys, description, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #1f201d; border: 1px solid #2d2e2b; border-radius: 6px; padding: 8px; margin: 4px; }"
            "QFrame:hover { background: #242521; border: 1px solid #c2d07f; }"
        )

        layout = QHBoxLayout()

        keys_label = QLabel(keys)
        keys_label.setStyleSheet(
            "QLabel { background: #242521; color: #c2d07f; font-size: 12px; font-weight: bold; "
            "padding: 6px 12px; border-radius: 4px; border: none; min-width: 120px; }"
        )
        keys_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(keys_label)

        desc_label = QLabel(description)
        desc_label.setStyleSheet(
            "QLabel { color: #e8e6df; font-size: 13px; padding-left: 10px; border: none; background: transparent; }"
        )
        layout.addWidget(desc_label, stretch=1)

        self.setLayout(layout)


class ShortcutsDialog(QDialog):
    """Dialog showing all keyboard shortcuts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts Reference")
        self.setMinimumSize(640, 520)
        self.platform = "mac" if sys.platform == "darwin" else "win_linux"
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()

        header = QLabel("⌨️ Keyboard Shortcuts")
        header.setStyleSheet(
            "QLabel { color: #c2d07f; font-size: 24px; font-weight: bold; padding: 10px; background: transparent; border: none; }"
        )
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        subtitle = QLabel("Quick reference for all available keyboard shortcuts")
        subtitle.setStyleSheet(
            "QLabel { color: #a7a59b; font-size: 12px; padding-bottom: 10px; background: transparent; border: none; }"
        )
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
        self.search_input.setStyleSheet(
            "QLineEdit { background: #242521; color: #e8e6df; font-size: 12px; "
            "border: 1px solid #2d2e2b; border-radius: 6px; padding: 6px 10px; }"
        )
        self.search_input.textChanged.connect(self._render_shortcuts)
        search_row.addWidget(search_label)
        search_row.addWidget(self.search_input, stretch=1)
        layout.addLayout(search_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #171716; }")

        content_widget = QWidget()
        self.content_layout = QVBoxLayout()
        self.content_layout.setSpacing(15)
        content_widget.setLayout(self.content_layout)
        scroll.setWidget(content_widget)
        layout.addWidget(scroll)

        close_layout = QHBoxLayout()
        close_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            "QPushButton { background: #c2d07f; color: #1a1a18; font-size: 13px; font-weight: bold; "
            "padding: 8px 24px; border: none; border-radius: 4px; min-width: 100px; }"
            "QPushButton:hover { background: #d2df8e; }"
            "QPushButton:pressed { background: #b7c66e; }"
        )
        close_btn.clicked.connect(self.accept)
        close_layout.addWidget(close_btn)

        close_layout.addStretch()
        layout.addLayout(close_layout)

        self.setLayout(layout)
        self._render_shortcuts()

    def _render_shortcuts(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        shortcuts_data = self._get_shortcuts_data()
        query = self.search_input.text().strip().lower() if hasattr(self, "search_input") else ""
        shown = 0

        for category, shortcuts in shortcuts_data:
            matched = []
            for keys, description in shortcuts:
                hay = f"{keys} {description} {category}".lower()
                if not query or query in hay:
                    matched.append((keys, description))

            if not matched:
                continue

            category_label = QLabel(category)
            category_label.setStyleSheet(
                "QLabel { color: #c2d07f; font-size: 16px; font-weight: bold; padding: 8px; background: transparent; "
                "border: none; border-bottom: 2px solid #c2d07f; margin-top: 10px; }"
            )
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
                ("Ctrl+1", "Dashboard tab"),
                ("Ctrl+2", "Input tab"),
                ("Ctrl+3", "Targets tab"),
                ("Ctrl+4", "Configuration tab"),
                ("Ctrl+5", "Harvest tab"),
                ("Ctrl+6", "Results tab"),
                ("Ctrl+7", "AI Agent tab"),
                ("Ctrl+Shift+D", "Jump to Dashboard"),
                ("Ctrl+Shift+H", "Jump to Harvest"),
                ("Ctrl+Shift+R", "Jump to Results"),
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
        return keys.replace("Ctrl+Enter", "Cmd+Enter").replace("Ctrl+", "Cmd+").replace("Ctrl", "Cmd")
