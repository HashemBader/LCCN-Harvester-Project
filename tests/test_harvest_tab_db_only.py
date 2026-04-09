import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
PROJECT_ROOT = SRC_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


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
    tab.input_file = "dummy.txt"
    tab.set_data_sources(
        lambda: {"retry_days": 3, "call_number_mode": "lccn"},
        lambda: [
            {"selected": True, "name": "Library of Congress", "type": "api"},
            {"selected": True, "name": "Harvard", "type": "api"},
        ],
    )
    yield tab
    tab.close()


def test_start_clicked_allows_db_only_run_when_no_targets_selected(harvest_tab, monkeypatch):
    harvest_tab.set_data_sources(
        lambda: {"retry_days": 3, "call_number_mode": "lccn"},
        lambda: [
            {"selected": False, "name": "Library of Congress", "type": "api"},
            {"selected": False, "name": "Harvard", "type": "api"},
        ],
    )

    monkeypatch.setattr(harvest_tab, "_check_recent_not_found_isbns", lambda retry_days: set())
    monkeypatch.setattr(harvest_tab, "_confirm_db_only_without_targets", lambda: True)

    captured = {}

    def fake_start_worker(config, targets, bypass_retry_isbns=None):
        captured["config"] = dict(config)
        captured["targets"] = list(targets)

    monkeypatch.setattr(harvest_tab, "_start_worker", fake_start_worker)

    harvest_tab._on_start_clicked()

    assert captured["config"]["db_only"] is True
    assert captured["targets"] == [
        {"selected": False, "name": "Library of Congress", "type": "api"},
        {"selected": False, "name": "Harvard", "type": "api"},
    ]
    assert harvest_tab.log_output.text() == "No targets selected. Running against the existing database only."


def test_start_clicked_cancels_when_no_targets_selected_and_user_cancels(harvest_tab, monkeypatch):
    harvest_tab.set_data_sources(
        lambda: {"retry_days": 3, "call_number_mode": "lccn"},
        lambda: [
            {"selected": False, "name": "Library of Congress", "type": "api"},
        ],
    )

    monkeypatch.setattr(harvest_tab, "_check_recent_not_found_isbns", lambda retry_days: set())
    monkeypatch.setattr(harvest_tab, "_confirm_db_only_without_targets", lambda: False)

    called = {"started": False}

    def fake_start_worker(config, targets, bypass_retry_isbns=None):
        called["started"] = True

    monkeypatch.setattr(harvest_tab, "_start_worker", fake_start_worker)

    harvest_tab._on_start_clicked()

    assert called["started"] is False
    assert harvest_tab.log_output.text() == "Harvest cancelled: no targets selected."


def test_start_clicked_allows_explicit_db_only_even_with_selected_targets(harvest_tab, monkeypatch):
    monkeypatch.setattr(harvest_tab, "_check_recent_not_found_isbns", lambda retry_days: set())

    captured = {}

    def fake_start_worker(config, targets, bypass_retry_isbns=None):
        captured["config"] = dict(config)
        captured["targets"] = list(targets)
        captured["bypass_retry_isbns"] = set(bypass_retry_isbns or [])

    monkeypatch.setattr(harvest_tab, "_start_worker", fake_start_worker)

    harvest_tab.chk_db_only.setChecked(True)
    harvest_tab._on_start_clicked()

    assert captured["config"]["db_only"] is True
    assert captured["targets"] == [
        {"selected": True, "name": "Library of Congress", "type": "api"},
        {"selected": True, "name": "Harvard", "type": "api"},
    ]
    assert captured["bypass_retry_isbns"] == set()
    assert harvest_tab.log_output.text() == "Database-only mode enabled for this run. Skipping live targets."
