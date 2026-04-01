"""
Module: test_db.py
Part of the LCCN Harvester Project.
"""
import sqlite3
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


def test_main_stores_one_row_per_call_number_type(tmp_path: Path):
    import sqlite3 as _sqlite3

    db_path = tmp_path / "test.sqlite3"
    db = DatabaseManager(db_path)
    db.init_db()

    db.upsert_main(
        MainRecord(
            isbn="9780132350884",
            lccn="QA76.76",
            lccn_source="LoC",
            nlmcn="W1 100",
            nlmcn_source="NLM",
        )
    )

    with _sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT isbn, call_number, call_number_type, source
            FROM main
            WHERE isbn = ?
            ORDER BY call_number_type
            """,
            ("9780132350884",),
        ).fetchall()

    assert rows == [
        ("9780132350884", "QA76.76", "lccn", "LoC"),
        ("9780132350884", "W1 100", "nlmcn", "NLM"),
    ]


def test_main_allows_multiple_sources_for_same_isbn_and_type(tmp_path: Path):
    db_path = tmp_path / "test.sqlite3"
    db = DatabaseManager(db_path)
    db.init_db()

    db.upsert_main(MainRecord(isbn="9780132350884", lccn="QA76.76", lccn_source="UCLA", date_added=20260320))
    db.upsert_main(MainRecord(isbn="9780132350884", lccn="QA76.76", lccn_source="Yale", date_added=20260321))

    rows = db.get_main_rows("9780132350884")
    assert [(row["call_number_type"], row["call_number"], row["source"]) for row in rows] == [
        ("lccn", "QA76.76", "UCLA"),
        ("lccn", "QA76.76", "Yale"),
    ]

    yale_only = db.get_main("9780132350884", allowed_sources={"Yale"})
    assert yale_only is not None
    assert yale_only.lccn == "QA76.76"
    assert yale_only.lccn_source == "Yale"
    assert yale_only.source == "Yale"

    ucla_only = db.get_main("9780132350884", allowed_sources={"UCLA"})
    assert ucla_only is not None
    assert ucla_only.lccn_source == "UCLA"

    no_match = db.get_main("9780132350884", allowed_sources={"Harvard"})
    assert no_match is None


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


def test_date_stored_as_yyyymmdd_integer(tmp_path: Path):
    """After upsert, date_added and last_attempted must be stored as yyyymmdd integers, not strings."""
    import sqlite3 as _sqlite3
    from src.database.db_manager import today_yyyymmdd

    db_path = tmp_path / "test.sqlite3"
    db = DatabaseManager(db_path)
    db.init_db()

    # -- main.date_added --
    rec = MainRecord(isbn="9780000000001", lccn="QA1.A1", source="LoC")
    db.upsert_main(rec)

    with _sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT date_added, typeof(date_added) FROM main WHERE isbn = '9780000000001'"
        ).fetchone()
    assert row is not None, "Record not found in main table"
    date_val, type_val = row
    assert type_val == "integer", f"date_added should be INTEGER, got {type_val!r} (value={date_val!r})"
    today = today_yyyymmdd()
    assert date_val == today, f"date_added should be today's yyyymmdd ({today}), got {date_val!r}"

    # -- attempted.last_attempted --
    db.upsert_attempted(isbn="9780000000002", last_target="LoC", attempt_type="both", last_error="Not found")

    with _sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT last_attempted, typeof(last_attempted) FROM attempted WHERE isbn = '9780000000002'"
        ).fetchone()
    assert row is not None, "Record not found in attempted table"
    att_val, att_type = row
    assert att_type == "integer", f"last_attempted should be INTEGER, got {att_type!r} (value={att_val!r})"
    assert att_val == today, f"last_attempted should be today's yyyymmdd ({today}), got {att_val!r}"


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


def test_init_db_recovers_from_legacy_main_table_before_index_creation(tmp_path: Path):
    db_path = tmp_path / "legacy.sqlite3"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE main (
                isbn TEXT PRIMARY KEY,
                lccn TEXT,
                lccn_source TEXT,
                nlmcn TEXT,
                nlmcn_source TEXT,
                classification TEXT,
                date_added TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO main (isbn, lccn, lccn_source, nlmcn, nlmcn_source, classification, date_added)
            VALUES ('9780132350884', 'QA76.76', 'LoC', 'W1 100', 'NLM', 'QA', '2026-03-23')
            """
        )

    db = DatabaseManager(db_path)
    db.init_db()

    got = db.get_main("9780132350884")
    assert got is not None
    assert got.lccn == "QA76.76"
    assert got.lccn_source == "LoC"
    assert got.nlmcn == "W1 100"
    assert got.nlmcn_source == "NLM"

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT call_number_type, call_number, source, typeof(date_added)
            FROM main
            WHERE isbn = ?
            ORDER BY call_number_type
            """,
            ("9780132350884",),
        ).fetchall()

    assert rows == [
        ("lccn", "QA76.76", "LoC", "integer"),
        ("nlmcn", "W1 100", "NLM", "integer"),
    ]


def test_linked_isbn_helpers_insert_query_and_update(tmp_path: Path):
    db_path = tmp_path / "test.sqlite3"
    db = DatabaseManager(db_path)
    db.init_db()

    with sqlite3.connect(db_path) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(linked_isbns)").fetchall()]
        index_names = {row[1] for row in conn.execute("PRAGMA index_list(linked_isbns)").fetchall()}

    assert columns == ["lowest_isbn", "other_isbn"]
    assert "idx_linked_lowest" in index_names
    assert "idx_linked_other" in index_names

    db.upsert_linked_isbn(lowest_isbn="9780000000001", other_isbn="9780000000002")

    assert db.get_lowest_isbn("9780000000002") == "9780000000001"
    assert db.get_linked_isbns("9780000000001") == ["9780000000002"]

    db.upsert_linked_isbn(lowest_isbn="9780000000000", other_isbn="9780000000002")

    assert db.get_lowest_isbn("9780000000002") == "9780000000000"
    assert db.get_linked_isbns("9780000000001") == []
    assert db.get_linked_isbns("9780000000000") == ["9780000000002"]


def test_init_db_migrates_legacy_linked_isbn_schema(tmp_path: Path):
    db_path = tmp_path / "legacy_linked.sqlite3"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE linked_isbns (
                isbn TEXT PRIMARY KEY,
                canonical_isbn TEXT NOT NULL
            )
            """
        )
        conn.executemany(
            "INSERT INTO linked_isbns (isbn, canonical_isbn) VALUES (?, ?)",
            [
                ("9780000000001", "9780000000001"),
                ("9780000000002", "9780000000001"),
                ("9780000000003", "9780000000001"),
            ],
        )

    db = DatabaseManager(db_path)
    db.init_db()

    with sqlite3.connect(db_path) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(linked_isbns)").fetchall()]
        rows = conn.execute(
            "SELECT lowest_isbn, other_isbn FROM linked_isbns ORDER BY other_isbn"
        ).fetchall()

    assert columns == ["lowest_isbn", "other_isbn"]
    assert rows == [
        ("9780000000001", "9780000000002"),
        ("9780000000001", "9780000000003"),
    ]


def test_rewrite_to_lowest_isbn_moves_main_attempted_and_linked_rows(tmp_path: Path):
    db_path = tmp_path / "rewrite.sqlite3"
    db = DatabaseManager(db_path)
    db.init_db()

    lowest_isbn = "9780000000001"
    other_isbn = "9780000000002"

    db.upsert_main(
        MainRecord(
            isbn=lowest_isbn,
            nlmcn="W1 100",
            nlmcn_source="NLM",
            date_added=20260320,
        )
    )
    db.upsert_main(
        MainRecord(
            isbn=other_isbn,
            lccn="QA76.76",
            lccn_source="LoC",
            date_added=20260321,
        )
    )

    db.upsert_attempted(
        isbn=lowest_isbn,
        last_target="Harvard",
        attempt_type="both",
        last_error="Earlier failure",
        attempted_time=20260320,
    )
    db.upsert_attempted(
        isbn=other_isbn,
        last_target="Harvard",
        attempt_type="both",
        last_error="Later failure",
        attempted_time=20260321,
    )
    db.upsert_attempted(
        isbn=other_isbn,
        last_target="Harvard",
        attempt_type="both",
        last_error="Latest failure",
        attempted_time=20260322,
    )

    db.rewrite_to_lowest_isbn(lowest_isbn=lowest_isbn, other_isbn=other_isbn)

    moved = db.get_main(lowest_isbn)
    assert moved is not None
    assert moved.isbn == lowest_isbn
    assert moved.lccn == "QA76.76"
    assert moved.nlmcn == "W1 100"
    assert db.get_main(other_isbn) is None

    attempted = db.get_attempted_for(lowest_isbn, "Harvard", "both")
    assert attempted is not None
    assert attempted.fail_count == 3
    assert attempted.last_attempted == 20260322
    assert attempted.last_error == "Latest failure"
    assert db.get_attempted_for(other_isbn, "Harvard", "both") is None

    assert db.get_lowest_isbn(other_isbn) == lowest_isbn
    assert db.get_linked_isbns(lowest_isbn) == [other_isbn]
