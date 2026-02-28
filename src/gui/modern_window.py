"""
Module: modern_window.py
V2 Professional Window: Custom Collapsible Sidebar + Stacked Layout.
"""
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QFrame, QStatusBar, QMessageBox, QButtonGroup, QScrollArea
)
from PyQt6.QtGui import QIcon, QAction, QKeySequence, QPixmap, QShortcut
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
import sys

# Import Tabs
from .targets_tab_v2 import TargetsTabV2
from .config_tab_v2 import ConfigTabV2
from .harvest_tab_v2 import HarvestTabV2
from .dashboard_v2 import DashboardTabV2
from .ai_assistant_tab import AIAssistantTab

# Dialogs & Utils
from .notifications import NotificationManager
from .styles_v2 import V2_STYLESHEET, generate_stylesheet, CATPPUCCIN_DARK, CATPPUCCIN_LIGHT
from .shortcuts_dialog import ShortcutsDialog
from .accessibility_statement_dialog import AccessibilityStatementDialog
from .icons import (
    get_icon, get_pixmap, 
    SVG_DASHBOARD, SVG_INPUT, SVG_TARGETS, SVG_SETTINGS, 
    SVG_HARVEST, SVG_AI, SVG_CHEVRON_LEFT, SVG_CHEVRON_RIGHT
)
from .theme_manager import ThemeManager
from config.profile_manager import ProfileManager

class ModernMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LCCN Harvester Pro")
        self.setGeometry(100, 100, 1380, 900)
        # Ensure window is resizable: clear accidental maximum constraints and enable min/max buttons
        try:
            # sensible minimum so layout remains usable
            self.setMinimumSize(400, 300)
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

        # Small diagnostic print to help debug resize/flag issues (harmless)
        try:
            print("[ModernMainWindow] size=%s min=%s max=%s flags=%s" % (
                str(self.size()), str(self.minimumSize()), str(self.maximumSize()), str(int(self.windowFlags()))
            ))
        except Exception:
            pass

        # Data
        self.advanced_mode = False
        self.sidebar_collapsed = False
        self._shortcut_modifier = "Meta" if sys.platform == "darwin" else "Ctrl"
        self._profile_manager = ProfileManager()
        # Theme manager: persist and read preferred theme
        self._theme_manager = ThemeManager()

        # Core Services
        self.notification_manager = NotificationManager(self)
        self.notification_manager.setup_system_tray()

        # Apply Global V2 Theme
        self.setStyleSheet(V2_STYLESHEET)
        self._setup_layout()
        self._apply_advanced_mode()

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

        # Navigation Buttons (Icon + Text)
        self.btn_dashboard = self._create_nav_btn("Dashboard", SVG_DASHBOARD, 0)
        self.btn_targets = self._create_nav_btn("Targets", SVG_TARGETS, 1)
        self.btn_config = self._create_nav_btn("Settings", SVG_SETTINGS, 2)
        self.btn_harvest = self._create_nav_btn("Harvest", SVG_HARVEST, 3)
        self.btn_ai = self._create_nav_btn("AI Agent", SVG_AI, 4)

        sidebar_layout.addWidget(self.btn_dashboard)
        sidebar_layout.addWidget(self.btn_targets)
        sidebar_layout.addWidget(self.btn_config)
        sidebar_layout.addWidget(self.btn_harvest)
        sidebar_layout.addWidget(self.btn_ai)

        sidebar_layout.addStretch() # Spacer

        # Clean "Status Pill"
        self.status_pill = QLabel("Idle")
        self.status_pill.setObjectName("StatusPill") # Matches styles_v2
        self.status_pill.setProperty("class", "StatusPill") # Helper for some qt styles
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_pill.setFixedSize(100, 30)
        self.status_pill.setStyleSheet("background-color: #363a4f; color: #d4daf2; border-radius: 15px; font-weight: bold;")
        
        status_frame = QWidget()
        status_layout = QHBoxLayout(status_frame)
        status_layout.addWidget(self.status_pill)
        sidebar_layout.addWidget(status_frame)

        # Shortcuts Button (Bottom)
        mod_label = "Cmd" if self._shortcut_modifier == "Meta" else "Ctrl"
        self.btn_shortcuts = QPushButton("Shortcuts")
        self.btn_shortcuts.setIcon(get_icon(SVG_SETTINGS, "#a5adcb"))
        self.btn_shortcuts.setObjectName("NavButton")
        self.btn_shortcuts.setProperty("class", "NavButton")
        self.btn_shortcuts.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_shortcuts.clicked.connect(self._show_shortcuts)
        self.btn_shortcuts.setToolTip(f"Open keyboard shortcuts ({mod_label}+/)")
        sidebar_layout.addWidget(self.btn_shortcuts)

        self.btn_accessibility = QPushButton("Accessibility Statement")
        self.btn_accessibility.setIcon(get_icon(SVG_SETTINGS, "#a5adcb"))
        self.btn_accessibility.setObjectName("NavButton")
        self.btn_accessibility.setProperty("class", "NavButton")
        self.btn_accessibility.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_accessibility.clicked.connect(self._show_accessibility_statement)
        self.btn_accessibility.setToolTip(f"Open accessibility statement ({mod_label}+Shift+A)")
        sidebar_layout.addWidget(self.btn_accessibility)

        # Theme toggle button (bottom, like Accessibility)
        self.btn_theme = QPushButton("Toggle Theme (BETA)")
        self.btn_theme.setIcon(get_icon(SVG_SETTINGS, "#a5adcb"))
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

        # Page Header (Dynamic)
        self.page_title = QLabel("Dashboard")
        self.page_title.setObjectName("PageTitle")
        content_layout.addWidget(self.page_title)

        # Stacked Pages
        self.stack = QStackedWidget()
        
        # Instantiate Pages (Using V2 tabs)
        self.dashboard_tab = DashboardTabV2()
        self.targets_tab = TargetsTabV2()
        self.config_tab = ConfigTabV2()
        self.harvest_tab = HarvestTabV2()
        self.ai_assistant_tab = AIAssistantTab()

        self.stack.addWidget(self.dashboard_tab) # 0
        self.stack.addWidget(self.targets_tab)   # 1
        self.stack.addWidget(self.config_tab)    # 2
        self.stack.addWidget(self.harvest_tab)   # 3
        self.stack.addWidget(self.ai_assistant_tab) # 4

        content_layout.addWidget(self.stack)
        main_layout.addWidget(content_container)

        # --- Wire Up V2 Data Flow ---
        # HarvestTab needs access to Config and Targets to run
        self.harvest_tab.set_data_sources(
            config_getter=self.config_tab.get_config,
            targets_getter=self.targets_tab.get_targets,
        )

        self._connect_signals()
        self._setup_accessibility()
        self._setup_shortcuts()
        self._refresh_dashboard_profile_controls()
        self._sync_tab_state()
        
        # Select default
        self.btn_dashboard.setChecked(True)

    def _create_nav_btn(self, text, svg_icon, index):
        btn = QPushButton(text)
        btn.setProperty("class", "NavButton")
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setIcon(get_icon(svg_icon, "#a5adcb"))
        btn.setIconSize(QSize(20, 20))
        btn.setProperty("page_index", index)
        # Store original text for expanding/collapsing
        btn.setProperty("full_text", text)
        self.nav_group.addButton(btn)
        return btn

    def _setup_accessibility(self):
        self.toggle_btn.setToolTip("Collapse or expand sidebar")
        self.toggle_btn.setAccessibleName("Toggle Sidebar")
        self.toggle_btn.setAccessibleDescription("Collapse or expand left navigation sidebar.")

        for btn in self.nav_group.buttons():
            label = btn.property("full_text") or btn.text().strip()
            btn.setAccessibleName(f"Open {label} page")
            btn.setToolTip(f"Open {label}")

        self.btn_shortcuts.setAccessibleName("Show keyboard shortcuts")
        self.btn_accessibility.setAccessibleName("Show accessibility statement")
        self.btn_theme.setAccessibleName("Toggle application theme")
        self.status_pill.setAccessibleName("Application status")

    def _setup_shortcuts(self):
        mod = self._shortcut_modifier
        QShortcut(QKeySequence(f"{mod}+B"), self, activated=self._toggle_sidebar)
        QShortcut(QKeySequence(f"{mod}+Q"), self, activated=self.close)
        QShortcut(QKeySequence(f"{mod}+1"), self, activated=lambda: self.btn_dashboard.click())
        QShortcut(QKeySequence(f"{mod}+2"), self, activated=lambda: self.btn_targets.click())
        QShortcut(QKeySequence(f"{mod}+3"), self, activated=lambda: self.btn_config.click())
        QShortcut(QKeySequence(f"{mod}+4"), self, activated=lambda: self.btn_harvest.click())
        QShortcut(QKeySequence(f"{mod}+5"), self, activated=lambda: self.btn_ai.click())

        QShortcut(QKeySequence(f"{mod}+Shift+D"), self, activated=lambda: self.btn_dashboard.click())
        QShortcut(QKeySequence(f"{mod}+Shift+H"), self, activated=lambda: self.btn_harvest.click())

        QShortcut(QKeySequence(f"{mod}+H"), self, activated=self._shortcut_start_harvest)
        QShortcut(QKeySequence("Esc"), self, activated=self._shortcut_stop_harvest)
        QShortcut(QKeySequence(f"{mod}+."), self, activated=self._shortcut_stop_harvest)
        QShortcut(QKeySequence(f"{mod}+R"), self, activated=self._shortcut_refresh_dashboard)
        QShortcut(QKeySequence(f"{mod}+/"), self, activated=self._show_shortcuts)
        QShortcut(QKeySequence(f"{mod}+Shift+A"), self, activated=self._show_accessibility_statement)
        QShortcut(QKeySequence("F1"), self, activated=self._show_shortcuts)

    def _shortcut_start_harvest(self):
        if self.harvest_tab.is_running:
            return
        self.btn_harvest.click()
        if self.harvest_tab.btn_start.isEnabled():
            self.harvest_tab.btn_start.click()

    def _shortcut_stop_harvest(self):
        if self.harvest_tab.is_running:
            self.harvest_tab.stop_harvest()

    def _shortcut_refresh_dashboard(self):
        self.dashboard_tab.refresh_data()

    def _show_shortcuts(self):
        dialog = ShortcutsDialog(self)
        dialog.exec()

    def _show_accessibility_statement(self):
        dialog = AccessibilityStatementDialog(self)
        dialog.exec()

    def _toggle_sidebar(self):
        self.sidebar_collapsed = not self.sidebar_collapsed
        
        width = 72 if self.sidebar_collapsed else 240
        
        # Animate width
        self.anim = QPropertyAnimation(self.sidebar, b"minimumWidth")
        self.anim.setDuration(300)
        self.anim.setStartValue(self.sidebar.width())
        self.anim.setEndValue(width)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuart)
        
        self.anim2 = QPropertyAnimation(self.sidebar, b"maximumWidth")
        self.anim2.setDuration(300)
        self.anim2.setStartValue(self.sidebar.width())
        self.anim2.setEndValue(width)
        
        self.anim_group = QParallelAnimationGroup()
        self.anim_group.addAnimation(self.anim)
        self.anim_group.addAnimation(self.anim2)
        self.anim_group.start()
        
        # Update Icon
        icon = SVG_CHEVRON_RIGHT if self.sidebar_collapsed else SVG_CHEVRON_LEFT
        self.toggle_btn.setIcon(get_icon(icon, "#8aadf4"))
        
        # Update Text Visibility
        self.title_label.setVisible(not self.sidebar_collapsed)
        self.status_pill.setVisible(not self.sidebar_collapsed)
        
        for btn in self.nav_group.buttons():
            if self.sidebar_collapsed:
                btn.setText("") # Icon only
                btn.setToolTip(btn.property("full_text"))
            else:
                btn.setText("  " + btn.property("full_text"))
                btn.setToolTip("")

        if self.sidebar_collapsed:
            self.btn_shortcuts.setText("")
            self.btn_shortcuts.setToolTip("Keyboard shortcuts")
            self.btn_accessibility.setText("")
            self.btn_accessibility.setToolTip("Accessibility statement")
            self.btn_theme.setText("")
            self.btn_theme.setToolTip("Toggle application theme (dark / light)")
        else:
            self.btn_shortcuts.setText("Shortcuts")
            self.btn_accessibility.setText("Accessibility Statement")
            self.btn_theme.setText("Toggle Theme")

    def _on_nav_clicked(self, btn):
        index = btn.property("page_index")
        self.stack.setCurrentIndex(index)
        self.page_title.setText(btn.property("full_text"))

    def _connect_signals(self):
        
        # Harvest Signals
        self.harvest_tab.harvest_started.connect(self._on_harvest_started)
        self.harvest_tab.harvest_finished.connect(self._on_harvest_finished)
        self.harvest_tab.milestone_reached.connect(
            lambda t, v: self.notification_manager.notify_milestone(t, v)
        )
        
        # Live Dashboard Updates
        self.harvest_tab.progress_updated.connect(self._on_harvest_progress)

        # Target Updates
        self.targets_tab.targets_changed.connect(self._on_targets_changed)

        # Reload targets when the active profile changes
        self.config_tab.profile_changed.connect(self.targets_tab.load_profile_targets)
        self.config_tab.profile_changed.connect(self._on_profile_changed)

        # Dashboard profile dock controls
        self.dashboard_tab.profile_selected.connect(self._on_dashboard_profile_selected)
        self.dashboard_tab.create_profile_requested.connect(self._open_profile_settings)

        # Keep tab state fresh when navigating
        self.stack.currentChanged.connect(self._on_page_changed)

    def _on_harvest_progress(self, isbn, status, source, message):
        """Pass real-time harvest events to dashboard."""
        # Calculate approximate progress if possible, or just pass 0 if unknown
        # We can store total in harvest_tab and pass it, but for now let's pass dummy %
        # or ask dashboard to use its own logic.
        # Actually LiveActivityPanel takes (target, isbn, progress, msg).
        
        # We need progress %. HarvestTab has it but doesn't pass it in this signal.
        # Let's peek at harvest_tab.progress_bar.value() or processed_count
        
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
        
        # Real-time results update
        if status in ("found", "failed", "cached", "skipped"):
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
        """Fan out target changes to dependent tabs."""
        self.harvest_tab.on_targets_changed(targets)
        # Dashboard stats come from DB, but refreshing keeps UI current after navigation/actions.
        self.dashboard_tab.refresh_data()

    def _refresh_dashboard_profile_controls(self):
        profiles = self.config_tab.list_profile_names()
        current = self._profile_manager.get_active_profile()
        self.dashboard_tab.set_profile_options(profiles, current)

    def _on_dashboard_profile_selected(self, name):
        if not name:
            return
        self.config_tab.select_profile(name)
        # If user cancels due to unsaved changes, resync displayed selection.
        self._refresh_dashboard_profile_controls()

    def _open_profile_settings(self):
        self.btn_config.click()
        if hasattr(self.config_tab, "btn_new"):
            self.config_tab.btn_new.setFocus()

    def _on_profile_changed(self, profile_name):
        self._profile_manager.set_active_profile(profile_name)
        self._refresh_dashboard_profile_controls()
        self.dashboard_tab.refresh_data()

    def _on_page_changed(self, index):
        """Refresh dependent tabs on navigation to keep views current."""
        if index == 0:  # Dashboard
            self.dashboard_tab.refresh_data()
        elif index == 1:  # Targets
            # Reflect latest profile/target state when revisiting the tab.
            self.targets_tab.refresh_targets()
        elif index == 3:  # Harvest
            self.harvest_tab.on_targets_changed(self.targets_tab.get_targets())

    # --- Logic ---

    def _apply_advanced_mode(self):
        # AI Button now always visible, so we don't toggle it here
        # self.btn_ai.setVisible(self.advanced_mode) <--- REMOVED
        
        for tab in [self.dashboard_tab, self.targets_tab, 
                   self.config_tab, self.harvest_tab, self.ai_assistant_tab]:
            if hasattr(tab, 'set_advanced_mode'):
                tab.set_advanced_mode(self.advanced_mode)

    def _on_harvest_started(self):
        self.status_pill.setText("Running")
        self.status_pill.setStyleSheet("background-color: #8aadf4; color: #1e2030; border-radius: 15px; font-weight: bold;")
        self.btn_harvest.click()
        self.dashboard_tab.set_running()


    def _on_harvest_finished(self, success, stats):
        self.status_pill.setText("Idle")
        self.status_pill.setStyleSheet("background-color: #363a4f; color: #d4daf2; border-radius: 15px; font-weight: bold;")
        self.dashboard_tab.refresh_data()
        
        if success:
            self.notification_manager.notify_harvest_completed(stats)
        elif isinstance(stats, dict) and stats.get("cancelled", False):
            # Quietly finish without an error toast for deliberate cancellations
            pass
        else:
            error_msg = stats.get("error", "Harvest stopped or failed") if isinstance(stats, dict) else "Harvest stopped or failed"
            self.notification_manager.notify_harvest_error(error_msg)
            
        self.dashboard_tab.set_idle(success)

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

    def closeEvent(self, event):
        if self.harvest_tab.is_running:
            reply = QMessageBox.question(self, "Harvesting", "Stop harvest and exit?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            self.harvest_tab.stop_harvest()
        event.accept()

    def _apply_theme(self, theme: str):
        """Apply color theme (light first, then optional pyqtdarktheme for dark).

        Strategy:
        - Apply the light stylesheet first to create a consistent base.
        - If dark is requested, attempt to use `pyqtdarktheme` (best-effort) to
          obtain and apply a richer dark stylesheet. If that fails, fall back to
          the internal dark palette via `generate_stylesheet(CATPPUCCIN_DARK)`.
        - Persist the selection via ThemeManager.
        """
        try:
            mode = theme if isinstance(theme, str) and theme in ("dark", "light") else self._theme_manager.get_theme()

            # Apply light base first for a predictable starting state
            try:
                light_qss = generate_stylesheet(CATPPUCCIN_LIGHT)
                self.setStyleSheet(light_qss)
            except Exception:
                # fallback to bundled stylesheet if generation fails
                try:
                    self.setStyleSheet(V2_STYLESHEET)
                except Exception:
                    pass

            if mode == "dark":
                # Best-effort: try to use pyqtdarktheme if installed
                try:
                    import pyqtdarktheme as _pdt
                    stylesheet = None

                    # Candidate functions that may produce a QSS string
                    candidates = (
                        "apply_dark_theme", "enable_dark_theme", "setup_theme",
                        "get_stylesheet", "load_stylesheet", "get_qss", "get_style_sheet",
                    )
                    applied_by_module = False
                    for cand in candidates:
                        func = getattr(_pdt, cand, None)
                        if callable(func):
                            try:
                                # Some APIs accept a widget/window reference
                                try:
                                    out = func(self)
                                except TypeError:
                                    out = func()
                                # If function returns a stylesheet string, use it
                                if isinstance(out, str) and out.strip():
                                    stylesheet = out
                                    break
                                # If function returns None or True, assume it applied the theme directly
                                if out is None or out is True:
                                    stylesheet = None
                                    applied_by_module = True
                                    break
                            except Exception:
                                stylesheet = None
                                applied_by_module = False

                    # Try module-level stylesheet variables
                    if not stylesheet:
                        for var in ("STYLESHEET", "STYLE_SHEET", "stylesheet", "style_sheet"):
                            val = getattr(_pdt, var, None)
                            if isinstance(val, str) and val.strip():
                                stylesheet = val
                                break

                    if stylesheet:
                        self.setStyleSheet(stylesheet)
                    elif applied_by_module:
                        # Module applied theme in-place — don't override
                        pass
                    else:
                        self.setStyleSheet(generate_stylesheet(CATPPUCCIN_DARK))
                except Exception:
                    # pyqtdarktheme absent or failed; use internal dark stylesheet
                    try:
                        self.setStyleSheet(generate_stylesheet(CATPPUCCIN_DARK))
                    except Exception:
                        try:
                            self.setStyleSheet(V2_STYLESHEET)
                        except Exception:
                            pass
            else:
                # Light requested — already applied above
                pass

            # Persist selection (best-effort)
            try:
                self._theme_manager.set_theme(mode)
            except Exception:
                pass
        except Exception:
            # Very last-resort fallback
            try:
                self.setStyleSheet(V2_STYLESHEET)
            except Exception:
                pass
