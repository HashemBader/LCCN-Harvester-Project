"""run_harvest.py: Define the harvest pipeline interface using HarvestOrchestrator."""

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


@dataclass
class ParsedISBNFile:
    unique_valid: list[str]
    valid_count: int
    duplicate_count: int
    invalid_isbns: list[str]
    total_nonempty: int

def parse_isbn_file(input_path: Path, max_lines: int = 0) -> ParsedISBNFile:
    """Parse a TSV/CSV/TXT file and return structured statistics and deduplicated ISBNs."""
    valid_isbns: list[str] = []
    invalid_isbns: list[str] = []
    seen = set()
    total_nonempty = 0
    valid_count = 0

    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        delimiter = "," if input_path.suffix.lower() == ".csv" else "\t"
        reader = csv.reader(f, delimiter=delimiter)
        first_data_row_seen = False

        for i, row in enumerate(reader, start=1):
            if max_lines and i > max_lines:
                break

            # Check if entirely empty
            if not row or not "".join(row).strip():
                continue
            total_nonempty += 1

            raw_isbn = row[0].strip() if row else ""
            if not raw_isbn or raw_isbn.startswith("#"):
                continue

            # Header skip
            if not first_data_row_seen and raw_isbn.lower() in {"isbn", "isbns", "isbn13", "isbn10"}:
                first_data_row_seen = True
                continue

            first_data_row_seen = True
            normalized = isbn_validator.normalize_isbn(raw_isbn)

            if normalized:
                valid_count += 1
                if normalized not in seen:
                    seen.add(normalized)
                    valid_isbns.append(normalized)
            else:
                invalid_isbns.append(raw_isbn)

    return ParsedISBNFile(
        unique_valid=valid_isbns,
        valid_count=valid_count,
        duplicate_count=valid_count - len(valid_isbns),
        invalid_isbns=invalid_isbns,
        total_nonempty=total_nonempty,
    )


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
    call_number_mode: str = "both",
    include_z3950: bool = False,
) -> HarvestSummary:

    input_path = input_path.expanduser().resolve()

    db = DatabaseManager(db_path)
    db.init_db()

    parsed = parse_isbn_file(input_path)
    isbns = parsed.unique_valid

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
        call_number_mode=call_number_mode,
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
