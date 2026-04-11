"""Help page — keyboard shortcuts, accessibility overview, and support links.

The Help tab keeps a single overview page and routes supporting resources to
browser-friendly URLs. This includes the accessibility statement, which opens
the repository-hosted WCAG notes for the current checkout/fork.
"""
import sys

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QPushButton, QSizePolicy, QStackedWidget, QMessageBox,
)

from src.config.help_links import (
    ACCESSIBILITY_STATEMENT_URL,
    SUPPORT_GUIDANCE_URL,
    USER_GUIDE_URL,
    resolve_help_link_target,
)
from .icons import get_pixmap, SVG_RESULTS, SVG_SETTINGS, SVG_CHECK_CIRCLE, SVG_ACTIVITY
from .styles import CATPPUCCIN_DARK, CATPPUCCIN_LIGHT
from .theme_manager import ThemeManager


class HelpTab(QWidget):
    """Redesigned Help tab — fills available space, no scroll, modern KBD key styling."""

    page_title_changed = pyqtSignal(str)

    def __init__(self, shortcut_modifier: str = "Ctrl"):
        super().__init__()
        self._shortcut_modifier = shortcut_modifier
        self.platform_name = self._detect_platform_name()

        try:
            tm = ThemeManager()
            self._colors = CATPPUCCIN_DARK if tm.get_theme() == "dark" else CATPPUCCIN_LIGHT
        except Exception:
            self._colors = CATPPUCCIN_DARK

        self._kbd_labels: list[QLabel] = []
        self._dividers: list[QFrame] = []
        self._panel_frames: list[QFrame] = []
        self._desc_labels: list[QLabel] = []
        self._plus_labels: list[QLabel] = []
        self._section_labels: list[QLabel] = []
        self._text_labels: list[tuple[QLabel, str]] = []

        self._setup_ui()

    def refresh_theme(self, colors: dict) -> None:
        """Apply new theme colours to every inline-styled widget in this tab."""
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
        section_style = self._section_title_style()
        for lbl in self._section_labels:
            lbl.setStyleSheet(section_style)
        text_color = colors.get("text", "#f9fafb")
        for lbl, fmt in self._text_labels:
            lbl.setStyleSheet(fmt.format(color=text_color))
        if hasattr(self, "_help_header_frame"):
            c = colors
            self._help_header_frame.setStyleSheet(
                f"QFrame#HelpHeader {{"
                f"  background-color: {c.get('surface', '#1f2937')};"
                f"  border: 1px solid {c.get('border', '#4b5563')};"
                f"  border-bottom: 2px solid {c.get('shadow', '#030712')};"
                f"  border-radius: 12px;"
                f"}}"
                f"QFrame#HelpHeader:hover {{"
                f"  background-color: {c.get('surface', '#1f2937')};"
                f"  border: 1px solid {c.get('border', '#4b5563')};"
                f"  border-bottom: 2px solid {c.get('shadow', '#030712')};"
                f"}}"
            )

    def _kbd_style(self) -> str:
        c = self._colors
        return (
            f"background-color: {c.get('surface2', '#374151')};"
            f"color: {c.get('text', '#f9fafb')};"
            f"border: 1px solid {c.get('border_strong', '#6b7280')};"
            f"border-bottom: 2px solid {c.get('shadow', '#030712')};"
            f"border-radius: 6px;"
            f"padding: 4px 11px;"
            f"font-family: 'SF Mono','Consolas','Courier New',monospace;"
            f"font-size: 12px;"
            f"font-weight: 700;"
            f"letter-spacing: 0;"
        )

    def _panel_style(self) -> str:
        c = self._colors
        bg = c.get("surface", "#1f2937")
        border = c.get("border", "#4b5563")
        shadow = c.get("shadow", "#030712")
        return (
            f"QFrame#HelpPanel {{"
            f"  background-color: {bg};"
            f"  border: 1px solid {border};"
            f"  border-bottom: 2px solid {shadow};"
            f"  border-radius: 12px;"
            f"}}"
            f"QFrame#HelpPanel:hover {{"
            f"  border: 1px solid {border};"
            f"  border-bottom: 2px solid {shadow};"
            f"}}"
        )

    def _divider_style(self) -> str:
        return f"border: none; border-top: 1px solid {self._colors.get('border', '#374151')};"

    def _desc_style(self) -> str:
        return (
            f"font-size: 13px;"
            f"color: {self._colors.get('text', '#f9fafb')};"
            f"background: transparent; border: none;"
        )

    def _plus_style(self) -> str:
        return (
            f"font-size: 12px; font-weight: 700;"
            f"color: {self._colors.get('text_muted', '#9ca3af')};"
            f"padding: 0 2px; background: transparent; border: none;"
        )

    def _set_text_label(self, lbl: QLabel, fmt: str) -> None:
        lbl.setStyleSheet(fmt.format(color=self._colors.get("text", "#f9fafb")))
        self._text_labels.append((lbl, fmt))

    def _section_title_style(self) -> str:
        section_color = "#ffffff" if self._colors.get("bg", "").lower() == CATPPUCCIN_DARK.get("bg", "").lower() else "#000000"
        return (
            "font-size: 13px; font-weight: 800; letter-spacing: 1px;"
            f"color: {section_color};"
        )

    @staticmethod
    def _detect_platform_name() -> str:
        if sys.platform == "darwin":
            return "macOS"
        if sys.platform.startswith("win"):
            return "Windows"
        if sys.platform.startswith("linux"):
            return "Linux"
        return "Unknown"

    def _setup_ui(self) -> None:
        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _outer.setSpacing(0)

        self._main_stack = QStackedWidget()
        self._main_stack.addWidget(self._build_help_center_page())
        _outer.addWidget(self._main_stack)

    def _build_help_center_page(self) -> QWidget:
        page = QWidget()
        _outer = QVBoxLayout(page)
        _outer.setContentsMargins(0, 0, 0, 0)
        _outer.setSpacing(0)

        _scr_content = QWidget()
        _scr_content.setMinimumWidth(620)
        _outer.addWidget(_scr_content)

        root = QVBoxLayout(_scr_content)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(14)
        body.addWidget(self._build_shortcuts_panel(), 5)
        body.addWidget(self._build_right_panel(), 3)

        root.addLayout(body, 1)
        return page

    def show_accessibility_page(self) -> None:
        """Open the repository-hosted accessibility statement in the browser."""
        self._open_help_link(ACCESSIBILITY_STATEMENT_URL, "Accessibility Statement")

    def show_help_overview(self) -> None:
        self._main_stack.setCurrentIndex(0)
        self.page_title_changed.emit("Help")

    def current_page_title(self) -> str:
        return "Help"

    def _open_help_link(self, target: str, label: str) -> bool:
        resolved = resolve_help_link_target(target)
        if resolved is None:
            QMessageBox.warning(
                self,
                "Link Not Available",
                f"Could not find the configured {label.lower()} target:\n{target}",
            )
            return False

        url = QUrl.fromLocalFile(str(resolved)) if not isinstance(resolved, str) else QUrl(resolved)
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(
                self,
                "Open Failed",
                f"Could not open the configured {label.lower()} target:\n{target}",
            )
            return False
        return True

    def _build_header(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("HelpHeader")
        c = self._colors
        frame.setStyleSheet(
            f"QFrame#HelpHeader {{"
            f"  background-color: {c.get('surface', '#1f2937')};"
            f"  border: 1px solid {c.get('border', '#4b5563')};"
            f"  border-bottom: 2px solid {c.get('shadow', '#030712')};"
            f"  border-radius: 12px;"
            f"}}"
            f"QFrame#HelpHeader:hover {{"
            f"  background-color: {c.get('surface', '#1f2937')};"
            f"  border: 1px solid {c.get('border', '#4b5563')};"
            f"  border-bottom: 2px solid {c.get('shadow', '#030712')};"
            f"}}"
        )
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

        self._help_header_frame = frame
        return frame

    def _build_shortcuts_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("HelpPanel")
        frame.setStyleSheet(self._panel_style())
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._panel_frames.append(frame)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(28, 20, 28, 20)
        lay.setSpacing(0)

        heading_row = QHBoxLayout()
        heading_row.setSpacing(9)
        h_icon = QLabel()
        h_icon.setPixmap(get_pixmap(SVG_SETTINGS, "#3b82f6", 15))
        h_icon.setFixedSize(17, 17)
        heading_row.addWidget(h_icon)
        heading_lbl = QLabel("Keyboard Shortcuts")
        self._set_text_label(heading_lbl, "font-size: 15px; font-weight: 800; color: {color};")
        heading_row.addWidget(heading_lbl)
        heading_row.addStretch()
        lay.addLayout(heading_row)
        lay.addSpacing(14)

        sections = self._shortcut_sections()
        for index, (category, items) in enumerate(sections):
            lay.addWidget(self._build_shortcut_section(category, items))
            if index < len(sections) - 1:
                lay.addSpacing(10)
        lay.addStretch(1)
        return frame

    def _build_shortcut_section(self, category: str, items: list[tuple[str, str]]) -> QWidget:
        widget = QWidget()
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        cat_row = QHBoxLayout()
        cat_row.setSpacing(10)
        cat_row.setContentsMargins(0, 2, 0, 8)
        cat_lbl = QLabel(category.upper())
        cat_lbl.setStyleSheet(self._section_title_style())
        self._section_labels.append(cat_lbl)
        cat_lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        cat_row.addWidget(cat_lbl)

        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(self._divider_style())
        self._dividers.append(div)
        cat_row.addWidget(div, 1)
        layout.addLayout(cat_row)

        for row_index, (keys, description) in enumerate(items):
            layout.addWidget(self._build_shortcut_row(keys, description))
            if row_index < len(items) - 1:
                layout.addSpacing(6)

        widget.setFixedHeight(widget.sizeHint().height())
        return widget

    def _build_shortcut_row(self, keys: str, description: str) -> QWidget:
        widget = QWidget()
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        widget.setFixedHeight(34)
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)

        badge_box = QHBoxLayout()
        badge_box.setSpacing(7)
        badge_box.setContentsMargins(0, 0, 0, 0)
        badge_box.addStretch(1)

        parts = [p.strip() for p in keys.split("+")]
        for i, part in enumerate(parts):
            kbd = QLabel(part)
            kbd.setAlignment(Qt.AlignmentFlag.AlignCenter)
            kbd.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            kbd.setFixedHeight(30)
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
        badge_wrapper.setFixedWidth(188)
        row.addWidget(badge_wrapper, 0, Qt.AlignmentFlag.AlignVCenter)

        desc = QLabel(description)
        desc.setStyleSheet(self._desc_style())
        self._desc_labels.append(desc)
        desc.setWordWrap(True)
        row.addWidget(desc, 1)

        return widget

    def _build_right_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("HelpPanel")
        frame.setStyleSheet(self._panel_style())
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._panel_frames.append(frame)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.setSpacing(0)

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
            "Full accessibility statement available in the repository",
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
        self.btn_view_accessibility_statement = stmt_btn
        stmt_btn.clicked.connect(self.show_accessibility_page)
        stmt_btn.setFixedHeight(36)
        lay.addWidget(stmt_btn)

        lay.addSpacing(18)

        support_div = QFrame()
        support_div.setFrameShape(QFrame.Shape.HLine)
        support_div.setStyleSheet(self._divider_style())
        self._dividers.append(support_div)
        lay.addWidget(support_div)

        lay.addSpacing(18)

        support_heading = QHBoxLayout()
        support_heading.setSpacing(9)
        s_icon = QLabel()
        s_icon.setPixmap(get_pixmap(SVG_RESULTS, "#3b82f6", 15))
        s_icon.setFixedSize(17, 17)
        support_heading.addWidget(s_icon)
        support_lbl = QLabel("Support and Guidance")
        self._set_text_label(support_lbl, "font-size: 13px; font-weight: 800; color: {color};")
        support_heading.addWidget(support_lbl)
        support_heading.addStretch()
        lay.addLayout(support_heading)

        lay.addSpacing(14)

        support_helper = QLabel(
            "Documentation to support users and guide them through the application."
        )
        support_helper.setProperty("class", "HelperText")
        support_helper.setWordWrap(True)
        self._desc_labels.append(support_helper)
        lay.addWidget(support_helper)

        lay.addSpacing(12)

        docs_btn = QPushButton("Open Support and Guidance →")
        docs_btn.setProperty("class", "SecondaryButton")
        docs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        docs_btn.setFixedHeight(36)
        docs_btn.clicked.connect(
            lambda: self._open_help_link(SUPPORT_GUIDANCE_URL, "Support and Guidance")
        )
        self.btn_support_guidance = docs_btn
        lay.addWidget(docs_btn)

        lay.addSpacing(8)

        guide_btn = QPushButton("Open User Guide  →")
        guide_btn.setProperty("class", "PrimaryButton")
        guide_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        guide_btn.setFixedHeight(36)
        guide_btn.clicked.connect(lambda: self._open_help_link(USER_GUIDE_URL, "User Guide"))
        self.btn_user_guide = guide_btn
        lay.addWidget(guide_btn)

        lay.addSpacing(18)

        mid_div = QFrame()
        mid_div.setFrameShape(QFrame.Shape.HLine)
        mid_div.setStyleSheet(self._divider_style())
        self._dividers.append(mid_div)
        lay.addWidget(mid_div)

        lay.addSpacing(18)

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

        about_rows = [
            ("Version", "1.0.0"),
            ("Platform", self.platform_name),
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

        return frame

    def _shortcut_sections(self):
        """Return the structured shortcut data used to populate the shortcuts panel."""
        mod = "Control" if self.platform_name == "macOS" else "Ctrl"
        return [
            ("General", [
                (f"{mod}+B", "Toggle sidebar collapse"),
                (f"{mod}+Q", "Quit the application"),
                (f"{mod}+R", "Refresh dashboard"),
            ]),
            ("Navigation", [
                (f"{mod}+1", "Open Configure"),
                (f"{mod}+2", "Open Harvest"),
                (f"{mod}+3", "Open Dashboard"),
                (f"{mod}+4", "Open Help"),
            ]),
            ("Harvest Controls", [
                (f"{mod}+H", "Start harvest"),
                ("Esc", "Stop harvest"),
                (f"{mod}+.", "Cancel harvest"),
            ]),
        ]
