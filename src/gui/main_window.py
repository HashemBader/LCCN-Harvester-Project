"""
Module: main_window.py
Main application window for the LCCN Harvester GUI.
"""
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QStatusBar, QLabel, QToolBar, QPushButton
)
from PyQt6.QtGui import QAction, QIcon
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


class MainWindow(QMainWindow):
    advanced_mode_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LCCN Harvester")
        self.setGeometry(100, 100, 1200, 800)

        # Load advanced mode preference
        self.settings_file = Path("data/gui_settings.json")
        self.advanced_mode = self._load_advanced_mode()

        self._setup_menu_bar()
        self._setup_central_widget()
        self._setup_status_bar()
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

        self.setCentralWidget(self.tabs)

    def _setup_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Main status label
        self.status_label = QLabel("Ready")
        self.status_bar.addWidget(self.status_label)

        # Spacer to push button to the right
        spacer = QWidget()
        self.status_bar.addPermanentWidget(spacer, 1)

        # Advanced Mode Toggle Button in status bar
        self.advanced_toggle_btn = QPushButton()
        self.advanced_toggle_btn.setCheckable(True)
        self.advanced_toggle_btn.setChecked(self.advanced_mode)
        self.advanced_toggle_btn.clicked.connect(self._toggle_advanced_mode)
        self.advanced_toggle_btn.setMinimumHeight(28)
        self.advanced_toggle_btn.setMinimumWidth(150)
        self._update_toggle_button_style()
        self.status_bar.addPermanentWidget(self.advanced_toggle_btn)

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
                    background-color: #7c3aed;
                    color: white;
                    font-weight: bold;
                    font-size: 11px;
                    border: 1px solid #6d28d9;
                    border-radius: 3px;
                    padding: 4px 12px;
                }
                QPushButton:hover {
                    background-color: #6d28d9;
                }
                QPushButton:pressed {
                    background-color: #5b21b6;
                }
            """
        else:
            self.advanced_toggle_btn.setText("📋 Simple Mode")
            style = """
                QPushButton {
                    background-color: #f0f0f0;
                    color: #333333;
                    font-weight: normal;
                    font-size: 11px;
                    border: 1px solid #cccccc;
                    border-radius: 3px;
                    padding: 4px 12px;
                }
                QPushButton:hover {
                    background-color: #e0e0e0;
                    border: 1px solid #999999;
                }
                QPushButton:pressed {
                    background-color: #d0d0d0;
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

    def _on_harvest_finished(self, success, stats):
        """Handle harvest completion."""
        if success:
            self._update_status(f"Harvest completed: {stats.get('found', 0)} found, {stats.get('failed', 0)} failed")
            self.results_tab.refresh()
            self.dashboard_tab.refresh_data()  # Refresh dashboard
        else:
            self._update_status("Harvest failed or cancelled")

    def _update_status(self, message):
        """Update status bar message."""
        self.status_label.setText(message)

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
        from PyQt6.QtWidgets import QMessageBox
        shortcuts_text = """
Keyboard Shortcuts:

General:
  Ctrl+Q        - Quit application
  F1            - Show documentation
  F5            - Refresh results
  Ctrl+A        - Toggle Advanced Mode

Navigation:
  Ctrl+1-5      - Switch between tabs
  Tab           - Next field
  Shift+Tab     - Previous field

Harvest:
  Ctrl+H        - Start harvest
  Ctrl+.        - Stop harvest
  Ctrl+P        - Pause/Resume harvest
"""
        QMessageBox.information(
            self,
            "Keyboard Shortcuts",
            shortcuts_text
        )

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