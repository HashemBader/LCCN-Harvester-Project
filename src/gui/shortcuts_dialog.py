"""
Module: shortcuts_dialog.py
Visual keyboard shortcuts reference dialog.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QWidget, QFrame, QPushButton
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
        platform_label = QLabel("Platform:")
        platform_label.setStyleSheet("color: #a7a59b; font-size: 12px;")
        platform_row.addWidget(platform_label)

        self.platform_buttons = {}
        for label, key in [("Windows/Linux", "win_linux"), ("macOS", "mac")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == self.platform)
            btn.clicked.connect(lambda checked, k=key: self._set_platform(k))
            btn.setStyleSheet(
                "QPushButton { background: #242521; color: #e8e6df; font-size: 11px; padding: 4px 10px; "
                "border: 1px solid #2d2e2b; border-radius: 12px; }"
                "QPushButton:checked { background: #c2d07f; color: #1a1a18; border: 1px solid #c2d07f; }"
            )
            self.platform_buttons[key] = btn
            platform_row.addWidget(btn)

        platform_row.addStretch()
        layout.addLayout(platform_row)

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

    def _set_platform(self, platform):
        self.platform = platform
        for key, btn in self.platform_buttons.items():
            btn.setChecked(key == platform)
        self._render_shortcuts()

    def _render_shortcuts(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        shortcuts_data = self._get_shortcuts_data()

        for category, shortcuts in shortcuts_data:
            category_label = QLabel(category)
            category_label.setStyleSheet(
                "QLabel { color: #c2d07f; font-size: 16px; font-weight: bold; padding: 8px; background: transparent; "
                "border: none; border-bottom: 2px solid #c2d07f; margin-top: 10px; }"
            )
            self.content_layout.addWidget(category_label)

            for keys, description in shortcuts:
                item = ShortcutItem(keys, description)
                self.content_layout.addWidget(item)

        self.content_layout.addStretch()

    def _get_shortcuts_data(self):
        shortcuts_data = [
            ("General", [
                ("Ctrl+Q", "Quit application"),
                ("F1", "Show documentation"),
                ("F5", "Refresh results"),
                ("Ctrl+/", "Show this shortcuts help"),
                ("Ctrl+A", "Toggle Advanced Mode"),
                ("Ctrl+R", "Refresh dashboard"),
            ]),
            ("Navigation", [
                ("Ctrl+1", "Dashboard tab"),
                ("Ctrl+2", "Input tab"),
                ("Ctrl+3", "Targets tab"),
                ("Ctrl+4", "Configuration tab"),
                ("Ctrl+5", "Harvest tab"),
                ("Ctrl+6", "Results tab"),
                ("Ctrl+Shift+D", "Jump to Dashboard"),
                ("Ctrl+Shift+H", "Jump to Harvest"),
                ("Ctrl+Shift+R", "Jump to Results"),
            ]),
            ("Harvest", [
                ("Ctrl+H", "Start harvest"),
                ("Esc", "Stop harvest"),
                ("Ctrl+.", "Stop harvest (alternative)"),
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
        return keys.replace("Ctrl+", "Cmd+").replace("Ctrl", "Cmd")
