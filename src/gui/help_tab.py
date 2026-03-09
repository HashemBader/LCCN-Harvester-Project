"""
Module: help_tab.py
In-app Help page with shortcuts, accessibility guidance, and app info.
"""
from pathlib import Path
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame, QHBoxLayout,
    QGroupBox, QTextBrowser
)
from .icons import get_pixmap, SVG_HARVEST


class ShortcutItem(QFrame):
    """Single shortcut row shown in Help."""

    def __init__(self, keys: str, description: str, parent=None):
        super().__init__(parent)
        self.setProperty("class", "ShortcutItem")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        keys_label = QLabel(keys)
        keys_label.setObjectName("ShortcutKeys")
        keys_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(keys_label)

        desc_label = QLabel(description)
        desc_label.setObjectName("ShortcutDesc")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label, stretch=1)


class HelpTab(QWidget):
    """Professional Help tab aligned with app theme."""

    def __init__(self, shortcut_modifier: str = "Ctrl"):
        super().__init__()
        self._shortcut_modifier = shortcut_modifier
        self.platform = "mac" if sys.platform == "darwin" else "win_linux"
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setProperty("class", "TransparentScroll")
        root.addWidget(scroll)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(8, 8, 8, 8)
        body_layout.setSpacing(14)
        scroll.setWidget(body)

        # Header card
        intro = QFrame()
        intro.setProperty("class", "Card")
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(16, 16, 16, 16)
        intro_layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)

        logo = QLabel()
        logo.setPixmap(get_pixmap(SVG_HARVEST, "#3b82f6", 20))
        logo.setFixedSize(22, 22)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_row.addWidget(logo)

        title = QLabel("Help Center")
        title.setProperty("class", "CardTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        intro_layout.addLayout(title_row)

        subtitle = QLabel(
            "Shortcuts, accessibility guidance, and support details for using the LCCN Harvester."
        )
        subtitle.setProperty("class", "HelperText")
        subtitle.setWordWrap(True)
        intro_layout.addWidget(subtitle)

        version = QLabel("Version 1.0")
        version.setProperty("class", "CardHelper")
        intro_layout.addWidget(version)

        platform_name = "macOS" if self.platform == "mac" else "Windows/Linux"
        platform_label = QLabel(f"Auto-detected platform: {platform_name}")
        platform_label.setProperty("class", "CardHelper")
        intro_layout.addWidget(platform_label)

        body_layout.addWidget(intro)

        # Shortcuts card
        shortcuts_card = QFrame()
        shortcuts_card.setProperty("class", "Card")
        shortcuts_layout = QVBoxLayout(shortcuts_card)
        shortcuts_layout.setContentsMargins(16, 16, 16, 16)
        shortcuts_layout.setSpacing(10)

        shortcuts_title = QLabel("Keyboard Shortcuts")
        shortcuts_title.setProperty("class", "CardTitle")
        shortcuts_layout.addWidget(shortcuts_title)

        shortcuts_sub = QLabel("Use these commands to navigate and control harvest runs quickly.")
        shortcuts_sub.setProperty("class", "HelperText")
        shortcuts_sub.setWordWrap(True)
        shortcuts_layout.addWidget(shortcuts_sub)

        for category, items in self._shortcut_sections():
            section = QGroupBox(category)
            section_layout = QVBoxLayout(section)
            section_layout.setContentsMargins(10, 12, 10, 10)
            section_layout.setSpacing(6)
            for keys, description in items:
                section_layout.addWidget(ShortcutItem(keys, description))
            shortcuts_layout.addWidget(section)

        body_layout.addWidget(shortcuts_card)

        # Accessibility + More Info card
        access_card = QFrame()
        access_card.setProperty("class", "Card")
        access_layout = QVBoxLayout(access_card)
        access_layout.setContentsMargins(16, 16, 16, 16)
        access_layout.setSpacing(10)

        access_title = QLabel("Accessibility")
        access_title.setProperty("class", "CardTitle")
        access_layout.addWidget(access_title)

        access_sub = QLabel(
            "Keyboard navigation and accessibility support details are provided below."
        )
        access_sub.setProperty("class", "HelperText")
        access_sub.setWordWrap(True)
        access_layout.addWidget(access_sub)

        viewer = QTextBrowser()
        viewer.setReadOnly(True)
        viewer.setOpenExternalLinks(True)
        viewer.setProperty("class", "TerminalViewport")
        viewer.setMarkdown(self._load_accessibility_statement())
        viewer.setMinimumHeight(220)
        access_layout.addWidget(viewer)

        more_info = QLabel(
            "For more info, see docs/wcag.md (or docs/WCAG_ACCESSIBILITY.md), "
            "docs/release/user_guide.md, or contact the project maintainer."
        )
        more_info.setProperty("class", "CardHelper")
        more_info.setWordWrap(True)
        access_layout.addWidget(more_info)

        body_layout.addWidget(access_card)
        body_layout.addStretch()

    def _shortcut_sections(self):
        mod = "Control" if self.platform == "mac" else "Ctrl"
        return [
            ("General", [
                (f"{mod}+B", "Toggle sidebar collapse"),
                (f"{mod}+Q", "Quit the application"),
                (f"{mod}+R", "Refresh dashboard"),
            ]),
            ("Navigation", [
                (f"{mod}+1", "Open Dashboard"),
                (f"{mod}+2", "Open Configure"),
                (f"{mod}+3", "Open Harvest"),
                (f"{mod}+4", "Open AI Agent"),
                (f"{mod}+5", "Open Help"),
            ]),
            ("Harvest", [
                (f"{mod}+H", "Start harvest"),
                ("Esc", "Stop harvest"),
                (f"{mod}+.", "Cancel harvest"),
            ]),
        ]

    def _load_accessibility_statement(self) -> str:
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
