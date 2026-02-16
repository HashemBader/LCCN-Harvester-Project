"""
run_harvest.py

Sprint 3+: Define the harvest pipeline interface using HarvestOrchestrator.

Sprint 5:
- Pass batch_size so orchestrator writes in transactions instead of per-ISBN.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

from src.database import DatabaseManager
from src.harvester.orchestrator import HarvestOrchestrator, HarvestTarget, ProgressCallback, CancelCheck
from src.harvester.api_targets import build_default_api_targets
from src.utils import isbn_validator

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
    isbns: list[str] = []

    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        first_row = next(reader, None)
        if first_row is None:
            return []

        has_header = len(first_row) > 0 and first_row[0].strip().lower() == "isbn"

        def add_raw(raw_val: str) -> None:
            if raw_val.startswith("#"):
                return
            norm = isbn_validator.normalize_isbn(raw_val)
            if norm:
                isbns.append(norm)

        if has_header:
            for row in reader:
                if row and (row[0] or "").strip():
                    add_raw((row[0] or "").strip())
        else:
            if first_row and (first_row[0] or "").strip():
                add_raw((first_row[0] or "").strip())
            for row in reader:
                if row and (row[0] or "").strip():
                    add_raw((row[0] or "").strip())

    # de-dup preserve order
    seen = set()
    uniq: list[str] = []
    for v in isbns:
        if v not in seen:
            uniq.append(v)
            seen.add(v)
    return uniq


def run_harvest(
    input_path: Path,
    dry_run: bool = False,
    *,
    db_path: Path | str = "data/lccn_harvester.sqlite3",
    retry_days: int = 7,
    targets: list[HarvestTarget] | None = None,
    bypass_retry_isbns: set[str] | None = None,
    bypass_cache_isbns: set[str] | None = None,
    progress_cb: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    max_workers: int = 1,
    batch_size: int = 50,
    include_z3950: bool = False,
) -> HarvestSummary:

    input_path = input_path.expanduser().resolve()

    db = DatabaseManager(db_path)
    db.init_db()

    isbns = read_isbns_from_tsv(input_path)

    if targets is None:
        targets = []
        targets.extend(build_default_api_targets())
        if include_z3950:
            from src.harvester.z3950_targets import build_default_z3950_targets
            targets.extend(build_default_z3950_targets())

    orch = HarvestOrchestrator(
        db=db,
        targets=targets,
        retry_days=retry_days,
        bypass_retry_isbns=bypass_retry_isbns,
        bypass_cache_isbns=bypass_cache_isbns,
        progress_cb=progress_cb,
        cancel_check=cancel_check,
        max_workers=max_workers,
        batch_size=batch_size,
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
