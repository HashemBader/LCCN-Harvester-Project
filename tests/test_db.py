"""
Module: test_db.py
Part of the LCCN Harvester Project.
"""
from pathlib import Path

from src.database.db_manager import DatabaseManager, MainRecord


def test_db_init_and_main_roundtrip(tmp_path: Path):
    db_path = tmp_path / "test.sqlite3"
    db = DatabaseManager(db_path)
    db.init_db()

    rec = MainRecord(isbn="9780132350884", lccn="QA76.76", source="LoC")
    db.upsert_main(rec)

    got = db.get_main("9780132350884")
    assert got is not None
    assert got.isbn == "9780132350884"
    assert got.lccn == "QA76.76"
    # classification should be auto-derived from lccn
    assert got.classification == "QA"
    assert got.source == "LoC"


def test_attempted_upsert_increments_fail_count(tmp_path: Path):
    db_path = tmp_path / "test.sqlite3"
    db = DatabaseManager(db_path)
    db.init_db()

    db.upsert_attempted(isbn="0000000000", last_target="Harvard", last_error="Not found")
    a1 = db.get_attempted("0000000000")
    assert a1 is not None
    assert a1.fail_count == 1

    db.upsert_attempted(isbn="0000000000", last_target="Harvard", last_error="Not found again")
    a2 = db.get_attempted("0000000000")
    assert a2 is not None
    assert a2.fail_count == 2
    assert a2.last_error == "Not found again"


def test_should_skip_retry(tmp_path: Path):
    db_path = tmp_path / "test.sqlite3"
    db = DatabaseManager(db_path)
    db.init_db()

    # Not attempted yet -> do not skip
    assert db.should_skip_retry("1111111111", retry_days=7) is False

    # Log an attempt now -> should skip for retry_days >= 1
    db.upsert_attempted(isbn="1111111111", last_target="Test", last_error="x")
    assert db.should_skip_retry("1111111111", retry_days=7) is True
