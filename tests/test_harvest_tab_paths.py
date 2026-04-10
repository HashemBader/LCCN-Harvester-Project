import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication


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
    from src.gui.harvest_tab import HarvestTab

    tab = HarvestTab()
    tab.show()
    qapp.processEvents()
    yield tab
    tab.close()


def test_open_output_folder_path_uses_qt_desktop_services(harvest_tab, monkeypatch, tmp_path):
    opened = {}

    def fake_open_url(url):
        opened["path"] = url.toLocalFile()
        return True

    monkeypatch.setattr("src.gui.harvest_tab.QDesktopServices.openUrl", fake_open_url)

    folder = tmp_path / "exports"
    harvest_tab._open_output_folder_path(folder)

    assert folder.exists()
    assert opened["path"] == str(folder.resolve())


def test_open_local_path_warns_when_missing(harvest_tab, monkeypatch, tmp_path):
    warnings = []

    def fake_warning(_parent, title, text):
        warnings.append((title, text))

    monkeypatch.setattr("src.gui.harvest_tab.QMessageBox.warning", fake_warning)

    missing = tmp_path / "missing.tsv"
    result = harvest_tab._open_local_path(missing, missing_title="Not Found", open_title="Open Failed")

    assert result is False
    assert warnings == [("Not Found", f"Path does not exist:\n{missing.name}")]
