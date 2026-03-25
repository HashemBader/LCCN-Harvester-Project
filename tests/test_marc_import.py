from __future__ import annotations

import sys

import src.config.app_paths as src_config_app_paths
import src.config as src_config_package

sys.modules.setdefault("config", src_config_package)
sys.modules.setdefault("config.app_paths", src_config_app_paths)

import config.app_paths as config_app_paths

from src.config.profile_manager import ProfileManager
from src.database import DatabaseManager
from src.harvester.marc_import import MarcImportService


def test_marc_import_persists_main_attempted_and_active_profile_source(tmp_path, monkeypatch):
    app_root = tmp_path / "app"
    app_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config_app_paths, "get_app_root", lambda: app_root)
    monkeypatch.setattr(src_config_app_paths, "get_app_root", lambda: app_root)

    profile_manager = ProfileManager()
    profile_manager.set_active_profile("Default Settings")

    db_path = tmp_path / "marc_import.sqlite3"
    service = MarcImportService(
        db_path,
        profile_manager=profile_manager,
    )

    successful_record = {
        "fields": [
            {"020": {"subfields": [{"a": "978-0-13-235088-4"}, {"a": "0132350882"}]}},
            {"050": {"subfields": [{"a": "QA76.76"}, {"b": "C65 2004"}]}},
        ]
    }
    attempted_record = {
        "fields": [
            {"020": {"subfields": [{"a": "9780596007973"}]}},
        ]
    }
    skipped_record = {
        "fields": [
            {"050": {"subfields": [{"a": "QA99"}, {"b": "A1"}]}},
        ]
    }

    summary = service.import_json_records(
        [successful_record, attempted_record, skipped_record],
        source_name="Manual MARC Import",
        import_date=20260324,
    )

    assert summary.main_rows == 1
    assert summary.attempted_rows == 1
    assert summary.skipped_records == 1

    db = DatabaseManager(db_path)
    stored = db.get_main("0132350882")
    assert stored is not None
    assert stored.lccn == "QA76.76 C65 2004"
    assert stored.lccn_source == "Manual MARC Import"
    assert stored.date_added == "2026-03-24"
    assert db.get_linked_isbns("0132350882") == ["9780132350884"]

    attempted = db.get_attempted_for("9780596007973", "Manual MARC Import", "both")
    assert attempted is not None
    assert attempted.last_attempted == 20260324
    assert attempted.last_error == "MARC import record missing call number"

    assert profile_manager.get_active_profile_setting("last_marc_import_source") == "Manual MARC Import"
