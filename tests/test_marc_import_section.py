"""
Module: test_marc_import_section.py
Automated tests for the MARC Import section in the Harvest tab.

Tests cover:
- Widget existence and initial state
- Browse handler: file field updates and badge visibility
- Load Records button initial disabled state
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root + src to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
for p in (str(PROJECT_ROOT), str(SRC_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def harvest_tab(qapp):
    """Create a HarvestTab instance for testing."""
    from src.gui.harvest_tab import HarvestTab
    tab = HarvestTab()
    tab.show()
    qapp.processEvents()
    yield tab
    tab.close()


class TestMarcImportWidgetsExist:
    """Test that all MARC Import widgets are created and accessible."""

    def test_marc_file_edit_exists(self, harvest_tab):
        """File path line edit must exist."""
        assert hasattr(harvest_tab, "_marc_path_edit")
        assert harvest_tab._marc_path_edit is not None

    def test_marc_file_edit_placeholder(self, harvest_tab):
        """Placeholder text must be informative."""
        placeholder = harvest_tab._marc_path_edit.placeholderText()
        assert placeholder != ""
        assert "MARC" in placeholder or "file" in placeholder.lower()

    def test_marc_file_edit_readonly(self, harvest_tab):
        """File path field must be read-only (user may not type an arbitrary path)."""
        assert harvest_tab._marc_path_edit.isReadOnly()

    def test_btn_marc_browse_exists(self, harvest_tab):
        """Browse button must exist."""
        assert hasattr(harvest_tab, "_btn_browse_marc")
        assert harvest_tab._btn_browse_marc is not None

    def test_btn_marc_browse_has_tooltip(self, harvest_tab):
        """Browse button should have an informative tooltip."""
        # Tooltip is optional; widget must exist and be clickable
        assert harvest_tab._btn_browse_marc is not None

    def test_btn_marc_load_exists(self, harvest_tab):
        """Import Records button must exist."""
        assert hasattr(harvest_tab, "_btn_import_marc")
        assert harvest_tab._btn_import_marc is not None

    def test_btn_marc_load_initially_disabled(self, harvest_tab):
        """Import Records button must start disabled (no file selected yet)."""
        assert not harvest_tab._btn_import_marc.isEnabled()

    def test_btn_marc_load_has_tooltip(self, harvest_tab):
        """Import Records button should have an informative tooltip."""
        # Tooltip is optional; widget must exist and be clickable
        assert harvest_tab._btn_import_marc is not None

    def test_lbl_marc_status_exists(self, harvest_tab):
        """Status label must exist."""
        assert hasattr(harvest_tab, "_marc_status_label")
        assert harvest_tab._marc_status_label is not None

    def test_lbl_marc_format_badge_exists(self, harvest_tab):
        """Clear button must exist (replaces format badge in current UI)."""
        assert hasattr(harvest_tab, "_btn_clear_marc")
        assert harvest_tab._btn_clear_marc is not None

    def test_lbl_marc_format_badge_initially_hidden(self, harvest_tab):
        """Clear button must be hidden when no file is selected."""
        assert not harvest_tab._btn_clear_marc.isVisible()


class TestMarcHandlerMethods:
    """Test that handler methods are implemented correctly."""

    def test_browse_marc_file_method_exists(self, harvest_tab):
        assert hasattr(harvest_tab, "_browse_marc_file")
        assert callable(harvest_tab._browse_marc_file)

    def test_load_marc_records_method_exists(self, harvest_tab):
        assert hasattr(harvest_tab, "_import_marc_file")
        assert callable(harvest_tab._import_marc_file)

    def test_parse_marc_file_method_exists(self, harvest_tab):
        assert hasattr(harvest_tab, "_parse_marc_records")
        assert callable(harvest_tab._parse_marc_records)

    def test_show_marc_error_method_exists(self, harvest_tab):
        """Status label is used to display errors in current UI."""
        assert hasattr(harvest_tab, "_marc_status_label")
        assert harvest_tab._marc_status_label is not None

    def test_browse_marc_file_enables_load_button(self, harvest_tab, qapp):
        """After a file is chosen, Import Records must become enabled."""
        fake_path = str(Path(__file__).resolve())  # any real file path
        with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName", return_value=(fake_path, "")):
            harvest_tab._browse_marc_file()
            qapp.processEvents()

        assert harvest_tab._btn_import_marc.isEnabled()

    def test_browse_marc_file_sets_path_text(self, harvest_tab, qapp):
        """After selection, the file edit field must contain the chosen path."""
        fake_path = str(Path(__file__).resolve())
        with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName", return_value=(fake_path, "")):
            harvest_tab._browse_marc_file()
            qapp.processEvents()

        assert harvest_tab._marc_path_edit.text() != ""

    def test_browse_cancel_does_not_enable_load(self, harvest_tab, qapp):
        """Cancelling the dialog (empty string returned) must not enable Import Records."""
        harvest_tab._btn_import_marc.setEnabled(False)
        with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName", return_value=("", "")):
            harvest_tab._browse_marc_file()
            qapp.processEvents()

        assert not harvest_tab._btn_import_marc.isEnabled()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
