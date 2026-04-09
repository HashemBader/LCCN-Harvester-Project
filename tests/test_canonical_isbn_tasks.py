"""
Sprint tests: canonical ISBN behavior, trailing-X, linked_isbns integrity, real file e2e.

Covers
------
Task 1. Confirm canonical ISBN stored in every harvest path (parametrized matrix).
Task 2. Trailing-X comparison sorts correctly and stored value is unchanged.
Task 4. linked_isbns never contains self-links or duplicate rows.
Task 5. Real multi-ISBN input file parsed and harvested correctly end-to-end.

(Task 3 — rewrite when lower ISBN discovered later — is covered by
 test_old_rows_rewritten_when_lower_isbn_discovered_via_harvest and
 test_old_rows_rewritten_when_lower_isbn_discovered_via_marc_import in
 test_linked_isbn_e2e.py, both already passing.)
"""

from __future__ import annotations

import pytest

from src.database import MainRecord
from src.database.db_manager import DatabaseManager
from src.harvester.marc_import import MarcImportService, ParsedMarcImportRecord
from src.harvester.orchestrator import HarvestOrchestrator, TargetResult
from src.harvester.run_harvest import parse_isbn_file
from src.utils.isbn_validator import pick_lowest_isbn

# ── ISBN constants ────────────────────────────────────────────────────
# Standard ISBN-10 / ISBN-13 pair — ISBN-10 is lexicographically lower.
ISBN10 = "0131103628"       # canonical (lower)
ISBN13 = "9780131103627"    # non-canonical (higher)

# ISBN-10 ending in X — useful for trailing-X tests.
ISBN_X   = "019853453X"     # trailing X; sort key: "0198534539"
ISBN_X_2 = "0198534531"     # same prefix but digit 1; sort key: "0198534531" → wins over X
ISBN13_X = "9780198534532"  # ISBN-13 pair for ISBN_X


# ── helpers ──────────────────────────────────────────────────────────

class PerISBNTarget:
    """Mock target: configurable TargetResult per ISBN."""

    def __init__(self, name: str, results: dict):
        self.name = name
        self._results = results

    def lookup(self, isbn: str) -> TargetResult:
        return self._results.get(isbn, TargetResult(success=False, error="not found"))


def _make_db(path) -> DatabaseManager:
    db = DatabaseManager(path)
    db.init_db()
    return db


def _flush(db, pending_main, pending_attempted, pending_linked):
    """Flush pending buffers exactly as HarvestOrchestrator.flush() does."""
    with db.transaction() as conn:
        if pending_linked:
            db.rewrite_to_lowest_isbn_many(conn, pending_linked)
        db.upsert_main_many(conn, pending_main, clear_attempted_on_success=True)
        db.upsert_attempted_many(conn, pending_attempted)
        db.upsert_linked_isbns_many(conn, pending_linked)


def _seed_link(db, lowest, other):
    with db.transaction() as conn:
        db._upsert_linked_isbn_conn(conn, lowest_isbn=lowest, other_isbn=other)


def _all_linked_rows(db):
    with db.connect() as conn:
        return conn.execute("SELECT lowest_isbn, other_isbn FROM linked_isbns").fetchall()


# ════════════════════════════════════════════════════════════════════════
# Task 1 — Canonical ISBN in every harvest path (matrix)
# ════════════════════════════════════════════════════════════════════════

HARVEST_PATH_CASES = [
    # (path_name, target_results_dict, expect_in_main, expect_in_attempted)
    (
        "primary_success",
        {ISBN13: TargetResult(success=True, lccn="QA76.73.P38")},
        True, False,
    ),
    (
        "fallback_success",
        {ISBN10: TargetResult(success=True, lccn="PZ7.R65")},
        True, False,
    ),
    (
        "all_fail",
        {},   # both ISBNs fail
        False, True,
    ),
]


@pytest.mark.parametrize("path_name,target_results,in_main,in_attempted", HARVEST_PATH_CASES)
def test_canonical_isbn_in_all_harvest_paths(tmp_path, path_name, target_results, in_main, in_attempted):
    """Matrix: regardless of harvest path, only the lowest ISBN appears in main/attempted."""
    db = _make_db(tmp_path / "test.sqlite3")
    target = PerISBNTarget("T", target_results)
    orch = HarvestOrchestrator(db, targets=[target], call_number_mode="lccn", stop_rule="stop_either")

    pending_main, pending_attempted, pending_linked = [], [], []
    orch.process_isbn_group(
        ISBN13, [ISBN10],
        dry_run=False,
        pending_main=pending_main,
        pending_attempted=pending_attempted,
        pending_linked=pending_linked,
    )
    _flush(db, pending_main, pending_attempted, pending_linked)

    canonical = min(ISBN13, ISBN10)   # "0131103628"

    if in_main:
        rec = db.get_main(canonical)
        assert rec is not None, f"[{path_name}] canonical {canonical!r} missing from main"
        # The non-canonical ISBN must NOT have its own main row
        non_canonical = ISBN13
        stale = db.get_main(non_canonical)
        assert stale is None or non_canonical == canonical, (
            f"[{path_name}] non-canonical {non_canonical!r} still has a row in main"
        )

    if in_attempted:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT isbn FROM attempted WHERE isbn = ?", (canonical,)
            ).fetchone()
        assert row is not None, (
            f"[{path_name}] canonical {canonical!r} missing from attempted"
        )
        # Non-canonical must NOT have an attempted row
        with db.connect() as conn:
            bad = conn.execute(
                "SELECT isbn FROM attempted WHERE isbn = ?", (ISBN13,)
            ).fetchone()
        assert bad is None, (
            f"[{path_name}] non-canonical {ISBN13!r} found in attempted"
        )


def test_canonical_isbn_db_only_mode(tmp_path):
    """db_only path: cache hit resolves through canonical and emits linked_cached."""
    db = _make_db(tmp_path / "test.sqlite3")

    # Pre-seed canonical record and link
    _seed_link(db, lowest=ISBN10, other=ISBN13)
    with db.transaction() as conn:
        db.upsert_main_many(conn, [
            MainRecord(isbn=ISBN10, lccn="QA76.73.P38", source="LOC", date_added=20240101)
        ], clear_attempted_on_success=False)

    target = PerISBNTarget("LOC", {})
    orch = HarvestOrchestrator(db, targets=[target], call_number_mode="lccn", db_only=True)

    events = []
    orch.progress_cb = lambda name, payload: events.append(name)

    summary = orch.run([ISBN13], dry_run=False)

    assert summary.cached_hits == 1, "db_only cache hit expected"
    assert db.get_main(ISBN13) is None, "non-canonical must not have its own main row"
    assert "linked_cached" in events, f"linked_cached event missing; got {events}"


# ════════════════════════════════════════════════════════════════════════
# Task 2 — Trailing-X comparison and stored value unchanged
# ════════════════════════════════════════════════════════════════════════

class TestTrailingX:
    """pick_lowest_isbn treats X as 9 for ordering; the original string is kept."""

    def test_x_loses_to_lower_digit(self):
        """'019853453X' vs '0198534531' → '0198534531' wins (1 < 9)."""
        assert pick_lowest_isbn([ISBN_X, ISBN_X_2]) == ISBN_X_2

    def test_x_beats_isbn13(self):
        """ISBN-10 with X beats ISBN-13 because '0...' < '9...'."""
        assert pick_lowest_isbn([ISBN_X, ISBN13_X]) == ISBN_X

    def test_single_x_returned_as_is(self):
        """Single X-ISBN returned unchanged."""
        assert pick_lowest_isbn([ISBN_X]) == ISBN_X

    def test_two_x_isbns_lower_digit_wins(self):
        """Between two X-ISBNs the standard sort still applies to the prefix."""
        # "047002193X" vs "048002193X" → first wins ('4' < '8')
        assert pick_lowest_isbn(["047002193X", "048002193X"]) == "047002193X"

    def test_stored_isbn_value_unchanged_in_db(self, tmp_path):
        """The ISBN stored in main must be the original string, not a sort-key form."""
        db = _make_db(tmp_path / "test.sqlite3")
        svc = MarcImportService(db_path=tmp_path / "test.sqlite3")

        # ISBN_X is the lowest so it will be canonical
        rec = ParsedMarcImportRecord(isbns=(ISBN_X, ISBN13_X), lccn="QA76")
        svc.persist_records([rec], source_name="test")

        canonical = pick_lowest_isbn([ISBN_X, ISBN13_X])
        row = db.get_main(canonical)
        assert row is not None, f"canonical {canonical!r} not found in DB"
        assert row.isbn == canonical, (
            f"stored isbn {row.isbn!r} differs from expected {canonical!r}"
        )
        # Confirm the 'X' was not replaced by '9' or stripped
        assert "X" in row.isbn or canonical == ISBN13_X, (
            "trailing-X was altered when stored"
        )

    def test_x_isbn_as_canonical_in_linked_isbns(self, tmp_path):
        """When X-ISBN is lowest, linked_isbns stores it as lowest_isbn."""
        db = _make_db(tmp_path / "test.sqlite3")
        svc = MarcImportService(db_path=tmp_path / "test.sqlite3")

        # ISBN_X < ISBN13_X lexicographically (with _isbn_sort_key)
        rec = ParsedMarcImportRecord(isbns=(ISBN_X, ISBN13_X), lccn="QA76")
        svc.persist_records([rec], source_name="test")

        canonical = pick_lowest_isbn([ISBN_X, ISBN13_X])
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT lowest_isbn, other_isbn FROM linked_isbns WHERE lowest_isbn = ?",
                (canonical,),
            ).fetchall()
        assert rows, f"No linked_isbns row found for canonical {canonical!r}"
        for r in rows:
            assert r["lowest_isbn"] == canonical
            assert r["other_isbn"] != canonical


# ════════════════════════════════════════════════════════════════════════
# Task 4 — linked_isbns structural integrity (no self-links, no duplicates)
# ════════════════════════════════════════════════════════════════════════

class TestLinkedIsbnIntegrity:

    def test_no_self_links_after_harvest(self, tmp_path):
        """linked_isbns must never contain a row where lowest_isbn == other_isbn."""
        db = _make_db(tmp_path / "test.sqlite3")
        target = PerISBNTarget("T", {ISBN13: TargetResult(success=True, lccn="QA76")})
        orch = HarvestOrchestrator(db, targets=[target], call_number_mode="lccn", stop_rule="stop_either")

        pending_main, pending_attempted, pending_linked = [], [], []
        orch.process_isbn_group(
            ISBN13, [ISBN10],
            dry_run=False,
            pending_main=pending_main,
            pending_attempted=pending_attempted,
            pending_linked=pending_linked,
        )
        _flush(db, pending_main, pending_attempted, pending_linked)

        rows = _all_linked_rows(db)
        for r in rows:
            assert r["lowest_isbn"] != r["other_isbn"], (
                f"Self-link detected: {r['lowest_isbn']!r} → {r['other_isbn']!r}"
            )

    def test_no_self_links_after_marc_import(self, tmp_path):
        """MARC import must not produce self-link rows."""
        db = _make_db(tmp_path / "test.sqlite3")
        svc = MarcImportService(db_path=tmp_path / "test.sqlite3")

        rec = ParsedMarcImportRecord(isbns=(ISBN10, ISBN13), lccn="PZ7")
        svc.persist_records([rec], source_name="test")

        rows = _all_linked_rows(db)
        for r in rows:
            assert r["lowest_isbn"] != r["other_isbn"], (
                f"Self-link detected: {r['lowest_isbn']!r}"
            )

    def test_no_duplicate_rows_after_repeated_inserts(self, tmp_path):
        """Inserting the same link twice must not produce duplicate rows."""
        db = _make_db(tmp_path / "test.sqlite3")
        _seed_link(db, ISBN10, ISBN13)
        _seed_link(db, ISBN10, ISBN13)   # second insert — should be ignored

        rows = _all_linked_rows(db)
        pairs = [(r["lowest_isbn"], r["other_isbn"]) for r in rows]
        assert len(pairs) == len(set(pairs)), f"Duplicate rows found: {pairs}"

    def test_lowest_isbn_is_always_lower_than_other(self, tmp_path):
        """Every row in linked_isbns must have lowest_isbn ≤ other_isbn lexicographically."""
        db = _make_db(tmp_path / "test.sqlite3")

        # Insert several pairs via MARC import
        svc = MarcImportService(db_path=tmp_path / "test.sqlite3")
        recs = [
            ParsedMarcImportRecord(isbns=(ISBN13, ISBN10), lccn="QA76"),
            ParsedMarcImportRecord(isbns=(ISBN_X, ISBN13_X), lccn="PZ7"),
        ]
        svc.persist_records(recs, source_name="test")

        rows = _all_linked_rows(db)
        assert rows, "No linked_isbns rows found"
        for r in rows:
            lowest = r["lowest_isbn"]
            other  = r["other_isbn"]
            assert lowest <= other, (
                f"linked_isbns row has lowest_isbn={lowest!r} > other_isbn={other!r}"
            )

    def test_no_duplicate_rows_after_harvest_then_marc_import(self, tmp_path):
        """Harvest followed by MARC import for same pair must not create duplicates."""
        db = _make_db(tmp_path / "test.sqlite3")

        # Step 1: harvest creates the link
        target = PerISBNTarget("T", {ISBN13: TargetResult(success=True, lccn="QA76")})
        orch = HarvestOrchestrator(db, targets=[target], call_number_mode="lccn", stop_rule="stop_either")
        pending_main, pending_attempted, pending_linked = [], [], []
        orch.process_isbn_group(
            ISBN13, [ISBN10], dry_run=False,
            pending_main=pending_main, pending_attempted=pending_attempted, pending_linked=pending_linked,
        )
        _flush(db, pending_main, pending_attempted, pending_linked)

        # Step 2: MARC import for the same pair
        svc = MarcImportService(db_path=tmp_path / "test.sqlite3")
        rec = ParsedMarcImportRecord(isbns=(ISBN10, ISBN13), lccn="QA76")
        svc.persist_records([rec], source_name="test")

        rows = _all_linked_rows(db)
        pairs = [(r["lowest_isbn"], r["other_isbn"]) for r in rows]
        assert len(pairs) == len(set(pairs)), f"Duplicate rows found: {pairs}"


# ════════════════════════════════════════════════════════════════════════
# Task 5 — Real harvest input file with linked ISBN columns
# ════════════════════════════════════════════════════════════════════════

class TestRealInputFile:
    """End-to-end tests using actual TSV files written to disk."""

    def test_parse_isbn_file_reads_linked_column(self, tmp_path):
        """parse_isbn_file returns the linked dict when a second column is present."""
        tsv = tmp_path / "input.tsv"
        tsv.write_text(
            f"{ISBN13}\t{ISBN10}\n",
            encoding="utf-8",
        )

        parsed = parse_isbn_file(tsv)

        assert ISBN13 in parsed.unique_valid or ISBN10 in parsed.unique_valid, (
            "Neither ISBN found in unique_valid"
        )
        assert parsed.linked, "linked dict should not be empty"
        primary = parsed.unique_valid[0]
        assert primary in parsed.linked, f"primary {primary!r} not in linked map"
        linked_variants = parsed.linked[primary]
        # The other ISBN should be in the variants list
        other = ISBN10 if primary == ISBN13 else ISBN13
        assert other in linked_variants, (
            f"{other!r} not found in linked variants for {primary!r}"
        )

    def test_parse_isbn_file_single_column_no_linked(self, tmp_path):
        """Single-column file yields an empty linked dict (no regression)."""
        tsv = tmp_path / "input.tsv"
        tsv.write_text(f"{ISBN13}\n{ISBN10}\n", encoding="utf-8")

        parsed = parse_isbn_file(tsv)

        assert len(parsed.unique_valid) == 2
        assert parsed.linked == {}, "Single-column file must produce empty linked dict"

    def test_end_to_end_multi_isbn_file_stores_canonical(self, tmp_path):
        """Full pipeline: TSV file → parse → orchestrator → DB contains canonical ISBN."""
        db = _make_db(tmp_path / "test.sqlite3")

        tsv = tmp_path / "input.tsv"
        tsv.write_text(f"{ISBN13}\t{ISBN10}\n", encoding="utf-8")

        parsed = parse_isbn_file(tsv)
        assert parsed.linked, "linked map must be populated from two-column file"

        target = PerISBNTarget("T", {
            ISBN13: TargetResult(success=True, lccn="QA76.73.P38"),
            ISBN10: TargetResult(success=True, lccn="QA76.73.P38"),
        })
        orch = HarvestOrchestrator(db, targets=[target], call_number_mode="lccn", stop_rule="stop_either")

        summary = orch.run(parsed.unique_valid, linked=parsed.linked, dry_run=False)

        assert summary.successes >= 1, "Expected at least one success"

        canonical = min(ISBN13, ISBN10)
        rec = db.get_main(canonical)
        assert rec is not None, f"canonical {canonical!r} not in DB after full run"
        assert rec.lccn == "QA76.73.P38"

        # Non-canonical must not have its own main row
        non_canonical = ISBN13
        stale = db.get_main(non_canonical)
        assert stale is None, f"non-canonical {non_canonical!r} has a stale main row"

    def test_end_to_end_multi_isbn_file_linked_isbns_populated(self, tmp_path):
        """After a real file harvest, linked_isbns table is correctly populated."""
        db = _make_db(tmp_path / "test.sqlite3")

        tsv = tmp_path / "input.tsv"
        tsv.write_text(f"{ISBN13}\t{ISBN10}\n", encoding="utf-8")

        parsed = parse_isbn_file(tsv)
        target = PerISBNTarget("T", {ISBN13: TargetResult(success=True, lccn="QA76")})
        orch = HarvestOrchestrator(db, targets=[target], call_number_mode="lccn", stop_rule="stop_either")
        orch.run(parsed.unique_valid, linked=parsed.linked, dry_run=False)

        rows = _all_linked_rows(db)
        assert rows, "linked_isbns must have rows after harvesting a two-column file"

        canonical = min(ISBN13, ISBN10)
        non_canonical = ISBN13
        found = any(
            r["lowest_isbn"] == canonical and r["other_isbn"] == non_canonical
            for r in rows
        )
        assert found, (
            f"Expected row ({canonical!r}, {non_canonical!r}) in linked_isbns; got {list(rows)}"
        )

    def test_end_to_end_header_row_skipped(self, tmp_path):
        """Header row 'isbn' in the file is skipped; data rows are parsed."""
        db = _make_db(tmp_path / "test.sqlite3")

        tsv = tmp_path / "input.tsv"
        tsv.write_text(f"isbn\tlinked_isbn\n{ISBN13}\t{ISBN10}\n", encoding="utf-8")

        parsed = parse_isbn_file(tsv)

        assert parsed.unique_valid, "No valid ISBNs found — header row may not have been skipped"
        assert "isbn" not in parsed.unique_valid
        assert "linked_isbn" not in parsed.unique_valid
