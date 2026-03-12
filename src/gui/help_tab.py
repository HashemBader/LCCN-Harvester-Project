"""
Module: help_tab.py
Redesigned Help page — fills the tab, no scroll, modern KBD key badges.
"""
import sys

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QPushButton, QSizePolicy, QScrollArea,
)

from .icons import get_pixmap, SVG_RESULTS, SVG_SETTINGS, SVG_CHECK_CIRCLE, SVG_ACTIVITY
from .styles_v2 import CATPPUCCIN_DARK, CATPPUCCIN_LIGHT
from .theme_manager import ThemeManager


class HelpTab(QWidget):
    """Redesigned Help tab — fills space, no scroll, modern KBD key styling."""

    open_accessibility_requested = pyqtSignal()

    def __init__(self, shortcut_modifier: str = "Ctrl"):
        super().__init__()
        self._shortcut_modifier = shortcut_modifier
        self.platform = "mac" if sys.platform == "darwin" else "win_linux"

        # Resolve current theme colours once at startup so KBD badges are correct
        try:
            tm = ThemeManager()
            self._colors = CATPPUCCIN_DARK if tm.get_theme() == "dark" else CATPPUCCIN_LIGHT
        except Exception:
            self._colors = CATPPUCCIN_DARK

        # Track theme-sensitive widgets for live refresh
        self._kbd_labels: list[QLabel] = []
        self._dividers: list[QFrame] = []
        self._panel_frames: list[QFrame] = []   # main panels — no hover border
        self._desc_labels: list[QLabel] = []              # shortcut descriptions + accessibility items
        self._plus_labels: list[QLabel] = []              # "+" separators between key badges
        self._text_labels: list[tuple[QLabel, str]] = []  # heading/value labels — (label, fmt with {color})

        self._setup_ui()

    # ──────────────────────────────────────────────────────────────────
    # Public API – called by ModernMainWindow on theme toggle
    # ──────────────────────────────────────────────────────────────────
    def refresh_theme(self, colors: dict) -> None:
        self._colors = colors
        kbd_style = self._kbd_style()
        for lbl in self._kbd_labels:
            lbl.setStyleSheet(kbd_style)
        div_style = f"border: none; border-top: 1px solid {colors.get('border', '#374151')};"
        for div in self._dividers:
            div.setStyleSheet(div_style)
        panel_style = self._panel_style()
        for frame in self._panel_frames:
            frame.setStyleSheet(panel_style)
        desc_style = self._desc_style()
        for lbl in self._desc_labels:
            lbl.setStyleSheet(desc_style)
        plus_style = self._plus_style()
        for lbl in self._plus_labels:
            lbl.setStyleSheet(plus_style)
        text_color = colors.get("text", "#f9fafb")
        for lbl, fmt in self._text_labels:
            lbl.setStyleSheet(fmt.format(color=text_color))

    # ──────────────────────────────────────────────────────────────────
    # Style helpers
    # ──────────────────────────────────────────────────────────────────
    def _kbd_style(self) -> str:
        c = self._colors
        return (
            f"background-color: {c.get('surface2', '#374151')};"
            f"color: {c.get('text', '#f9fafb')};"
            f"border: 1px solid {c.get('border_strong', '#6b7280')};"
            f"border-bottom: 2px solid {c.get('shadow', '#030712')};"
            f"border-radius: 5px;"
            f"padding: 3px 9px;"
            f"font-family: 'SF Mono','Consolas','Courier New',monospace;"
            f"font-size: 11px;"
            f"font-weight: 700;"
            f"letter-spacing: 0.3px;"
        )

    def _panel_style(self) -> str:
        """Inline stylesheet for the two main panels.
        Uses objectName selector so the Card class hover rule (blue border)
        is overridden — panels should never flash blue on mouse-over.
        """
        c = self._colors
        bg     = c.get("surface",       "#1f2937")
        border = c.get("border",        "#4b5563")
        shadow = c.get("shadow",        "#030712")
        return (
            f"QFrame#HelpPanel {{"
            f"  background-color: {bg};"
            f"  border: 1px solid {border};"
            f"  border-bottom: 2px solid {shadow};"
            f"  border-radius: 12px;"
            f"}}"
            # Keep border identical on hover so it never flashes blue
            f"QFrame#HelpPanel:hover {{"
            f"  border: 1px solid {border};"
            f"  border-bottom: 2px solid {shadow};"
            f"}}"
        )

    def _divider_style(self) -> str:
        return f"border: none; border-top: 1px solid {self._colors.get('border', '#374151')};"

    def _desc_style(self) -> str:
        """Body text for shortcut descriptions and accessibility items — full text colour."""
        return (
            f"font-size: 12px;"
            f"color: {self._colors.get('text', '#f9fafb')};"
            f"background: transparent; border: none;"
        )

    def _plus_style(self) -> str:
        """The '+' separator between key badges."""
        return (
            f"font-size: 11px; font-weight: 700;"
            f"color: {self._colors.get('text_muted', '#9ca3af')};"
            f"padding: 0 2px; background: transparent; border: none;"
        )

    def _set_text_label(self, lbl: QLabel, fmt: str) -> None:
        """Apply *fmt* (must contain ``{color}``) and register for theme refresh."""
        lbl.setStyleSheet(fmt.format(color=self._colors.get("text", "#f9fafb")))
        self._text_labels.append((lbl, fmt))

    def _section_title_style(self) -> str:
        return (
            "font-size: 12px; font-weight: 800; letter-spacing: 1.3px;"
            f"color: {self._colors.get('text_muted', '#9ca3af')};"
        )

    # ──────────────────────────────────────────────────────────────────
    # Root layout
    # ──────────────────────────────────────────────────────────────────
    def _setup_ui(self) -> None:
        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _outer.setSpacing(0)
        _scroll = QScrollArea()
        _scroll.setWidgetResizable(True)
        _scroll.setFrameShape(QFrame.Shape.NoFrame)
        _scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        _scr_content = QWidget()
        _scr_content.setMinimumWidth(620)
        _scroll.setWidget(_scr_content)
        _outer.addWidget(_scroll)

        root = QVBoxLayout(_scr_content)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(14)
        body.addWidget(self._build_shortcuts_panel(), 3)
        body.addWidget(self._build_right_panel(), 2)

        root.addLayout(body, 1)

    # ──────────────────────────────────────────────────────────────────
    # Header
    # ──────────────────────────────────────────────────────────────────
    def _build_header(self) -> QFrame:
        frame = QFrame()
        frame.setProperty("class", "Card")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(22, 13, 22, 13)
        lay.setSpacing(10)

        icon = QLabel()
        icon.setPixmap(get_pixmap(SVG_RESULTS, "#3b82f6", 18))
        icon.setFixedSize(22, 22)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon)

        title = QLabel("LCCN Harvester  ·  Help Center")
        self._set_text_label(
            title,
            "font-size: 15px; font-weight: 800; letter-spacing: 0.2px; color: {color};"
        )
        lay.addWidget(title)

        lay.addStretch()

        return frame

    # ──────────────────────────────────────────────────────────────────
    # Left panel – Keyboard shortcuts
    # ──────────────────────────────────────────────────────────────────
    def _build_shortcuts_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("HelpPanel")
        frame.setStyleSheet(self._panel_style())
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._panel_frames.append(frame)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.setSpacing(0)

        # Panel heading
        heading_row = QHBoxLayout()
        heading_row.setSpacing(9)
        h_icon = QLabel()
        h_icon.setPixmap(get_pixmap(SVG_SETTINGS, "#3b82f6", 15))
        h_icon.setFixedSize(17, 17)
        heading_row.addWidget(h_icon)
        heading_lbl = QLabel("Keyboard Shortcuts")
        self._set_text_label(heading_lbl, "font-size: 13px; font-weight: 800; color: {color};")
        heading_row.addWidget(heading_lbl)
        heading_row.addStretch()
        lay.addLayout(heading_row)
        lay.addSpacing(14)

        for category, items in self._shortcut_sections():
            # Section label + divider
            cat_row = QHBoxLayout()
            cat_row.setSpacing(10)
            cat_row.setContentsMargins(0, 6, 0, 6)
            cat_lbl = QLabel(category.upper())
            cat_lbl.setStyleSheet(self._section_title_style())
            cat_lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            cat_row.addWidget(cat_lbl)
            div = QFrame()
            div.setFrameShape(QFrame.Shape.HLine)
            div.setStyleSheet(self._divider_style())
            self._dividers.append(div)
            cat_row.addWidget(div, 1)
            lay.addLayout(cat_row)

            for keys, description in items:
                lay.addWidget(self._build_shortcut_row(keys, description))
                lay.addSpacing(5)

            lay.addSpacing(6)

        lay.addStretch()
        return frame

    def _build_shortcut_row(self, keys: str, description: str) -> QWidget:
        widget = QWidget()
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)

        # KBD badges — stretch at start right-aligns all badges so single keys
        # like "Esc" land at the same horizontal position as the second key in
        # two-part shortcuts (Control+B → [Control][+][B], Esc → ________[Esc]).
        badge_box = QHBoxLayout()
        badge_box.setSpacing(6)
        badge_box.setContentsMargins(0, 0, 0, 0)
        badge_box.addStretch(1)  # ← pushes badges to the right edge of wrapper

        parts = [p.strip() for p in keys.split("+")]
        for i, part in enumerate(parts):
            kbd = QLabel(part)
            kbd.setAlignment(Qt.AlignmentFlag.AlignCenter)
            kbd.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            kbd.setStyleSheet(self._kbd_style())
            self._kbd_labels.append(kbd)
            badge_box.addWidget(kbd)
            if i < len(parts) - 1:
                plus = QLabel("+")
                plus.setAlignment(Qt.AlignmentFlag.AlignCenter)
                plus.setStyleSheet(self._plus_style())
                self._plus_labels.append(plus)
                badge_box.addWidget(plus)

        badge_wrapper = QWidget()
        badge_wrapper.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        badge_wrapper.setLayout(badge_box)
        badge_wrapper.setFixedWidth(165)
        row.addWidget(badge_wrapper, 0, Qt.AlignmentFlag.AlignVCenter)

        desc = QLabel(description)
        desc.setStyleSheet(self._desc_style())
        self._desc_labels.append(desc)
        row.addWidget(desc, 1)

        return widget

    # ──────────────────────────────────────────────────────────────────
    # Right panel – Accessibility + About
    # ──────────────────────────────────────────────────────────────────
    def _build_right_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("HelpPanel")
        frame.setStyleSheet(self._panel_style())
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._panel_frames.append(frame)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.setSpacing(0)

        # ── Accessibility heading ──────────────────────────────────────
        acc_heading = QHBoxLayout()
        acc_heading.setSpacing(9)
        a_icon = QLabel()
        a_icon.setPixmap(get_pixmap(SVG_CHECK_CIRCLE, "#22c55e", 15))
        a_icon.setFixedSize(17, 17)
        acc_heading.addWidget(a_icon)
        acc_lbl = QLabel("Accessibility")
        self._set_text_label(acc_lbl, "font-size: 13px; font-weight: 800; color: {color};")
        acc_heading.addWidget(acc_lbl)
        acc_heading.addStretch()
        lay.addLayout(acc_heading)
        lay.addSpacing(14)

        features = [
            "Keyboard navigation across all major actions",
            "Readable contrast and clear status colours",
            "Live progress and actionable error feedback",
            "Consistent behaviour in light and dark mode",
            "Full accessibility statement available in-app",
        ]
        for text in features:
            feat_row = QHBoxLayout()
            feat_row.setSpacing(10)
            feat_row.setContentsMargins(0, 0, 0, 0)
            tick = QLabel("✓")
            tick.setStyleSheet("color: #22c55e; font-weight: 800; font-size: 13px;")
            tick.setFixedWidth(16)
            tick.setAlignment(Qt.AlignmentFlag.AlignTop)
            feat_row.addWidget(tick)
            feat_lbl = QLabel(text)
            feat_lbl.setStyleSheet(self._desc_style())
            feat_lbl.setWordWrap(True)
            self._desc_labels.append(feat_lbl)
            feat_row.addWidget(feat_lbl, 1)
            lay.addLayout(feat_row)
            lay.addSpacing(6)

        lay.addSpacing(10)

        stmt_btn = QPushButton("View Full Accessibility Statement  →")
        stmt_btn.setProperty("class", "PrimaryButton")
        stmt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        stmt_btn.clicked.connect(self.open_accessibility_requested.emit)
        stmt_btn.setFixedHeight(36)
        lay.addWidget(stmt_btn)

        lay.addSpacing(18)

        # Thin divider
        mid_div = QFrame()
        mid_div.setFrameShape(QFrame.Shape.HLine)
        mid_div.setStyleSheet(self._divider_style())
        self._dividers.append(mid_div)
        lay.addWidget(mid_div)

        lay.addSpacing(18)

        # ── About heading ──────────────────────────────────────────────
        about_heading = QHBoxLayout()
        about_heading.setSpacing(9)
        ab_icon = QLabel()
        ab_icon.setPixmap(get_pixmap(SVG_ACTIVITY, "#3b82f6", 15))
        ab_icon.setFixedSize(17, 17)
        about_heading.addWidget(ab_icon)
        about_lbl = QLabel("About")
        self._set_text_label(about_lbl, "font-size: 13px; font-weight: 800; color: {color};")
        about_heading.addWidget(about_lbl)
        about_heading.addStretch()
        lay.addLayout(about_heading)

        lay.addSpacing(14)

        platform_name = "macOS" if self.platform == "mac" else "Windows / Linux"
        about_rows = [
            ("Version",      "1.0.0"),
            ("Organisation", "UPEI Library"),
            ("Platform",     platform_name),
        ]
        for key, val in about_rows:
            info_row = QHBoxLayout()
            info_row.setSpacing(0)
            info_row.setContentsMargins(0, 0, 0, 0)
            key_lbl = QLabel(key)
            key_lbl.setProperty("class", "HelperText")
            key_lbl.setFixedWidth(100)
            val_lbl = QLabel(val)
            self._set_text_label(val_lbl, "font-weight: 600; font-size: 13px; color: {color};")
            info_row.addWidget(key_lbl)
            info_row.addWidget(val_lbl)
            info_row.addStretch()
            lay.addLayout(info_row)
            lay.addSpacing(7)

        lay.addStretch()
        return frame

    # ──────────────────────────────────────────────────────────────────
    # Data
    # ──────────────────────────────────────────────────────────────────
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
            ("Harvest Controls", [
                (f"{mod}+H", "Start harvest"),
                ("Esc",       "Stop harvest"),
                (f"{mod}+.", "Cancel harvest"),
            ]),
        ]
