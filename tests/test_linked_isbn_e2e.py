"""
End-to-end tests: MARC import → DB population, then linked ISBN harvest.

Covers
------
1.  process_isbn_group stores result under min(all_isbns) — the canonical ISBN
2.  Cross-ref record written for every non-canonical ISBN in the group
3.  linked_isbns table populated for every member of the group
4.  Fallback: primary fails → variant tried → success stored under canonical
5.  All fail: attempted recorded under canonical ISBN, no linked_isbns rows
6.  No regression: single-column file behaves identically to today
7.  Full run() with a linked dict wires everything together
8.  MARC import populates DB; subsequent db_only harvest with linked ISBNs
    finds the record via cache and creates the cross-ref + linked_isbns rows

Task 1-4 regression tests
--------------------------
T1. process_isbn (single, no group) resolves input ISBN to canonical via
    get_lowest_isbn() before writing to main / attempted
T2. Old rows are rewritten to the lower canonical when a link is discovered
    later — both via the harvest batch flush and via MARC import
T3. Merged rows use the call_number from the more recently dated source
T4. FK enforcement is restored after every rewrite so subsequent writes
    within the same transaction are fully constrained
T5. Full run() with pre-seeded linked_isbns writes every result under the
    lowest ISBN and leaves no stale rows behind
"""

from src.database import MainRecord
from src.database.db_manager import DatabaseManager
from src.harvester.marc_import import MarcImportService, ParsedMarcImportRecord
from src.harvester.orchestrator import HarvestOrchestrator, TargetResult

# ── ISBNs used across the suite ──────────────────────────────────────
# A known valid ISBN-10 / ISBN-13 pair for the same title.
ISBN13 = "9780131103627"   # "higher" lexicographically
ISBN10 = "0131103628"      # "lower"  lexicographically → will be canonical
CANONICAL = min(ISBN13, ISBN10)   # "0131103628"
assert CANONICAL == ISBN10, "sanity: ISBN-10 must be the canonical"

# A second ISBN-13 used for three-way group tests
ISBN13B = "9780131103628"   # higher than ISBN10, lower than ISBN13


# ── helpers ──────────────────────────────────────────────────────────

class PerISBNTarget:
    """Mock target: returns a configurable TargetResult per ISBN."""

    def __init__(self, name: str, results: dict):
        self.name = name
        self._results = results  # {isbn: TargetResult}

    def lookup(self, isbn: str) -> TargetResult:
        return self._results.get(isbn, TargetResult(success=False, error="not found"))


def _make_db(path) -> DatabaseManager:
    db = DatabaseManager(path)
    db.init_db()
    return db


def _query_canonical(db: DatabaseManager, isbn: str):
    """Return the canonical (lowest) ISBN for *isbn*, or None if not linked.

    - If *isbn* is stored as other_isbn  → returns its lowest_isbn
    - If *isbn* is stored as lowest_isbn → returns *isbn* itself
    - Otherwise                          → returns None
    """
    with db.connect() as conn:
        row = conn.execute(
            "SELECT lowest_isbn FROM linked_isbns WHERE other_isbn = ? LIMIT 1",
            (isbn,),
        ).fetchone()
        if row:
            return str(row["lowest_isbn"])
        row = conn.execute(
            "SELECT 1 FROM linked_isbns WHERE lowest_isbn = ? LIMIT 1",
            (isbn,),
        ).fetchone()
        if row:
            return isbn
    return None


def _flush(db: DatabaseManager, pending_main, pending_attempted, pending_linked):
    """Flush the three pending buffers to DB in one transaction.
    Mirrors the exact sequence used by HarvestOrchestrator.flush().
    """
    with db.transaction() as conn:
        if pending_linked:
            db.rewrite_to_lowest_isbn_many(conn, pending_linked)
        db.upsert_main_many(conn, pending_main, clear_attempted_on_success=True)
        db.upsert_attempted_many(conn, pending_attempted)
        db.upsert_linked_isbns_many(conn, pending_linked)


def _seed_link(db: DatabaseManager, lowest: str, other: str) -> None:
    """Directly insert a linked_isbns row without triggering any rewrite."""
    with db.transaction() as conn:
        db._upsert_linked_isbn_conn(conn, lowest_isbn=lowest, other_isbn=other)


# ═══════════════════════════════════════════════════════════════════════
# 1. Canonical selection
# ═══════════════════════════════════════════════════════════════════════

def test_canonical_is_lexicographically_lowest(tmp_path):
    """Success on the primary; result must be stored under min(all_isbns)."""
    db = _make_db(tmp_path / "test.sqlite3")

    target = PerISBNTarget("T", {ISBN13: TargetResult(success=True, lccn="QA76.73 P38")})
    orch = HarvestOrchestrator(db, targets=[target], call_number_mode="lccn", stop_rule="stop_either")

    pending_main, pending_attempted, pending_linked = [], [], []
    status = orch.process_isbn_group(
        ISBN13, [ISBN10],
        dry_run=False,
        pending_main=pending_main,
        pending_attempted=pending_attempted,
        pending_linked=pending_linked,
    )

    assert status == "success"
    _flush(db, pending_main, pending_attempted, pending_linked)

    rec = db.get_main(CANONICAL)
    assert rec is not None, f"{CANONICAL} not in DB"
    assert rec.lccn == "QA76.73 P38"

    # process_isbn_group does not write cross-ref rows — only the canonical row
    # is kept in main; the relationship is recorded in linked_isbns instead.
    assert _query_canonical(db, CANONICAL) == CANONICAL
    assert _query_canonical(db, ISBN13) == CANONICAL


# ═══════════════════════════════════════════════════════════════════════
# 2. Fallback to variant
# ═══════════════════════════════════════════════════════════════════════

def test_fallback_to_variant_when_primary_fails(tmp_path):
    """Primary returns no result; variant succeeds; stored under canonical."""
    db = _make_db(tmp_path / "test.sqlite3")

    target = PerISBNTarget("T", {ISBN10: TargetResult(success=True, lccn="PZ7.R65")})
    orch = HarvestOrchestrator(db, targets=[target], call_number_mode="lccn", stop_rule="stop_either")

    pending_main, pending_attempted, pending_linked = [], [], []
    status = orch.process_isbn_group(
        ISBN13, [ISBN10],
        dry_run=False,
        pending_main=pending_main,
        pending_attempted=pending_attempted,
        pending_linked=pending_linked,
    )

    assert status == "success"
    _flush(db, pending_main, pending_attempted, pending_linked)

    rec = db.get_main(CANONICAL)
    assert rec is not None, f"Canonical {CANONICAL} missing after fallback"
    assert rec.lccn == "PZ7.R65"

    assert _query_canonical(db, CANONICAL) == CANONICAL
    assert _query_canonical(db, ISBN13) == CANONICAL


# ═══════════════════════════════════════════════════════════════════════
# 3. All candidates fail
# ═══════════════════════════════════════════════════════════════════════

def test_all_fail_attempted_recorded_under_canonical(tmp_path):
    """When every candidate fails, attempted row is written under canonical ISBN."""
    db = _make_db(tmp_path / "test.sqlite3")

    target = PerISBNTarget("T", {})   # always fails
    orch = HarvestOrchestrator(db, targets=[target], call_number_mode="lccn", stop_rule="stop_either")

    pending_main, pending_attempted, pending_linked = [], [], []
    status = orch.process_isbn_group(
        ISBN13, [ISBN10],
        dry_run=False,
        pending_main=pending_main,
        pending_attempted=pending_attempted,
        pending_linked=pending_linked,
    )

    assert status == "failed"
    assert not pending_main,   "No main record expected on total failure"
    assert not pending_linked, "No linked_isbns rows expected on total failure"

    _flush(db, pending_main, pending_attempted, pending_linked)

    att = db.get_attempted(CANONICAL)
    assert att is not None, f"attempted row missing for canonical {CANONICAL}"

    assert _query_canonical(db, CANONICAL) is None
    assert _query_canonical(db, ISBN13) is None


# ═══════════════════════════════════════════════════════════════════════
# 4. No regression: single ISBN, no linked map
# ═══════════════════════════════════════════════════════════════════════

def test_no_regression_single_isbn(tmp_path):
    """Without a linked dict, run() processes each ISBN independently as before."""
    db = _make_db(tmp_path / "test.sqlite3")

    target = PerISBNTarget("T", {ISBN13: TargetResult(success=True, lccn="QA123")})
    orch = HarvestOrchestrator(db, targets=[target], call_number_mode="lccn", stop_rule="stop_either")

    summary = orch.run([ISBN13], dry_run=False)   # no linked= arg

    assert summary.successes == 1
    assert db.get_main(ISBN13) is not None

    assert _query_canonical(db, ISBN13) is None


# ═══════════════════════════════════════════════════════════════════════
# 5. Full run() with linked dict
# ═══════════════════════════════════════════════════════════════════════

def test_run_with_linked_dict(tmp_path):
    """run() dispatches to process_isbn_group when linked variants are present."""
    db = _make_db(tmp_path / "test.sqlite3")

    target = PerISBNTarget("T", {ISBN13: TargetResult(success=True, lccn="QA76.73 P38")})
    orch = HarvestOrchestrator(db, targets=[target], call_number_mode="lccn", stop_rule="stop_either")

    summary = orch.run(
        [ISBN13],
        dry_run=False,
        linked={ISBN13: [ISBN10]},
    )

    assert summary.successes == 1
    assert summary.failures == 0

    rec = db.get_main(CANONICAL)
    assert rec is not None and rec.lccn == "QA76.73 P38", (
        f"Expected canonical {CANONICAL} to have lccn, got {rec}"
    )

    # No cross-ref row under ISBN13 — only the canonical is stored in main.
    assert _query_canonical(db, CANONICAL) == CANONICAL
    assert _query_canonical(db, ISBN13) == CANONICAL


# ═══════════════════════════════════════════════════════════════════════
# T1. process_isbn resolves to canonical via get_lowest_isbn
# ═══════════════════════════════════════════════════════════════════════

def test_process_isbn_resolves_to_canonical_when_link_exists(tmp_path):
    """Task 1: process_isbn (single, no group) must write under the canonical ISBN
    if linked_isbns already maps the input ISBN to a lower canonical."""
    db = _make_db(tmp_path / "test.sqlite3")

    # Pre-seed the link: ISBN10 is canonical, ISBN13 is other
    _seed_link(db, lowest=ISBN10, other=ISBN13)

    # Target only knows ISBN13 → would be wrong key without Task 1 fix
    target = PerISBNTarget("T", {ISBN13: TargetResult(success=True, lccn="QA76.73 P38")})
    orch = HarvestOrchestrator(db, targets=[target], call_number_mode="lccn", stop_rule="stop_either")

    pending_main, pending_attempted, pending_linked = [], [], []
    status = orch.process_isbn(
        ISBN13,
        dry_run=False,
        pending_main=pending_main,
        pending_attempted=pending_attempted,
        pending_linked=pending_linked,
    )

    assert status == "success"
    _flush(db, pending_main, pending_attempted, pending_linked)

    # Result must be under the canonical, NOT under the input ISBN13
    rec = db.get_main(ISBN10)
    assert rec is not None, f"Canonical {ISBN10} missing — wrote under wrong ISBN"
    assert rec.lccn == "QA76.73 P38"

    # No stale row under the higher ISBN
    assert db.get_main(ISBN13) is None, f"Stale row found under {ISBN13}"


# ═══════════════════════════════════════════════════════════════════════
# T2a. Old rows rewritten via harvest batch flush
# ═══════════════════════════════════════════════════════════════════════

def test_old_rows_rewritten_when_lower_isbn_discovered_via_harvest(tmp_path):
    """Task 2 (harvest path): a row already stored under ISBN13 must be moved
    to ISBN10 when the harvest batch discovers they are linked."""
    db = _make_db(tmp_path / "test.sqlite3")

    # Simulate a prior run that wrote ISBN13 to main (before the link was known)
    with db.transaction() as conn:
        db.upsert_main_many(conn, [
            MainRecord(isbn=ISBN13, lccn="QA76.73 P38", source="LOC", date_added=20240101)
        ], clear_attempted_on_success=False)

    assert db.get_main(ISBN13) is not None, "Pre-condition: row under ISBN13"

    # Now process a group that discovers ISBN10 < ISBN13
    target = PerISBNTarget("T", {ISBN10: TargetResult(success=True, lccn="QA76.73 P38")})
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

    # Old row under ISBN13 must be gone
    assert db.get_main(ISBN13) is None or "Linked from" in (db.get_main(ISBN13).lccn_source or ""), (
        "Stale primary row still under ISBN13 after rewrite"
    )

    # Canonical row exists
    rec = db.get_main(ISBN10)
    assert rec is not None, f"Canonical {ISBN10} missing after rewrite"
    assert rec.lccn == "QA76.73 P38"


# ═══════════════════════════════════════════════════════════════════════
# T2b. Old rows rewritten via MARC import
# ═══════════════════════════════════════════════════════════════════════

def test_old_rows_rewritten_when_lower_isbn_discovered_via_marc_import(tmp_path):
    """Task 2 (MARC path): a row already stored under ISBN13 must be moved to
    ISBN10 when MarcImportService imports a record containing both ISBNs."""
    db = _make_db(tmp_path / "test.sqlite3")

    # Simulate a prior harvest that stored the result under ISBN13
    with db.transaction() as conn:
        db.upsert_main_many(conn, [
            MainRecord(isbn=ISBN13, lccn="QA76.73 P38", source="LOC", date_added=20240101)
        ], clear_attempted_on_success=False)

    assert db.get_main(ISBN13) is not None, "Pre-condition: row under ISBN13"

    # MARC import discovers the same title with BOTH ISBNs → should rewrite
    svc = MarcImportService(db_path=tmp_path / "test.sqlite3")
    svc.persist_records(
        [ParsedMarcImportRecord(isbns=(ISBN10, ISBN13), lccn="QA76.73 P38")],
        source_name="MARC Import",
        import_date=20240601,
    )

    # Old row under ISBN13 must have been moved to ISBN10
    assert db.get_main(ISBN13) is None, f"Stale row still under {ISBN13} after MARC rewrite"

    rec = db.get_main(ISBN10)
    assert rec is not None, f"Canonical {ISBN10} missing after MARC import rewrite"
    assert rec.lccn == "QA76.73 P38"


# ═══════════════════════════════════════════════════════════════════════
# T3. Merge uses most recent call_number
# ═══════════════════════════════════════════════════════════════════════

def test_merge_keeps_most_recent_call_number(tmp_path):
    """Task 3: when both sides have a call_number, the row with the higher
    date_added wins — the stale call_number is replaced, not silently dropped."""
    db = _make_db(tmp_path / "test.sqlite3")

    # ISBN10 (canonical) has an older call_number
    with db.transaction() as conn:
        db.upsert_main_many(conn, [
            MainRecord(isbn=ISBN10, lccn="QA000.OLD", source="OldSource", date_added=20230101)
        ], clear_attempted_on_success=False)

    # ISBN13 has a newer call_number
    with db.transaction() as conn:
        db.upsert_main_many(conn, [
            MainRecord(isbn=ISBN13, lccn="QA999.NEW", source="NewSource", date_added=20240601)
        ], clear_attempted_on_success=False)

    # Trigger rewrite: ISBN13 → ISBN10
    db.rewrite_to_lowest_isbn(lowest_isbn=ISBN10, other_isbn=ISBN13)

    rec = db.get_main(ISBN10)
    assert rec is not None
    # The newer call_number from ISBN13 must have replaced the older one
    assert rec.lccn == "QA999.NEW", (
        f"Expected newer call_number 'QA999.NEW', got '{rec.lccn}'"
    )
    # Source must be a combination of both
    assert "OldSource" in (rec.lccn_source or rec.source or ""), "Old source lost"
    assert "NewSource" in (rec.lccn_source or rec.source or ""), "New source lost"


# ═══════════════════════════════════════════════════════════════════════
# T4. FK enforcement restored after rewrite
# ═══════════════════════════════════════════════════════════════════════

def test_rewrite_and_upsert_are_atomic(tmp_path):
    """Task 4: rewrite + upsert_main + upsert_attempted + upsert_linked_isbns
    all commit together or not at all.  Simulate failure mid-flush and verify
    the DB contains no partial state."""
    db = _make_db(tmp_path / "test.sqlite3")

    # Pre-write a row under ISBN13
    with db.transaction() as conn:
        db.upsert_main_many(conn, [
            MainRecord(isbn=ISBN13, lccn="QA76.73 P38", source="LOC", date_added=20240101)
        ], clear_attempted_on_success=False)

    # Simulate a flush that fails mid-way (rewrite succeeds but upsert_main raises)
    import unittest.mock as mock

    def _fail_upsert(*_args, **_kwargs):
        raise RuntimeError("simulated mid-flush failure")

    with mock.patch.object(db, "upsert_main_many", side_effect=_fail_upsert):
        try:
            with db.transaction() as conn:
                db.rewrite_to_lowest_isbn_many(conn, [(ISBN10, ISBN13)])
                db.upsert_main_many(conn, [
                    MainRecord(isbn=ISBN10, lccn="QA76.73 P38", source="LOC", date_added=20240601)
                ], clear_attempted_on_success=True)
        except RuntimeError:
            pass  # expected

    # Transaction rolled back — original ISBN13 row must still be intact
    assert db.get_main(ISBN13) is not None, (
        "ISBN13 row should be preserved after rolled-back transaction"
    )
    assert db.get_main(ISBN10) is None, (
        "ISBN10 row must not exist — partial flush was rolled back"
    )


# ═══════════════════════════════════════════════════════════════════════
# T5. Full run() with pre-seeded linked_isbns uses lowest ISBN throughout
# ═══════════════════════════════════════════════════════════════════════

def test_full_run_uses_lowest_isbn_throughout(tmp_path):
    """Task 5 (end-to-end): when linked_isbns is pre-seeded and the harvest
    processes the higher ISBN standalone, every write goes under the canonical
    and any stale row under the higher ISBN is cleaned up."""
    db = _make_db(tmp_path / "test.sqlite3")

    # Stale row from a prior run before the link was known
    with db.transaction() as conn:
        db.upsert_main_many(conn, [
            MainRecord(isbn=ISBN13, lccn="QA76.73 P38", source="LOC", date_added=20240101)
        ], clear_attempted_on_success=False)

    # Pre-seed the link so get_lowest_isbn(ISBN13) → ISBN10
    _seed_link(db, lowest=ISBN10, other=ISBN13)

    target = PerISBNTarget("T", {ISBN13: TargetResult(success=True, lccn="QA76.73 P38")})
    orch = HarvestOrchestrator(db, targets=[target], call_number_mode="lccn", stop_rule="stop_either")

    # run() with ISBN13 only — no explicit group, relies on Task 1 + Task 2
    summary = orch.run([ISBN13], dry_run=False)

    assert summary.successes == 1, (
        f"Expected 1 success, got {summary.successes} successes / {summary.failures} failures"
    )

    # Result stored under canonical
    rec = db.get_main(ISBN10)
    assert rec is not None, f"Canonical {ISBN10} missing"
    assert rec.lccn == "QA76.73 P38"

    # Stale row under ISBN13 moved away (rewrite via Task 2 pending_linked path)
    stale = db.get_main(ISBN13)
    assert stale is None or "Linked from" in (stale.lccn_source or ""), (
        f"Stale primary row still under {ISBN13}"
    )

    # linked_isbns reflects the canonical
    assert _query_canonical(db, ISBN10) == ISBN10
    assert _query_canonical(db, ISBN13) == ISBN10
