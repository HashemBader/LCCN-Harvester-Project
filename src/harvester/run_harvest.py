"""
run_harvest.py

Sprint 3+: Define the harvest pipeline interface using HarvestOrchestrator.

Responsibilities:
- Read ISBNs from input TSV
- Initialize database
- Delegate cache/retry/target order logic to HarvestOrchestrator
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

from src.utils import isbn_validator
from src.database import DatabaseManager
from src.harvester.orchestrator import HarvestOrchestrator, HarvestTarget, ProgressCallback
from src.harvester.api_targets import build_default_api_targets
from src.harvester.z3950_targets import build_default_z3950_targets

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

    Returns unique, normalized ISBN strings.
    Invalid ISBNs are skipped (and logged by isbn_validator).
    """
    isbns: list[str] = []

    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        first_row = next(reader, None)
        if first_row is None:
            return []

        has_header = len(first_row) > 0 and first_row[0].strip().lower() == "isbn"

        def add_raw(raw_val: str) -> None:
            norm = isbn_validator.normalize_isbn(raw_val)
            if norm:
                isbns.append(norm)

        if has_header:
            for row in reader:
                if not row:
                    continue
                raw = (row[0] or "").strip()
                if raw:
                    add_raw(raw)
        else:
            raw0 = (first_row[0] or "").strip() if first_row else ""
            if raw0:
                add_raw(raw0)

            for row in reader:
                if not row:
                    continue
                raw = (row[0] or "").strip()
                if raw:
                    add_raw(raw)

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
    targets: list[HarvestTarget] | None = None,
    progress_cb: ProgressCallback | None = None,
) -> HarvestSummary:
    """
    Sprint 3 pipeline interface (delegates to HarvestOrchestrator).
    """
    input_path = input_path.expanduser().resolve()

    db = DatabaseManager(db_path)
    db.init_db()

    isbns = read_isbns_from_tsv(input_path)

    # Default to Abdo API targets if none provided
    if targets is None:
        targets = []
        targets.extend(build_default_api_targets())
        targets.extend(build_default_z3950_targets())

    orch = HarvestOrchestrator(
        db=db,
        targets=targets,
        retry_days=retry_days,
        progress_cb=progress_cb,
    )

    orch_summary = orch.run(isbns, dry_run=dry_run)

    return HarvestSummary(
        total_rows=orch_summary.total_isbns,
        total_isbns=orch_summary.total_isbns,
        cached_hits=orch_summary.cached_hits,
        skipped_recent_fail=orch_summary.skipped_recent_fail,
        attempted=orch_summary.attempted,
        successes=orch_summary.successes,
        failures=orch_summary.failures,
        dry_run=orch_summary.dry_run,
    )
