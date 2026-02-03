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
import sys
from dataclasses import dataclass
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import DatabaseManager
from harvester.orchestrator import HarvestOrchestrator, HarvestTarget, ProgressCallback

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
    targets: list[HarvestTarget] | None = None,
    bypass_retry_isbns: set[str] | None = None,
    progress_cb: ProgressCallback | None = None,
) -> HarvestSummary:
    """
    Sprint 3 pipeline interface (delegates to HarvestOrchestrator).
    """
    input_path = input_path.expanduser().resolve()

    db = DatabaseManager(db_path)
    db.init_db()

    isbns = read_isbns_from_tsv(input_path)

    orch = HarvestOrchestrator(
        db=db,
        targets=targets,
        retry_days=retry_days,
        bypass_retry_isbns=bypass_retry_isbns,
        progress_cb=progress_cb,
    )

    orch_summary = orch.run(isbns, dry_run=dry_run)

    # Map orchestrator summary into the Sprint-2-compatible summary shape.
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
