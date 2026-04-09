import importlib
import sys

from src.config.profile_manager import ProfileManager
from src.database import DatabaseManager, MainRecord


def test_get_db_path_returns_shared_db_for_all_profiles(monkeypatch, tmp_path):
    app_paths = importlib.import_module("src.config.app_paths")
    monkeypatch.setitem(sys.modules, "config.app_paths", app_paths)
    monkeypatch.setattr(app_paths, "get_app_root", lambda: tmp_path)

    profile_manager = ProfileManager()

    default_path = profile_manager.get_db_path("Default Settings")
    custom_path = profile_manager.get_db_path("Abdel")

    expected = tmp_path / "data" / "lccn_harvester.sqlite3"
    assert default_path == expected
    assert custom_path == expected


def test_get_db_path_merges_legacy_profile_db_into_shared(monkeypatch, tmp_path):
    app_paths = importlib.import_module("src.config.app_paths")
    monkeypatch.setitem(sys.modules, "config.app_paths", app_paths)
    monkeypatch.setattr(app_paths, "get_app_root", lambda: tmp_path)

    profile_manager = ProfileManager()
    legacy_path = tmp_path / "data" / "abdel" / "lccn_harvester.sqlite3"

    legacy_db = DatabaseManager(legacy_path)
    legacy_db.init_db()
    legacy_db.upsert_main(
        MainRecord(
            isbn="9780132350884",
            lccn="QA76.73.P98",
            lccn_source="LegacyProfile",
            date_added=20260331,
        )
    )
    legacy_db.upsert_attempted(
        isbn="9780132350884",
        last_target="LegacyTarget",
        attempt_type="lccn",
        attempted_time=20260331,
        last_error="No records found in LegacyTarget.",
    )
    with legacy_db.transaction() as conn:
        legacy_db.upsert_linked_isbns_many(conn, [("0132350882", "9780132350884")])

    shared_path = profile_manager.get_db_path("Abdel")
    shared_db = DatabaseManager(shared_path)
    shared_db.init_db()

    main_row = shared_db.get_main("9780132350884")
    attempted_row = shared_db.get_attempted_for("9780132350884", "LegacyTarget", "lccn")
    linked = shared_db.get_linked_isbns("0132350882")
    marker = tmp_path / "data" / "abdel" / ".shared_db_merged"

    assert main_row is not None
    assert main_row.lccn == "QA76.73.P98"
    assert main_row.lccn_source == "LegacyProfile"
    assert attempted_row is not None
    assert attempted_row.last_error == "No records found in LegacyTarget."
    assert linked == ["9780132350884"]
    assert marker.exists()
