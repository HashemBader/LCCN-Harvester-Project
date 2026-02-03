"""
Module: shortcuts_dialog.py
Visual keyboard shortcuts reference dialog.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QWidget, QFrame, QPushButton
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class ShortcutItem(QFrame):
    """A single shortcut display item."""

    def __init__(self, keys, description, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background: white;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                padding: 8px;
                margin: 4px;
            }
            QFrame:hover {
                background: #f8f9fa;
                border: 1px solid #3498db;
            }
        """)

        layout = QHBoxLayout()

        # Keys display
        keys_label = QLabel(keys)
        keys_label.setStyleSheet("""
            QLabel {
                background: #2c3e50;
                color: white;
                font-family: Arial, Helvetica;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
                border: none;
                min-width: 120px;
            }
        """)
        keys_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(keys_label)

        # Description
        desc_label = QLabel(description)
        desc_label.setStyleSheet("""
            QLabel {
                color: #2c3e50;
                font-size: 13px;
                font-family: Arial, Helvetica;
                padding-left: 10px;
                border: none;
                background: transparent;
            }
        """)
        layout.addWidget(desc_label, stretch=1)

        self.setLayout(layout)


class ShortcutsDialog(QDialog):
    """Dialog showing all keyboard shortcuts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts Reference")
        self.setMinimumSize(600, 500)
        self._setup_ui()

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout()

        # Header
        header = QLabel("⌨️ Keyboard Shortcuts")
        header.setStyleSheet("""
            QLabel {
                color: #2c3e50;
                font-size: 24px;
                font-weight: bold;
                font-family: Arial, Helvetica;
                padding: 10px;
                background: transparent;
                border: none;
            }
        """)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        subtitle = QLabel("Quick reference for all available keyboard shortcuts")
        subtitle.setStyleSheet("""
            QLabel {
                color: #7f8c8d;
                font-size: 12px;
                font-family: Arial, Helvetica;
                padding-bottom: 10px;
                background: transparent;
                border: none;
            }
        """)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #f8f9fa; }")

        content_widget = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setSpacing(15)

        # Define shortcuts by category
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

        # Create sections
        for category, shortcuts in shortcuts_data:
            # Category header
            category_label = QLabel(category)
            category_label.setStyleSheet("""
                QLabel {
                    color: #3498db;
                    font-size: 16px;
                    font-weight: bold;
                    font-family: Arial, Helvetica;
                    padding: 8px;
                    background: transparent;
                    border: none;
                    border-bottom: 2px solid #3498db;
                    margin-top: 10px;
                }
            """)
            content_layout.addWidget(category_label)

            # Shortcuts in this category
            for keys, description in shortcuts:
                item = ShortcutItem(keys, description)
                content_layout.addWidget(item)

        content_layout.addStretch()
        content_widget.setLayout(content_layout)
        scroll.setWidget(content_widget)
        layout.addWidget(scroll)

        # Close button
        close_layout = QHBoxLayout()
        close_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                font-size: 13px;
                font-weight: bold;
                font-family: Arial, Helvetica;
                padding: 8px 24px;
                border: none;
                border-radius: 4px;
                min-width: 100px;
            }
            QPushButton:hover {
                background: #2980b9;
            }
            QPushButton:pressed {
                background: #21618c;
            }
        """)
        close_btn.clicked.connect(self.accept)
        close_layout.addWidget(close_btn)

        close_layout.addStretch()
        layout.addLayout(close_layout)

        self.setLayout(layout)
