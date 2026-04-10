import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication, QSizePolicy


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
for path in (str(PROJECT_ROOT), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def harvest_tab(qapp):
    from src.gui.harvest_tab import HarvestTab, UIState

    tab = HarvestTab()
    tab.show()
    qapp.processEvents()
    assert tab.current_state == UIState.IDLE
    yield tab
    tab.close()


def test_set_input_file_enables_start_for_valid_tsv(harvest_tab, qapp, tmp_path):
    """Uploading a valid ISBN file should leave the tab ready to harvest."""
    input_path = tmp_path / "isbns.tsv"
    input_path.write_text("isbn\n9780131103627\n", encoding="utf-8")

    harvest_tab.set_input_file(str(input_path))
    qapp.processEvents()

    assert harvest_tab.input_file == str(input_path)
    assert harvest_tab.btn_start.isEnabled()
    assert harvest_tab.current_state.name == "READY"
    assert harvest_tab.log_output.text() == "Ready to harvest 1 unique ISBNs."
    assert harvest_tab.lbl_val_loaded.text() == "1"


def test_completed_layout_keeps_top_cards_pinned(harvest_tab, qapp):
    """The completion banner should not stretch the top cards out of place."""
    from src.gui.harvest_tab import UIState

    harvest_tab._transition_state(UIState.COMPLETED)
    qapp.processEvents()

    margins = harvest_tab.content_grid.contentsMargins()
    assert margins.top() == 6
    assert harvest_tab.content_grid.rowStretch(0) == 0
    assert harvest_tab.content_grid.rowStretch(1) == 1
    assert harvest_tab.input_card.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Preferred
    assert harvest_tab.stats_card.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Preferred


def test_clear_input_resets_file_preview(harvest_tab, qapp, tmp_path):
    """Clearing the loaded file should restore the preview widget to its empty state."""
    input_path = tmp_path / "isbns.tsv"
    input_path.write_text("isbn\n9780131103627\n9780306406157\n", encoding="utf-8")

    harvest_tab.set_input_file(str(input_path))
    qapp.processEvents()

    assert harvest_tab.preview_table.rowCount() > 0
    assert harvest_tab.lbl_preview_filename.text() != "No file selected"

    harvest_tab._clear_input()
    qapp.processEvents()

    assert harvest_tab.preview_table.columnCount() == 2
    assert harvest_tab.preview_table.rowCount() == 0
    assert harvest_tab.preview_table.horizontalHeaderItem(0).text() == "ISBN"
    assert harvest_tab.preview_table.horizontalHeaderItem(1).text() == "Status"
    assert harvest_tab.lbl_preview_filename.text() == "No file selected"
