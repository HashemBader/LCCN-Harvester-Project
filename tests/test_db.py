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
    """fail_count increments are scoped to (isbn, target, type) — not global."""
    db_path = tmp_path / "test.sqlite3"
    db = DatabaseManager(db_path)
    db.init_db()

    db.upsert_attempted(isbn="0000000000", last_target="Harvard", attempt_type="both", last_error="Not found")
    # Use the precise per-target lookup — not the coarse get_attempted(isbn) — to
    # prove that the increment is target/type-specific.
    a1 = db.get_attempted_for("0000000000", "Harvard", "both")
    assert a1 is not None
    assert a1.fail_count == 1

    db.upsert_attempted(isbn="0000000000", last_target="Harvard", attempt_type="both", last_error="Not found again")
    a2 = db.get_attempted_for("0000000000", "Harvard", "both")
    assert a2 is not None
    assert a2.fail_count == 2
    assert a2.last_error == "Not found again"

    # A second target for the same ISBN keeps its own independent counter.
    db.upsert_attempted(isbn="0000000000", last_target="LoC", attempt_type="both", last_error="Timeout")
    loc = db.get_attempted_for("0000000000", "LoC", "both")
    assert loc is not None
    assert loc.fail_count == 1, "LoC counter must be independent of Harvard counter"

    # The type axis is also independent.
    db.upsert_attempted(isbn="0000000000", last_target="Harvard", attempt_type="lccn", last_error="No LCCN")
    lccn_row = db.get_attempted_for("0000000000", "Harvard", "lccn")
    assert lccn_row is not None
    assert lccn_row.fail_count == 1, "lccn-type counter must be independent of both-type counter"

    # get_all_attempted_for returns one row per (target, type) pair.
    all_rows = db.get_all_attempted_for("0000000000")
    keys = {(r.last_target, r.attempt_type) for r in all_rows}
    assert keys == {("Harvard", "both"), ("LoC", "both"), ("Harvard", "lccn")}


def test_should_skip_retry(tmp_path: Path):
    db_path = tmp_path / "test.sqlite3"
    db = DatabaseManager(db_path)
    db.init_db()

    # Not attempted yet -> do not skip
    assert db.should_skip_retry("1111111111", "Test", "both", retry_days=7) is False

    # Log an attempt now -> should skip for retry_days >= 1
    db.upsert_attempted(isbn="1111111111", last_target="Test", attempt_type="both", last_error="x")
    assert db.should_skip_retry("1111111111", "Test", "both", retry_days=7) is True
    # Different target/type should not be skipped by that record.
    assert db.should_skip_retry("1111111111", "OtherTarget", "both", retry_days=7) is False
    assert db.should_skip_retry("1111111111", "Test", "lccn", retry_days=7) is False
