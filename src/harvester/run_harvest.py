"""
High-level harvest pipeline entry point.

This module bridges user-facing input (an ISBN file) with the
``HarvestOrchestrator`` runtime.  It is the primary entry point for both the
GUI harvest tab and the CLI.

Public API:
    parse_isbn_file(path)  -- Read an ISBN file and return validated, deduplicated ISBNs.
    run_harvest(path, ...) -- Full pipeline: parse → configure targets → run → return summary.

Supported input formats:
    .txt / .tsv  -- One ISBN per line (tab-separated files use column 0 as primary).
    .csv         -- Comma-separated; column 0 = primary, columns 1+ = linked variants.
    .xlsx / .xls -- Excel; column 0 = primary, columns 1+ = linked variants.

Multi-column files
    When a file has more than one column, extra columns are treated as linked
    ISBN variants for the same edition.  The orchestrator tries all variants
    together via ``process_isbn_group``.
"""

from __future__ import annotations

import csv  # Reading CSV and TSV ISBN input files
import logging  # Module-level logger for parse and harvest warnings
from dataclasses import dataclass  # Frozen/mutable result and stats DTOs
from pathlib import Path  # OS-independent path handling for input files and DB

from src.database import DatabaseManager  # SQLite database initialisation and access
from src.harvester.orchestrator import HarvestOrchestrator, HarvestTarget, ProgressCallback, CancelCheck  # Core harvest engine and callback types
from src.harvester.api_targets import build_default_api_targets  # Default HTTP API target factory
from src.utils import isbn_validator  # ISBN normalisation and validation helpers

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HarvestSummary:
    """Aggregate outcome statistics returned by ``run_harvest``.

    Attributes:
        total_rows:           Total ISBNs submitted (after deduplication).
        total_isbns:          Same as ``total_rows`` (alias for compatibility).
        cached_hits:          ISBNs found in the local DB without an API call.
        skipped_recent_fail:  ISBNs still within the retry suppression window.
        attempted:            ISBNs that were actually looked up externally.
        successes:            ISBNs for which a call number was found.
        failures:             ISBNs attempted but not found.
        not_in_local_catalog: ISBNs missing from the local DB during a DB-only run.
        dry_run:              ``True`` if the run was read-only (no DB writes).
    """
    total_rows: int
    total_isbns: int
    cached_hits: int
    skipped_recent_fail: int
    attempted: int
    successes: int
    failures: int
    dry_run: bool
    not_in_local_catalog: int = 0


@dataclass
class ParsedISBNFile:
    """Result of parsing an ISBN input file.

    Attributes:
        unique_valid:     Deduplicated list of normalised valid ISBNs (in input order).
        valid_count:      Total number of valid ISBNs seen (including duplicates).
        duplicate_count:  ``valid_count - len(unique_valid)``.
        invalid_isbns:    Raw strings that could not be normalised.
        total_nonempty:   Total non-empty rows read (header excluded).
        linked:           Mapping of primary ISBN → list of linked variant ISBNs.
                          Empty dict for single-column files.
    """
    unique_valid: list[str]
    valid_count: int
    duplicate_count: int
    invalid_isbns: list[str]
    total_nonempty: int
    linked: dict = None  # primary_isbn -> [variant_isbn, ...] (empty if single-column file)

    def __post_init__(self):
        """Replace the ``None`` sentinel with an empty dict so callers can always iterate ``linked``."""
        if self.linked is None:
            self.linked = {}

@dataclass
class RunStats:
    """Mutable running counters used by GUI progress tracking.

    Updated incrementally during a harvest run so the UI can display
    live progress without waiting for the final ``HarvestSummary``.
    """
    total_rows: int = 0
    valid_rows: int = 0
    duplicates: int = 0
    invalid: int = 0
    processed_unique: int = 0
    found: int = 0
    failed: int = 0
    skipped: int = 0

def parse_isbn_file(input_path: Path, max_lines: int = 0) -> ParsedISBNFile:
    """Parse an ISBN input file and return validated, deduplicated ISBNs with statistics.

    Handles four file formats:
      - ``.xlsx`` / ``.xls``: Excel workbook read via ``pandas``; column 0 is
        the primary ISBN, columns 1+ are linked variant ISBNs.
      - ``.csv``: Comma-separated; same column convention as Excel.
      - ``.tsv`` / ``.txt``: Tab-separated; column 0 is the primary ISBN,
        columns 1+ are linked variants.

    For all formats, rows starting with ``#`` and blank rows are skipped.
    A header row is detected and skipped when the first non-empty cell
    matches a known header token (``"isbn"``, ``"isbn13"``, etc.).

    Args:
        input_path: Path to the input file.
        max_lines:  If > 0, stop after this many data rows (useful for previews).

    Returns:
        A ``ParsedISBNFile`` with deduplicated valid ISBNs, invalid raw strings,
        counters, and a ``linked`` mapping of primary ISBN → variant list.
    """
    valid_isbns: list[str] = []
    invalid_isbns: list[str] = []
    seen = set()
    total_nonempty = 0
    valid_count = 0
    linked_map: dict[str, list[str]] = {}  # primary_isbn -> [linked_variant, ...]

    suffix = input_path.suffix.lower()  # Determines which parser branch to use below

    if suffix in {".xlsx", ".xls"}:
        try:
            import pandas as pd
            # Read first sheet, no headers assumed to get raw data
            df = pd.read_excel(input_path, header=None, engine='openpyxl' if suffix == '.xlsx' else None)
            first_data_row_seen = False

            for i, row in df.iterrows():
                if max_lines and i >= max_lines:
                    break
                
                # Check entirely empty row
                if row.isna().all():
                    continue

                total_nonempty += 1
                
                # Column 0 is the primary ISBN; columns 1+ are linked variants
                raw_val = row.iloc[0]
                raw_isbn = str(raw_val).strip() if pd.notna(raw_val) else ""

                if not raw_isbn or raw_isbn.startswith("#"):
                    continue

                if not first_data_row_seen and raw_isbn.lower() in {"isbn", "isbns", "isbn13", "isbn10"}:
                    first_data_row_seen = True
                    continue

                first_data_row_seen = True

                # pandas reads pure-digit ISBN-13s as floats, e.g. 9780131103627.0.
                # Stripping ".0" restores the correct 13-digit string before validation.
                if raw_isbn.endswith(".0"):
                    raw_isbn = raw_isbn[:-2]

                normalized = isbn_validator.normalize_isbn(raw_isbn)

                if normalized:
                    valid_count += 1
                    if normalized not in seen:
                        seen.add(normalized)
                        valid_isbns.append(normalized)
                    # Collect linked ISBNs from extra columns
                    linked_variants: list[str] = []
                    for col_idx in range(1, len(row)):
                        extra_val = row.iloc[col_idx]
                        if pd.isna(extra_val):
                            continue
                        extra_raw = str(extra_val).strip()
                        if extra_raw.endswith(".0"):
                            extra_raw = extra_raw[:-2]
                        extra_norm = isbn_validator.normalize_isbn(extra_raw)
                        if extra_norm and extra_norm != normalized and extra_norm not in linked_variants:
                            linked_variants.append(extra_norm)
                    if linked_variants:
                        linked_map.setdefault(normalized, []).extend(
                            v for v in linked_variants if v not in linked_map.get(normalized, [])
                        )
                else:
                    invalid_isbns.append(raw_isbn)
        except Exception as e:
            logger.error(f"Failed parsing Excel file: {e}")

    else:
        with input_path.open("r", encoding="utf-8-sig", newline="") as f:
            delimiter = "," if suffix == ".csv" else "\t"
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
                    # Collect linked ISBNs from extra columns
                    linked_variants: list[str] = []
                    for col_idx in range(1, len(row)):
                        extra_raw = row[col_idx].strip()
                        extra_norm = isbn_validator.normalize_isbn(extra_raw)
                        if extra_norm and extra_norm != normalized and extra_norm not in linked_variants:
                            linked_variants.append(extra_norm)
                    if linked_variants:
                        linked_map.setdefault(normalized, []).extend(
                            v for v in linked_variants if v not in linked_map.get(normalized, [])
                        )
                else:
                    invalid_isbns.append(raw_isbn)

    return ParsedISBNFile(
        unique_valid=valid_isbns,
        valid_count=valid_count,
        duplicate_count=valid_count - len(valid_isbns),
        invalid_isbns=invalid_isbns,
        total_nonempty=total_nonempty,
        linked=linked_map,
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
    stop_rule: str = "stop_either",
    include_z3950: bool = False,
    db_only: bool = False,
    both_stop_policy: str | None = None,
) -> HarvestSummary:
    """Parse *input_path* and run a full harvest, returning aggregate statistics.

    Args:
        input_path:          Path to the ISBN input file (.txt, .tsv, .csv, .xlsx).
        dry_run:             When ``True``, targets are queried but no DB writes occur.
        db_path:             Path to the SQLite database file.
        retry_days:          Suppress re-trying ISBNs that failed within this many days.
        targets:             Pre-built target list.  Defaults to API targets (+ Z39.50
                             if ``include_z3950=True``) when ``None``.
        bypass_retry_isbns:  ISBNs to force-retry regardless of the retry window.
        bypass_cache_isbns:  ISBNs to look up even if already in the DB cache.
        progress_cb:         Optional ``(event, payload)`` progress callback.
        cancel_check:        Optional callable returning ``True`` to abort the run.
        max_workers:         Number of parallel lookup threads (1 = sequential).
        call_number_mode:    ``"lccn"``, ``"nlmcn"``, or ``"both"`` (default).
        stop_rule:           When to stop querying further targets after a result.
        include_z3950:       When ``True`` and ``targets`` is ``None``, Z39.50 targets
                             from the config files are also included.
        db_only:             When ``True``, only the local DB is consulted (no APIs).
        both_stop_policy:    Deprecated alias; use ``stop_rule`` instead.

    Returns:
        A ``HarvestSummary`` with outcome counts for the entire batch.
    """

    input_path = input_path.expanduser().resolve()

    db = DatabaseManager(db_path)
    db.init_db()  # Ensure schema and migrations are applied before any reads/writes

    parsed = parse_isbn_file(input_path)
    isbns = parsed.unique_valid

    if targets is None:
        if db_only:
            targets = []  # db_only mode: no external API calls; orchestrator uses cache only
        else:
            targets = []
            targets.extend(build_default_api_targets())
            if include_z3950:
                # Z39.50 targets are optional; only loaded when explicitly requested
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
        stop_rule=stop_rule,
        db_only=db_only,
    )

    orch_summary = orch.run(isbns, dry_run=dry_run, linked=parsed.linked or None)

    return HarvestSummary(
        total_rows=orch_summary.total_isbns,
        total_isbns=orch_summary.total_isbns,
        cached_hits=orch_summary.cached_hits,
        skipped_recent_fail=orch_summary.skipped_recent_fail,
        attempted=orch_summary.attempted,
        successes=orch_summary.successes,
        failures=orch_summary.failures,
        not_in_local_catalog=orch_summary.not_in_local_catalog,
        dry_run=orch_summary.dry_run,
    )
