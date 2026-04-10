"""Main application window for the LCCN Harvester desktop application.

This module defines ``ModernMainWindow``, the top-level ``QMainWindow`` that
assembles the sidebar navigation, stacked page area, and all cross-tab signal
wiring.  It is the single entry point through which every major feature tab
(Dashboard, Configure, Harvest, Help) is created, laid out, and kept in sync.

Key responsibilities:
- Build and manage the collapsible left sidebar with nav buttons and status pill.
- Host a ``QStackedWidget`` that switches between the four application pages.
- Wire cross-tab signals so that config/target changes propagate to the harvest
  worker and the dashboard stats view.
- Apply and persist the active color theme (light/dark) via ``ThemeManager``.
- Register all global keyboard shortcuts.
- Handle the window resize event that auto-collapses/expands the sidebar.
"""
import logging
import sys

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QFrame, QStatusBar, QMessageBox, QButtonGroup, QScrollArea
)
from PyQt6.QtGui import QIcon, QAction, QKeySequence, QPixmap, QShortcut
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup

# Import Tabs
from .targets_config_tab import TargetsConfigTab
from .harvest_tab import HarvestTab
from .dashboard import DashboardTab
from .help_tab import HelpTab

# Dialogs & Utils
from .notifications import NotificationManager
from .styles import DEFAULT_STYLESHEET, generate_stylesheet, CATPPUCCIN_DARK, CATPPUCCIN_LIGHT
from .icons import (
    get_icon, get_pixmap, 
    SVG_DASHBOARD, SVG_TARGETS, SVG_SETTINGS, SVG_RESULTS,
    SVG_HARVEST, SVG_CHEVRON_LEFT, SVG_CHEVRON_RIGHT,
    SVG_TOGGLE_ON, SVG_TOGGLE_OFF
)
from src.config.profile_manager import ProfileManager
from .theme_manager import ThemeManager

logger = logging.getLogger(__name__)


class ModernMainWindow(QMainWindow):
    """Top-level application window.

    Combines a collapsible sidebar (navigation + status pill + theme toggle) with
    a ``QStackedWidget`` content area that hosts the four main pages:

    - Page 0: Dashboard  – KPI cards, live activity, result file shortcuts.
    - Page 1: Configure  – Profile settings (ConfigTab) + target list (TargetsTab)
                           stacked vertically in a splitter.
    - Page 2: Harvest    – Input file selector, run controls, progress display.
    - Page 3: Help       – Keyboard shortcuts reference and embedded accessibility page.

    Cross-tab communication is handled entirely through PyQt signals so no page
    holds a direct reference to another.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LCCN Harvester")
        self.setGeometry(100, 100, 1380, 900)
        # Ensure window is resizable: clear accidental maximum constraints and enable min/max buttons
        try:
            # Minimum size derived from the widest fixed-width content:
            # sidebar(240) + content-margins(60) + content(660) = 960 wide;
            # dashboard stacked content (profile panel 74 + KPI cards ~120 +
            # content split ~200 + headers/spacing ~100) + margins(60) = 660 tall.
            self.setMinimumSize(900, 660)
            # remove any accidental maximum constraint
            self.setMaximumSize(16777215, 16777215)
            # ensure title and min/max buttons are present
            self.setWindowFlag(Qt.WindowType.WindowTitleHint, True)
            self.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, True)
            # ensure not forced on top
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
            # commit flags (some Qt versions require resetting flags)
            self.setWindowFlags(self.windowFlags())
        except Exception:
            pass

        # Data
        self.advanced_mode = False
        self.sidebar_collapsed = False
        self._sidebar_auto_collapsed = False
        # In Qt/macOS key sequences: Ctrl maps to Command, Meta maps to physical Control.
        # Use Meta on macOS so shortcuts are truly Control+... as requested.
        self._shortcut_modifier = "Meta" if sys.platform == "darwin" else "Ctrl"
        self._profile_manager = ProfileManager()
        self._theme_manager = ThemeManager()
        try:
            self._profile_manager.set_active_profile("Default Settings")
        except Exception:
            pass
        
        # Core Services
        self.notification_manager = NotificationManager(self)
        self.notification_manager.setup_system_tray()

        self._setup_layout()
        self._apply_advanced_mode()

        # Always start in light mode on launch
        try:
            self._apply_theme("light")
        except Exception:
            logger.exception("Theme generation fallback triggered.")
            self.setStyleSheet(DEFAULT_STYLESHEET)

    def _setup_layout(self):
        """Build the Sidebar + Content Layout."""
        # Main Container
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Left Sidebar
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(240)
        
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 20)
        sidebar_layout.setSpacing(5)

        # Header (Toggle + Title)
        header_frame = QWidget()
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 15, 10, 15)
        
        self.title_label = QLabel("LCCN Pro")
        self.title_label.setObjectName("SidebarTitle")
        self.title_label.setContentsMargins(10, 0, 0, 0) # Offset for icon alignment
        
        self.toggle_btn = QPushButton()
        self.toggle_btn.setIcon(get_icon(SVG_CHEVRON_LEFT, "#8aadf4"))
        self.toggle_btn.setFixedSize(30, 30)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.setStyleSheet("background: transparent; border: none;")
        self.toggle_btn.clicked.connect(self._toggle_sidebar)
        
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.toggle_btn)
        
        sidebar_layout.addWidget(header_frame)

        # Nav Button Group
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_group.buttonClicked.connect(self._on_nav_clicked)

        # Navigation Buttons — order matches the stacked-widget page indices below.
        # Dashboard(0) → Configure(1) → Harvest(2) → Help(3)
        self.btn_configure = self._create_nav_btn("Configure", SVG_TARGETS, 1)
        self.btn_harvest = self._create_nav_btn("Harvest", SVG_HARVEST, 2)
        self.btn_dashboard = self._create_nav_btn("Dashboard", SVG_DASHBOARD, 0)
        self.btn_help = self._create_nav_btn("Help", SVG_RESULTS, 3)

        sidebar_layout.addWidget(self.btn_configure)
        sidebar_layout.addWidget(self.btn_harvest)
        sidebar_layout.addWidget(self.btn_dashboard)
        sidebar_layout.addWidget(self.btn_help)

        sidebar_layout.addStretch() # Spacer

        # Sidebar status pill — shows harvester state (Idle / Running / Paused / etc.)
        self.sidebar_status = QLabel("● Idle")
        self.sidebar_status.setProperty("class", "StatusPill")
        self.sidebar_status.setProperty("state", "idle")
        self.sidebar_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sidebar_status.setContentsMargins(10, 4, 10, 4)
        sidebar_layout.addWidget(self.sidebar_status)
        self.sidebar_status.setText("Idle")
        self.status_pill = self.sidebar_status

        # Theme toggle button (bottom, like Accessibility)
        self.btn_theme = QPushButton("Toggle Theme")
        self.btn_theme.setIcon(get_icon(SVG_SETTINGS, "#a5adcb")) # Will be replaced dynamically in _apply_theme
        self.btn_theme.setObjectName("NavButton")
        self.btn_theme.setProperty("class", "NavButton")
        self.btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme.clicked.connect(self._toggle_theme)
        self.btn_theme.setToolTip("Toggle application theme (dark / light)")
        sidebar_layout.addWidget(self.btn_theme)

        main_layout.addWidget(self.sidebar)

        # 2. Right Content Area
        content_container = QWidget()
        content_container.setObjectName("ContentArea")
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(20)

        # Page Header (Dynamic) — default matches the first visible page (Dashboard)
        self.page_title = QLabel("Dashboard")
        self.page_title.setObjectName("PageTitle")
        content_layout.addWidget(self.page_title)

        # Stacked Pages
        self.stack = QStackedWidget()
        
        # Instantiate pages.
        self.dashboard_tab = DashboardTab()
        self.targets_config_tab = TargetsConfigTab()
        # Backward-compatibility aliases so all existing signal wiring still works
        self.targets_tab = self.targets_config_tab.targets_tab
        self.config_tab = self.targets_config_tab.config_tab
        self.harvest_tab = HarvestTab()
        self.help_tab = HelpTab(shortcut_modifier=self._shortcut_modifier)

        # Page indices must stay in sync with the nav-button indices above.
        self.stack.addWidget(self.dashboard_tab)         # 0 – Dashboard
        self.stack.addWidget(self.targets_config_tab)    # 1 – Configure
        self.stack.addWidget(self.harvest_tab)           # 2 – Harvest
        self.stack.addWidget(self.help_tab)              # 3 – Help

        content_layout.addWidget(self.stack)

        main_layout.addWidget(content_container)

        # Wire up page-to-page data flow.
        # HarvestTab needs access to Config and Targets to run
        self.harvest_tab.set_data_sources(
            config_getter=self.config_tab.get_config,
            targets_getter=self.targets_tab.get_targets,
            profile_getter=self._profile_manager.get_active_profile,
            db_path_getter=lambda: self._profile_manager.get_db_path(
                self._profile_manager.get_active_profile()
            ),
        )

        self._connect_signals()
        self._setup_accessibility()
        self._setup_shortcuts()
        self._refresh_dashboard_profile_controls()
        self._refresh_targets_profile_controls()
        self._sync_tab_state()
        
        # Select default page: Configure (index 1)
        self.btn_configure.setChecked(True)
        self.stack.setCurrentIndex(1)
        self.page_title.setText("Configure")

    def _create_nav_btn(self, text, svg_icon, index):
        """Create a checkable sidebar navigation button and register it with the button group.

        Args:
            text: Human-readable label shown when the sidebar is expanded.
            svg_icon: SVG string constant from ``icons.py`` used as the button icon.
            index: Zero-based stacked-widget page index this button should activate.

        Returns:
            The configured ``QPushButton`` instance (not yet added to a layout).
        """
        btn = QPushButton(text)
        btn.setObjectName("NavButton")
        btn.setProperty("class", "NavButton")
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setIcon(get_icon(svg_icon, "#a5adcb"))
        btn.setIconSize(QSize(20, 20))
        # page_index is read back in _on_nav_clicked to switch the stack
        btn.setProperty("page_index", index)
        # Store original text for expanding/collapsing
        btn.setProperty("full_text", text)
        self.nav_group.addButton(btn)
        return btn

    def _setup_accessibility(self):
        """Set accessible names, descriptions, and tooltips for screen-reader support."""
        self.toggle_btn.setToolTip("Collapse or expand sidebar")
        self.toggle_btn.setAccessibleName("Toggle Sidebar")
        self.toggle_btn.setAccessibleDescription("Collapse or expand left navigation sidebar.")

        for btn in self.nav_group.buttons():
            label = btn.property("full_text") or btn.text().strip()
            btn.setAccessibleName(f"Open {label} page")
            btn.setToolTip(f"Open {label}")


    def _setup_shortcuts(self):
        """Register all global application keyboard shortcuts.

        Shortcuts are stored in ``self._shortcuts`` so they are not garbage-collected
        (Qt shortcuts are only active while the owning Python object is alive).
        The modifier prefix is ``Ctrl`` on Windows/Linux and ``Meta`` on macOS so
        that shortcuts bind to the physical Control key on every platform.
        """
        mod = self._shortcut_modifier
        self._shortcuts = []

        def add_shortcut(sequence: str, callback):
            """Create a single application-scoped shortcut and keep a reference."""
            sc = QShortcut(QKeySequence(sequence), self)
            # ApplicationShortcut means the shortcut fires regardless of which widget has focus
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(callback)
            self._shortcuts.append(sc)

        def add_mod_shortcut(key: str, callback):
            """Convenience wrapper that prepends the platform modifier."""
            add_shortcut(f"{mod}+{key}", callback)

        add_mod_shortcut("B", self._toggle_sidebar)
        add_mod_shortcut("Q", self.close)
        # Numeric shortcuts match visible sidebar order: 1=Configure, 2=Harvest, 3=Dashboard, 4=Help
        add_mod_shortcut("1", lambda: self.btn_configure.click())
        add_mod_shortcut("2", lambda: self.btn_harvest.click())
        add_mod_shortcut("3", lambda: self.btn_dashboard.click())
        add_mod_shortcut("4", lambda: self.btn_help.click())

        add_mod_shortcut("Shift+D", lambda: self.btn_dashboard.click())
        add_mod_shortcut("Shift+H", lambda: self.btn_harvest.click())

        add_mod_shortcut("H", self._shortcut_start_harvest)
        add_shortcut("Esc", self._shortcut_stop_harvest)
        add_mod_shortcut(".", self._shortcut_stop_harvest)
        add_mod_shortcut("R", self._shortcut_refresh_dashboard)

    def _shortcut_start_harvest(self):
        """Keyboard shortcut handler: navigate to Harvest tab and start the run."""
        if self.harvest_tab.is_running:
            return
        self.btn_harvest.click()
        if self.harvest_tab.btn_start.isEnabled():
            self.harvest_tab.btn_start.click()

    def _shortcut_stop_harvest(self):
        """Keyboard shortcut handler: stop the currently-running harvest."""
        if self.harvest_tab.is_running:
            self.harvest_tab.stop_harvest()

    def _shortcut_refresh_dashboard(self):
        """Keyboard shortcut handler: force an immediate dashboard data refresh."""
        self.dashboard_tab.refresh_data()

    def _open_help_tab(self):
        """Navigate to the Help page via the sidebar nav button."""
        self.btn_help.click()

    def _toggle_sidebar(self):
        """Manually toggle sidebar between expanded (240 px) and collapsed (72 px) states."""
        # Clear the auto-collapse flag so the window-resize logic doesn't fight the user.
        self._sidebar_auto_collapsed = False
        self._set_sidebar_collapsed(not self.sidebar_collapsed, animated=True)

    def _set_sidebar_collapsed(self, collapsed: bool, animated: bool = True):
        """Expand or collapse the sidebar, optionally using a smooth animation.

        When collapsed the sidebar is 72 px wide (icon-only mode); when expanded
        it is 240 px wide (icon + label mode).  Both ``minimumWidth`` and
        ``maximumWidth`` are animated in parallel so Qt does not clip the frame
        during the transition.

        Args:
            collapsed: ``True`` to collapse, ``False`` to expand.
            animated: When ``True``, a 300 ms ``InOutQuart`` easing animation is used.
        """
        if self.sidebar_collapsed == collapsed and animated:
            return

        self.sidebar_collapsed = collapsed
        width = 72 if collapsed else 240

        if animated:
            # Animate both constraints simultaneously so the frame resizes smoothly.
            self.anim = QPropertyAnimation(self.sidebar, b"minimumWidth")
            self.anim.setDuration(300)
            self.anim.setStartValue(self.sidebar.width())
            self.anim.setEndValue(width)
            self.anim.setEasingCurve(QEasingCurve.Type.InOutQuart)

            self.anim2 = QPropertyAnimation(self.sidebar, b"maximumWidth")
            self.anim2.setDuration(300)
            self.anim2.setStartValue(self.sidebar.width())
            self.anim2.setEndValue(width)

            # QParallelAnimationGroup fires both animations at the same time.
            self.anim_group = QParallelAnimationGroup()
            self.anim_group.addAnimation(self.anim)
            self.anim_group.addAnimation(self.anim2)
            self.anim_group.start()
        else:
            # Instant resize (used during window resize events to avoid lag).
            self.sidebar.setMinimumWidth(width)
            self.sidebar.setMaximumWidth(width)

        # Flip the toggle chevron to indicate the new state.
        icon = SVG_CHEVRON_RIGHT if collapsed else SVG_CHEVRON_LEFT
        self.toggle_btn.setIcon(get_icon(icon, "#8aadf4"))

        # Update Text Visibility
        self.title_label.setVisible(not self.sidebar_collapsed)

        for btn in self.nav_group.buttons():
            if collapsed:
                # Icon-only mode: clear label text and show tooltip instead.
                btn.setText("")
                btn.setToolTip(btn.property("full_text"))
            else:
                # Expanded mode: show label text and disable tooltip (redundant).
                btn.setText("  " + btn.property("full_text"))
                btn.setToolTip("")

        # Show / hide sidebar status text on collapse
        if hasattr(self, 'sidebar_status'):
            self.sidebar_status.setVisible(not collapsed)

        if not collapsed:
            try:
                current_mode = self._theme_manager.get_theme()
                self.btn_theme.setText("Theme: Light" if current_mode == "light" else "Theme: Dark")
            except:
                self.btn_theme.setText("Toggle Theme")

    def resizeEvent(self, event):
        """Auto-collapse/expand the sidebar based on available window width.

        Below 1180 px the sidebar collapses to icon-only mode to reclaim content
        space.  The collapse is reversed once the window is widened past 1280 px,
        but only if it was the auto-collapse (not a manual user action) that hid
        it in the first place.
        """
        super().resizeEvent(event)
        width = event.size().width()
        if width < 1180 and not self.sidebar_collapsed:
            self._sidebar_auto_collapsed = True
            self._set_sidebar_collapsed(True, animated=False)
        elif width >= 1280 and self._sidebar_auto_collapsed and self.sidebar_collapsed:
            self._sidebar_auto_collapsed = False
            self._set_sidebar_collapsed(False, animated=False)

    def _on_nav_clicked(self, btn):
        """Handle a sidebar nav-button click and switch the stacked page.

        Before navigating away from the Configure page (index 1), ask the user to
        resolve any unsaved profile changes.  If they cancel, restore the currently
        selected nav button so the UI stays consistent.
        """
        if btn is None:
            return

        current_index = self.stack.currentIndex()
        index = btn.property("page_index")
        # Guard: prompt for unsaved changes when leaving the Configure page.
        if current_index == 0 and index != 0:
            if not self.targets_config_tab.resolve_unsaved_changes():
                # User cancelled — restore the previously-checked nav button.
                current_button = next(
                    (
                        candidate
                        for candidate in self.nav_group.buttons()
                        if candidate.property("page_index") == current_index
                    ),
                    None,
                )
                if current_button is not None:
                    # blockSignals prevents triggering _on_nav_clicked recursively.
                    current_button.blockSignals(True)
                    current_button.setChecked(True)
                    current_button.blockSignals(False)
                btn.blockSignals(True)
                btn.setChecked(False)
                btn.blockSignals(False)
                return
        self.stack.setCurrentIndex(index)
        current_page = self.stack.widget(index)
        if hasattr(current_page, "current_page_title"):
            self.page_title.setText(current_page.current_page_title())
        else:
            self.page_title.setText(btn.property("full_text"))

    def _connect_signals(self):
        """Wire all inter-tab signals after every widget has been constructed."""
        
        # Harvest Signals
        self.harvest_tab.harvest_started.connect(self._on_harvest_started)
        self.harvest_tab.harvest_finished.connect(self._on_harvest_finished)
        self.harvest_tab.result_files_ready.connect(self.dashboard_tab.set_result_files)
        self.harvest_tab.harvest_reset.connect(self._on_harvest_reset)
        self.harvest_tab.harvest_paused.connect(self._on_harvest_paused)
        
        # Live Dashboard Updates
        self.harvest_tab.progress_updated.connect(self._on_harvest_progress)
        self.harvest_tab.live_result_ready.connect(self._on_live_result)
        # Live stats streaming - bypasses DB with RunStats object
        if hasattr(self.harvest_tab, 'live_stats_ready'):
            self.harvest_tab.live_stats_ready.connect(self.dashboard_tab.update_live_stats)

        # Target Updates
        self.targets_config_tab.targets_changed.connect(self._on_targets_changed)

        # Reload targets when the active profile changes
        self.targets_config_tab.profile_changed.connect(self.targets_tab.load_profile_targets)
        self.targets_config_tab.profile_changed.connect(self._on_profile_changed)

        # Targets tab profile selector
        # (cross-navigation between Targets/Settings is handled internally by TargetsConfigTab)
        self.targets_config_tab.profile_selected.connect(self._on_targets_profile_selected)

        # Dashboard profile dock controls
        self.dashboard_tab.profile_selected.connect(self._on_dashboard_profile_selected)
        self.dashboard_tab.create_profile_requested.connect(self._open_profile_settings)
        self.dashboard_tab.page_title_changed.connect(self.page_title.setText)
        self.dashboard_tab.pause_harvest_requested.connect(self.harvest_tab._toggle_pause)
        self.dashboard_tab.cancel_harvest_requested.connect(self.harvest_tab.stop_harvest)
        self.help_tab.page_title_changed.connect(self.page_title.setText)

        # Keep tab state fresh when navigating
        self.stack.currentChanged.connect(self._on_page_changed)

    def _on_live_result(self, payload: dict):
        """Forward a per-ISBN harvest result to the dashboard's recent-results table.

        Args:
            payload: Dict with keys ``isbn``, ``status``, and ``detail`` from the worker.
        """
        if hasattr(self.dashboard_tab, '_append_recent_result'):
            self.dashboard_tab._append_recent_result(
                isbn=payload.get("isbn", ""),
                status=payload.get("status", ""),
                detail=payload.get("detail", "")
            )

    def _on_harvest_progress(self, isbn, status, source, message):
        """Forward a per-ISBN progress event to the dashboard live-activity panel.

        The ``progress_updated`` signal carries (isbn, status, source, message) but
        not a percentage.  The percentage is derived here by peeking at the worker's
        ``processed_count`` / ``total_count`` counters on ``harvest_tab``.

        Args:
            isbn: The ISBN that was just processed.
            status: Outcome string, e.g. ``"found"``, ``"failed"``, ``"cached"``.
            source: The target name that produced the result.
            message: Human-readable status message for the log/activity feed.
        """
        try:
            total = self.harvest_tab.total_count
            current = self.harvest_tab.processed_count
            pct = (current / total * 100) if total > 0 else 0
        except:
            pct = 0
            
        self.dashboard_tab.update_live_status(
            target=source,
            isbn=isbn,
            progress=pct,
            msg=message
        )
        self.dashboard_tab.record_harvest_event(isbn, status, message)
        
        # Real-time results update - only fall back to refresh if live_stats_ready is not connected
        if status in ("found", "failed", "cached", "skipped") and not getattr(self.harvest_tab, 'live_stats_ready', None):
            self.dashboard_tab.refresh_data()

    def _sync_tab_state(self):
        """Initial cross-tab synchronization after signals are connected."""
        try:
            self._on_targets_changed(self.targets_tab.get_targets())
        except Exception:
            pass
        try:
            self.dashboard_tab.refresh_data()
        except Exception:
            pass

    def _on_targets_changed(self, targets):
        """Fan out a target-list change to all tabs that depend on the target configuration.

        Args:
            targets: List of target config dicts from ``TargetsTab.get_targets()``.
        """
        self.harvest_tab.on_targets_changed(targets)
        self.config_tab.refresh_targets_preview(targets)
        # Only refresh DB stats if not actively streaming live data
        if not getattr(self.harvest_tab, 'is_running', False):
            self.dashboard_tab.refresh_data()

    def _refresh_dashboard_profile_controls(self):
        """Push the current profile list and active profile name to the dashboard combo."""
        profiles = self.config_tab.list_profile_names()
        current = self._profile_manager.get_active_profile()
        self.dashboard_tab.set_profile_options(profiles, current)

    def _on_dashboard_profile_selected(self, name):
        """Handle a profile selection made from the dashboard profile switcher.

        Args:
            name: Profile name chosen by the user.
        """
        if not name:
            return
        self.config_tab.select_profile(name)
        # If user cancels due to unsaved changes, resync displayed selection.
        self._refresh_dashboard_profile_controls()
        self._refresh_targets_profile_controls()

    def _refresh_targets_profile_controls(self):
        """Push the current profile list and active profile name to the targets tab combo."""
        profiles = self.config_tab.list_profile_names()
        current = self._profile_manager.get_active_profile()
        self.targets_tab.set_profile_options(profiles, current)

    def _on_targets_profile_selected(self, name):
        """Handle a profile selection made from the targets-tab profile switcher.

        Args:
            name: Profile name chosen by the user.
        """
        if not name:
            return
        self.config_tab.select_profile(name)
        self._refresh_dashboard_profile_controls()
        self._refresh_targets_profile_controls()

    def _open_profile_settings(self):
        """Navigate to the Configure page and focus the New Profile button."""
        self.btn_configure.click()
        if hasattr(self.config_tab, "btn_new"):
            self.config_tab.btn_new.setFocus()

    def _on_profile_changed(self, profile_name):
        """React to an active-profile change originating from the Configure tab.

        Persists the new profile, refreshes all profile-aware UI controls, resets
        the harvest tab, and reloads the dashboard stats from the new profile's DB.

        Args:
            profile_name: The newly activated profile name.
        """
        self._profile_manager.set_active_profile(profile_name)
        self._refresh_dashboard_profile_controls()
        self._refresh_targets_profile_controls()
        self.harvest_tab.reset_for_profile_switch()
        self.dashboard_tab.refresh_data()

    def _on_page_changed(self, index):
        """Refresh dependent tabs on navigation to keep views current.

        Index mapping (must stay in sync with stack.addWidget order):
            0 = Dashboard, 1 = Configure, 2 = Harvest, 3 = Help
        """
        if index == 0:  # Dashboard
            self.dashboard_tab.refresh_data()
        elif index == 1:  # Configure (Targets + Settings)
            self.targets_tab.refresh_targets()
            self.config_tab.refresh_targets_preview()

    # --- Logic ---

    def _apply_advanced_mode(self):
        for tab in [self.dashboard_tab, self.targets_config_tab,
                   self.harvest_tab]:
            if hasattr(tab, 'set_advanced_mode'):
                tab.set_advanced_mode(self.advanced_mode)

    def _on_harvest_started(self):
        """React to the harvest worker signalling that a run has begun."""
        self._set_sidebar_status("Running", "running")
        # Switch navigation to the Harvest page so progress is immediately visible.
        self.btn_harvest.click()
        self.dashboard_tab.set_running()


    def _on_harvest_finished(self, success, stats):
        """React to the harvest worker completing (success, cancellation, or error).

        Updates the sidebar status pill, the dashboard last-run label, KPI cards,
        and shows an error notification when appropriate.

        Args:
            success: ``True`` if the harvest completed without errors or cancellation.
            stats: Dict containing harvest outcome counters and optional ``cancelled``
                   / ``error`` keys, or a non-dict value when unavailable.
        """
        from datetime import datetime
        is_cancelled = isinstance(stats, dict) and stats.get("cancelled", False)
        has_error = isinstance(stats, dict) and bool(stats.get("error"))
        if success:
            self._set_sidebar_status("Completed", "success")
            outcome = "Completed"
        elif is_cancelled:
            self._set_sidebar_status("Cancelled", "error")
            outcome = "Cancelled"
        elif has_error:
            self._set_sidebar_status("Error", "error")
            outcome = "Error"
        else:
            self._set_sidebar_status("Failed", "error")
            outcome = "Failed"

        # Update "Last Run" with a real timestamp
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.dashboard_tab.last_run_text = f"Last Run: {ts} – {outcome}"
        self.dashboard_tab.lbl_last_run.setText(self.dashboard_tab.last_run_text)

        self.dashboard_tab.refresh_data()
        self.dashboard_tab.apply_run_stats(stats if isinstance(stats, dict) else {})

        if isinstance(stats, dict) and not stats.get("cancelled", False) and not success:
            error_msg = stats.get("error", "Harvest stopped or failed") if isinstance(stats, dict) else "Harvest stopped or failed"
            self.notification_manager.notify_harvest_error(error_msg)

        self.dashboard_tab.set_idle(success)

    def _on_harvest_paused(self, is_paused: bool):
        """Sync sidebar and dashboard pills when harvest is paused or resumed."""
        if is_paused:
            self._set_sidebar_status("Paused", "paused")
        else:
            self._set_sidebar_status("Running", "running")
        self.dashboard_tab.set_paused(is_paused)

    def _on_harvest_reset(self):
        """Called when user presses New Harvest — reset sidebar pill and dashboard status to Idle."""
        self._set_sidebar_status("Idle", "idle")
        self.dashboard_tab.set_idle()

    def _set_sidebar_status(self, text: str, state: str):
        """Update the sidebar status pill to mirror harvester state.

        Calls ``unpolish`` + ``polish`` to force Qt to re-evaluate the QSS
        ``[state="..."]`` property selector so the correct pill color is applied
        without needing to reload the full stylesheet.

        Args:
            text: Human-readable state label (e.g. ``"Running"``, ``"Idle"``).
            state: QSS property value matched by the ``StatusPill`` style rules
                   (``"idle"``, ``"running"``, ``"paused"``, ``"success"``, ``"error"``).
        """
        if hasattr(self, "status_pill"):
            self.status_pill.setText(text)
        self.sidebar_status.setText(f"● {text}")
        self.sidebar_status.setProperty("state", state)
        # unpolish/polish forces Qt to re-read the dynamic property and apply the
        # matching QSS rule (e.g. StatusPill[state="running"] { color: blue; }).
        self.sidebar_status.style().unpolish(self.sidebar_status)
        self.sidebar_status.style().polish(self.sidebar_status)

    def closeEvent(self, event):
        """Prompt the user before closing if a harvest is still in progress."""
        if self.harvest_tab.is_running:
            reply = QMessageBox.question(self, "Harvesting", "Stop harvest and exit?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            self.harvest_tab.stop_harvest()
        event.accept()
    def _toggle_theme(self):
        """Toggle between dark and light themes and apply immediately."""
        try:
            current = self._theme_manager.get_theme()
            new = "light" if current == "dark" else "dark"
            self._apply_theme(new)
        except Exception:
            # best-effort only
            try:
                self._apply_theme("dark")
            except Exception:
                pass

    def _apply_theme(self, theme: str):
        """Apply the requested color theme using the shared stylesheet helpers.

        Strategy:
        - Generate the complete application stylesheet based on the active mode.
        - Persist the selection via ThemeManager.
        """
        try:
            mode = theme if isinstance(theme, str) and theme in ("dark", "light") else self._theme_manager.get_theme()

            if mode == "light":
                qss = generate_stylesheet(CATPPUCCIN_LIGHT)
                if hasattr(self, 'btn_theme'):
                    self.btn_theme.setIcon(get_icon(SVG_TOGGLE_OFF, CATPPUCCIN_LIGHT['text_muted']))
                    if not self.sidebar_collapsed:
                        self.btn_theme.setText("Theme: Light")
            else:
                qss = generate_stylesheet(CATPPUCCIN_DARK)
                if hasattr(self, 'btn_theme'):
                    self.btn_theme.setIcon(get_icon(SVG_TOGGLE_ON, CATPPUCCIN_DARK['primary']))
                    if not self.sidebar_collapsed:
                        self.btn_theme.setText("Theme: Dark")
                
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                app.setStyleSheet(qss)
            else:
                self.setStyleSheet(qss)

            # Persist selection
            try:
                self._theme_manager.set_theme(mode)
            except Exception:
                pass

            # Notify tabs that use inline theme-specific styles
            try:
                colors = CATPPUCCIN_LIGHT if mode == "light" else CATPPUCCIN_DARK
                if hasattr(self, "help_tab"):
                    self.help_tab.refresh_theme(colors)
                if hasattr(self, "harvest_tab") and hasattr(self.harvest_tab, "_apply_db_only_checkbox_style"):
                    self.harvest_tab._apply_db_only_checkbox_style()
                if hasattr(self, "targets_tab"):
                    self.targets_tab.refresh_targets()
            except Exception:
                pass
        except Exception:
            # Very last-resort fallback
            try:
                self.setStyleSheet(DEFAULT_STYLESHEET)
            except Exception:
                pass
