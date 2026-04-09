"""Shared helpers and worker types for the harvest page.

Splitting these pieces out of ``harvest_tab.py`` keeps the tab class focused on
UI orchestration, while the background worker and file-format helpers remain
testable in a smaller module.

Public API consumed by ``harvest_tab.py``:
- ``HarvestWorker`` — ``QThread`` subclass that drives ``run_harvest`` in the
  background and emits progress/result signals.
- ``DroppableGroupBox`` — ``QGroupBox`` that accepts drag-and-drop file drops.
- ``_extract_lc_classification`` — derive an LC class prefix from a call number.
- ``_looks_like_header_cell`` — detect ISBN column headers in imported files.
- ``_prepare_marc_import_records`` — filter/transform MARC import tuples for DB
  persistence and TSV export.
- ``_safe_filename`` — sanitise a string for use as a file-system name.
- ``_write_csv_rows`` — write rows to a UTF-8 CSV file.

Threading model:
- ``HarvestWorker.run()`` executes entirely on the worker thread.
- All communication back to the main (GUI) thread goes through Qt signals, which
  are automatically queued across thread boundaries.
- File writes inside the worker use ``_live_results_lock`` (a ``threading.Lock``)
  to protect the shared file handles from concurrent access when ``parallel_workers``
  is greater than 1.
- ``_stop_requested`` and ``_pause_requested`` are plain Python booleans set from
  the GUI thread.  Python's GIL makes single-value boolean reads/writes atomic, so
  no additional lock is needed for these flags.
"""

from __future__ import annotations

import csv
import logging
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import QGroupBox, QMessageBox

from src.config.profile_manager import ProfileManager
from src.database import DatabaseManager, now_datetime_str
from src.database.db_manager import yyyymmdd_to_iso_date
from src.harvester.marc_import import ParsedMarcImportRecord
from src.harvester.orchestrator import HarvestCancelled
from src.harvester.run_harvest import RunStats, parse_isbn_file, run_harvest
from src.harvester.targets import create_target_from_config
from src.utils import messages

logger = logging.getLogger(__name__)


def _write_csv_rows(rows_with_header: list, path: str) -> None:
    """Write *rows_with_header* to a UTF-8 BOM CSV for Excel and Google Sheets.

    The ``utf-8-sig`` encoding writes a BOM so Excel auto-detects UTF-8 on Windows.

    Args:
        rows_with_header: List of rows (first element should be the header row).
        path: Absolute path string for the output CSV file.
    """
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows_with_header)


def _extract_lc_classification(lccn: str) -> str:
    """Derive the LC class prefix (leading letters only) from a call-number string.

    For example, ``"QA76.5 .H35"`` → ``"QA"`` and ``"RC489"`` → ``"RC"``.

    Args:
        lccn: Raw LC call number string, or empty/``None``.

    Returns:
        Uppercase letter prefix, or an empty string when no leading letters exist.
    """
    if not lccn:
        return ""
    match = re.match(r"^([A-Za-z]+)", lccn.strip())
    return match.group(1).upper() if match else ""


def _safe_filename(value: str) -> str:
    """Strip characters that are invalid or awkward in file names.

    Replaces runs of ``\\/:*?"<>|`` and whitespace with a single underscore
    and trims leading/trailing underscores.  Returns ``"default"`` for empty input.

    Args:
        value: Raw string (e.g. profile name) to sanitise.

    Returns:
        A file-system-safe string, never empty.
    """
    return re.sub(r'[\\/:*?"<>|\s]+', "_", value).strip("_") or "default"


def _display_date(value) -> str:
    """Format a storage date value (``yyyymmdd`` int or ISO-8601 str) for TSV display.

    Delegates to ``yyyymmdd_to_iso_date`` which converts ``20240501`` → ``"2024-05-01"``.

    Args:
        value: A date value in ``yyyymmdd`` integer/string or ISO-8601 format, or ``None``.

    Returns:
        ISO-8601 date string, or an empty string on failure.
    """
    return yyyymmdd_to_iso_date(value) or ""


def _looks_like_header_cell(value: str) -> bool:
    """Return ``True`` if *value* looks like an ISBN column header.

    Used by the file-preview loader to skip the header row of CSV/TSV input files
    so it is not displayed as a data row or validated as an ISBN.

    Args:
        value: Cell text from the first row of the file.

    Returns:
        ``True`` for known header tokens (``"isbn"``, ``"isbn-10"``, ``"isbn-13"``,
        ``"isbn10"``, ``"isbn13"``, ``"world isbn"``, ``"book isbn"``).
    """
    text = str(value or "").strip().lower()
    return text in {"isbn", "isbn-10", "isbn-13", "isbn10", "isbn13", "world isbn", "book isbn"}


def _dedupe_source_text(value: str) -> str:
    """Collapse duplicate source labels before showing them in the UI.

    Splits the value on common separators (``+``, ``,``, ``;``, ``|``), normalises
    the known ``UCB`` → ``UBC`` alias, deduplicates preserving order, and rejoins
    with " + ".  Returns an empty string if no non-empty parts remain.
    """
    parts: list[str] = []
    for piece in re.split(r"[+,;|]", str(value or "")):
        cleaned = piece.strip()
        # Normalise "UCB" to "UBC" (University of British Columbia common alias).
        if cleaned.upper() == "UCB":
            cleaned = "UBC"
        elif cleaned.upper() == "UBC":
            cleaned = "UBC"
        if cleaned and cleaned not in parts:
            parts.append(cleaned)
    return " + ".join(parts)


def _select_marc_values_for_mode(
    lccn: str | None,
    nlmcn: str | None,
    mode: str,
) -> tuple[str | None, str | None]:
    """Return only the call-number fields relevant to the chosen import mode.

    Args:
        lccn: LC call number extracted from the MARC record, or ``None``.
        nlmcn: NLM call number extracted from the MARC record, or ``None``.
        mode: Import mode string — ``"lccn"``, ``"nlmcn"``, or ``"both"``.

    Returns:
        Tuple of ``(selected_lccn, selected_nlmcn)`` with unused fields set to
        ``None`` so callers can rely on truthiness checks.
    """
    normalized_mode = (mode or "lccn").strip().lower()
    if normalized_mode == "nlmcn":
        return None, nlmcn or None
    if normalized_mode == "both":
        return lccn or None, nlmcn or None
    return lccn or None, None


def _prepare_marc_import_records(
    records: list[tuple[str | None, str | None, str | None]],
    *,
    mode: str,
    source_name: str,
) -> tuple[list[tuple[str, str | None, str | None]], list[ParsedMarcImportRecord], int, int, int]:
    """Filter and transform raw MARC tuples for DB persistence and TSV export.

    Iterates over ``(isbn, lccn, nlmcn)`` tuples, selects only the call-number
    fields relevant to *mode* via ``_select_marc_values_for_mode``, and skips
    any record that has no usable call number for the chosen mode.

    Args:
        records: List of ``(isbn, lccn, nlmcn)`` tuples from ``_parse_marc_records``;
                 any field may be ``None``.
        mode: Import mode — ``"lccn"``, ``"nlmcn"``, or ``"both"``.
        source_name: Human-readable source label stored on each DB record.

    Returns:
        A 5-tuple of:
        - ``selected_rows``: List of ``(isbn, lccn, nlmcn)`` tuples ready for TSV output.
        - ``parsed_records``: List of ``ParsedMarcImportRecord`` objects for DB persistence.
        - ``written``: Number of records included (had a call number for the mode).
        - ``skipped``: Number of records excluded (no call number for the mode).
        - ``no_isbn``: Number of included records that had no ISBN (written to DB
          but not linkable to a harvester record).
    """
    selected_rows: list[tuple[str, str | None, str | None]] = []
    parsed_records: list[ParsedMarcImportRecord] = []
    written = 0
    skipped = 0
    no_isbn = 0
    normalized_mode = (mode or "lccn").strip().lower()

    for isbn, lccn, nlmcn in records:
        selected_lccn, selected_nlmcn = _select_marc_values_for_mode(lccn, nlmcn, normalized_mode)

        if normalized_mode == "nlmcn":
            keep = bool(selected_nlmcn)
        elif normalized_mode == "both":
            keep = bool(selected_lccn or selected_nlmcn)
        else:
            keep = bool(selected_lccn)

        if not keep:
            skipped += 1
            continue

        normalized_isbn = str(isbn or "").replace("-", "").strip()
        if not normalized_isbn:
            no_isbn += 1

        selected_rows.append((normalized_isbn, selected_lccn, selected_nlmcn))
        parsed_records.append(
            ParsedMarcImportRecord(
                isbns=(normalized_isbn,) if normalized_isbn else tuple(),
                lccn=selected_lccn,
                nlmcn=selected_nlmcn,
                source=source_name,
            )
        )
        written += 1

    return selected_rows, parsed_records, written, skipped, no_isbn


class HarvestWorker(QThread):
    """Background worker thread that executes a full harvest run.

    Runs in a dedicated ``QThread`` so the Qt event loop (and therefore the GUI)
    stays responsive during long harvest sessions.  All progress and completion
    information is communicated back to the UI exclusively through Qt signals.

    Signals:
        progress_update(isbn, status, source, message): Fired for each significant
            per-ISBN event (found, failed, cached, etc.).
        harvest_complete(success, stats_dict): Fired once when the run ends,
            regardless of whether it succeeded, was cancelled, or errored.
        status_message(str): Human-readable log lines for the harvest log panel.
        started(): Re-emitted when the thread actually begins processing ISBNs.
        stats_update(RunStats): Emitted every 5 ISBNs with a live ``RunStats``
            dataclass so the dashboard KPI cards can update in real time.
        live_result(dict): Per-ISBN result dict with ``isbn``, ``status``,
            and ``detail`` for the recent-results table.
    """

    progress_update = pyqtSignal(str, str, str, str)
    harvest_complete = pyqtSignal(bool, dict)
    status_message = pyqtSignal(str)
    started = pyqtSignal()
    stats_update = pyqtSignal(object)
    live_result = pyqtSignal(dict)

    def __init__(
        self,
        input_file,
        config,
        targets,
        advanced_settings=None,
        bypass_retry_isbns=None,
        live_paths=None,
        db_path="data/lccn_harvester.sqlite3",
    ):
        """
        Args:
            input_file: Path string to the ISBN input file.
            config: Dict of profile settings (retry_days, call_number_mode, etc.).
            targets: List of target config dicts from ``TargetsTab.get_targets()``.
            advanced_settings: Optional dict of advanced overrides (parallel_workers,
                connection_timeout, max_retries).
            bypass_retry_isbns: Optional iterable of ISBNs that should skip the
                retry-window check for this run.
            live_paths: Dict mapping bucket names (``"successful"``, ``"failed"``,
                ``"invalid"``, ``"problems"``, ``"linked"``) to output file path strings.
            db_path: Path to the SQLite database file.
        """
        super().__init__()
        self.input_file = input_file
        self.config = config
        self.db_path = db_path
        self.targets = targets
        self.advanced_settings = advanced_settings or {}
        # ISBNs that should bypass the retry-window check for this specific run.
        self.bypass_retry_isbns = set(bypass_retry_isbns or [])
        self._stop_requested = False   # Set by stop() to request a clean shutdown.
        self._pause_requested = False  # Toggled by toggle_pause() for pause/resume.
        # Lock protecting concurrent writes to the live TSV file handles from multiple threads.
        self._live_results_lock = threading.Lock()
        self._live_result_handles = {}  # {bucket: file_handle} opened in _prepare_live_result_files
        # Tracks (target, problem) pairs already written to the problems file so duplicates
        # (the same connectivity issue appearing across many ISBNs) are not repeated.
        self._live_problem_rows_written = set()
        self.live_paths = live_paths or {}
        # Session-level result lists; snapshotted by HarvestTab._on_complete at run end.
        self._session_success = []
        self._session_failed = []
        self._session_invalid = []

    def run(self):
        """Entry point of the QThread; executes the full harvest lifecycle.

        Sequence:
        1. Parse and validate the ISBN input file.
        2. Open live output TSV file handles and write invalid ISBNs immediately.
        3. Record invalid ISBNs in the DB so they appear in stats.
        4. Call ``run_harvest`` with a ``progress_callback`` that emits signals
           and writes rows to the live files in real time.
        5. Emit ``harvest_complete`` with the final stats dict.
        6. On ``HarvestCancelled`` or any other exception, emit a failure result.
        7. In the ``finally`` block, close all live file handles and generate CSV copies.
        """
        try:
            self.started.emit()
            self.status_message.emit(messages.HarvestMessages.starting)

            parsed = self._read_and_validate_isbns()
            if not parsed:
                return
            isbns = parsed.unique_valid
            invalid_list = parsed.invalid_isbns
            total = len(isbns)
            invalid_count = len(invalid_list)

            # Reset per-run session lists (previous run data cleared).
            self._session_success = []
            self._session_failed = []
            self._session_invalid = list(invalid_list)

            # Create output file handles; invalid ISBNs are written before the main loop starts.
            self._prepare_live_result_files()
            self._write_invalid_live_rows(invalid_list)

            if invalid_count > 0:
                self._record_invalid_isbns(invalid_list)

            self.run_stats = RunStats(
                total_rows=parsed.total_nonempty,
                valid_rows=parsed.valid_count,
                duplicates=parsed.duplicate_count,
                invalid=invalid_count,
                processed_unique=0,
                found=0,
                failed=0,
                skipped=0,
            )

            if total == 0:
                self.status_message.emit(messages.HarvestMessages.no_valid_isbns)
                self.harvest_complete.emit(
                    False, {"total": 0, "found": 0, "failed": 0, "invalid": invalid_count}
                )
                return

            self.processed_count = 0

            def progress_callback(event: str, payload: dict):
                """Called by run_harvest for every significant per-ISBN event.

                Raises ``HarvestCancelled`` if a stop was requested, so the orchestrator
                aborts cleanly.  All UI updates and file writes happen here so the main
                thread stays responsive.

                Args:
                    event: Event type string (e.g. ``"success"``, ``"failed"``,
                           ``"cached"``, ``"stats"``).
                    payload: Dict with event-specific fields (isbn, lccn, source, etc.).
                """
                if self._stop_requested:
                    raise HarvestCancelled("Harvest cancelled by user")

                isbn = payload.get("isbn", "")

                if event == "isbn_start":
                    # Fired at the start of each ISBN; no UI update needed here.
                    return

                if event in ("cached", "linked_cached"):
                    lccn = payload.get("lccn") or ""
                    lccn_source = payload.get("lccn_source") or payload.get("source") or "Cache"
                    nlmcn = payload.get("nlmcn") or ""
                    nlmcn_source = payload.get("nlmcn_source") or payload.get("source") or "Cache"
                    source_text = _dedupe_source_text(payload.get("source") or "Cache")
                    self._session_success.append(
                        self._build_success_row(
                            isbn,
                            lccn=lccn,
                            lccn_source=lccn_source,
                            nlmcn=nlmcn,
                            nlmcn_source=nlmcn_source,
                        )
                    )
                    self._append_live_success(
                        isbn,
                        "Found in cache",
                        lccn=lccn,
                        lccn_source=lccn_source,
                        nlmcn=nlmcn,
                        nlmcn_source=nlmcn_source,
                    )
                    self.live_result.emit(
                        {
                            "isbn": isbn,
                            "status": "Linked ISBN" if event == "linked_cached" else "Found",
                            "detail": source_text,
                        }
                    )
                    self._update_processed()
                    return

                if event == "attempt_failed":
                    self._append_failed_attempt_row(
                        isbn,
                        payload.get("attempt_type"),
                        payload.get("target"),
                        payload.get("reason"),
                        payload.get("attempted_date"),
                    )
                    if payload.get("target") and payload.get("target") != "RetryRule":
                        normalized_problem = self._normalize_target_problem(payload.get("reason"))
                        if normalized_problem:
                            self._append_live_problem(payload.get("target"), normalized_problem)
                    return

                if event == "skip_retry":
                    retry_days = payload.get("retry_days", self.config.get("retry_days", 7))
                    error_text = f"Skipped due to retry window ({retry_days} days)"
                    self._append_retry_skip_rows(
                        isbn,
                        payload.get("targets"),
                        payload.get("attempt_type"),
                        error_text,
                    )
                    self.live_result.emit({"isbn": isbn, "status": "Failed", "detail": error_text})
                    self._update_processed()
                    return

                if event in ("success", "linked_success"):
                    source = payload.get("target", "")
                    lccn = payload.get("lccn") or ""
                    lccn_source = payload.get("lccn_source") or payload.get("source") or source or "Target"
                    nlmcn = payload.get("nlmcn") or ""
                    nlmcn_source = payload.get("nlmcn_source") or payload.get("source") or source or "Target"
                    source_text = _dedupe_source_text(payload.get("source") or source or "Target")
                    self._session_success.append(
                        self._build_success_row(
                            isbn,
                            lccn=lccn,
                            lccn_source=lccn_source,
                            nlmcn=nlmcn,
                            nlmcn_source=nlmcn_source,
                        )
                    )
                    self._append_live_success(
                        isbn,
                        "Found",
                        lccn=lccn,
                        lccn_source=lccn_source,
                        nlmcn=nlmcn,
                        nlmcn_source=nlmcn_source,
                    )
                    self.live_result.emit(
                        {
                            "isbn": isbn,
                            "status": "Linked ISBN" if event == "linked_success" else "Found",
                            "detail": source_text,
                        }
                    )
                    self._update_processed()
                    return

                if event == "not_in_local_catalog":
                    self._append_failed_attempt_row(
                        isbn,
                        self.config.get("call_number_mode", "lccn"),
                        "Local Catalog",
                        "Not found in local catalog",
                    )
                    self.live_result.emit(
                        {"isbn": isbn, "status": "Failed", "detail": "Not found in local catalog"}
                    )
                    self._update_processed()
                    return

                if event == "failed":
                    error = payload.get("last_error") or payload.get("error", "No results")
                    self.live_result.emit({"isbn": isbn, "status": "Failed", "detail": error})
                    self._update_processed()
                    return

                if event == "stats":
                    # Aggregate stats event emitted periodically by the orchestrator;
                    # update run_stats and push to the UI every batch.
                    self.run_stats.found = payload.get("successes", 0) + payload.get("cached", 0)
                    self.run_stats.failed = payload.get("failures", 0) + payload.get(
                        "not_in_local_catalog", 0
                    )
                    self.run_stats.skipped = payload.get("skipped", 0)
                    self.stats_update.emit(self.run_stats)

            targets = self._build_targets()

            retry_days = self.config.get("retry_days", 7)
            call_number_mode = self.config.get("call_number_mode", "lccn")
            try:
                max_workers = max(1, int(self.advanced_settings.get("parallel_workers", 1)))
            except Exception:
                max_workers = 10

            summary = run_harvest(
                input_path=Path(self.input_file),
                dry_run=False,
                db_path=self.db_path,
                retry_days=retry_days,
                targets=targets,
                bypass_retry_isbns=self.bypass_retry_isbns,
                progress_cb=progress_callback,
                cancel_check=lambda: self._check_cancel_and_pause(),
                max_workers=max_workers,
                call_number_mode=call_number_mode,
                stop_rule=self.config.get("stop_rule", "stop_either"),
                both_stop_policy=self.config.get("both_stop_policy", "both"),
                db_only=self.config.get("db_only", False),
            )

            final_stats = {
                "total": summary.total_isbns,
                "found": summary.successes,
                "failed": summary.failures,
                "cached": summary.cached_hits,
                "skipped": summary.skipped_recent_fail,
                "invalid": invalid_count,
                "run_stats": self.run_stats,
            }

            self.status_message.emit(
                messages.HarvestMessages.harvest_completed.format(
                    successes=summary.successes,
                    failures=summary.failures,
                )
            )
            self.harvest_complete.emit(True, final_stats)

        except HarvestCancelled:
            self.status_message.emit("Harvest cancelled by user.")
            stats = {
                "total": self.run_stats.total_rows if hasattr(self, "run_stats") else 0,
                "found": self.run_stats.found if hasattr(self, "run_stats") else 0,
                "failed": self.run_stats.failed if hasattr(self, "run_stats") else 0,
                "invalid": len(getattr(self, "_session_invalid", []) or []),
                "run_stats": self.run_stats if hasattr(self, "run_stats") else None,
                "cancelled": True,
            }
            self.harvest_complete.emit(False, stats)
        except Exception as exc:
            import traceback

            error_msg = f"Error: {exc}\n{traceback.format_exc()}"
            self.status_message.emit(error_msg)
            self.harvest_complete.emit(
                False, {"total": 0, "found": 0, "failed": 0, "invalid": 0, "error": str(exc)}
            )
        finally:
            self._close_live_result_files()

    def _update_processed(self):
        """Increment the processed-ISBN counter and emit stats at regular intervals.

        Emits ``stats_update`` every 5 ISBNs and on the final ISBN so the dashboard
        KPI cards stay in sync without a per-ISBN DB round-trip.
        Also refreshes the live linked-ISBNs snapshot file on each call.
        """
        self.processed_count += 1
        self.run_stats.processed_unique = self.processed_count
        # Keep the linked-ISBNs TSV/CSV snapshot current throughout the run.
        self._refresh_live_linked_isbns_file()

        # Emit every 5 ISBNs or at the very end to balance update frequency vs overhead.
        if self.processed_count % 5 == 0 or self.processed_count == getattr(self.run_stats, "valid_rows", 0):
            self.stats_update.emit(self.run_stats)

    def _prepare_live_result_files(self):
        """Create per-run TSV output files using the pre-computed named paths.

        Opens one file handle per output bucket and writes the column headers.
        The ``utf-8-sig`` BOM ensures Excel opens the files correctly on Windows.
        Existing files are closed and re-created (``_close_live_result_files`` is
        called first to avoid resource leaks).
        """
        headers = {
            "successful": self._successful_headers(),
            "invalid": ["ISBN"],
            "failed": ["Call Number Type", "ISBN", "Target", "Date Attempted", "Reason"],
            "problems": ["Target", "Problem"],
        }
        # Close any previously-open handles from a prior run within the same worker lifetime.
        self._close_live_result_files()
        self._live_problem_rows_written = set()
        for key, header in headers.items():
            path = Path(self.live_paths.get(key, f"data/{key}.tsv"))
            path.parent.mkdir(parents=True, exist_ok=True)
            # Keep the handle open for incremental appends throughout the harvest.
            handle = open(path, "w", encoding="utf-8-sig", newline="")
            writer = csv.writer(handle, delimiter="\t")
            writer.writerow(header)
            handle.flush()
            self._live_result_handles[key] = handle
        self._refresh_live_linked_isbns_file()

    def _close_live_result_files(self):
        """Flush and close all live TSV file handles, then generate CSV copies.

        Called from the ``finally`` block in ``run()`` to guarantee all output is
        persisted even when the run is cancelled or raises an exception.
        """
        saved_paths = []
        for handle in self._live_result_handles.values():
            try:
                handle.flush()
                saved_paths.append(handle.name)
                handle.close()
            except Exception:
                pass
        self._live_result_handles = {}
        # Convert each TSV to a companion CSV for spreadsheet apps.
        self._generate_csv_copies(saved_paths)

    def _generate_csv_copies(self, tsv_paths):
        """Post-flight conversion of TSV to CSV for spreadsheet-friendly output."""
        if not tsv_paths:
            return
        for path_str in tsv_paths:
            tsv_path = Path(path_str)
            if tsv_path.exists() and tsv_path.stat().st_size > 0:
                try:
                    with open(str(tsv_path), newline="", encoding="utf-8") as handle:
                        rows = list(csv.reader(handle, delimiter="\t"))
                    csv_path = tsv_path.with_suffix(".csv")
                    _write_csv_rows(rows, str(csv_path))
                except Exception:
                    logger.exception("Failed to convert %s to CSV.", tsv_path.name)

    def _append_live_row(self, bucket, row):
        """Append a single TSV row to the named output bucket, thread-safely.

        Args:
            bucket: One of ``"successful"``, ``"failed"``, ``"invalid"``, ``"problems"``.
            row: List of cell values to write.
        """
        handle = self._live_result_handles.get(bucket)
        if handle is None:
            return
        # Acquire the lock so parallel workers don't interleave partial rows.
        with self._live_results_lock:
            writer = csv.writer(handle, delimiter="\t")
            writer.writerow(row)
            handle.flush()  # Flush after each row so the file is readable mid-harvest.

    def _write_invalid_live_rows(self, invalid_list):
        for raw_isbn in invalid_list or []:
            self._append_live_row("invalid", [raw_isbn])

    def _refresh_live_linked_isbns_file(self):
        """Rewrite the linked-ISBNs snapshot file from the current DB state.

        Called after every processed ISBN so the file stays current during a long
        harvest.  Both TSV and CSV copies are written atomically (full rewrite, not
        append) because the table can change between calls.
        """
        linked_path_raw = self.live_paths.get("linked")
        if not linked_path_raw:
            return
        linked_path = Path(linked_path_raw)
        linked_path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        try:
            db = DatabaseManager(self.db_path)
            with db.connect() as conn:
                rows = conn.execute(
                    "SELECT other_isbn AS isbn, lowest_isbn AS canonical_isbn "
                    "FROM linked_isbns ORDER BY lowest_isbn, other_isbn"
                ).fetchall()
        except Exception:
            rows = []

        try:
            # Write the TSV snapshot.
            with open(linked_path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle, delimiter="\t")
                writer.writerow(["ISBN", "Canonical ISBN"])
                writer.writerows(rows)
            # Write the companion CSV snapshot for spreadsheet apps.
            _write_csv_rows([["ISBN", "Canonical ISBN"], *rows], str(linked_path.with_suffix(".csv")))
        except Exception:
            pass

    def _successful_headers(self):
        """Return the correct column headers for the successful-results TSV based on the active mode.

        The column set varies by ``call_number_mode``: LCCN-only, NLM-only, or both.
        """
        mode = (self.config.get("call_number_mode", "lccn") or "lccn").strip().lower()
        if mode == "nlmcn":
            return ["ISBN", "NLM", "NLM Source", "Date"]
        if mode == "both":
            return ["ISBN", "LCCN", "LCCN Source", "Classification", "NLM", "NLM Source", "Date"]
        return ["ISBN", "LCCN", "LCCN Source", "Classification", "Date"]

    def _build_success_row(
        self,
        isbn,
        *,
        lccn=None,
        lccn_source=None,
        nlmcn=None,
        nlmcn_source=None,
    ):
        classification = _extract_lc_classification(lccn or "")
        date_added = _display_date(now_datetime_str())
        normalized_isbn = str(isbn or "").replace("-", "").strip()
        mode = (self.config.get("call_number_mode", "lccn") or "lccn").strip().lower()
        if mode == "nlmcn":
            return [normalized_isbn, nlmcn or "", nlmcn_source or "-", date_added]
        if mode == "both":
            return [
                normalized_isbn,
                lccn or "",
                lccn_source or "-",
                classification,
                nlmcn or "",
                nlmcn_source or "-",
                date_added,
            ]
        return [normalized_isbn, lccn or "", lccn_source or "-", classification, date_added]

    def _append_live_success(
        self,
        isbn,
        message,
        *,
        lccn=None,
        lccn_source=None,
        nlmcn=None,
        nlmcn_source=None,
    ):
        """Write a success row to the live TSV file using ``_build_success_row``.

        The *message* parameter is intentionally ignored (kept for API compatibility).

        Args:
            isbn: The successfully processed ISBN.
            message: Ignored; retained so callers do not need a signature change.
            lccn: LC call number found, or ``None``.
            lccn_source: Name of the target that supplied the LCCN.
            nlmcn: NLM call number found, or ``None``.
            nlmcn_source: Name of the target that supplied the NLMCN.
        """
        _ = message
        self._append_live_row(
            "successful",
            self._build_success_row(
                isbn,
                lccn=lccn,
                lccn_source=lccn_source,
                nlmcn=nlmcn,
                nlmcn_source=nlmcn_source,
            ),
        )

    def _compute_next_try_value(self, isbn, retry_days):
        """Compute the earliest re-try date string for a failed ISBN.

        Args:
            isbn: Unused; kept for potential future use without a signature change.
            retry_days: Number of days to add to the current date.

        Returns:
            A ``YYYY/MM/DD`` string, or an empty string when retry_days is zero or
            an error occurs.
        """
        _ = isbn
        try:
            retry_days = int(retry_days or 0)
        except Exception:
            retry_days = 0
        if retry_days <= 0:
            return ""
        try:
            next_dt = datetime.now() + timedelta(days=retry_days)
            return next_dt.strftime("%Y/%m/%d")
        except Exception:
            return ""

    def _append_live_failed(
        self,
        isbn,
        reason,
        source,
        *,
        retry_days=None,
        not_found_targets=None,
        z3950_unsupported_targets=None,
        offline_targets=None,
        other_errors=None,
    ):
        """Write a failed-ISBN row to the live TSV and any applicable problem rows.

        Computes the next-retry date string and delegates problem reporting to
        ``_append_live_problem_rows``.

        Args:
            isbn: The failed ISBN.
            reason: Human-readable failure reason.
            source: Target name or ``"RetryRule"`` for retry-window skips.
            retry_days: Override for the retry window length; falls back to
                ``config["retry_days"]`` when ``None``.
            not_found_targets: Targets that returned a genuine "not found" response.
            z3950_unsupported_targets: Targets where Z39.50 is unavailable.
            offline_targets: Targets that were unreachable.
            other_errors: List of ``"target: reason"`` strings for miscellaneous errors.
        """
        retry_days = self.config.get("retry_days", 7) if retry_days is None else retry_days
        self._append_live_row("failed", [isbn, self._compute_next_try_value(isbn, retry_days)])
        self._append_live_problem_rows(
            source,
            reason,
            not_found_targets=not_found_targets,
            z3950_unsupported_targets=z3950_unsupported_targets,
            offline_targets=offline_targets,
            other_errors=other_errors,
        )

    def _failed_type_labels(self, attempt_type):
        """Map an attempt type to the list of call-number type labels for the failed TSV.

        When the mode is ``"both"`` one failed row is written per call-number type
        so the user can see which individual lookups were unsuccessful.

        Args:
            attempt_type: The attempt type from the harvest event (may be ``None``,
                          in which case the config mode is used as a fallback).

        Returns:
            List of one or two label strings (``"LCCN"`` and/or ``"NLM"``).
        """
        normalized = str(attempt_type or self.config.get("call_number_mode", "lccn")).strip().lower()
        if normalized == "both":
            return ["LCCN", "NLM"]
        if normalized == "nlmcn":
            return ["NLM"]
        return ["LCCN"]

    def _append_failed_attempt_row(self, isbn, attempt_type, target, reason, attempted_date=None):
        """Write one failed-attempt row per call-number type to the session list and live TSV.

        Args:
            isbn: The attempted ISBN.
            attempt_type: The call-number attempt type (used by ``_failed_type_labels``
                          to determine how many rows to write).
            target: Target name that was attempted.
            reason: Human-readable failure reason.
            attempted_date: Optional date value; defaults to the current datetime.
        """
        normalized_isbn = str(isbn or "").replace("-", "").strip()
        attempt_value = _display_date(attempted_date or now_datetime_str())
        for label in self._failed_type_labels(attempt_type):
            row = [label, normalized_isbn, target or "-", attempt_value, reason or "Unknown error"]
            self._session_failed.append(row)
            self._append_live_row("failed", row)

    def _append_retry_skip_rows(self, isbn, targets, attempt_type, reason):
        """Write retry-skip rows (one per target per call-number type) to session list and live TSV.

        Args:
            isbn: The skipped ISBN.
            targets: List of target names that were skipped; falls back to ``["RetryRule"]``.
            attempt_type: Call-number attempt type string.
            reason: Formatted skip reason including the retry window length.
        """
        normalized_isbn = str(isbn or "").replace("-", "").strip()
        attempt_value = _display_date(now_datetime_str())
        for target_name in targets or ["RetryRule"]:
            for label in self._failed_type_labels(attempt_type):
                row = [label, normalized_isbn, target_name or "RetryRule", attempt_value, reason]
                self._session_failed.append(row)
                self._append_live_row("failed", row)

    def _normalize_target_problem(self, reason):
        """Classify a raw failure reason into a normalised problem label for the problems TSV.

        "Not found" outcomes are not problems — they just mean the target does not hold
        the record.  Only genuine infrastructure issues (Z39.50 unavailability, offline
        servers, connection timeouts) are reported as target problems.

        Args:
            reason: Raw error/reason string from the harvest event.

        Returns:
            A normalised problem string, or ``None`` if the reason should not be
            written to the problems file.
        """
        text = str(reason or "").strip()
        lowered = text.lower()
        if not text:
            return None
        # "Not found" is a normal negative result, not a target infrastructure problem.
        if "no records found in" in lowered or "not found" in lowered:
            return None
        if "pyz3950 import failed" in lowered or "pyz3950 import error" in lowered:
            return f"Could not connect to Z39.50 server: {text}"
        if "z39.50 support not available" in lowered:
            return f"Could not connect to Z39.50 server: {text}"
        if (
            "remote end closed connection without response" in lowered
            or "timed out" in lowered
            or "connection refused" in lowered
            or "connection reset" in lowered
            or "temporary failure in name resolution" in lowered
            or "name or service not known" in lowered
            or "offline" in lowered
            or "unreachable" in lowered
        ):
            return "Offline"
        return text

    def _append_live_problem_rows(
        self,
        source,
        reason,
        *,
        not_found_targets=None,
        z3950_unsupported_targets=None,
        offline_targets=None,
        other_errors=None,
    ):
        if source == "RetryRule":
            return

        for target_name in z3950_unsupported_targets or []:
            normalized_problem = self._normalize_target_problem("Z39.50 support not available")
            if normalized_problem:
                self._append_live_problem(target_name, normalized_problem)

        for target_name in offline_targets or []:
            normalized_problem = self._normalize_target_problem("Target offline or unreachable")
            if normalized_problem:
                self._append_live_problem(target_name, normalized_problem)

        for item in other_errors or []:
            target_name, problem = self._split_problem_item(item)
            normalized_problem = self._normalize_target_problem(problem)
            if normalized_problem:
                self._append_live_problem(target_name, normalized_problem)

        if (
            not not_found_targets
            and not (z3950_unsupported_targets or [])
            and not (offline_targets or [])
            and not (other_errors or [])
            and source
            and reason
        ):
            normalized_problem = self._normalize_target_problem(reason)
            if normalized_problem:
                self._append_live_problem(source, normalized_problem)

    def _split_problem_item(self, item):
        text = str(item or "").strip()
        if ": " in text:
            return text.split(": ", 1)
        return ("Unknown", text or "Unknown error")

    def _append_live_problem(self, target, problem):
        """Append a single (target, problem) row to the problems TSV, deduplicating.

        Uses ``_live_problem_rows_written`` (a set of tuples) to avoid writing the
        same target/problem combination more than once — important when the same
        connectivity issue affects many ISBNs in a single run.

        Args:
            target: Target name where the problem was observed.
            problem: Normalised problem description from ``_normalize_target_problem``.
        """
        if target and str(target).strip().lower() == "retryrule":
            return
        row = (target or "Unknown", problem or "Unknown error")
        if row in self._live_problem_rows_written:
            return
        self._live_problem_rows_written.add(row)
        self._append_live_row("problems", list(row))

    def _read_and_validate_isbns(self):
        """Parse ``self.input_file`` and emit a status message for any invalid ISBNs.

        Delegates to ``parse_isbn_file`` from ``src.harvester.run_harvest``.

        Returns:
            A ``ParsedISBNFile`` object on success, or ``None`` if the file could
            not be read (error message emitted via ``status_message``).
        """
        try:
            parsed = parse_isbn_file(Path(self.input_file))
            if parsed.invalid_isbns:
                self.status_message.emit(
                    messages.HarvestMessages.invalid_isbns_count.format(
                        count=len(parsed.invalid_isbns)
                    )
                )
            return parsed
        except Exception as exc:
            self.status_message.emit(messages.HarvestMessages.error_reading_file.format(error=str(exc)))
            return None

    def _record_invalid_isbns(self, invalid_list):
        """Insert invalid ISBNs into the ``attempted`` table so they appear in stats.

        Uses ``INSERT OR ABORT ... ON CONFLICT ... DO UPDATE`` (upsert) so
        re-running the same file increments ``fail_count`` rather than creating
        duplicate rows.

        Args:
            invalid_list: Iterable of raw (non-normalised) ISBN strings that failed
                          validation.
        """
        if not invalid_list:
            return

        try:
            db = DatabaseManager(self.db_path)
            with db.transaction() as conn:
                for raw_isbn in invalid_list:
                    conn.execute(
                        "INSERT OR ABORT INTO attempted (isbn, last_target, attempt_type, last_attempted, fail_count, last_error) "
                        "VALUES (?, ?, ?, ?, 1, 'Invalid ISBN') "
                        "ON CONFLICT(isbn, last_target, attempt_type) DO UPDATE SET "
                        "last_attempted=excluded.last_attempted, fail_count=fail_count+1, last_error='Invalid ISBN'",
                        (raw_isbn[:20], "Validation", "validation", now_datetime_str()),
                    )
        except Exception:
            pass

    def _build_targets(self):
        """Instantiate harvest target objects from the targets configuration list.

        Filters to selected targets, sorts by ``rank``, applies any global timeout
        and retry overrides from ``advanced_settings``, and calls
        ``create_target_from_config`` for each one.

        Returns:
            List of target instances, ``None`` if instantiation failed for all, or
            an empty list if no targets were selected.
        """
        if not self.targets:
            return []

        try:
            selected_targets = [target for target in self.targets if target.get("selected", True)]
            if not selected_targets:
                return []
            sorted_targets = sorted(selected_targets, key=lambda item: item.get("rank", 999))
            try:
                global_timeout = int(self.advanced_settings.get("connection_timeout", 0))
            except Exception:
                global_timeout = 0
            try:
                global_retries = int(self.advanced_settings.get("max_retries", 0))
            except Exception:
                global_retries = 0

            target_instances = []
            for target_config in sorted_targets:
                try:
                    cfg = dict(target_config)
                    if global_timeout > 0:
                        cfg["timeout"] = global_timeout
                    if global_retries >= 0:
                        cfg["max_retries"] = global_retries
                    target_instances.append(create_target_from_config(cfg))
                except Exception as exc:
                    self.status_message.emit(
                        messages.HarvestMessages.failed_create_target.format(
                            name=target_config.get("name"),
                            error=str(exc),
                        )
                    )

            return target_instances if target_instances else None

        except Exception as exc:
            self.status_message.emit(messages.HarvestMessages.error_building_targets.format(error=str(exc)))
            return None

    def stop(self):
        """Signal the worker to stop after the current ISBN completes.

        Sets ``_stop_requested``; the ``progress_callback`` checks this flag and
        raises ``HarvestCancelled`` to unwind the harvest loop cleanly.
        """
        self._stop_requested = True

    def toggle_pause(self):
        """Toggle the worker's pause state.

        When ``_pause_requested`` is set to ``True``, ``_check_cancel_and_pause``
        will spin-wait in the worker thread until the flag is cleared again.
        """
        self._pause_requested = not self._pause_requested

    def _check_cancel_and_pause(self):
        """Spin-wait while paused; return ``True`` immediately if a stop was requested.

        Called by the harvest orchestrator as the ``cancel_check`` callback.
        Sleeping in 100 ms intervals keeps CPU usage low during a pause without
        blocking the GIL for long stretches.

        Returns:
            ``True`` if the harvest should be cancelled, ``False`` to continue.
        """
        import time

        # Block here while the user has paused the harvest.
        while self._pause_requested and not self._stop_requested:
            time.sleep(0.1)
        return self._stop_requested


class DroppableGroupBox(QGroupBox):
    """A ``QGroupBox`` that accepts drag-and-drop of harvest input files.

    Accepted extensions: ``.tsv``, ``.txt``, ``.csv``, ``.xlsx``, ``.xls``.
    Emits ``file_dropped`` with the path of the first valid file when a drop
    succeeds, or shows a warning dialog for unrecognised file types.

    The ``dropState`` dynamic property (``"normal"``, ``"hover"``, ``"dropped"``)
    drives QSS visual feedback during a drag operation.

    Signals:
        file_dropped(str): Emitted with the absolute path of the dropped file.
    """

    file_dropped = pyqtSignal(str)

    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.setAcceptDrops(True)
        self.setObjectName("DroppableArea")
        self.setProperty("dropState", "normal")

    def _update_state(self, state: str):
        """Update the ``dropState`` property and force a QSS re-polish.

        Args:
            state: One of ``"normal"``, ``"hover"``, or ``"dropped"``.
        """
        self.setProperty("dropState", state)
        # unpolish/polish forces Qt to re-evaluate the QSS [dropState="..."] selector.
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Accept the drag if at least one URL maps to a local file."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile():
                    event.acceptProposedAction()
                    # Switch to "hover" so QSS can apply a drag-over highlight.
                    self._update_state("hover")
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        """Restore the normal appearance when the drag leaves the widget."""
        _ = event
        self._update_state("normal")

    def dropEvent(self, event: QDropEvent):
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        # Filter to recognised input-file extensions only.
        valid_files = [path for path in files if path.endswith((".tsv", ".txt", ".csv", ".xlsx", ".xls"))]

        if valid_files:
            # Emit the first valid file and briefly show the "dropped" state for visual feedback.
            self.file_dropped.emit(valid_files[0])
            self._update_state("dropped")
            # Reset to normal after 500 ms so the group box does not stay highlighted.
            QTimer.singleShot(500, lambda: self._update_state("normal"))
            event.acceptProposedAction()
            return

        QMessageBox.warning(
            self,
            "Invalid File",
            "Please drop a valid TSV, TXT, CSV, or Excel file.",
        )
        event.ignore()
        self._update_state("normal")
