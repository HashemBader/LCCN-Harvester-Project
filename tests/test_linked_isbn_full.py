"""
Full linked ISBN verification suite.

Covers every meaningful scenario end-to-end:

 S1.  ISBN-10 beats ISBN-13 (standard pair, ISBN-10 is primary)
 S2.  ISBN-10 beats ISBN-13 (ISBN-13 is primary, ISBN-10 is linked)
 S3.  Three-way group — lowest of three wins
 S4.  Trailing-X ISBN — X treated as 9 for sorting, stored unchanged
 S5.  Two ISBN-13s — lower one wins
 S6.  Single ISBN, no linked column — no regression, normal harvest
 S7.  All candidates fail — attempted written under canonical, no linked_isbns row
 S8.  Fallback — primary fails, variant succeeds, result under canonical
 S9.  Rewrite: data stored under higher ISBN first, lower discovered later (harvest)
 S10. Rewrite: data stored under higher ISBN first, lower discovered later (MARC import)
 S11. MARC import with multiple ISBNs per record — canonical used in main
 S12. DB-only harvest — finds canonical record via linked_isbns cache
 S13. linked_isbns structural integrity — no self-links, no duplicates, lowest < other
 S14. Full run() with real TSV-style linked dict — end-to-end pipeline
 S15. Multiple independent ISBN groups in one run — groups don't bleed into each other
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
# Book A: C Programming Language
A_ISBN10 = "0131103628"        # canonical (lower)
A_ISBN13 = "9780131103627"     # non-canonical

# Book B: The Great Gatsby
B_ISBN10 = "0743273567"
B_ISBN13 = "9780743273565"

# Book C: three-way group
C_ISBN10  = "0306406152"       # lowest → canonical
C_ISBN13A = "9780306406157"    # higher
C_ISBN13B = "9780306406164"    # highest

# Book D: trailing-X
D_ISBNX  = "019853453X"        # X treated as 9 → "0198534539"
D_ISBN13 = "9780198534532"     # "9..." → higher → D_ISBNX wins

# Book E: two ISBN-13s, no ISBN-10
E_ISBN13_LOW  = "9780521641234"   # lower → canonical
E_ISBN13_HIGH = "9780521648721"   # higher


# ── helpers ──────────────────────────────────────────────────────────

class PerISBNTarget:
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
    with db.transaction() as conn:
        if pending_linked:
            db.rewrite_to_lowest_isbn_many(conn, pending_linked)
        db.upsert_main_many(conn, pending_main, clear_attempted_on_success=True)
        db.upsert_attempted_many(conn, pending_attempted)
        db.upsert_linked_isbns_many(conn, pending_linked)


def _run_group(db, target_results, primary, linked_isbns):
    """Run process_isbn_group and flush. Returns status."""
    target = PerISBNTarget("T", target_results)
    orch = HarvestOrchestrator(db, targets=[target], call_number_mode="lccn", stop_rule="stop_either")
    pm, pa, pl = [], [], []
    status = orch.process_isbn_group(primary, linked_isbns, dry_run=False,
                                     pending_main=pm, pending_attempted=pa, pending_linked=pl)
    _flush(db, pm, pa, pl)
    return status


def _linked_rows(db):
    with db.connect() as conn:
        return [(r["lowest_isbn"], r["other_isbn"])
                for r in conn.execute("SELECT lowest_isbn, other_isbn FROM linked_isbns").fetchall()]


def _attempted_isbns(db):
    with db.connect() as conn:
        return [r["isbn"] for r in conn.execute("SELECT DISTINCT isbn FROM attempted").fetchall()]


# ═══════════════════════════════════════════════════════════════════════
# S1 — ISBN-10 primary beats ISBN-13 linked
# ═══════════════════════════════════════════════════════════════════════

def test_s1_isbn10_primary_is_canonical(tmp_path):
    """ISBN-10 is primary column and lower → stored as canonical."""
    db = _make_db(tmp_path / "db.sqlite3")
    _run_group(db, {A_ISBN10: TargetResult(success=True, lccn="QA76.73.C15")},
               primary=A_ISBN10, linked_isbns=[A_ISBN13])

    assert db.get_main(A_ISBN10) is not None, "canonical ISBN-10 missing from main"
    assert db.get_main(A_ISBN13) is None, "non-canonical ISBN-13 must not be in main"
    assert (A_ISBN10, A_ISBN13) in _linked_rows(db)


# ═══════════════════════════════════════════════════════════════════════
# S2 — ISBN-13 primary, ISBN-10 linked → ISBN-10 still wins
# ═══════════════════════════════════════════════════════════════════════

def test_s2_isbn13_primary_isbn10_linked_canonical_is_isbn10(tmp_path):
    """Even when ISBN-13 is the primary column, the lower ISBN-10 becomes canonical."""
    db = _make_db(tmp_path / "db.sqlite3")
    _run_group(db, {A_ISBN13: TargetResult(success=True, lccn="QA76.73.C15")},
               primary=A_ISBN13, linked_isbns=[A_ISBN10])

    assert db.get_main(A_ISBN10) is not None, "canonical ISBN-10 missing"
    assert db.get_main(A_ISBN13) is None, "non-canonical ISBN-13 must not be in main"
    assert (A_ISBN10, A_ISBN13) in _linked_rows(db)


# ═══════════════════════════════════════════════════════════════════════
# S3 — Three-way group: lowest of three wins
# ═══════════════════════════════════════════════════════════════════════

def test_s3_three_way_group_lowest_wins(tmp_path):
    """With three ISBNs, pick_lowest_isbn selects the canonical correctly."""
    db = _make_db(tmp_path / "db.sqlite3")
    _run_group(db, {C_ISBN13A: TargetResult(success=True, lccn="HM621")},
               primary=C_ISBN13A, linked_isbns=[C_ISBN13B, C_ISBN10])

    canonical = pick_lowest_isbn([C_ISBN10, C_ISBN13A, C_ISBN13B])
    assert canonical == C_ISBN10

    assert db.get_main(C_ISBN10) is not None, "canonical missing"
    assert db.get_main(C_ISBN13A) is None
    assert db.get_main(C_ISBN13B) is None

    pairs = _linked_rows(db)
    assert (C_ISBN10, C_ISBN13A) in pairs
    assert (C_ISBN10, C_ISBN13B) in pairs


# ═══════════════════════════════════════════════════════════════════════
# S4 — Trailing-X ISBN: stored unchanged, sorted correctly
# ═══════════════════════════════════════════════════════════════════════

def test_s4_trailing_x_is_canonical_and_stored_unchanged(tmp_path):
    """ISBN ending in X beats ISBN-13 (0... < 9...) and is stored as-is."""
    db = _make_db(tmp_path / "db.sqlite3")
    _run_group(db, {D_ISBN13: TargetResult(success=True, lccn="QH301")},
               primary=D_ISBN13, linked_isbns=[D_ISBNX])

    canonical = pick_lowest_isbn([D_ISBNX, D_ISBN13])
    assert canonical == D_ISBNX, "trailing-X ISBN must be canonical"

    row = db.get_main(D_ISBNX)
    assert row is not None, "X-ISBN missing from main"
    assert "X" in row.isbn, f"stored isbn {row.isbn!r} has X stripped"
    assert db.get_main(D_ISBN13) is None


# ═══════════════════════════════════════════════════════════════════════
# S5 — Two ISBN-13s, no ISBN-10: lower ISBN-13 wins
# ═══════════════════════════════════════════════════════════════════════

def test_s5_two_isbn13s_lower_wins(tmp_path):
    db = _make_db(tmp_path / "db.sqlite3")
    _run_group(db, {E_ISBN13_LOW: TargetResult(success=True, lccn="QA9")},
               primary=E_ISBN13_HIGH, linked_isbns=[E_ISBN13_LOW])

    assert db.get_main(E_ISBN13_LOW) is not None, "lower ISBN-13 missing"
    assert db.get_main(E_ISBN13_HIGH) is None
    assert (E_ISBN13_LOW, E_ISBN13_HIGH) in _linked_rows(db)


# ═══════════════════════════════════════════════════════════════════════
# S6 — Single ISBN, no linked column: no regression
# ═══════════════════════════════════════════════════════════════════════

def test_s6_single_isbn_no_regression(tmp_path):
    """A single-column ISBN is harvested exactly as before — no linked_isbns rows."""
    db = _make_db(tmp_path / "db.sqlite3")
    target = PerISBNTarget("T", {A_ISBN10: TargetResult(success=True, lccn="QA76")})
    orch = HarvestOrchestrator(db, targets=[target], call_number_mode="lccn", stop_rule="stop_either")
    orch.run([A_ISBN10], dry_run=False)

    assert db.get_main(A_ISBN10) is not None
    assert _linked_rows(db) == [], "no linked_isbns rows expected for single-column harvest"


# ═══════════════════════════════════════════════════════════════════════
# S7 — All candidates fail: attempted under canonical, no linked_isbns
# ═══════════════════════════════════════════════════════════════════════

def test_s7_all_fail_attempted_under_canonical_no_links(tmp_path):
    db = _make_db(tmp_path / "db.sqlite3")
    status = _run_group(db, {}, primary=A_ISBN13, linked_isbns=[A_ISBN10])

    assert status == "failed"
    assert A_ISBN10 in _attempted_isbns(db), "canonical must be in attempted"
    assert A_ISBN13 not in _attempted_isbns(db), "non-canonical must NOT be in attempted"
    assert _linked_rows(db) == [], "no linked_isbns rows on total failure"


# ═══════════════════════════════════════════════════════════════════════
# S8 — Fallback: primary fails, variant succeeds, result under canonical
# ═══════════════════════════════════════════════════════════════════════

def test_s8_fallback_variant_succeeds_stored_under_canonical(tmp_path):
    """Primary lookup fails; linked variant returns a result; stored under canonical."""
    db = _make_db(tmp_path / "db.sqlite3")
    # ISBN-13 is primary but fails; ISBN-10 (canonical) is linked and succeeds
    _run_group(db, {A_ISBN10: TargetResult(success=True, lccn="QA76.73.C15")},
               primary=A_ISBN13, linked_isbns=[A_ISBN10])

    rec = db.get_main(A_ISBN10)
    assert rec is not None, "canonical missing after fallback"
    assert rec.lccn == "QA76.73.C15"
    assert db.get_main(A_ISBN13) is None


# ═══════════════════════════════════════════════════════════════════════
# S9 — Rewrite via harvest: higher ISBN stored first, lower discovered later
# ═══════════════════════════════════════════════════════════════════════

def test_s9_harvest_rewrite_moves_row_to_lower_isbn(tmp_path):
    """Row stored under ISBN-13; subsequent run with ISBN-10 moves it to canonical."""
    db = _make_db(tmp_path / "db.sqlite3")

    # Run 1: single-column harvest, only ISBN-13 known
    target = PerISBNTarget("T", {A_ISBN13: TargetResult(success=True, lccn="QA76")})
    orch = HarvestOrchestrator(db, targets=[target], call_number_mode="lccn", stop_rule="stop_either")
    orch.run([A_ISBN13], dry_run=False)
    assert db.get_main(A_ISBN13) is not None, "setup: row must be under ISBN-13 after run 1"

    # Run 2: two-column input, ISBN-10 appears as linked → triggers rewrite
    target2 = PerISBNTarget("T", {A_ISBN13: TargetResult(success=True, lccn="QA76")})
    orch2 = HarvestOrchestrator(db, targets=[target2], call_number_mode="lccn", stop_rule="stop_either")
    orch2.run([A_ISBN13], linked={A_ISBN13: [A_ISBN10]}, dry_run=False)

    assert db.get_main(A_ISBN10) is not None, "row must have moved to canonical ISBN-10"
    stale = db.get_main(A_ISBN13)
    assert stale is None, "stale row under ISBN-13 must be gone after rewrite"


# ═══════════════════════════════════════════════════════════════════════
# S10 — Rewrite via MARC import
# ═══════════════════════════════════════════════════════════════════════

def test_s10_marc_import_rewrite_moves_row_to_lower_isbn(tmp_path):
    """MARC import with two ISBNs moves pre-existing row to the canonical."""
    db = _make_db(tmp_path / "db.sqlite3")

    # Pre-seed a row under the higher ISBN
    with db.transaction() as conn:
        db.upsert_main_many(conn, [
            MainRecord(isbn=A_ISBN13, lccn="QA76", source="Test", date_added=20240101)
        ], clear_attempted_on_success=False)

    assert db.get_main(A_ISBN13) is not None

    # MARC import record has both ISBNs → lowest becomes canonical, rewrite fires
    svc = MarcImportService(db_path=tmp_path / "db.sqlite3")
    svc.persist_records(
        [ParsedMarcImportRecord(isbns=(A_ISBN13, A_ISBN10), lccn="QA76")],
        source_name="MARC Test",
    )

    assert db.get_main(A_ISBN10) is not None, "canonical ISBN-10 missing after MARC import"
    assert db.get_main(A_ISBN13) is None, "stale ISBN-13 row not removed after rewrite"


# ═══════════════════════════════════════════════════════════════════════
# S11 — MARC import: multiple ISBNs per record → canonical in main
# ═══════════════════════════════════════════════════════════════════════

def test_s11_marc_import_multiple_isbns_canonical_in_main(tmp_path):
    """MARC record with 3 ISBNs → only canonical appears in main."""
    db = _make_db(tmp_path / "db.sqlite3")
    svc = MarcImportService(db_path=tmp_path / "db.sqlite3")

    rec = ParsedMarcImportRecord(isbns=(C_ISBN13A, C_ISBN10, C_ISBN13B), lccn="HM621")
    svc.persist_records([rec], source_name="MARC Test")

    assert db.get_main(C_ISBN10) is not None, "canonical missing"
    assert db.get_main(C_ISBN13A) is None
    assert db.get_main(C_ISBN13B) is None

    pairs = _linked_rows(db)
    assert (C_ISBN10, C_ISBN13A) in pairs
    assert (C_ISBN10, C_ISBN13B) in pairs


# ═══════════════════════════════════════════════════════════════════════
# S12 — DB-only harvest resolves non-canonical via linked_isbns
# ═══════════════════════════════════════════════════════════════════════

def test_s12_db_only_finds_record_via_linked_isbns(tmp_path):
    """db_only run with non-canonical ISBN finds the canonical record via cache."""
    db = _make_db(tmp_path / "db.sqlite3")

    # Seed canonical record + link
    with db.transaction() as conn:
        db.upsert_main_many(conn, [
            MainRecord(isbn=A_ISBN10, lccn="QA76.73.C15", source="LOC", date_added=20240101)
        ], clear_attempted_on_success=False)
        db._upsert_linked_isbn_conn(conn, lowest_isbn=A_ISBN10, other_isbn=A_ISBN13)

    target = PerISBNTarget("LOC", {})
    orch = HarvestOrchestrator(db, targets=[target], call_number_mode="lccn", db_only=True)

    events = []
    orch.progress_cb = lambda name, _: events.append(name)

    summary = orch.run([A_ISBN13], dry_run=False)

    assert summary.cached_hits == 1, "expected cache hit via linked_isbns"
    assert "linked_cached" in events, f"linked_cached event missing; got {events}"
    assert db.get_main(A_ISBN13) is None, "non-canonical must not get its own main row"


# ═══════════════════════════════════════════════════════════════════════
# S13 — linked_isbns structural integrity
# ═══════════════════════════════════════════════════════════════════════

def test_s13_linked_isbns_no_self_links_no_duplicates_lowest_is_lower(tmp_path):
    """After a multi-group harvest, linked_isbns has no self-links, no duplicates,
    and every row has lowest_isbn < other_isbn."""
    db = _make_db(tmp_path / "db.sqlite3")
    svc = MarcImportService(db_path=tmp_path / "db.sqlite3")

    records = [
        ParsedMarcImportRecord(isbns=(A_ISBN13, A_ISBN10), lccn="QA76"),
        ParsedMarcImportRecord(isbns=(C_ISBN13A, C_ISBN10, C_ISBN13B), lccn="HM621"),
        ParsedMarcImportRecord(isbns=(D_ISBN13, D_ISBNX), lccn="QH301"),
    ]
    svc.persist_records(records, source_name="integrity test")

    # Insert same link twice — must not produce duplicate
    with db.transaction() as conn:
        db._upsert_linked_isbn_conn(conn, lowest_isbn=A_ISBN10, other_isbn=A_ISBN13)

    rows = _linked_rows(db)

    # No self-links
    for lowest, other in rows:
        assert lowest != other, f"self-link detected: {lowest}"

    # No duplicates
    assert len(rows) == len(set(rows)), f"duplicate rows: {rows}"

    # lowest_isbn is always lexicographically ≤ other_isbn
    for lowest, other in rows:
        assert lowest <= other, f"lowest {lowest!r} > other {other!r}"


# ═══════════════════════════════════════════════════════════════════════
# S14 — Full run() with real TSV-style linked dict
# ═══════════════════════════════════════════════════════════════════════

def test_s14_full_run_with_tsv_linked_dict(tmp_path):
    """Simulate parse_isbn_file output fed into run() — full pipeline test."""
    db = _make_db(tmp_path / "db.sqlite3")

    tsv = tmp_path / "input.tsv"
    tsv.write_text(f"{A_ISBN13}\t{A_ISBN10}\n{B_ISBN13}\t{B_ISBN10}\n", encoding="utf-8")

    parsed = parse_isbn_file(tsv)
    assert parsed.linked, "TSV must produce linked map"

    target = PerISBNTarget("T", {
        A_ISBN13: TargetResult(success=True, lccn="QA76.73.C15"),
        B_ISBN13: TargetResult(success=True, lccn="PS3511.I9"),
    })
    orch = HarvestOrchestrator(db, targets=[target], call_number_mode="lccn", stop_rule="stop_either")
    summary = orch.run(parsed.unique_valid, linked=parsed.linked, dry_run=False)

    assert summary.successes >= 1

    # Canonical rows in main
    assert db.get_main(A_ISBN10) is not None, "Book A canonical missing"
    assert db.get_main(B_ISBN10) is not None, "Book B canonical missing"

    # Non-canonicals not in main
    assert db.get_main(A_ISBN13) is None
    assert db.get_main(B_ISBN13) is None

    # Links recorded
    pairs = _linked_rows(db)
    assert (A_ISBN10, A_ISBN13) in pairs
    assert (B_ISBN10, B_ISBN13) in pairs


# ═══════════════════════════════════════════════════════════════════════
# S15 — Multiple independent groups don't bleed into each other
# ═══════════════════════════════════════════════════════════════════════

def test_s15_multiple_groups_independent(tmp_path):
    """Two separate ISBN groups in one run produce separate, non-overlapping link rows."""
    db = _make_db(tmp_path / "db.sqlite3")

    target = PerISBNTarget("T", {
        A_ISBN10: TargetResult(success=True, lccn="QA76"),
        B_ISBN10: TargetResult(success=True, lccn="PS3511"),
    })
    orch = HarvestOrchestrator(db, targets=[target], call_number_mode="lccn", stop_rule="stop_either")

    pm, pa, pl = [], [], []
    orch.process_isbn_group(A_ISBN13, [A_ISBN10], dry_run=False,
                            pending_main=pm, pending_attempted=pa, pending_linked=pl)
    orch.process_isbn_group(B_ISBN13, [B_ISBN10], dry_run=False,
                            pending_main=pm, pending_attempted=pa, pending_linked=pl)
    _flush(db, pm, pa, pl)

    # Each group has its own canonical
    assert db.get_main(A_ISBN10) is not None
    assert db.get_main(B_ISBN10) is not None

    # Links don't cross groups
    pairs = _linked_rows(db)
    assert (A_ISBN10, A_ISBN13) in pairs
    assert (B_ISBN10, B_ISBN13) in pairs
    assert (A_ISBN10, B_ISBN13) not in pairs, "groups must not bleed into each other"
    assert (B_ISBN10, A_ISBN13) not in pairs
