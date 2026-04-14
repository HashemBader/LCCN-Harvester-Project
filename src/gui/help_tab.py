"""Help page — keyboard shortcuts, accessibility overview, and support links.

The Help tab keeps a single overview page and routes supporting resources to
browser-friendly URLs. This includes the accessibility statement, which opens
the repository-hosted WCAG notes for the current checkout/fork.
"""
import sys  # Platform detection (sys.platform)

from PyQt6.QtCore import Qt, QUrl, pyqtSignal  # Core Qt enums, URL type, and custom signals
from PyQt6.QtGui import QDesktopServices  # Cross-platform "open URL/file" helper
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QPushButton, QSizePolicy, QStackedWidget, QMessageBox,
)  # All Qt widget and layout classes used to construct the tab

from src.config.help_links import (
    ACCESSIBILITY_STATEMENT_URL,
    SUPPORT_GUIDANCE_URL,
    USER_GUIDE_URL,
    resolve_help_link_target,
)  # Configured help/resource URLs and the resolver that maps them to local files or web URLs
from .icons import get_pixmap, SVG_RESULTS, SVG_SETTINGS, SVG_CHECK_CIRCLE, SVG_ACTIVITY  # SVG icon renderer and icon constants
from .styles import CATPPUCCIN_DARK, CATPPUCCIN_LIGHT  # Theme colour-palette dicts for dark and light modes
from .theme_manager import ThemeManager  # Reads and persists the active theme preference


class HelpTab(QWidget):
    """Help and documentation tab shown in the main sidebar stack.

    Displays a keyboard-shortcut reference, an accessibility overview, and
    buttons that open support resources in the system browser or file viewer.
    The tab uses a QStackedWidget internally so additional sub-pages can be
    added later without restructuring the outer layout.

    Attributes:
        page_title_changed: Signal emitted with the new page title string
            whenever the visible stack page changes.
        platform_name: Human-readable OS name used in the About section and
            to select the correct modifier key label.
        btn_view_accessibility_statement: Button that opens the accessibility
            statement; exposed as a public attribute for testing.
        btn_support_guidance: Button that opens the support/guidance document.
        btn_user_guide: Button that opens the user guide.
        _shortcut_modifier: Modifier key string passed in at construction time
            (currently unused in display logic — platform_name drives the label).
        _colors: Active theme colour-palette dict; rebuilt on every
            refresh_theme() call.
        _kbd_labels: All keyboard-badge QLabels, kept for bulk style refresh.
        _dividers: All horizontal-rule QFrames, kept for bulk style refresh.
        _panel_frames: All card QFrames with object name "HelpPanel".
        _desc_labels: All body-text / helper-text QLabels.
        _plus_labels: All "+" separator labels between key badges.
        _section_labels: All shortcut-category heading QLabels.
        _text_labels: (label, format_string) pairs whose colour must be
            injected at refresh time via str.format(color=...).
    """

    page_title_changed = pyqtSignal(str)

    def __init__(self, shortcut_modifier: str = "Ctrl"):
        """Initialise the tab, resolve the active theme, and build the UI.

        Args:
            shortcut_modifier: Modifier key label (e.g. "Ctrl" or "Cmd") that
                was detected by the caller.  The tab also performs its own
                platform detection for the displayed shortcut strings.
        """
        super().__init__()
        self._shortcut_modifier = shortcut_modifier
        self.platform_name = self._detect_platform_name()

        try:
            tm = ThemeManager()
            self._colors = CATPPUCCIN_DARK if tm.get_theme() == "dark" else CATPPUCCIN_LIGHT
        except Exception:
            self._colors = CATPPUCCIN_DARK  # Fall back to dark palette if theme prefs are unreadable

        # Widget registries — every themed widget appends itself here so that
        # refresh_theme() can restyle the whole tab in a single pass.
        self._kbd_labels: list[QLabel] = []
        self._dividers: list[QFrame] = []
        self._panel_frames: list[QFrame] = []
        self._desc_labels: list[QLabel] = []
        self._plus_labels: list[QLabel] = []
        self._section_labels: list[QLabel] = []
        self._text_labels: list[tuple[QLabel, str]] = []  # (label, format_string) pairs

        self._setup_ui()

    def refresh_theme(self, colors: dict) -> None:
        """Apply new theme colours to every inline-styled widget in this tab.

        Iterates all widget registries populated during construction and
        reapplies computed stylesheets so the tab responds to live theme
        switching without a full rebuild.

        Args:
            colors: Theme colour-palette dict (e.g. CATPPUCCIN_DARK).
        """
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
            # fmt contains a "{color}" placeholder injected at render time
            lbl.setStyleSheet(fmt.format(color=text_color))
        if hasattr(self, "_help_header_frame"):
            c = colors
            # Rebuild the header card stylesheet separately because it uses a
            # named QSS selector (QFrame#HelpHeader) rather than a plain style.
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
        """Return the QSS stylesheet for keyboard-badge labels.

        Produces the raised-key appearance: slightly elevated background,
        a stronger bottom border that mimics a physical keycap shadow, and
        a monospace font at a reduced size so badges stay compact.

        Returns:
            A plain CSS string (not a QSS selector block) ready for
            QLabel.setStyleSheet().
        """
        c = self._colors
        return (
            f"background-color: {c.get('surface2', '#374151')};"
            f"color: {c.get('text', '#f9fafb')};"
            f"border: 1px solid {c.get('border_strong', '#6b7280')};"
            f"border-bottom: 2px solid {c.get('shadow', '#030712')};"  # Thicker bottom = keycap depth effect
            f"border-radius: 6px;"
            f"padding: 4px 11px;"
            f"font-family: 'SF Mono','Consolas','Courier New',monospace;"
            f"font-size: 12px;"
            f"font-weight: 700;"
            f"letter-spacing: 0;"
        )

    def _panel_style(self) -> str:
        """Return the QSS block for card-style panel frames (object name HelpPanel).

        The hover rule repeats the same border values intentionally to prevent
        Qt from inheriting a highlight colour from the application stylesheet.

        Returns:
            A QSS selector block string ready for QFrame.setStyleSheet().
        """
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
            f"  border-bottom: 2px solid {shadow};"  # Suppress Qt default hover highlight
            f"}}"
        )

    def _divider_style(self) -> str:
        """Return the QSS for horizontal-rule divider frames.

        Clears all borders first, then adds only the top border so the frame
        renders as a single hairline rule.

        Returns:
            A plain CSS string ready for QFrame.setStyleSheet().
        """
        return f"border: none; border-top: 1px solid {self._colors.get('border', '#374151')};"

    def _desc_style(self) -> str:
        """Return the QSS for body-text / description labels.

        Returns:
            A plain CSS string ready for QLabel.setStyleSheet().
        """
        return (
            f"font-size: 13px;"
            f"color: {self._colors.get('text', '#f9fafb')};"
            f"background: transparent; border: none;"
        )

    def _plus_style(self) -> str:
        """Return the QSS for the "+" separator labels between key badges.

        Uses muted text so the separator recedes visually behind the badges.

        Returns:
            A plain CSS string ready for QLabel.setStyleSheet().
        """
        return (
            f"font-size: 12px; font-weight: 700;"
            f"color: {self._colors.get('text_muted', '#9ca3af')};"
            f"padding: 0 2px; background: transparent; border: none;"
        )

    def _set_text_label(self, lbl: QLabel, fmt: str) -> None:
        """Apply a colour-parametrised stylesheet to a label and register it for theme refresh.

        The format string must contain a ``{color}`` placeholder that will be
        substituted with the current theme text colour now, and again on every
        subsequent refresh_theme() call.

        Args:
            lbl: The QLabel to style.
            fmt: CSS string with a ``{color}`` placeholder, e.g.
                ``"font-size: 13px; color: {color};"``.
        """
        lbl.setStyleSheet(fmt.format(color=self._colors.get("text", "#f9fafb")))
        self._text_labels.append((lbl, fmt))  # Register so refresh_theme() can re-inject the colour

    def _section_title_style(self) -> str:
        """Return the QSS for shortcut-category heading labels.

        Uses pure white on dark themes and pure black on light themes for
        maximum contrast against the panel background, overriding the softer
        theme text colour used elsewhere.

        Returns:
            A plain CSS string ready for QLabel.setStyleSheet().
        """
        # Compare bg values case-insensitively to detect dark vs light palette
        section_color = "#ffffff" if self._colors.get("bg", "").lower() == CATPPUCCIN_DARK.get("bg", "").lower() else "#000000"
        return (
            "font-size: 13px; font-weight: 800; letter-spacing: 1px;"
            f"color: {section_color};"
        )

    @staticmethod
    def _detect_platform_name() -> str:
        """Map sys.platform to a human-readable OS label.

        Used both in the About section and to choose the correct modifier key
        label for the keyboard-shortcut display (macOS uses "Control" in full).

        Returns:
            One of ``"macOS"``, ``"Windows"``, ``"Linux"``, or ``"Unknown"``.
        """
        if sys.platform == "darwin":
            return "macOS"
        if sys.platform.startswith("win"):
            return "Windows"
        if sys.platform.startswith("linux"):
            return "Linux"
        return "Unknown"

    def _setup_ui(self) -> None:
        """Create the root layout and populate the main page stack."""
        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _outer.setSpacing(0)

        self._main_stack = QStackedWidget()
        self._main_stack.addWidget(self._build_help_center_page())  # Index 0 — the only page currently
        _outer.addWidget(self._main_stack)

    def _build_help_center_page(self) -> QWidget:
        """Build the main help-center page widget and return it.

        The page consists of a header banner followed by a two-column body:
        the shortcuts panel on the left (stretch 5) and the accessibility /
        support / about panel on the right (stretch 3).

        Returns:
            A QWidget suitable for insertion into the main stack at index 0.
        """
        page = QWidget()
        _outer = QVBoxLayout(page)
        _outer.setContentsMargins(0, 0, 0, 0)
        _outer.setSpacing(0)

        _scr_content = QWidget()
        _scr_content.setMinimumWidth(620)  # Prevent the two-column layout from collapsing too narrow
        _outer.addWidget(_scr_content)

        root = QVBoxLayout(_scr_content)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(14)
        body.addWidget(self._build_shortcuts_panel(), 5)  # Left column — wider
        body.addWidget(self._build_right_panel(), 3)       # Right column — narrower

        root.addLayout(body, 1)  # Give the body all remaining vertical space
        return page

    def show_accessibility_page(self) -> None:
        """Open the repository-hosted accessibility statement in the browser."""
        self._open_help_link(ACCESSIBILITY_STATEMENT_URL, "Accessibility Statement")

    def show_help_overview(self) -> None:
        """Navigate back to the main help-center page (stack index 0)."""
        self._main_stack.setCurrentIndex(0)
        self.page_title_changed.emit("Help")

    def current_page_title(self) -> str:
        """Return the title string for whichever stack page is currently visible.

        Returns:
            Always ``"Help"`` — the tab currently has only one page.
        """
        return "Help"

    def _open_help_link(self, target: str, label: str) -> bool:
        """Resolve a configured help target and open it in the system viewer.

        Delegates resolution to ``resolve_help_link_target``, which may return
        a local ``Path`` object (for bundled files) or a plain URL string (for
        web resources).  A warning dialog is shown if the target cannot be
        resolved or if the OS refuses to open it.

        Args:
            target: The raw target string from the help-links config module
                (may be a URL or a relative file path).
            label: Human-readable name used in warning dialog messages
                (e.g. ``"Accessibility Statement"``).

        Returns:
            ``True`` if the resource was successfully handed off to the OS,
            ``False`` otherwise.
        """
        resolved = resolve_help_link_target(target)
        if resolved is None:
            QMessageBox.warning(
                self,
                "Link Not Available",
                f"Could not find the configured {label.lower()} target:\n{target}",
            )
            return False

        # Wrap local Path objects in a file:// URL; plain strings are already URLs
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
        """Build the banner frame displayed at the top of the help-center page.

        The frame is stored as ``self._help_header_frame`` so that
        refresh_theme() can rebuild its named-selector stylesheet separately
        from the generic panel frames.

        Returns:
            A styled QFrame containing an icon and the page title.
        """
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

        self._help_header_frame = frame  # Saved for targeted stylesheet rebuild in refresh_theme()
        return frame

    def _build_shortcuts_panel(self) -> QFrame:
        """Build the left-hand card containing all keyboard-shortcut sections.

        Iterates the data returned by _shortcut_sections() and adds a
        _build_shortcut_section() widget for each category, separated by
        a fixed 10 px gap (omitted after the last section).

        Returns:
            A styled, expanding QFrame registered in _panel_frames.
        """
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
                lay.addSpacing(10)  # Gap between sections, not after the last one
        lay.addStretch(1)  # Push sections toward the top; absorb surplus vertical space
        return frame

    def _build_shortcut_section(self, category: str, items: list[tuple[str, str]]) -> QWidget:
        """Build a labelled group of shortcut rows for one category.

        Each section has a category-name label on the left with a hairline
        divider extending to the right of it, followed by one shortcut row
        per entry in ``items``.

        Args:
            category: Section heading text (displayed uppercased).
            items: Sequence of ``(key_combo, description)`` tuples, where
                ``key_combo`` uses ``"+"`` as a separator between keys.

        Returns:
            A fixed-height transparent QWidget containing the section.
        """
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
        cat_lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)  # Shrink-wrap to text width
        cat_row.addWidget(cat_lbl)

        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(self._divider_style())
        self._dividers.append(div)
        cat_row.addWidget(div, 1)  # Stretch factor 1: fill remaining row width
        layout.addLayout(cat_row)

        for row_index, (keys, description) in enumerate(items):
            layout.addWidget(self._build_shortcut_row(keys, description))
            if row_index < len(items) - 1:
                layout.addSpacing(6)  # Gap between rows, not after the last one

        widget.setFixedHeight(widget.sizeHint().height())  # Lock height so parent stretch works correctly
        return widget

    def _build_shortcut_row(self, keys: str, description: str) -> QWidget:
        """Build a single shortcut row containing key badges and a description.

        The key string is split on ``"+"`` to produce individual badge labels;
        a styled ``"+"`` separator label is inserted between consecutive badges.
        All badges and separators are registered in the themed-widget lists so
        refresh_theme() can restyle them.

        The badge area is wrapped in a fixed-width (188 px) container so that
        description text aligns vertically across all rows regardless of how
        many keys appear in the combo.

        Args:
            keys: Key-combo string such as ``"Ctrl+B"`` or ``"Esc"``.
            description: Plain-text description of what the shortcut does.

        Returns:
            A fixed-height (34 px) transparent QWidget for insertion into a
            section layout.
        """
        widget = QWidget()
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        widget.setFixedHeight(34)
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)

        badge_box = QHBoxLayout()
        badge_box.setSpacing(7)
        badge_box.setContentsMargins(0, 0, 0, 0)
        badge_box.addStretch(1)  # Right-align badges within the fixed-width wrapper

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
                # Insert a styled "+" between each pair of key badges
                plus = QLabel("+")
                plus.setAlignment(Qt.AlignmentFlag.AlignCenter)
                plus.setStyleSheet(self._plus_style())
                self._plus_labels.append(plus)
                badge_box.addWidget(plus)

        badge_wrapper = QWidget()
        badge_wrapper.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        badge_wrapper.setLayout(badge_box)
        badge_wrapper.setFixedWidth(188)  # Fixed column width keeps descriptions left-aligned
        row.addWidget(badge_wrapper, 0, Qt.AlignmentFlag.AlignVCenter)

        desc = QLabel(description)
        desc.setStyleSheet(self._desc_style())
        self._desc_labels.append(desc)
        desc.setWordWrap(True)
        row.addWidget(desc, 1)

        return widget

    def _build_right_panel(self) -> QFrame:
        """Build the right-hand card containing Accessibility, Support, and About sections.

        The panel is divided into three visual sections separated by hairline
        dividers:

        1. **Accessibility** — a bulleted feature list and a button to open
           the full accessibility statement.
        2. **Support and Guidance** — a helper description and buttons to open
           the support document and the user guide.
        3. **About** — static key/value rows for version and detected platform.

        Returns:
            A styled, expanding QFrame registered in _panel_frames.
        """
        frame = QFrame()
        frame.setObjectName("HelpPanel")
        frame.setStyleSheet(self._panel_style())
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._panel_frames.append(frame)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.setSpacing(0)

        # --- Accessibility section ---
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
            tick.setAlignment(Qt.AlignmentFlag.AlignTop)  # Pin tick to the top for multi-line labels
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
        self.btn_view_accessibility_statement = stmt_btn  # Exposed for testing
        stmt_btn.clicked.connect(self.show_accessibility_page)
        stmt_btn.setFixedHeight(36)
        lay.addWidget(stmt_btn)

        lay.addSpacing(18)

        # Divider between Accessibility and Support sections
        support_div = QFrame()
        support_div.setFrameShape(QFrame.Shape.HLine)
        support_div.setStyleSheet(self._divider_style())
        self._dividers.append(support_div)
        lay.addWidget(support_div)

        lay.addSpacing(18)

        # --- Support and Guidance section ---
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
        self.btn_support_guidance = docs_btn  # Exposed for testing
        lay.addWidget(docs_btn)

        lay.addSpacing(8)

        guide_btn = QPushButton("Open User Guide  →")
        guide_btn.setProperty("class", "PrimaryButton")
        guide_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        guide_btn.setFixedHeight(36)
        guide_btn.clicked.connect(lambda: self._open_help_link(USER_GUIDE_URL, "User Guide"))
        self.btn_user_guide = guide_btn  # Exposed for testing
        lay.addWidget(guide_btn)

        lay.addSpacing(18)

        # Divider between Support and About sections
        mid_div = QFrame()
        mid_div.setFrameShape(QFrame.Shape.HLine)
        mid_div.setStyleSheet(self._divider_style())
        self._dividers.append(mid_div)
        lay.addWidget(mid_div)

        lay.addSpacing(18)

        # --- About section ---
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
            ("Platform", self.platform_name),  # Resolved at init time via _detect_platform_name()
        ]
        for key, val in about_rows:
            info_row = QHBoxLayout()
            info_row.setSpacing(0)
            info_row.setContentsMargins(0, 0, 0, 0)
            key_lbl = QLabel(key)
            key_lbl.setProperty("class", "HelperText")
            key_lbl.setFixedWidth(100)  # Fixed label column keeps values left-aligned
            val_lbl = QLabel(val)
            self._set_text_label(val_lbl, "font-weight: 600; font-size: 13px; color: {color};")
            info_row.addWidget(key_lbl)
            info_row.addWidget(val_lbl)
            info_row.addStretch()
            lay.addLayout(info_row)
            lay.addSpacing(7)

        return frame

    def _shortcut_sections(self):
        """Return the structured shortcut data used to populate the shortcuts panel.

        Each entry in the returned list is a ``(category, items)`` pair where
        ``items`` is a list of ``(key_combo, description)`` tuples.  The key
        combos use ``"+"`` as a separator so ``_build_shortcut_row`` can split
        them into individual badge labels.

        Returns:
            List of ``(str, list[tuple[str, str]])`` — one entry per section.
        """
        # macOS convention spells out "Control" in full; all other platforms use "Ctrl"
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
                ("Esc", "Stop harvest"),   # No modifier — Esc is used standalone
                (f"{mod}+.", "Cancel harvest"),
            ]),
        ]
