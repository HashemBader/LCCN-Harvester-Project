"""
run_harvest.py

Sprint 2: Define the harvest pipeline interface.

This module provides:
- run_harvest(input_path, dry_run): loops through ISBNs, checks DB cache,
  applies retry-skip logic, and records attempts (placeholder until real
  target lookups are implemented in Sprint 3+).

NOTE (requirements-aligned DB):
- attempted tracking is per (isbn, target)
- dates are stored as yyyymmdd integers in the DB layer
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

from src.database import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HarvestSummary:
    total_rows: int
    total_isbns: int
    cached_hits: int
    skipped_recent_fail: int
    attempted: int
    successes: int
    failures: int
    dry_run: bool


def read_isbns_from_tsv(input_path: Path) -> list[str]:
    """
    Read ISBNs from a TSV file.

    Accepts either:
    - header with an 'isbn' column, or
    - no header (ISBN in first column)

    Returns unique ISBN strings (keeps leading zeros).
    """
    isbns: list[str] = []

    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        first_row = next(reader, None)
        if first_row is None:
            return []

        # Detect header by seeing if first cell is "isbn"
        has_header = len(first_row) > 0 and first_row[0].strip().lower() == "isbn"

        if has_header:
            for row in reader:
                if not row:
                    continue
                raw = (row[0] or "").strip()
                if raw:
                    isbns.append(raw)
        else:
            raw0 = (first_row[0] or "").strip() if first_row else ""
            if raw0:
                isbns.append(raw0)

            for row in reader:
                if not row:
                    continue
                raw = (row[0] or "").strip()
                if raw:
                    isbns.append(raw)

    # De-dup while preserving order
    seen = set()
    uniq: list[str] = []
    for isbn in isbns:
        if isbn not in seen:
            uniq.append(isbn)
            seen.add(isbn)

    return uniq


def run_harvest(
    input_path: Path,
    dry_run: bool = False,
    *,
    db_path: Path | str = "data/lccn_harvester.sqlite3",
    retry_days: int = 7,
) -> HarvestSummary:
    """
    Sprint 2 pipeline interface.

    Loop all ISBNs in input TSV:
      1) If main cache hit => skip (cached_hits++)
      2) If attempted for the placeholder target within retry_days => skip
         (skipped_recent_fail++)
      3) Else:
         - In dry_run: count as attempted but do not write DB
         - In non-dry_run (Sprint 2 placeholder): record attempted failure
           because real target lookup isn't implemented yet.

    Later sprints will replace the placeholder target "(pipeline)" with a
    real list of targets and real lookup calls.
    """
    input_path = input_path.expanduser().resolve()
    db = DatabaseManager(db_path)
    db.init_db()

    isbns = read_isbns_from_tsv(input_path)

    cached_hits = 0
    skipped_recent_fail = 0
    attempted = 0
    successes = 0
    failures = 0

    # Sprint 2 placeholder target name (now required by the DB schema)
    target = "(pipeline)"

    for isbn in isbns:
        # 1) cache check
        existing = db.get_main(isbn)
        if existing is not None:
            cached_hits += 1
            continue

        # 2) retry skip check (now per isbn+target)
        if db.should_skip_retry(isbn, target, retry_days=retry_days):
            skipped_recent_fail += 1
            continue

        # 3) attempt
        attempted += 1

        if dry_run:
            continue

        # Sprint 2 placeholder: no real harvesting yet
        db.upsert_attempted(
            isbn=isbn,
            target=target,
            last_error="Harvest not implemented yet (Sprint 2 placeholder)",
        )
        failures += 1

    return HarvestSummary(
        total_rows=len(isbns),  # unique ISBN count (TSV rows may differ if duplicates)
        total_isbns=len(isbns),
        cached_hits=cached_hits,
        skipped_recent_fail=skipped_recent_fail,
        attempted=attempted,
        successes=successes,
        failures=failures,
        dry_run=dry_run,
    )
