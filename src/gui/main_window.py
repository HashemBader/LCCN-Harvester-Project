"""
Module: main_window.py
Main application window for the LCCN Harvester GUI.
"""
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QStatusBar, QLabel, QToolBar, QPushButton,
    QVBoxLayout, QHBoxLayout, QScrollArea
)
from PyQt6.QtGui import QAction, QIcon, QShortcut, QKeySequence
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from pathlib import Path
import json

from .input_tab import InputTab
from .targets_tab import TargetsTab
from .config_tab import ConfigTab
from .harvest_tab import HarvestTab
from .results_tab import ResultsTab
from .dashboard_tab import DashboardTab
from .ai_assistant_tab import AIAssistantTab
from .advanced_settings_dialog import AdvancedSettingsDialog
from .notifications import NotificationManager
from .shortcuts_dialog import ShortcutsDialog
from utils import messages


class MainWindow(QMainWindow):
    advanced_mode_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LCCN Harvester Pro")
        self.setGeometry(100, 100, 1200, 800)

        # Load advanced mode preference
        self.settings_file = Path("data/gui_settings.json")
        self.advanced_mode = self._load_advanced_mode()

        # Setup notification manager and system tray
        self.notification_manager = NotificationManager(self)
        self.notification_manager.setup_system_tray()

        self._setup_menu_bar()
        self._setup_central_widget()
        self._setup_status_bar()
        self._setup_keyboard_shortcuts()
        self._apply_advanced_mode()

    def _load_advanced_mode(self):
        """Load advanced mode setting from file."""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
                    return settings.get("advanced_mode", False)
        except Exception:
            pass
        return False

    def _save_advanced_mode(self):
        """Save advanced mode setting to file."""
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            settings = {"advanced_mode": self.advanced_mode}
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def _setup_menu_bar(self):
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        file_menu.addSeparator()

        # Advanced Settings (only visible in advanced mode)
        self.advanced_settings_action = QAction("Advanced Settings...", self)
        self.advanced_settings_action.triggered.connect(self._show_advanced_settings)
        file_menu.addAction(self.advanced_settings_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("View")

        refresh_action = QAction("Refresh Results", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self._refresh_results)
        view_menu.addAction(refresh_action)

        # Tools menu (advanced only)
        self.tools_menu = menubar.addMenu("Tools")

        clear_cache_action = QAction("Clear Database Cache", self)
        clear_cache_action.triggered.connect(self._clear_cache)
        self.tools_menu.addAction(clear_cache_action)

        benchmark_action = QAction("Run Benchmark", self)
        benchmark_action.triggered.connect(self._run_benchmark)
        self.tools_menu.addAction(benchmark_action)

        # Help menu
        help_menu = menubar.addMenu("Help")

        docs_action = QAction("Documentation", self)
        docs_action.setShortcut("F1")
        docs_action.triggered.connect(self._show_docs)
        help_menu.addAction(docs_action)

        keyboard_shortcuts_action = QAction("Keyboard Shortcuts", self)
        keyboard_shortcuts_action.triggered.connect(self._show_shortcuts)
        help_menu.addAction(keyboard_shortcuts_action)

        help_menu.addSeparator()

        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_central_widget(self):
        # Main container with header + tabs
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet("background-color: #1f201d; border-bottom: 1px solid #2d2e2b;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 16)

        title = QLabel("LCCN Harvester Pro")
        title.setStyleSheet("font-size: 24px; font-weight: 700; color: #c2d07f; background: transparent;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        main_layout.addWidget(header)

        # Create tab widget
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)

        # Create tabs
        self.dashboard_tab = DashboardTab()
        self.input_tab = InputTab()
        self.targets_tab = TargetsTab()
        self.config_tab = ConfigTab()
        self.harvest_tab = HarvestTab()
        self.results_tab = ResultsTab()
        self.ai_assistant_tab = AIAssistantTab()

        # Connect signals
        self.input_tab.file_selected.connect(self._on_file_selected)
        self.harvest_tab.harvest_started.connect(self._on_harvest_started)
        self.harvest_tab.harvest_finished.connect(self._on_harvest_finished)
        self.harvest_tab.status_message.connect(self._update_status)
        self.harvest_tab.milestone_reached.connect(self._on_milestone_reached)

        # Add tabs to widget
        self.tabs.addTab(self.dashboard_tab, "📊 Dashboard")
        self.tabs.addTab(self.input_tab, "1. Input")
        self.tabs.addTab(self.targets_tab, "2. Targets")
        self.tabs.addTab(self.config_tab, "3. Configuration")
        self.tabs.addTab(self.harvest_tab, "4. Harvest")
        self.tabs.addTab(self.results_tab, "5. Results")

        # AI tab index for show/hide
        self.ai_tab_index = self.tabs.addTab(self.ai_assistant_tab, "🤖 AI Assistant")
        self.tabs.setTabVisible(self.ai_tab_index, False)  # Hidden by default

        # Scroll wrapper for smaller windows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setWidget(self.tabs)
        main_layout.addWidget(scroll)
        self.setCentralWidget(container)

    def _setup_status_bar(self):
        self.status_bar = QStatusBar()
        self.status_bar.setMinimumHeight(32)
        self.setStatusBar(self.status_bar)

        # Main status label
        self.status_label = QLabel("Ready")
        self.status_bar.addWidget(self.status_label)

        # Spacer to push button to the right
        spacer = QWidget()
        self.status_bar.addPermanentWidget(spacer, 1)

        # Keyboard shortcuts hint button
        shortcuts_hint_btn = QPushButton("⌨️ Shortcuts (Ctrl+/)")
        shortcuts_hint_btn.setStyleSheet("""
            QPushButton {
                background: #242521;
                color: #c2d07f;
                font-size: 10px;
                border: 1px solid #2d2e2b;
                border-radius: 3px;
                padding: 4px 8px;
                margin-right: 5px;
            }
            QPushButton:hover {
                background: #2b2c28;
                color: #d2df8e;
                border: 1px solid #3a3b35;
            }
        """)
        shortcuts_hint_btn.clicked.connect(self._show_shortcuts)
        shortcuts_hint_btn.setToolTip("View all keyboard shortcuts (Ctrl+/)")
        self.status_bar.addPermanentWidget(shortcuts_hint_btn)

        # Advanced Mode Toggle Button in status bar
        self.advanced_toggle_btn = QPushButton()
        self.advanced_toggle_btn.setCheckable(True)
        self.advanced_toggle_btn.setChecked(self.advanced_mode)
        self.advanced_toggle_btn.clicked.connect(self._toggle_advanced_mode)
        self.advanced_toggle_btn.setMinimumHeight(28)
        self.advanced_toggle_btn.setMinimumWidth(150)
        self._update_toggle_button_style()
        self.status_bar.addPermanentWidget(self.advanced_toggle_btn)

    def _setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts for the application."""
        # Toggle Advanced Mode - Ctrl+A
        toggle_advanced = QShortcut(QKeySequence("Ctrl+A"), self)
        toggle_advanced.activated.connect(lambda: self.advanced_toggle_btn.click())

        # Tab Navigation - Ctrl+1 through Ctrl+6
        for i in range(6):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{i+1}"), self)
            shortcut.activated.connect(lambda idx=i: self.tabs.setCurrentIndex(idx))

        # Start Harvest - Ctrl+H
        start_harvest = QShortcut(QKeySequence("Ctrl+H"), self)
        start_harvest.activated.connect(self._shortcut_start_harvest)

        # Stop Harvest - Escape or Ctrl+.
        stop_harvest_esc = QShortcut(QKeySequence("Esc"), self)
        stop_harvest_esc.activated.connect(self._shortcut_stop_harvest)

        stop_harvest_ctrl = QShortcut(QKeySequence("Ctrl+."), self)
        stop_harvest_ctrl.activated.connect(self._shortcut_stop_harvest)

        # Refresh Dashboard - Ctrl+R
        refresh_dashboard = QShortcut(QKeySequence("Ctrl+R"), self)
        refresh_dashboard.activated.connect(self._shortcut_refresh_dashboard)

        # Go to Harvest Tab - Ctrl+Shift+H
        go_harvest = QShortcut(QKeySequence("Ctrl+Shift+H"), self)
        go_harvest.activated.connect(lambda: self.tabs.setCurrentWidget(self.harvest_tab))

        # Go to Results Tab - Ctrl+Shift+R
        go_results = QShortcut(QKeySequence("Ctrl+Shift+R"), self)
        go_results.activated.connect(lambda: self.tabs.setCurrentWidget(self.results_tab))

        # Go to Dashboard Tab - Ctrl+Shift+D
        go_dashboard = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        go_dashboard.activated.connect(lambda: self.tabs.setCurrentWidget(self.dashboard_tab))

        # Show Keyboard Shortcuts - Ctrl+/
        show_shortcuts = QShortcut(QKeySequence("Ctrl+/"), self)
        show_shortcuts.activated.connect(self._show_shortcuts)

    def _shortcut_start_harvest(self):
        """Handle Ctrl+H shortcut to start harvest."""
        if not self.harvest_tab.is_running:
            # Switch to harvest tab
            self.tabs.setCurrentWidget(self.harvest_tab)
            # Trigger start if button is enabled
            if self.harvest_tab.start_button.isEnabled():
                self.harvest_tab.start_button.click()
                self._update_status("Harvest started via keyboard shortcut (Ctrl+H)")
            else:
                self._update_status(messages.GuiMessages.err_body_no_input)
                self.notification_manager.notify_harvest_error(
                    messages.GuiMessages.err_body_no_input
                )

    def _shortcut_stop_harvest(self):
        """Handle Esc or Ctrl+. shortcut to stop harvest."""
        if self.harvest_tab.is_running:
            self.harvest_tab.stop_button.click()
            self._update_status("Harvest stopped via keyboard shortcut")

    def _shortcut_refresh_dashboard(self):
        """Handle Ctrl+R shortcut to refresh dashboard."""
        self.dashboard_tab.refresh_data()
        self._update_status("Dashboard refreshed (Ctrl+R)")

    def _toggle_advanced_mode(self, checked):
        """Toggle advanced mode on/off."""
        self.advanced_mode = checked
        self._save_advanced_mode()
        self._apply_advanced_mode()
        self._update_toggle_button_style()
        self.advanced_mode_changed.emit(checked)

        # Update status message
        mode_text = "Advanced Mode" if checked else "Simple Mode"
        features = "AI Assistant + Advanced Tools enabled" if checked else "Basic features only"
        self._update_status(f"{mode_text}: {features}")

    def _update_toggle_button_style(self):
        """Update the toggle button appearance based on state."""
        if self.advanced_mode:
            self.advanced_toggle_btn.setText("🔧 Advanced Mode")
            style = """
                QPushButton {
                    background-color: #c2d07f;
                    color: #1a1a18;
                    font-weight: bold;
                    font-size: 11px;
                    border: 1px solid #c2d07f;
                    border-radius: 3px;
                    padding: 4px 12px;
                }
                QPushButton:hover {
                    background-color: #d2df8e;
                }
                QPushButton:pressed {
                    background-color: #b7c66e;
                }
            """
        else:
            self.advanced_toggle_btn.setText("📋 Simple Mode")
            style = """
                QPushButton {
                    background-color: #242521;
                    color: #e8e6df;
                    font-weight: normal;
                    font-size: 11px;
                    border: 1px solid #2d2e2b;
                    border-radius: 3px;
                    padding: 4px 12px;
                }
                QPushButton:hover {
                    background-color: #2b2c28;
                    border: 1px solid #3a3b35;
                }
                QPushButton:pressed {
                    background-color: #1f201d;
                }
            """

        self.advanced_toggle_btn.setStyleSheet(style)

    def _apply_advanced_mode(self):
        """Apply advanced mode to all tabs."""
        self.advanced_settings_action.setVisible(self.advanced_mode)
        self.tools_menu.menuAction().setVisible(self.advanced_mode)

        # Show/hide AI Assistant tab
        self.tabs.setTabVisible(self.ai_tab_index, self.advanced_mode)

        # Notify tabs of mode change
        for tab in [self.dashboard_tab, self.input_tab, self.targets_tab, self.config_tab,
                    self.harvest_tab, self.results_tab, self.ai_assistant_tab]:
            if hasattr(tab, 'set_advanced_mode'):
                tab.set_advanced_mode(self.advanced_mode)


    def _show_advanced_settings(self):
        """Show advanced settings dialog."""
        dialog = AdvancedSettingsDialog(self)
        dialog.exec()

    def _on_file_selected(self, file_path):
        """Handle file selection from input tab."""
        self.harvest_tab.set_input_file(file_path)
        self._update_status(f"Input file selected: {Path(file_path).name}")

    def _on_harvest_started(self):
        """Handle harvest start."""
        self._update_status("Harvest started...")
        # Send notification (will be updated with actual count from harvest tab)
        self.notification_manager.show_notification(
            "Harvest Started",
            "Processing ISBNs...",
            "info"
        )

    def _on_harvest_finished(self, success, stats):
        """Handle harvest completion."""
        if success:
            self._update_status(f"Harvest completed: {stats.get('found', 0)} found, {stats.get('failed', 0)} failed")
            self.results_tab.refresh()
            self.dashboard_tab.refresh_data()  # Refresh dashboard

            # Send success notification
            self.notification_manager.notify_harvest_completed(stats)
        else:
            self._update_status("Harvest failed or cancelled")

            # Send error notification
            error_msg = stats.get('error', 'Unknown error') if isinstance(stats, dict) else 'Harvest was cancelled'
            self.notification_manager.notify_harvest_error(error_msg)

    def _update_status(self, message):
        """Update status bar message."""
        self.status_label.setText(message)

    def _on_milestone_reached(self, milestone_type, value):
        """Handle harvest milestone notifications."""
        self.notification_manager.notify_milestone(milestone_type, value)

    def _refresh_results(self):
        """Refresh results tab."""
        self.results_tab.refresh()
        self._update_status("Results refreshed")

    def _clear_cache(self):
        """Clear database cache."""
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "Clear Cache",
            "This will clear all cached results from the database.\n"
            "Failed attempts will also be cleared.\n\n"
            "Are you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                from database import DatabaseManager
                db = DatabaseManager()
                with db.connect() as conn:
                    conn.execute("DELETE FROM main")
                    conn.execute("DELETE FROM attempted")
                    conn.commit()
                QMessageBox.information(self, "Success", "Cache cleared successfully")
                self._update_status("Cache cleared")
                self.results_tab.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear cache: {str(e)}")

    def _run_benchmark(self):
        """Run performance benchmark."""
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Benchmark",
            "Benchmark feature coming soon!\n\n"
            "This will test:\n"
            "• API response times\n"
            "• Database query performance\n"
            "• Z39.50 connection speeds\n"
            "• Overall throughput"
        )

    def _show_docs(self):
        """Show documentation."""
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Documentation",
            "Documentation:\n\n"
            "See docs/ folder for comprehensive documentation including:\n"
            "• User Guide\n"
            "• Technical Documentation\n"
            "• API References\n"
            "• MARC Standards\n\n"
            "Or visit: https://github.com/your-repo/lccn-harvester"
        )

    def _show_shortcuts(self):
        """Show keyboard shortcuts."""
        dialog = ShortcutsDialog(self)
        dialog.exec()

    def _show_about(self):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.about(
            self,
            "About LCCN Harvester",
            "LCCN Harvester v1.0\n\n"
            "A tool for harvesting Library of Congress Call Numbers (LCCNs) from ISBNs.\n\n"
            "Built with Python 3 and PyQt6\n"
            "Licensed under MIT Open Source License\n\n"
            "Client: Melissa Belvadi, UPEI\n"
            "Development Team: Ahmed, Abdo, Eyad, Hashem, Karim"
        )

    def closeEvent(self, event):
        """Handle window close event."""
        if self.harvest_tab.is_running:
            from PyQt6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self,
                "Harvest in Progress",
                "A harvest is currently running.\n\n"
                "Are you sure you want to exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

            self.harvest_tab.stop_harvest()

        event.accept()
