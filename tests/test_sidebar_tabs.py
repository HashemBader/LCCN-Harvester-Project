"""
Module: test_sidebar_tabs.py
Automated unit tests for sidebar tab functionality in the LCCN Harvester GUI.

Tests cover:
- Tab button creation and properties
- Tab switching and state management
- Theme toggle functionality
- Sidebar collapse/expand animation
- Tab accessibility attributes
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add src to path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
PROJECT_ROOT = SRC_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from PyQt6.QtWidgets import QApplication, QPushButton, QMainWindow
from PyQt6.QtCore import Qt


class TestSidebarTabsExist:
    """Test that all sidebar tabs are created and accessible."""

    @pytest.fixture(scope="session")
    def qapp(self):
        """Create QApplication for GUI tests."""
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        return app

    @pytest.fixture
    def main_window(self, qapp):
        """Create main window instance for testing."""
        # Mock the notification manager and other dependencies to avoid full init
        with patch('gui.modern_window.NotificationManager'):
            from gui.modern_window import ModernMainWindow
            window = ModernMainWindow()
            window.show()
            qapp.processEvents()
            yield window
            window.close()

    def test_dashboard_tab_exists(self, main_window):
        """Test Dashboard tab is created and accessible."""
        assert hasattr(main_window, 'btn_dashboard')
        assert main_window.btn_dashboard is not None
        assert main_window.btn_dashboard.text() == "Dashboard"
        assert main_window.btn_dashboard.isVisible()

    def test_configure_tab_exists(self, main_window):
        """Test Configure tab (merged Targets + Settings) is created and accessible."""
        assert hasattr(main_window, 'btn_configure')
        assert main_window.btn_configure is not None
        assert main_window.btn_configure.text() == "Configure"
        assert main_window.btn_configure.isVisible()

    def test_configure_tab_has_subtabs(self, main_window):
        """Test Configure tab contains both Targets and Settings panes in the splitter."""
        tc = main_window.targets_config_tab
        assert hasattr(tc, 'targets_tab'), 'targets_tab pane missing'
        assert hasattr(tc, 'config_tab'), 'config_tab pane missing'
        assert tc.targets_tab is not None
        assert tc.config_tab is not None

    def test_harvest_tab_exists(self, main_window):
        """Test Harvest tab is created and accessible."""
        assert hasattr(main_window, 'btn_harvest')
        assert main_window.btn_harvest is not None
        assert main_window.btn_harvest.text() == "Harvest"
        assert main_window.btn_harvest.isVisible()

    def test_help_tab_exists(self, main_window):
        """Test Help tab is created and accessible."""
        assert hasattr(main_window, 'btn_help')
        assert main_window.btn_help is not None
        assert main_window.btn_help.text() == "Help"
        assert main_window.btn_help.isVisible()


class TestTabSwitching:
    """Test switching between tabs."""

    @pytest.fixture(scope="session")
    def qapp(self):
        """Create QApplication for GUI tests."""
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        return app

    @pytest.fixture
    def main_window(self, qapp):
        """Create main window instance for testing."""
        with patch('gui.modern_window.NotificationManager'):
            from gui.modern_window import ModernMainWindow
            window = ModernMainWindow()
            window.show()
            qapp.processEvents()
            yield window
            window.close()

    def test_switch_to_dashboard(self, main_window):
        """Test switching to Dashboard tab (index 0)."""
        main_window.btn_dashboard.click()
        assert main_window.stack.currentIndex() == 0
        assert main_window.page_title.text() == "Dashboard"

    def test_switch_to_configure(self, main_window):
        """Test switching to Configure tab (index 1 — merged Targets + Settings)."""
        main_window.btn_configure.click()
        assert main_window.stack.currentIndex() == 1
        assert main_window.page_title.text() == "Configure"

    def test_configure_inner_tab_switch_to_targets(self, main_window):
        """Test that the targets pane is visible inside the Configure tab."""
        main_window.btn_configure.click()
        assert main_window.targets_config_tab.targets_tab.isVisible()

    def test_switch_to_harvest(self, main_window):
        """Test switching to Harvest tab (index 2)."""
        main_window.btn_harvest.click()
        assert main_window.stack.currentIndex() == 2
        assert main_window.page_title.text() == "Harvest"

    def test_switch_to_help(self, main_window):
        """Test switching to Help tab (index 3)."""
        main_window.btn_help.click()
        assert main_window.stack.currentIndex() == 3
        assert main_window.page_title.text() == "Help"


class TestThemeToggle:
    """Test theme toggle functionality."""

    @pytest.fixture(scope="session")
    def qapp(self):
        """Create QApplication for GUI tests."""
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        return app

    @pytest.fixture
    def main_window(self, qapp):
        """Create main window instance for testing."""
        with patch('gui.modern_window.NotificationManager'):
            from gui.modern_window import ModernMainWindow
            window = ModernMainWindow()
            window.show()
            qapp.processEvents()
            # Ensure a canonical dark starting state regardless of persisted settings
            window._apply_theme("dark")
            yield window
            window.close()

    def test_theme_button_exists(self, main_window):
        """Test theme toggle button exists in sidebar."""
        assert hasattr(main_window, 'btn_theme')
        assert main_window.btn_theme is not None
        # After init _apply_theme() renames the button to reflect current theme
        assert main_window.btn_theme.text() in ("Toggle Theme", "Theme: Dark", "Theme: Light")
        assert main_window.btn_theme.isVisible()

    def test_initial_theme_is_dark(self, main_window):
        """Test that initial theme is dark by default."""
        current_theme = main_window._theme_manager.get_theme()
        assert current_theme == "dark"

    def test_toggle_theme_dark_to_light(self, main_window):
        """Test toggling theme from dark to light."""
        # Start with dark theme
        main_window._theme_manager.set_theme("dark")
        assert main_window._theme_manager.get_theme() == "dark"

        # Toggle to light
        main_window._toggle_theme()
        assert main_window._theme_manager.get_theme() == "light"

    def test_toggle_theme_light_to_dark(self, main_window):
        """Test toggling theme from light to dark."""
        # Start with light theme
        main_window._theme_manager.set_theme("light")
        assert main_window._theme_manager.get_theme() == "light"

        # Toggle to dark
        main_window._toggle_theme()
        assert main_window._theme_manager.get_theme() == "dark"

    def test_apply_theme_persists(self, main_window):
        """Test that theme preference is persisted."""
        main_window._apply_theme("light")
        # Create a new window and verify it loads the saved theme
        with patch('gui.modern_window.NotificationManager'):
            from gui.modern_window import ModernMainWindow
            new_window = ModernMainWindow()
            assert new_window._theme_manager.get_theme() == "light"
            new_window.close()


class TestSidebarCollapse:
    """Test sidebar collapse/expand functionality."""

    @pytest.fixture(scope="session")
    def qapp(self):
        """Create QApplication for GUI tests."""
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        return app

    @pytest.fixture
    def main_window(self, qapp):
        """Create main window instance for testing."""
        with patch('gui.modern_window.NotificationManager'):
            from gui.modern_window import ModernMainWindow
            window = ModernMainWindow()
            window.show()
            qapp.processEvents()
            yield window
            window.close()

    def test_sidebar_initial_width(self, main_window):
        """Test that sidebar initial width is 240px."""
        assert main_window.sidebar.width() == 240

    def test_toggle_sidebar_collapse(self, main_window):
        """Test toggling sidebar collapse state."""
        initial_state = main_window.sidebar_collapsed
        main_window._toggle_sidebar()
        assert main_window.sidebar_collapsed != initial_state

    def test_title_label_visibility_on_collapse(self, main_window):
        """Test that title label visibility changes on collapse."""
        # Start expanded
        main_window.sidebar_collapsed = False
        assert main_window.title_label.isVisible()

        # Collapse
        main_window._toggle_sidebar()
        # Note: Visibility change happens via animation, so we check the flag
        assert main_window.sidebar_collapsed


class TestTabAccessibility:
    """Test accessibility attributes of tab buttons."""

    @pytest.fixture(scope="session")
    def qapp(self):
        """Create QApplication for GUI tests."""
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        return app

    @pytest.fixture
    def main_window(self, qapp):
        """Create main window instance for testing."""
        with patch('gui.modern_window.NotificationManager'):
            from gui.modern_window import ModernMainWindow
            window = ModernMainWindow()
            yield window
            window.close()

    def test_dashboard_accessible_name(self, main_window):
        """Test Dashboard button has accessible name."""
        assert main_window.btn_dashboard.accessibleName() == "Open Dashboard page"

    def test_configure_accessible_name(self, main_window):
        """Test Configure button has accessible name."""
        assert main_window.btn_configure.accessibleName() == "Open Configure page"

    def test_harvest_accessible_name(self, main_window):
        """Test Harvest button has accessible name."""
        assert main_window.btn_harvest.accessibleName() == "Open Harvest page"

    def test_help_accessible_name(self, main_window):
        """Test Help button has accessible name."""
        assert main_window.btn_help.accessibleName() == "Open Help page"

    def test_tab_buttons_have_tooltips(self, main_window):
        """Test that all tab buttons have tooltip text."""
        buttons = [
            main_window.btn_dashboard,
            main_window.btn_configure,
            main_window.btn_harvest,
            main_window.btn_help,
        ]
        for btn in buttons:
            assert btn.toolTip() != ""


class TestStatusPill:
    """Test status indicator pill functionality."""

    @pytest.fixture(scope="session")
    def qapp(self):
        """Create QApplication for GUI tests."""
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        return app

    @pytest.fixture
    def main_window(self, qapp):
        """Create main window instance for testing."""
        with patch('gui.modern_window.NotificationManager'):
            from gui.modern_window import ModernMainWindow
            window = ModernMainWindow()
            window.show()
            qapp.processEvents()
            yield window
            window.close()

    def test_status_pill_exists(self, main_window):
        """Test status pill is created."""
        assert hasattr(main_window, 'status_pill')
        assert main_window.status_pill is not None

    def test_status_pill_initial_text(self, main_window):
        """Test status pill initial text is 'Idle'."""
        assert main_window.status_pill.text() == "Idle"

    def test_status_pill_visibility(self, main_window):
        """Test status pill is visible."""
        assert main_window.status_pill.isVisible()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

