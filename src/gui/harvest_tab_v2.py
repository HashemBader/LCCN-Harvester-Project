"""
Module: harvest_tab_v2.py
V2 Harvest Tab: Functional Core with Professional UI.
"""

from PyQt6.QtWidgets import (
    QWidget,
    QApplication,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QTextEdit,
    QProgressBar,
    QFrame,
    QGridLayout,
    QMessageBox,
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QComboBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialog,
    QCheckBox,
)
from datetime import datetime, timedelta, timezone
from PyQt6.QtCore import Qt, QTimer, QTime, pyqtSignal, QSize, QThread
from PyQt6.QtGui import QShortcut, QKeySequence, QDragEnterEvent, QDropEvent, QColor, QBrush
from pathlib import Path
from enum import Enum, auto
from itertools import islice
import csv
import sys
import json
import threading
import re

# Add src to path for utils import
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.isbn_validator import normalize_isbn

from .combo_boxes import ConsistentComboBox
from .icons import SVG_HARVEST, SVG_INPUT, SVG_ACTIVITY
from .input_tab import ClickableDropZone

# Add imports for Worker
from src.harvester.run_harvest import run_harvest, parse_isbn_file, RunStats
from src.harvester.marc_import import MarcImportService, ParsedMarcImportRecord
from src.harvester.targets import create_target_from_config
from src.harvester.orchestrator import HarvestCancelled
from src.database import DatabaseManager, now_datetime_str
from src.database.db_manager import yyyymmdd_to_iso_date
from src.config.profile_manager import ProfileManager
from src.utils import messages
from .theme_manager import ThemeManager


def _write_csv_rows(rows_with_header: list, path: str) -> None:
    """Write rows to a UTF-8 CSV file for Excel and Google Sheets."""
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows_with_header)


def _extract_lc_classification(lccn: str) -> str:
    """Derive the LC class prefix (letters only) from an LCCN / call-number string."""
    if not lccn:
        return ""
    m = re.match(r"^([A-Za-z]+)", lccn.strip())
    return m.group(1).upper() if m else ""


def _safe_filename(s: str) -> str:
    """Strip characters that are invalid in file names."""
    return re.sub(r'[\\/:*?"<>|\s]+', "_", s).strip("_") or "default"


def _display_date(value) -> str:
    """Format storage dates for TSV/live display."""
    return yyyymmdd_to_iso_date(value) or ""


def _looks_like_header_cell(value: str) -> bool:
    text = str(value or "").strip().lower()
    return text in {"isbn", "isbn-10", "isbn-13", "isbn10", "isbn13", "world isbn", "book isbn"}


def _dedupe_source_text(value: str) -> str:
    parts: list[str] = []
    for piece in re.split(r"[+,;|]", str(value or "")):
        cleaned = piece.strip()
        if cleaned.upper() == "UCB":
            cleaned = "UBC"
        elif cleaned.upper() == "UBC":
            cleaned = "UBC"
        if cleaned and cleaned not in parts:
            parts.append(cleaned)
    return " + ".join(parts)


def _select_marc_values_for_mode(lccn: str | None, nlmcn: str | None, mode: str) -> tuple[str | None, str | None]:
    """Return only the call-number fields relevant to the chosen import mode."""
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
    """Prepare MARC rows for both export files and database persistence."""
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


class HarvestWorkerV2(QThread):
    """Background worker thread for harvest operations (V2)."""

    progress_update = pyqtSignal(str, str, str, str)  # isbn, status, source, message
    harvest_complete = pyqtSignal(
        bool, dict
    )  # success, statistics (can include 'cancelled': True)
    status_message = pyqtSignal(str)
    started = pyqtSignal()
    stats_update = pyqtSignal(object)  # real-time statistics update (RunStats)
    live_result = pyqtSignal(dict)   # real-time single row result

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
        super().__init__()
        self.input_file = input_file
        self.config = config
        self.db_path = db_path
        self.targets = targets
        self.advanced_settings = advanced_settings or {}
        self.bypass_retry_isbns = set(bypass_retry_isbns or [])
        self._stop_requested = False
        self._pause_requested = False
        self._live_results_lock = threading.Lock()
        self._live_result_handles = {}
        self._live_problem_rows_written = set()
        # Paths for the live output files (computed before thread starts)
        self.live_paths = live_paths or {}
        # Session-only result accumulators (never read from DB)
        self._session_success = (
            []
        )  # per-run success TSV rows
        self._session_failed = (
            []
        )  # [call_number_type, isbn, target, reason]
        self._session_invalid = []  # [isbn]

    def run(self):
        """Run the harvest operation in background thread."""
        try:
            self.started.emit()
            self.status_message.emit(messages.HarvestMessages.starting)

            # Read and validate ISBNs
            parsed = self._read_and_validate_isbns()
            if not parsed:
                return
            isbns = parsed.unique_valid
            invalid_list = parsed.invalid_isbns
            total = len(isbns)
            invalid_count = len(invalid_list)

            # Reset session accumulators for this run
            self._session_success = []
            self._session_failed = []
            self._session_invalid = list(invalid_list)

            # Overwrite live result files at the start of each run
            self._prepare_live_result_files()
            self._write_invalid_live_rows(invalid_list)

            # Record invalid stats
            if invalid_count > 0:
                self._record_invalid_isbns(invalid_list)

            # Track stats for GUI updates using centralized RunStats
            self.run_stats = RunStats(
                total_rows=parsed.total_nonempty,
                valid_rows=parsed.valid_count,
                duplicates=parsed.duplicate_count,
                invalid=invalid_count,
                processed_unique=0,
                found=0,
                failed=0,
                skipped=0
            )

            if total == 0:
                self.status_message.emit(messages.HarvestMessages.no_valid_isbns)
                self.harvest_complete.emit(
                    False, {"total": 0, "found": 0, "failed": 0, "invalid": invalid_count}
                )
                return

            self.processed_count = 0

            # Create progress callback
            def progress_callback(event: str, payload: dict):
                if self._stop_requested:
                    raise HarvestCancelled("Harvest cancelled by user")

                isbn = payload.get("isbn", "")

                if event == "isbn_start":
                    # self.progress_update.emit(
                    #    isbn, "processing", "", messages.HarvestMessages.processing_isbn
                    # )
                    pass

                elif event in ("cached", "linked_cached"):
                    # self.progress_update.emit(
                    #    isbn, "cached", "Cache", messages.HarvestMessages.found_in_cache
                    # )
                    _lccn = payload.get("lccn") or ""
                    _lccn_source = payload.get("lccn_source") or payload.get("source") or "Cache"
                    _nlmcn = payload.get("nlmcn") or ""
                    _nlmcn_source = payload.get("nlmcn_source") or payload.get("source") or "Cache"
                    _src = _dedupe_source_text(payload.get("source") or "Cache")
                    self._session_success.append(self._build_success_row(
                        isbn,
                        lccn=_lccn,
                        lccn_source=_lccn_source,
                        nlmcn=_nlmcn,
                        nlmcn_source=_nlmcn_source,
                    ))
                    self._append_live_success(
                        isbn,
                        "Found in cache",
                        lccn=_lccn,
                        lccn_source=_lccn_source,
                        nlmcn=_nlmcn,
                        nlmcn_source=_nlmcn_source,
                    )
                    self.live_result.emit({
                        "isbn": isbn,
                        "status": "Linked ISBN" if event == "linked_cached" else "Found",
                        "detail": _src
                    })
                    self._update_processed()

                elif event == "attempt_failed":
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

                elif event == "skip_retry":
                    # self.progress_update.emit(
                    #     isbn,
                    #     "skipped",
                    #     "",
                    #     messages.HarvestMessages.skipped_recent_failure,
                    # )
                    retry_days = payload.get(
                        "retry_days", self.config.get("retry_days", 7)
                    )
                    _err = f"Skipped due to retry window ({retry_days} days)"
                    self._append_retry_skip_rows(
                        isbn,
                        payload.get("targets"),
                        payload.get("attempt_type"),
                        _err,
                    )
                    self.live_result.emit({
                        "isbn": isbn,
                        "status": "Failed",
                        "detail": _err
                    })
                    self._update_processed()

                elif event in ("success", "linked_success"):
                    source = payload.get("target", "")
                    # self.progress_update.emit(isbn, "found", source, "Found")
                    _lccn = payload.get("lccn") or ""
                    _lccn_source = payload.get("lccn_source") or payload.get("source") or source or "Target"
                    _nlmcn = payload.get("nlmcn") or ""
                    _nlmcn_source = payload.get("nlmcn_source") or payload.get("source") or source or "Target"
                    _src = _dedupe_source_text(payload.get("source") or source or "Target")
                    self._session_success.append(self._build_success_row(
                        isbn,
                        lccn=_lccn,
                        lccn_source=_lccn_source,
                        nlmcn=_nlmcn,
                        nlmcn_source=_nlmcn_source,
                    ))
                    self._append_live_success(
                        isbn,
                        "Found",
                        lccn=_lccn,
                        lccn_source=_lccn_source,
                        nlmcn=_nlmcn,
                        nlmcn_source=_nlmcn_source,
                    )
                    self.live_result.emit({
                        "isbn": isbn,
                        "status": "Linked ISBN" if event == "linked_success" else "Found",
                        "detail": _src
                    })
                    self._update_processed()

                elif event == "not_in_local_catalog":
                    self._append_failed_attempt_row(
                        isbn,
                        self.config.get("call_number_mode", "lccn"),
                        "Local Catalog",
                        "Not found in local catalog",
                    )
                    self.live_result.emit({
                        "isbn": isbn,
                        "status": "Failed",
                        "detail": "Not found in local catalog"
                    })
                    self._update_processed()

                elif event == "failed":
                    error = payload.get("last_error") or payload.get(
                        "error", "No results"
                    )
                    source = payload.get("last_target") or "All"
                    # self.progress_update.emit(isbn, "failed", source, error)
                    self.live_result.emit({
                        "isbn": isbn,
                        "status": "Failed",
                        "detail": error
                    })
                    self._update_processed()

                elif event == "stats":
                    self.run_stats.found = payload.get("successes", 0) + payload.get("cached", 0)
                    self.run_stats.failed = payload.get("failures", 0) + payload.get("not_in_local_catalog", 0)
                    self.run_stats.skipped = payload.get("skipped", 0)
                    # Force stats update to UI
                    self.stats_update.emit(self.run_stats)

            # Build targets list from config
            targets = self._build_targets()

            # Print target info
            if targets:
                pass

            # Run the harvest pipeline
            retry_days = self.config.get("retry_days", 7)
            call_number_mode = self.config.get("call_number_mode", "lccn")
            try:
                max_workers = max(
                    1, int(self.advanced_settings.get("parallel_workers", 1))
                )
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

            # Final stats
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
                    successes=summary.successes, failures=summary.failures
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
                "cancelled": True
            }
            self.harvest_complete.emit(False, stats)
        except Exception as e:
            import traceback

            error_msg = f"Error: {str(e)}\n{traceback.format_exc()}"
            self.status_message.emit(error_msg)
            self.harvest_complete.emit(
                False, {"total": 0, "found": 0, "failed": 0, "invalid": 0, "error": str(e)}
            )
        finally:
            self._close_live_result_files()

    def _update_processed(self):
        """Update processed count and emit stats/milestones."""
        self.processed_count += 1
        self.run_stats.processed_unique = self.processed_count
        self._refresh_live_linked_isbns_file()

        # Emit stats update for UI
        if self.processed_count % 5 == 0 or self.processed_count == getattr(self.run_stats, 'valid_rows', 0):
            self.stats_update.emit(self.run_stats)

    def _prepare_live_result_files(self):
        """Create per-run TSV output files using the pre-computed named paths."""
        headers = {
            "successful": self._successful_headers(),
            "invalid": ["ISBN"],
            "failed": ["Call Number Type", "ISBN", "Target", "Date Attempted", "Reason"],
            "problems": ["Target", "Problem"],
        }
        self._close_live_result_files()
        self._live_problem_rows_written = set()
        for key, header in headers.items():
            path = Path(self.live_paths.get(key, f"data/{key}.tsv"))
            path.parent.mkdir(parents=True, exist_ok=True)
            fh = open(path, "w", encoding="utf-8-sig", newline="")
            writer = csv.writer(fh, delimiter="\t")
            writer.writerow(header)
            fh.flush()
            self._live_result_handles[key] = fh
        self._refresh_live_linked_isbns_file()

    def _close_live_result_files(self):
        saved_paths = []
        for key, fh in self._live_result_handles.items():
            try:
                fh.flush()
                saved_paths.append(fh.name)
                fh.close()
            except Exception:
                pass
        self._live_result_handles = {}
        self._generate_csv_copies(saved_paths)

    def _generate_csv_copies(self, tsv_paths):
        """Post-flight conversion of TSV to CSV for spreadsheet-friendly output."""
        import csv as _csv
        if not tsv_paths:
            return
        for path_str in tsv_paths:
            tsv_path = Path(path_str)
            if tsv_path.exists() and tsv_path.stat().st_size > 0:
                try:
                    with open(str(tsv_path), newline="", encoding="utf-8") as f:
                        rows = list(_csv.reader(f, delimiter="\t"))
                    csv_path = tsv_path.with_suffix(".csv")
                    _write_csv_rows(rows, str(csv_path))
                except Exception as e:
                    print(f"Failed to convert {tsv_path.name} to CSV: {e}")

    def _append_live_row(self, bucket, row):
        fh = self._live_result_handles.get(bucket)
        if fh is None:
            return
        with self._live_results_lock:
            writer = csv.writer(fh, delimiter="\t")
            writer.writerow(row)
            fh.flush()  # Flush immediately so file is readable live during harvest

    def _write_invalid_live_rows(self, invalid_list):
        for raw_isbn in invalid_list or []:
            self._append_live_row("invalid", [raw_isbn])

    def _refresh_live_linked_isbns_file(self):
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
            with open(linked_path, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh, delimiter="\t")
                writer.writerow(["ISBN", "Canonical ISBN"])
                writer.writerows(rows)
            _write_csv_rows([["ISBN", "Canonical ISBN"], *rows], str(linked_path.with_suffix(".csv")))
        except Exception:
            pass

    def _successful_headers(self):
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
        try:
            retry_days = int(retry_days or 0)
        except Exception:
            retry_days = 0
        if retry_days <= 0:
            return ""
        try:
            # Compute "next try" from *now* – no DB query needed during a live run.
            # The attempted record may not be committed yet at the moment this is called.
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
        retry_days = (
            self.config.get("retry_days", 7) if retry_days is None else retry_days
        )
        self._append_live_row(
            "failed",
            [
                isbn,
                self._compute_next_try_value(isbn, retry_days),
            ],
        )
        self._append_live_problem_rows(
            source,
            reason,
            not_found_targets=not_found_targets,
            z3950_unsupported_targets=z3950_unsupported_targets,
            offline_targets=offline_targets,
            other_errors=other_errors,
        )

    def _failed_type_labels(self, attempt_type):
        normalized = str(attempt_type or self.config.get("call_number_mode", "lccn")).strip().lower()
        if normalized == "both":
            return ["LCCN", "NLM"]
        if normalized == "nlmcn":
            return ["NLM"]
        return ["LCCN"]

    def _append_failed_attempt_row(self, isbn, attempt_type, target, reason, attempted_date=None):
        normalized_isbn = str(isbn or "").replace("-", "").strip()
        attempt_value = _display_date(attempted_date or now_datetime_str())
        for label in self._failed_type_labels(attempt_type):
            row = [label, normalized_isbn, target or "-", attempt_value, reason or "Unknown error"]
            self._session_failed.append(row)
            self._append_live_row("failed", row)

    def _append_retry_skip_rows(self, isbn, targets, attempt_type, reason):
        normalized_isbn = str(isbn or "").replace("-", "").strip()
        attempt_value = _display_date(now_datetime_str())
        for target_name in targets or ["RetryRule"]:
            for label in self._failed_type_labels(attempt_type):
                row = [label, normalized_isbn, target_name or "RetryRule", attempt_value, reason]
                self._session_failed.append(row)
                self._append_live_row("failed", row)

    def _normalize_target_problem(self, reason):
        text = str(reason or "").strip()
        lowered = text.lower()
        if not text:
            return None
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
        if target and str(target).strip().lower() == "retryrule":
            return
        row = (target or "Unknown", problem or "Unknown error")
        if row in self._live_problem_rows_written:
            return
        self._live_problem_rows_written.add(row)
        self._append_live_row("problems", list(row))

    def _read_and_validate_isbns(self):
        """Read and validate ISBNs using the centralized parser."""
        try:
            parsed = parse_isbn_file(Path(self.input_file))
            if parsed.invalid_isbns:
                self.status_message.emit(
                    messages.HarvestMessages.invalid_isbns_count.format(
                        count=len(parsed.invalid_isbns)
                    )
                )
            return parsed
        except Exception as e:
            self.status_message.emit(
                messages.HarvestMessages.error_reading_file.format(error=str(e))
            )
            return None

    def _record_invalid_isbns(self, invalid_list):
        """Record invalid ISBNs in DB so they appear in stats."""
        if not invalid_list:
            return

        try:
            db = DatabaseManager(self.db_path)
            with db.transaction() as conn:
                for raw_isbn in invalid_list:
                    # Upsert into attempted with 'Invalid' error
                    # We use a placeholder target 'Validation'
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
        """Build list of harvest targets from targets configuration."""
        if not self.targets:
            return []

        try:
            selected_targets = [t for t in self.targets if t.get("selected", True)]
            if not selected_targets:
                return []
            sorted_targets = sorted(selected_targets, key=lambda x: x.get("rank", 999))
            try:
                global_timeout = int(
                    self.advanced_settings.get("connection_timeout", 0)
                )
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
                    target = create_target_from_config(cfg)
                    target_instances.append(target)
                except Exception as e:
                    self.status_message.emit(
                        messages.HarvestMessages.failed_create_target.format(
                            name=target_config.get("name"), error=str(e)
                        )
                    )

            return target_instances if target_instances else None

        except Exception as e:
            self.status_message.emit(
                messages.HarvestMessages.error_building_targets.format(error=str(e))
            )
            return None

    def stop(self):
        """Request worker to stop."""
        self._stop_requested = True

    def toggle_pause(self):
        """Toggle pause state."""
        self._pause_requested = not self._pause_requested

    def _check_cancel_and_pause(self):
        import time

        while self._pause_requested and not self._stop_requested:
            time.sleep(0.1)
        return self._stop_requested


class DroppableGroupBox(QGroupBox):
    """A group box that accepts drag and drop (for the compact upload card)."""

    file_dropped = pyqtSignal(str)

    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.setAcceptDrops(True)
        self.setObjectName("DroppableArea")
        self.setProperty("dropState", "normal")

    def _update_state(self, state: str):
        self.setProperty("dropState", state)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if True:  # Accept all types or handled elsewhere
                    event.acceptProposedAction()
                    self._update_state("hover")
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._update_state("normal")

    def dropEvent(self, event: QDropEvent):
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        valid_files = [f for f in files if f.endswith((".tsv", ".txt", ".csv", ".xlsx", ".xls"))]

        if valid_files:
            file_path = valid_files[0]
            self.file_dropped.emit(file_path)
            self._update_state("dropped")
            
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(500, lambda: self._update_state("normal"))
            event.acceptProposedAction()
        else:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self, "Invalid File", "Please drop a valid TSV, TXT, CSV, or Excel file."
            )
            event.ignore()
            self._update_state("normal")


class UIState(Enum):
    IDLE = auto()
    READY = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    ERROR = auto()
    CANCELLED = auto()


class HarvestTabV2(QWidget):
    harvest_started = pyqtSignal()
    harvest_finished = pyqtSignal(bool, dict)
    harvest_reset = pyqtSignal()
    harvest_paused = pyqtSignal(bool)  # True = paused, False = resumed
    progress_updated = pyqtSignal(str, str, str, str)  # isbn, status, source, message
    result_files_ready = pyqtSignal(dict)  # emitted when live output paths are known
    live_result_ready = pyqtSignal(dict)   # emitted per ISBN harvested
    live_stats_ready = pyqtSignal(object)    # emitted for batch counts (RunStats)

    # Signals to request data from main window
    request_start_harvest = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.worker = None
        self.is_running = False
        self.current_state = UIState.IDLE
        self.input_file = None
        # Session-only result snapshots populated after each harvest completes
        self._last_session_success = []
        self._last_session_failed = []
        self._last_session_invalid = []
        # Current-run output file paths (set in _start_worker)
        self._run_live_paths = {}  # paths for dashboard live files
        # External data sources (set by Main Window)
        self._config_getter = None
        self._targets_getter = None
        self._profile_getter = None
        self._db_path_getter = None

        self.processed_count = 0
        self.total_count = 0
        self._shortcut_modifier = "Meta" if sys.platform == "darwin" else "Ctrl"

        self._setup_ui()
        self._setup_shortcuts()
        self._update_scrollbar_policy()

    def set_data_sources(self, config_getter, targets_getter, profile_getter=None, db_path_getter=None):
        """Set callbacks to retrieve config, targets, active profile name, and db path."""
        self._config_getter = config_getter
        self._targets_getter = targets_getter
        self._profile_getter = profile_getter
        self._db_path_getter = db_path_getter

    def on_targets_changed(self, targets):
        """Handle target selection changes from TargetsTab."""
        # Don't reset UI state while a harvest is in progress or showing results
        if self.current_state in (
            UIState.RUNNING,
            UIState.PAUSED,
            UIState.COMPLETED,
            UIState.CANCELLED,
        ):
            return
        self._check_start_conditions()

    def _setup_ui(self):
        # Direct layout — no scroll area; everything must fit in one screen
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(20, 12, 20, 12)

        # ── 1. Header ──────────────────────────────────────────────────────────
        header_layout = QHBoxLayout()
        title = QLabel("Harvest Execution")
        title.setProperty("class", "SectionTitle")
        subtitle = QLabel("Configure your run and monitor progress")
        subtitle.setStyleSheet("font-size: 12px;")
        header_col = QVBoxLayout()
        header_col.setSpacing(2)
        header_col.addWidget(title)
        header_col.addWidget(subtitle)
        header_layout.addLayout(header_col)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # ── 2. Status Banner ───────────────────────────────────────────────────
        self.banner_frame = QFrame()
        self.banner_frame.setObjectName("HarvestBanner")
        self.banner_frame.setProperty("class", "Card")
        banner_layout = QHBoxLayout(self.banner_frame)
        banner_layout.setContentsMargins(16, 6, 16, 6)
        self.lbl_banner_title = QLabel("READY")
        self.lbl_banner_title.setProperty("class", "CardTitle")
        self.lbl_banner_stats = QLabel("")
        self.lbl_banner_stats.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_banner_stats.setProperty("class", "HelperText")
        self.lbl_banner_stats.setVisible(False)
        banner_layout.addWidget(self.lbl_banner_title)
        banner_layout.addStretch()
        banner_layout.addWidget(self.lbl_banner_stats)
        layout.addWidget(self.banner_frame)

        # ── 3. 2×2 grid: [Run Setup | File Statistics] / [MARC Import | File Preview]
        middle_row = QGridLayout()
        middle_row.setSpacing(12)
        middle_row.setColumnStretch(0, 1)
        middle_row.setColumnStretch(1, 1)
        middle_row.setRowStretch(0, 1)
        middle_row.setRowStretch(1, 1)

        # ── LEFT: Run Setup card ───────────────────────────────────────────────
        self.input_card = DroppableGroupBox("Run Setup")
        self.input_card.file_dropped.connect(self.set_input_file)
        self.input_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        input_layout = QVBoxLayout(self.input_card)
        input_layout.setContentsMargins(16, 10, 16, 10)
        input_layout.setSpacing(6)

        setup_grid = QGridLayout()
        setup_grid.setSpacing(6)
        setup_grid.setColumnStretch(1, 1)

        lbl_input = QLabel("Input file:")
        lbl_input.setProperty("class", "HelperText")
        file_input_layout = QHBoxLayout()
        file_input_layout.setSpacing(6)
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setPlaceholderText("No file selected… drag & drop or browse")
        self.file_path_edit.setReadOnly(True)
        self.file_path_edit.setProperty("class", "LineEdit")
        self.btn_browse = QPushButton("Browse…")
        self.btn_browse.setProperty("class", "PrimaryButton")
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.clicked.connect(self._browse_file)
        self.btn_clear_file = QPushButton("Clear")
        self.btn_clear_file.setProperty("class", "DangerButton")
        self.btn_clear_file.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_file.clicked.connect(self._clear_input)
        self.btn_clear_file.setVisible(False)
        file_input_layout.addWidget(self.file_path_edit)
        file_input_layout.addWidget(self.btn_clear_file)
        file_input_layout.addWidget(self.btn_browse)
        setup_grid.addWidget(lbl_input, 0, 0)
        setup_grid.addLayout(file_input_layout, 0, 1)

        lbl_run_mode = QLabel("Run Mode:")
        lbl_run_mode.setProperty("class", "HelperText")
        self.combo_run_mode = ConsistentComboBox()
        self.combo_run_mode.setProperty("class", "ComboBox")
        self.combo_run_mode.addItems(["LCCN Only", "NLM Only", "Both (LCCN & NLM)", "MARC Import Only"])
        self.combo_run_mode.setToolTip("Select the type of call numbers to harvest")
        if hasattr(self, "_config_getter") and callable(self._config_getter):
            config = self._config_getter() or {}
            saved_mode = config.get("call_number_mode", "lccn")
            if saved_mode == "nlmcn":
                self.combo_run_mode.setCurrentText("NLM Only")
            elif saved_mode == "both":
                self.combo_run_mode.setCurrentText("Both (LCCN & NLM)")
            elif saved_mode == "marc_only":
                self.combo_run_mode.setCurrentText("MARC Import Only")
            else:
                self.combo_run_mode.setCurrentText("LCCN Only")
        else:
            self.combo_run_mode.setCurrentText("LCCN Only")
        setup_grid.addWidget(lbl_run_mode, 1, 0)
        setup_grid.addWidget(self.combo_run_mode, 1, 1)

        self.lbl_stop_rule = QLabel("Stop Rule:")
        self.lbl_stop_rule.setProperty("class", "HelperText")
        self.combo_stop_rule = ConsistentComboBox()
        self.combo_stop_rule.setProperty("class", "ComboBox")
        self.combo_stop_rule.addItems([
            "Stop if either found",
            "Stop if LCCN found",
            "Stop if NLMCN found",
            "Continue until both found",
        ])
        if hasattr(self, "_config_getter") and callable(self._config_getter):
            saved_stop = config.get("stop_rule", "stop_either")
            mapping = {
                "stop_either": "Stop if either found",
                "stop_lccn": "Stop if LCCN found",
                "stop_nlmcn": "Stop if NLMCN found",
                "continue_both": "Continue until both found",
            }
            self.combo_stop_rule.setCurrentText(mapping.get(saved_stop, "Stop if either found"))
        setup_grid.addWidget(self.lbl_stop_rule, 2, 0)
        setup_grid.addWidget(self.combo_stop_rule, 2, 1)

        self.chk_db_only = QCheckBox("Database only for this run")
        self.chk_db_only.setToolTip("Skip APIs and Z39.50 targets and search only the existing SQLite database")
        self.chk_db_only.setCursor(Qt.CursorShape.PointingHandCursor)
        setup_grid.addWidget(self.chk_db_only, 3, 1)
        self._apply_db_only_checkbox_style()

        self.combo_run_mode.currentTextChanged.connect(self._toggle_stop_rule_visibility)
        self.chk_db_only.toggled.connect(self._toggle_stop_rule_visibility)
        self._toggle_stop_rule_visibility(self.combo_run_mode.currentText())
        input_layout.addLayout(setup_grid)
        input_layout.addStretch()

        # ── MARC Import card (bottom-left) ────────────────────────────────────
        marc_card = QGroupBox("MARC Import")
        marc_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        marc_vbox = QVBoxLayout(marc_card)
        marc_vbox.setContentsMargins(14, 12, 14, 14)
        marc_vbox.setSpacing(10)

        # 1. Status banner
        self._marc_status_label = QLabel("Select a MARC file (.mrc / .xml) to import into the database and export results.")
        self._marc_status_label.setWordWrap(True)
        self._marc_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._marc_status_label.setProperty("class", "MarcStatusBanner")
        marc_vbox.addWidget(self._marc_status_label)

        # 2. Four stat tiles in a row
        marc_stat_row = QHBoxLayout()
        marc_stat_row.setSpacing(8)
        marc_stat_defs = [
            ("Records Found", "_marc_stat_records"),
            ("Call Numbers",  "_marc_stat_callnums"),
            ("Matched",       "_marc_stat_matched"),
            ("Unmatched",     "_marc_stat_unmatched"),
        ]
        for label_text, attr_name in marc_stat_defs:
            tile = QWidget()
            tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            tile.setProperty("class", "StatTile")
            tile_vbox = QVBoxLayout(tile)
            tile_vbox.setContentsMargins(10, 10, 10, 10)
            tile_vbox.setSpacing(3)
            tile_vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_val = QLabel("—")
            lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_val.setProperty("class", "StatTileValueSmall")
            lbl_cat = QLabel(label_text)
            lbl_cat.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_cat.setProperty("class", "StatTileLabelSmall")
            tile_vbox.addWidget(lbl_val)
            tile_vbox.addWidget(lbl_cat)
            marc_stat_row.addWidget(tile)
            setattr(self, attr_name, lbl_val)
        marc_vbox.addLayout(marc_stat_row)

        # 3. Drop zone — expands to fill remaining space
        marc_drop_zone = QFrame()
        marc_drop_zone.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        marc_drop_zone.setProperty("class", "MarcDropZone")
        drop_zone_vbox = QVBoxLayout(marc_drop_zone)
        drop_hint = QLabel("Drop .mrc or .xml file here")
        drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_hint.setStyleSheet("font-size: 13px;")
        drop_zone_vbox.addWidget(drop_hint)
        marc_vbox.addWidget(marc_drop_zone, stretch=1)

        # 4. File row at bottom
        marc_file_row = QHBoxLayout()
        marc_file_row.setSpacing(6)
        self._marc_path_edit = QLineEdit()
        self._marc_path_edit.setReadOnly(True)
        self._marc_path_edit.setPlaceholderText("No MARC file selected… (.mrc binary or .xml MARCXML)")
        self._marc_path_edit.setProperty("class", "LineEdit")
        self._btn_browse_marc = QPushButton("Browse…")
        self._btn_browse_marc.setProperty("class", "PrimaryButton")
        self._btn_browse_marc.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_browse_marc.clicked.connect(self._browse_marc_file)
        self._btn_import_marc = QPushButton("Run")
        self._btn_import_marc.setProperty("class", "PrimaryButton")
        self._btn_import_marc.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_import_marc.clicked.connect(self._import_marc_file)
        self._btn_import_marc.setEnabled(False)
        self._btn_clear_marc = QPushButton("Clear")
        self._btn_clear_marc.setProperty("class", "DangerButton")
        self._btn_clear_marc.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_clear_marc.clicked.connect(self._clear_marc_file)
        self._btn_clear_marc.setVisible(False)
        marc_file_row.addWidget(self._marc_path_edit)
        marc_file_row.addWidget(self._btn_clear_marc)
        marc_file_row.addWidget(self._btn_browse_marc)
        marc_file_row.addWidget(self._btn_import_marc)
        marc_vbox.addLayout(marc_file_row)

        stats_card = QGroupBox("File Statistics")
        stats_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        stats_card_layout = QVBoxLayout(stats_card)
        stats_card_layout.setContentsMargins(14, 14, 14, 14)
        stats_card_layout.setSpacing(10)

        stats_grid = QGridLayout()
        stats_grid.setSpacing(10)
        stat_defs = [
            ("Total rows", "lbl_val_rows", 0, 0),
            ("Valid rows", "lbl_val_rows_valid", 0, 1),
            ("Invalid rows", "lbl_val_invalid", 0, 2),
            ("Valid (unique)", "lbl_val_loaded", 1, 0),
            ("Duplicates", "lbl_val_duplicates", 1, 1),
            ("File size", "lbl_val_size", 1, 2),
        ]

        for label_text, attr_name, row_idx, col_idx in stat_defs:
            tile = QWidget()
            tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            tile.setProperty("class", "StatTile")
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(14, 14, 14, 12)
            tile_layout.setSpacing(4)
            tile_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_val = QLabel("—")
            lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_val.setProperty("class", "StatTileValue")
            lbl_cat = QLabel(label_text)
            lbl_cat.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_cat.setProperty("class", "StatTileLabel")
            tile_layout.addWidget(lbl_val)
            tile_layout.addWidget(lbl_cat)
            stats_grid.addWidget(tile, row_idx, col_idx)
            setattr(self, attr_name, lbl_val)

        stats_card_layout.addLayout(stats_grid)

        # ── File Preview card (bottom-right) ──────────────────────────────────
        preview_frame = QGroupBox("File Preview")
        preview_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        preview_frame_layout = QVBoxLayout(preview_frame)
        preview_frame_layout.setContentsMargins(12, 12, 12, 12)
        preview_frame_layout.setSpacing(6)

        preview_toolbar = QHBoxLayout()
        self.lbl_preview_filename = QLabel("No file selected")
        self.lbl_preview_filename.setStyleSheet("font-size: 10px; font-style: italic;")
        preview_toolbar.addWidget(self.lbl_preview_filename)
        preview_toolbar.addStretch()
        preview_frame_layout.addLayout(preview_toolbar)

        # Table view with row numbers and status column
        self.preview_table = QTableWidget()
        self.preview_table.setShowGrid(False)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.preview_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.preview_table.horizontalHeader().setStretchLastSection(False)
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.preview_table.verticalHeader().setDefaultSectionSize(26)
        self.preview_table.verticalHeader().setVisible(True)
        self.preview_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_table.setStyleSheet(
            "QTableWidget { font-size: 12px; font-family: 'Consolas', monospace; }"
            "QTableWidget::item { padding: 2px 8px; }"
            "QHeaderView::section { font-size: 11px; font-weight: 600; padding: 4px 8px; }"
        )
        # Show placeholder headers before any file is loaded
        self.preview_table.setColumnCount(2)
        self.preview_table.setHorizontalHeaderLabels(["ISBN", "Status"])
        self.preview_table.setRowCount(0)
        preview_frame_layout.addWidget(self.preview_table, stretch=1)

        # Keep preview_text as hidden attribute for backward compat
        self.info_label = QLabel("No file selected")
        self.info_label.setVisible(False)
        self.preview_text = QTextEdit()
        self.preview_text.setVisible(False)

        middle_row.addWidget(self.input_card,  0, 0)
        middle_row.addWidget(stats_card,       0, 1)
        middle_row.addWidget(marc_card,        1, 0)
        middle_row.addWidget(preview_frame,    1, 1)
        
        layout.addLayout(middle_row, stretch=1)

        # ── 4. Status pill + elapsed timer ────────────────────────────────────
        self.lbl_run_status = QLabel("Idle")
        self.lbl_run_status.setProperty("class", "StatusPill")
        self.lbl_run_elapsed = QLabel("00:00:00")
        self.lbl_run_elapsed.setProperty("class", "ActivityValue")

        self.run_timer = QTimer(self)
        self.run_timer.timeout.connect(self._update_timer)
        self.run_time = QTime(0, 0, 0)
        self.timer_is_paused = False

        # ── 5. Action Bar ──────────────────────────────────────────────────────
        action_frame = QFrame()
        action_frame.setProperty("class", "Card")
        action_frame.setStyleSheet("QFrame[class=\"Card\"] { border-radius: 10px; }")
        
        # We need a vertical layout for action_frame so the progress bar goes across the bottom
        action_layout = QVBoxLayout(action_frame)
        action_layout.setContentsMargins(20, 10, 20, 8)
        action_layout.setSpacing(8)

        # Top row: text + buttons
        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        top_row.addWidget(self.lbl_run_status)

        lbl_elapsed_label = QLabel("Elapsed:")
        lbl_elapsed_label.setStyleSheet("font-size: 11px;")
        top_row.addWidget(lbl_elapsed_label)
        top_row.addWidget(self.lbl_run_elapsed)
        top_row.addStretch()

        self.lbl_progress_text = QLabel("0 / 0")
        self.lbl_progress_text.setStyleSheet("font-size: 11px; font-weight: 600; min-width: 80px;")
        self.lbl_progress_text.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top_row.addWidget(self.lbl_progress_text)
        
        self.log_output = QLabel("Ready…")
        self.log_output.setProperty("class", "CardHelper")
        self.log_output.setAccessibleName("Harvest status message")
        self.log_output.setStyleSheet("font-size: 11px; font-style: italic; min-width: 250px;")
        top_row.addWidget(self.log_output)

        BTN_H = 36

        self.btn_stop = QPushButton("✕  Cancel")
        self.btn_stop.setProperty("class", "DangerButton")
        self.btn_stop.setFixedHeight(BTN_H)
        self.btn_stop.clicked.connect(self._stop_harvest)
        self.btn_stop.setEnabled(False)

        self.btn_pause = QPushButton("⏸  Pa&use")
        self.btn_pause.setProperty("class", "SecondaryButton")
        self.btn_pause.setFixedHeight(BTN_H)
        self.btn_pause.setToolTip("Pause or resume the harvest")
        self.btn_pause.setAccessibleName("Pause harvest")
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_pause.setEnabled(False)

        self.btn_start = QPushButton("▶  Start Harvest")
        self.btn_start.setProperty("class", "PrimaryButton")
        self.btn_start.setFixedHeight(BTN_H)
        mod_name = "Cmd" if self._shortcut_modifier == "Meta" else "Ctrl"
        self.btn_start.setToolTip(f"Start harvest ({mod_name}+Enter)")
        self.btn_start.clicked.connect(self._on_start_clicked)
        self.btn_start.setEnabled(False)

        self.btn_new_run = QPushButton("↺  New Harvest")
        self.btn_new_run.setProperty("class", "PrimaryButton")
        self.btn_new_run.setFixedHeight(BTN_H)
        self.btn_new_run.clicked.connect(self._clear_input)
        self.btn_new_run.setVisible(False)

        self.lbl_start_helper = QLabel("")
        self.lbl_start_helper.setVisible(False)

        top_row.addWidget(self.btn_stop)
        top_row.addWidget(self.btn_pause)
        top_row.addWidget(self.btn_new_run)
        top_row.addWidget(self.btn_start)
        
        action_layout.addLayout(top_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setProperty("class", "TerminalProgressBar")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet(
            "QProgressBar { border-radius: 3px; } QProgressBar::chunk { border-radius: 3px; }"
        )
        action_layout.addWidget(self.progress_bar)
        layout.addWidget(action_frame)

        self._transition_state(UIState.IDLE)

    def _toggle_stop_rule_visibility(self, mode_text=None):
        if not mode_text:
            mode_text = self.combo_run_mode.currentText()

        is_both = mode_text == "Both (LCCN & NLM)"
        db_only_for_run = getattr(self, "chk_db_only", None) is not None and self.chk_db_only.isChecked()
        stop_rule_active = is_both and not db_only_for_run
        self.lbl_stop_rule.setEnabled(True)
        self.combo_stop_rule.setEnabled(stop_rule_active)

        if stop_rule_active:
            # Restore normal theme appearance
            self.lbl_stop_rule.setStyleSheet("")
            self.combo_stop_rule.setStyleSheet("")
            self.combo_stop_rule.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            # Visually mute — grey text, faded background, blocked cursor
            muted_combo = (
                "QComboBox {"
                "  color: rgba(120, 120, 140, 0.55);"
                "  background: rgba(100, 100, 120, 0.10);"
                "  border: 1px solid rgba(120, 120, 140, 0.20);"
                "  border-radius: 6px;"
                "}"
                "QComboBox::drop-down { border: none; }"
                "QComboBox::down-arrow { opacity: 0.3; }"
            )
            self.lbl_stop_rule.setStyleSheet("")
            self.combo_stop_rule.setStyleSheet(muted_combo)
            self.combo_stop_rule.setCursor(Qt.CursorShape.ForbiddenCursor)

    def _confirm_db_only_without_targets(self) -> bool:
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("No Targets Selected")
        msg.setText("No targets are selected for this run.")
        msg.setInformativeText(
            "This run will search only the existing database and will not query any live targets."
        )
        ok_btn = msg.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
        cancel_btn = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(ok_btn)
        msg.exec()
        return msg.clickedButton() == ok_btn


    def _transition_state(self, state: UIState, **kwargs):
        """Unified UI state machine handling buttons, banners, and status."""
        self.current_state = state

        # Default all action buttons to hidden/disabled
        self.btn_start.setVisible(False)
        self.btn_pause.setVisible(False)
        self.btn_stop.setVisible(False)
        self.btn_new_run.setVisible(False)

        # Update is_running flag based on state
        self.is_running = state in (UIState.RUNNING, UIState.PAUSED)

        bg_color = "#181926"
        left_color = "#45475a"
        text_color = "#cad3f5"
        title_text = "READY"
        show_stats = False

        if state == UIState.IDLE:
            self.banner_frame.setProperty("state", "idle")
            self.lbl_run_status.setProperty("state", "idle")
            self.lbl_banner_title.setProperty("state", "idle")
            title_text = "READY"

            self.lbl_run_status.setText("Idle")

            self.btn_start.setVisible(True)
            self.btn_start.setEnabled(False)
            self.btn_start.setText("Start Harvest")

        elif state == UIState.READY:
            self.banner_frame.setProperty("state", "ready")
            self.lbl_run_status.setProperty("state", "ready")
            self.lbl_banner_title.setProperty("state", "ready")
            title_text = "READY"

            self.lbl_run_status.setText("Ready")

            self.btn_start.setVisible(True)
            self.btn_start.setEnabled(True)
            count = kwargs.get("count", "?")
            self.btn_start.setText(f"Start Harvest ({count} ISBNs)")

        elif state == UIState.RUNNING:
            self.banner_frame.setProperty("state", "running")
            self.lbl_run_status.setProperty("state", "running")
            self.lbl_banner_title.setProperty("state", "running")
            title_text = "RUNNING"

            self.lbl_run_status.setText("Running")

            # Reset progress bar style class (if customized in CSS)
            self.progress_bar.setProperty("state", "running")
            self.progress_bar.style().unpolish(self.progress_bar)
            self.progress_bar.style().polish(self.progress_bar)

            self.btn_pause.setVisible(True)
            self.btn_pause.setEnabled(True)
            self.btn_pause.setText("Pause")
            self.btn_pause.setStyleSheet(
                "background-color: #f97316; color: #ffffff; border: 1px solid #ea580c; border-radius: 10px; font-weight: 700; padding: 8px 16px;"
            )
            self.btn_stop.setVisible(True)
            self.btn_stop.setEnabled(True)

        elif state == UIState.PAUSED:
            self.banner_frame.setProperty("state", "paused")
            self.lbl_run_status.setProperty("state", "paused")
            self.lbl_banner_title.setProperty("state", "paused")
            
            title_text = "PAUSED"
            self.lbl_run_status.setText("Paused")

            self.btn_pause.setVisible(True)
            self.btn_pause.setEnabled(True)
            self.btn_pause.setText("Resume")
            self.btn_pause.setStyleSheet(
                "background-color: #f97316; color: #ffffff; border: 1px solid #ea580c; border-radius: 10px; font-weight: 700; padding: 8px 16px;"
            )
            self.btn_stop.setVisible(True)
            self.btn_stop.setEnabled(True)

        elif state == UIState.ERROR:
            self.banner_frame.setProperty("state", "error")
            self.lbl_run_status.setProperty("state", "error")
            self.lbl_banner_title.setProperty("state", "error")
            
            title_text = "ERROR"
            self.lbl_run_status.setText("Error")

            self.btn_start.setVisible(True)
            self.btn_start.setEnabled(False)
            self.btn_start.setText("Start Harvest")

        elif state in (UIState.COMPLETED, UIState.CANCELLED):
            is_success = state == UIState.COMPLETED
            state_prop = "completed" if is_success else "cancelled"
            
            self.banner_frame.setProperty("state", state_prop)
            self.lbl_run_status.setProperty("state", state_prop)
            self.lbl_banner_title.setProperty("state", state_prop)
            
            title_text = "COMPLETED" if is_success else "CANCELLED"
            self.lbl_run_status.setText("Completed" if is_success else "Cancelled")

            self.btn_new_run.setVisible(True)

        # Apply changes to banner
        self.banner_frame.style().unpolish(self.banner_frame)
        self.banner_frame.style().polish(self.banner_frame)
        self.lbl_run_status.style().unpolish(self.lbl_run_status)
        self.lbl_run_status.style().polish(self.lbl_run_status)
        self.lbl_banner_title.style().unpolish(self.lbl_banner_title)
        self.lbl_banner_title.style().polish(self.lbl_banner_title)
        if state not in (UIState.RUNNING, UIState.PAUSED):
            self.btn_pause.setStyleSheet("")

        self.lbl_banner_title.setText(title_text)
        self.lbl_banner_stats.setVisible(show_stats)

    def _setup_shortcuts(self):
        mod = self._shortcut_modifier
        QShortcut(QKeySequence(f"{mod}+O"), self, activated=self._browse_file)
        QShortcut(QKeySequence(f"{mod}+Return"), self, activated=self._on_start_clicked)
        QShortcut(QKeySequence(f"{mod}+."), self, activated=self._stop_harvest)

    def _update_scrollbar_policy(self):
        """Hide vertical scrollbar when the window is maximized/fullscreen."""
        pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scrollbar_policy()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            self._update_scrollbar_policy()

    def set_input_file(self, path):
        if not path:
            self._clear_input()
            return

        # If user picks a new file after a run, reset so the harvest button reappears
        if self.current_state in (UIState.COMPLETED, UIState.CANCELLED):
            self.current_state = UIState.IDLE
            self.btn_new_run.setVisible(False)
            self.btn_start.setVisible(True)
            self.btn_start.setEnabled(False)

        path_obj = Path(path)

        # Extension Check removed to allow all file types
        # parse_isbn_file will handle non-text files correctly by returning 0 valid rows

        # Content Check (Real Validation)
        try:
            size_kb = path_obj.stat().st_size / 1024
            sampled = path_obj.stat().st_size > 20 * 1024 * 1024  # 20 MB
            INFO_SAMPLE_MAX_LINES = 200_000

            parsed = parse_isbn_file(
                path_obj, max_lines=INFO_SAMPLE_MAX_LINES if sampled else 0
            )

            unique_valid = len(parsed.unique_valid)
            valid_rows = parsed.valid_count
            invalid_rows = len(parsed.invalid_isbns)
            duplicate_valid_rows = parsed.duplicate_count

            sample_note = ""
            if sampled:
                sample_note = f"\nNote: Large file detected. Stats based on first {INFO_SAMPLE_MAX_LINES:,} lines."

            print(
                f"DEBUG: Validation Results - Unique Valid: {unique_valid}, Invalid: {invalid_rows}"
            )

            if valid_rows == 0:
                msg = "File contains no valid ISBNs"
                if invalid_rows > 0:
                    msg += f" ({invalid_rows} invalid lines)"
                self._set_invalid_state(path_obj.name, msg)
                return

            # Success State
            self.input_file = path

            # Update Path Display with blue accent border (theme-neutral)
            self.file_path_edit.setText(str(path_obj))
            self.file_path_edit.setStyleSheet(
                "border: 1.5px solid #3b82f6; border-radius: 6px; padding: 4px 8px;"
            )

            # Show quiet ghost Clear button
            self.btn_clear_file.setEnabled(True)
            self.btn_clear_file.setVisible(True)

            # Labels and Preview
            self.progress_bar.setFormat(f"0 / {unique_valid}")
            self.log_output.setText(f"Ready to harvest {unique_valid} unique ISBNs.")

            self.file_path_edit.setText(str(path_obj))
            # File summary
            self.lbl_val_size.setText(f"{size_kb:.2f} KB")
            self.lbl_val_rows_valid.setText(str(valid_rows))
            self.lbl_val_rows.setText(str(valid_rows + invalid_rows))
            self.lbl_val_loaded.setText(str(unique_valid))

            # Red highlight if invalid > 0
            self.lbl_val_invalid.setText(str(invalid_rows))
            if invalid_rows > 0:
                self.lbl_val_invalid.setProperty("state", "error")
            else:
                self.lbl_val_invalid.setProperty("state", "idle")
            self.lbl_val_invalid.style().unpolish(self.lbl_val_invalid)
            self.lbl_val_invalid.style().polish(self.lbl_val_invalid)

            self.lbl_val_duplicates.setText(str(duplicate_valid_rows))

            self.file_path_edit.setText(path_obj.name)
            self.btn_clear_file.setVisible(True)
            self._load_file_preview_v2()

            self._check_start_conditions(unique_valid)

        except Exception as e:
            self._set_invalid_state(path_obj.name, f"Error reading file: {e}")

    def _check_start_conditions(self, isbn_count=None):
        """Enable start button when a valid file is loaded.
        Target validation happens only at harvest time in _on_start_clicked.
        """
        # Never override the UI while a harvest is running, paused, or showing completion
        if self.current_state in (
            UIState.RUNNING,
            UIState.PAUSED,
            UIState.COMPLETED,
            UIState.CANCELLED,
        ):
            return

        # Get ISBN count if not passed (parse from label or store in member)
        if not self.input_file:
            self._transition_state(UIState.IDLE)
            return

        count_text = self.progress_bar.format()
        count = (
            count_text.split("/")[0].strip()
            if "/" in count_text
            else "?"
        )
        if isbn_count is not None:
            count = str(isbn_count)

        self._transition_state(UIState.READY, count=count)

    def _load_file_preview(self):
        """Load a snippet of the file into the preview table."""
        self.preview_table.clearContents()
        self.preview_table.setRowCount(0)
        if not self.input_file:
            return

        path_obj = Path(self.input_file)
        if not path_obj.exists():
            self._show_preview_message("Error: File does not exist.")
            return

        try:
            with open(path_obj, "r", encoding="utf-8-sig") as f:
                raw_lines = list(islice(f, 21))

            truncated = len(raw_lines) == 21
            lines = raw_lines[:20]
            rows = [ln.rstrip("\n\r").split("\t") for ln in lines]
            if not rows:
                return

            max_cols = max(len(r) for r in rows)
            # Columns: data cols + Status
            self.preview_table.setColumnCount(max_cols + 1)
            self.preview_table.setRowCount(len(rows))
            headers = [f"Col {i + 1}" for i in range(max_cols)] + ["Status"]
            self.preview_table.setHorizontalHeaderLabels(headers)

            for r, row in enumerate(rows):
                for c, cell in enumerate(row):
                    item = QTableWidgetItem(cell.strip())
                    self.preview_table.setItem(r, c, item)
                # Status: validate first cell as ISBN
                raw = row[0].strip() if row else ""
                is_valid = bool(normalize_isbn(raw.replace("-", "")))
                status_item = QTableWidgetItem("✓ Valid" if is_valid else "✗ Invalid")
                status_item.setForeground(
                    QBrush(QColor("#22c55e" if is_valid else "#ef4444"))
                )
                self.preview_table.setItem(r, max_cols, status_item)

            # Stretch the first data column, fit-to-content for status
            self.preview_table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.Stretch
            )
            self.preview_table.horizontalHeader().setSectionResizeMode(
                max_cols, QHeaderView.ResizeMode.ResizeToContents
            )

            name = path_obj.name + (" (first 20 rows)" if truncated else "")
            self.lbl_preview_filename.setText(name)
        except Exception as e:
            self._show_preview_message(f"Error reading preview: {e}")

    def _show_preview_message(self, msg: str):
        """Show a single-cell message in the preview table."""
        self.preview_table.setColumnCount(1)
        self.preview_table.setRowCount(1)
        self.preview_table.setHorizontalHeaderLabels(["Info"])
        self.preview_table.setItem(0, 0, QTableWidgetItem(msg))

    def _apply_db_only_checkbox_style(self):
        is_dark = ThemeManager().get_theme() == "dark"
        text_color = "#f9fafb" if is_dark else "#000000"
        self.chk_db_only.setStyleSheet(
            "QCheckBox { color: " + text_color + "; font-weight: 600; spacing: 8px; }"
        )

    def _load_file_preview_v2(self):
        """Load a preview using ISBN-aware row numbering and optional header skipping."""
        self.preview_table.clearContents()
        self.preview_table.setRowCount(0)
        if not self.input_file:
            return

        path_obj = Path(self.input_file)
        if not path_obj.exists():
            self._show_preview_message("Error: File does not exist.")
            return

        try:
            preview_rows = []
            total_read = 0
            skipped_header = False

            with open(path_obj, "r", encoding="utf-8-sig") as handle:
                for line in handle:
                    total_read += 1
                    row = line.rstrip("\n\r").split("\t")
                    first_cell = row[0].strip() if row else ""
                    if not first_cell:
                        continue

                    normalized = normalize_isbn(first_cell.replace("-", ""))
                    if normalized:
                        preview_rows.append((row, True))
                    elif not skipped_header and _looks_like_header_cell(first_cell):
                        skipped_header = True
                        continue
                    else:
                        preview_rows.append((row, False))

                    if len(preview_rows) >= 20:
                        break

            if not preview_rows:
                return

            truncated = total_read > len(preview_rows)
            self.preview_table.setColumnCount(2)
            self.preview_table.setRowCount(len(preview_rows))
            self.preview_table.setHorizontalHeaderLabels(["ISBN", "Status"])

            for row_index, (row, is_valid) in enumerate(preview_rows):
                first_cell = row[0].strip() if row else ""
                self.preview_table.setItem(row_index, 0, QTableWidgetItem(first_cell))
                status_item = QTableWidgetItem("Valid" if is_valid else "Invalid")
                status_item.setForeground(QBrush(QColor("#22c55e" if is_valid else "#ef4444")))
                self.preview_table.setItem(row_index, 1, status_item)

            self.preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            self.preview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            name = path_obj.name + (" (first 20 rows)" if truncated else "")
            self.lbl_preview_filename.setText(name)
        except Exception as e:
            self._show_preview_message(f"Error reading preview: {e}")

    def _copy_preview_content(self):
        """Copy preview table content as tab-separated text."""
        lines = []
        for r in range(self.preview_table.rowCount()):
            cells = []
            for c in range(self.preview_table.columnCount() - 1):  # skip Status col
                item = self.preview_table.item(r, c)
                cells.append(item.text() if item else "")
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))

    def reset_for_profile_switch(self):
        """Reset the harvest tab when the user switches profiles.

        No-op while a harvest is actively running so we never disrupt live work.
        """
        if self.current_state == UIState.RUNNING:
            return
        self._clear_input()

    def _clear_input(self):
        """Reset input state."""
        self.run_timer.stop()
        self.run_time = QTime(0, 0, 0)
        self.lbl_run_elapsed.setText("00:00:00")
        self.timer_is_paused = False
        self.input_file = None
        self.file_path_edit.clear()
        self.file_path_edit.setStyleSheet("")
        self.info_label.setText("No file selected")

        self.lbl_val_size.setText("-")
        self.lbl_val_rows_valid.setText("-")
        self.lbl_val_rows.setText("-")
        self.lbl_val_loaded.setText("-")
        self.lbl_val_invalid.setText("-")
        self.lbl_val_duplicates.setText("-")
        self.preview_text.clear()
        self.lbl_preview_filename.setText("No file selected")

        # Reset clear button
        self.btn_clear_file.setVisible(False)

        self.lbl_progress_text.setText("0 / 0")
        self.progress_bar.setValue(0)
        self.log_output.setText("Ready...")
        self.log_output.setProperty("state", "idle")
        self.log_output.style().unpolish(self.log_output)
        self.log_output.style().polish(self.log_output)

        self.lbl_val_invalid.setProperty("state", "idle")
        self.lbl_val_invalid.style().unpolish(self.lbl_val_invalid)
        self.lbl_val_invalid.style().polish(self.lbl_val_invalid)

        # Reset progress bar to default blue style
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0/0 (0%)")
        self.progress_bar.setProperty("state", "idle")
        self.progress_bar.style().unpolish(self.progress_bar)
        self.progress_bar.style().polish(self.progress_bar)

        self._transition_state(UIState.IDLE)
        self.harvest_reset.emit()

    def _set_invalid_state(self, filename, error_msg):
        """Show error state."""
        self.input_file = None
        self.file_path_edit.setText(filename)
        self.btn_clear_file.setVisible(True)

        self.lbl_val_size.setText("-")
        self.lbl_val_rows_valid.setText("-")
        self.lbl_val_rows.setText("-")
        self.lbl_val_loaded.setText("-")
        self.lbl_val_invalid.setText("-")
        self.lbl_val_duplicates.setText("-")

        self.preview_text.clear()
        self.preview_text.setText(f"Error: {error_msg}")

        self.progress_bar.setFormat("0 / 0")
        self.log_output.setText(error_msg)
        self.log_output.setProperty("state", "error")
        self.log_output.style().unpolish(self.log_output)
        self.log_output.style().polish(self.log_output)

        self._transition_state(UIState.ERROR)

    def _browse_file(self):
        """Open file picker (mimicking InputTab's filtering)."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select ISBN Input File",
            "",
            "All Files (*.*);;Excel Files (*.xlsx *.xls);;TSV Files (*.tsv);;Text Files (*.txt);;CSV Files (*.csv)",
        )
        if file_path:
            self.set_input_file(file_path)

    def _on_start_clicked(self):
        """Prepare and start harvest using external config."""
        if not self.input_file:
            return

        # 1. Get Config
        config = (
            self._config_getter()
            if self._config_getter
            else {"retry_days": 7, "call_number_mode": "lccn"}
        )

        retry_days = int(config.get("retry_days", 7) or 0)
        bypass_retry_isbns = self._check_recent_not_found_isbns(retry_days)
        if bypass_retry_isbns is None:
            self.log_output.setText(
                "Harvest cancelled: retry window still active for some ISBNs."
            )
            return
        
        # Override call_number_mode based on UI selection
        mode_text = self.combo_run_mode.currentText()
        if mode_text == "NLM Only":
            config["call_number_mode"] = "nlmcn"
            config["both_stop_policy"] = "nlmcn"
            config["db_only"] = False
        elif mode_text == "Both (LCCN & NLM)":
            config["call_number_mode"] = "both"
            config["db_only"] = False
            stop_text = self.combo_stop_rule.currentText()

            # Read stop rule from the UI combo (no popup needed — user already chose)
            stop_mapping = {
                "Stop if either found": ("stop_either", "either"),
                "Stop if LCCN found": ("stop_lccn", "lccn"),
                "Stop if NLMCN found": ("stop_nlmcn", "nlmcn"),
                "Continue until both found": ("continue_both", "both"),
            }
            stop_rule_val, both_policy_val = stop_mapping.get(stop_text, ("stop_either", "either"))
            config["stop_rule"] = stop_rule_val
            config["both_stop_policy"] = both_policy_val
        elif mode_text == "MARC Import Only":
            config["call_number_mode"] = "both"
            config["db_only"] = True
        else:
            config["call_number_mode"] = "lccn"
            config["both_stop_policy"] = "lccn"
            config["db_only"] = False

        # 2. Get Targets
        targets = self._targets_getter() if self._targets_getter else []
        selected_targets = [t for t in targets if t.get("selected", True)]
        explicit_db_only = self.chk_db_only.isChecked()

        if not selected_targets:
            if not self._confirm_db_only_without_targets():
                self.log_output.setText("Harvest cancelled: no targets selected.")
                return
            config["db_only"] = True
            self.log_output.setText(
                "No targets selected. Running against the existing database only."
            )
        elif explicit_db_only:
            config["db_only"] = True
            self.log_output.setText(
                "Database-only mode enabled for this run. Skipping live targets."
            )

        # 3. Start Worker
        self._start_worker(config, targets, bypass_retry_isbns=bypass_retry_isbns)

    def _prompt_both_stop_policy(self):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setWindowTitle("Both Mode")
        msg.setText("If one target returns only one of LCCN or NLM, when should this run stop for that ISBN?")
        msg.setInformativeText("Choose one rule for this run.")

        btn_lccn = msg.addButton("Stop on LCCN only", QMessageBox.ButtonRole.ActionRole)
        btn_nlm = msg.addButton("Stop on NLM only", QMessageBox.ButtonRole.ActionRole)
        btn_either = msg.addButton("Stop on either one first", QMessageBox.ButtonRole.ActionRole)
        btn_both = msg.addButton("Keep going until both or exhausted", QMessageBox.ButtonRole.ActionRole)
        cancel_btn = msg.addButton(QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton(btn_both)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == btn_lccn:
            return "lccn"
        if clicked == btn_nlm:
            return "nlmcn"
        if clicked == btn_either:
            return "either"
        if clicked == btn_both:
            return "both"
        if clicked == cancel_btn:
            return None
        return None

    def _start_worker(self, config, targets, bypass_retry_isbns=None):
        if self.worker and self.worker.isRunning():
            return

        self.run_timer.stop()
        self.run_time = QTime(0, 0, 0)
        self.lbl_run_elapsed.setText("00:00:00")
        self.timer_is_paused = False

        # Compute timestamped output file names for this run
        profile = "default"
        if self._profile_getter:
            try:
                profile = _safe_filename(self._profile_getter() or "default")
            except Exception:
                pass
        date_str = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        # Use a per-run timestamp so repeated harvests never overwrite earlier files.
        live_dir = Path("data") / profile
        live_dir.mkdir(parents=True, exist_ok=True)
        suffix = 0
        while True:
            run_stamp = date_str if suffix == 0 else f"{date_str}-{suffix}"
            candidate_paths = {
                "successful": str(live_dir / f"{profile}-success-{run_stamp}.tsv"),
                "failed": str(live_dir / f"{profile}-failed-{run_stamp}.tsv"),
                "problems": str(live_dir / f"{profile}-problems-{run_stamp}.tsv"),
                "invalid": str(live_dir / f"{profile}-invalid-{run_stamp}.tsv"),
                "linked": str(live_dir / f"{profile}-linked-isbns-{run_stamp}.tsv"),
                "profile_dir": str(live_dir),
            }
            if not any(
                Path(candidate_paths[key]).exists()
                for key in ("successful", "failed", "problems", "invalid", "linked")
            ):
                self._run_live_paths = candidate_paths
                break
            suffix += 1

        # Notify dashboard of new live file paths
        self.result_files_ready.emit(self._run_live_paths)

        db_path = "data/lccn_harvester.sqlite3"
        if self._db_path_getter:
            try:
                db_path = str(self._db_path_getter())
            except Exception:
                pass

        self.worker = HarvestWorkerV2(
            self.input_file,
            config,
            targets,
            advanced_settings=self._load_advanced_settings(),
            bypass_retry_isbns=bypass_retry_isbns,
            live_paths=self._run_live_paths,
            db_path=db_path,
        )
        self.worker.progress_update.connect(self._on_progress)
        self.worker.harvest_complete.connect(self._on_complete)
        self.worker.stats_update.connect(self._on_stats)
        self.worker.stats_update.connect(self.live_stats_ready.emit)
        self.worker.status_message.connect(self._on_status)
        self.worker.live_result.connect(self.live_result_ready.emit)

        self._transition_state(UIState.RUNNING)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0/0 (0%)")

        self.worker.start()
        self.run_timer.start(1000)

        self.harvest_started.emit()

    def _update_timer(self):
        """Update the elapsed time display."""
        if not self.timer_is_paused:
            self.run_time = self.run_time.addSecs(1)
            self.lbl_run_elapsed.setText(self.run_time.toString("hh:mm:ss"))

    def _stop_harvest(self):
        if self.worker:
            self.worker.stop()
            self.run_timer.stop()
            self.lbl_banner_title.setText("CANCELLING...")
            self.lbl_run_status.setText("Cancelling...")
            self.lbl_run_status.setProperty("state", "error")
            self.lbl_run_status.style().unpolish(self.lbl_run_status)
            self.lbl_run_status.style().polish(self.lbl_run_status)
            self.log_output.setText(
                "Cancelling harvest (waiting for current thread)..."
            )
            self.btn_stop.setEnabled(False)  # Prevent double click
            self.btn_pause.setEnabled(False)

    def _toggle_pause(self):
        if self.worker:
            self.worker.toggle_pause()
            if self.worker._pause_requested:
                self._transition_state(UIState.PAUSED)
                self.log_output.setText("Harvest paused. Click Resume to continue.")
                self.timer_is_paused = True
                self.harvest_paused.emit(True)
            else:
                self._transition_state(UIState.RUNNING)
                self.log_output.setText("Harvest resumed...")
                self.timer_is_paused = False
                self.harvest_paused.emit(False)

    def _iter_normalized_input_isbns(self):
        """Yield normalized ISBNs from current input file."""
        if not self.input_file:
            return
        input_path = Path(self.input_file)
        delimiter = "," if input_path.suffix.lower() == ".csv" else "\t"
        with open(input_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, delimiter=delimiter)
            for row in reader:
                raw = (row[0] or "").strip() if row else ""
                if not raw or raw.lower().startswith("isbn") or raw.startswith("#"):
                    continue
                norm = normalize_isbn(raw)
                if norm:
                    yield norm

    def _check_recent_not_found_isbns(self, retry_days: int):
        """
        Warn user when ISBNs with recent 'not found' failures are still inside retry window.
        Returns:
          - set() to keep retry rule
          - set(isbns) to bypass retry for selected ISBNs
          - None if user cancels harvest
        """
        if not self.input_file or retry_days <= 0:
            return set()

        try:
            _db_path = (
                str(self._db_path_getter())
                if self._db_path_getter
                else "data/lccn_harvester.sqlite3"
            )
            db = DatabaseManager(_db_path)
            db.init_db()
            recent = []
            for isbn in self._iter_normalized_input_isbns():
                attempted_rows = db.get_all_attempted_for(isbn)
                matching_attempts = []
                for att in attempted_rows:
                    err = (att.last_error or "").lower()
                    if "invalid isbn" in err:
                        continue
                    if db.should_skip_retry(
                        isbn,
                        att.last_target or "",
                        att.attempt_type or "both",
                        retry_days=retry_days,
                    ):
                        matching_attempts.append(att)
                if matching_attempts:
                    recent.append((isbn, matching_attempts[0]))
        except Exception as e:
            self.log_output.setText(f"Warning: could not check retry window ({e})")
            return set()

        if not recent:
            return set()

        details = []
        for isbn, att in recent:
            last_attempted = att.last_attempted
            try:
                last_val = str(last_attempted) if last_attempted is not None else ""
                if last_val.isdigit() and len(last_val) == 8:
                    # yyyymmdd integer format
                    last_dt = datetime(int(last_val[:4]), int(last_val[4:6]), int(last_val[6:8]), tzinfo=timezone.utc)
                elif last_val:
                    # legacy ISO string format
                    last_dt = datetime.fromisoformat(last_val)
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                else:
                    raise ValueError("empty")
                next_dt = last_dt + timedelta(days=retry_days)
                next_str = next_dt.astimezone().strftime("%Y-%m-%d")
                last_str = last_dt.astimezone().strftime("%Y-%m-%d")
            except Exception:
                last_str = str(last_attempted) if last_attempted is not None else "Unknown"
                next_str = "Unknown"
            details.append(
                f"{isbn} | last not found: {last_str} | retry after: {next_str}"
            )
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Retry Date Not Reached")
        msg.setText(
            f"{len(recent)} ISBN(s) were previously not found and are still within the {retry_days}-day retry window."
        )
        msg.setInformativeText(
            "You have not passed the retry date yet for these ISBNs.\n"
            "Cancel to wait, continue to keep retry skips, or override to rerun now."
        )
        msg.setDetailedText("\n".join(details))

        override_btn = msg.addButton(
            "Override and Re-run Now", QMessageBox.ButtonRole.ActionRole
        )
        cancel_btn = msg.addButton("Cancel Harvest", QMessageBox.ButtonRole.RejectRole)
        continue_btn = msg.addButton(
            "Continue (Keep Retry Rules)", QMessageBox.ButtonRole.AcceptRole
        )
        msg.setDefaultButton(cancel_btn)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == cancel_btn:
            return None
        if clicked == override_btn:
            return {isbn for isbn, _ in recent}
        if clicked == continue_btn:
            return set()
        return set()

    def _is_retry_popup_candidate(self, error_text: str) -> bool:
        lowered = str(error_text or "").lower()
        if "not found" in lowered:
            return True
        if "no lccn call number" in lowered:
            return True
        if "no nlmcn call number" in lowered:
            return True
        if "found " in lowered and " only; missing " in lowered:
            return True
        if "missing lccn" in lowered or "missing nlmcn" in lowered:
            return True
        return False

    def _load_advanced_settings(self):
        """Load persisted advanced settings if available."""
        settings_path = Path("data/advanced_settings.json")
        if not settings_path.exists():
            return {}
        try:
            return json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _on_progress(self, isbn, status, source, msg):
        log_msg = msg
        self.log_output.setText(log_msg)
        self.progress_updated.emit(isbn, status, source, msg)

    def _on_stats(self, stats):
        # stats is a RunStats dataclass; use getattr so it also works if a dict is passed
        total = getattr(stats, "valid_rows", 0) or (stats.get("total", 0) if hasattr(stats, "get") else 0)
        processed = getattr(stats, "processed_unique", 0) or (
            stats.get("found", 0) + stats.get("failed", 0) + stats.get("cached", 0) + stats.get("skipped", 0)
            if hasattr(stats, "get") else 0
        )
        self.processed_count = processed
        self.total_count = total

        progress_str = f"{processed} / {total}"
        pct = int(processed / total * 100) if total > 0 else 0
        self.lbl_progress_text.setText(f"{progress_str}  ({pct}%)")
        self.progress_bar.setValue(pct)

    def _on_status(self, msg):
        self.log_output.setText(msg)

    def _on_complete(self, success, stats):
        self.is_running = False
        self.run_timer.stop()

        # Snapshot session results from the worker BEFORE any DB query
        if self.worker is not None:
            self._last_session_success = list(self.worker._session_success)
            self._last_session_failed = list(self.worker._session_failed)
            self._last_session_invalid = list(self.worker._session_invalid)

        error_msg = stats.get("error") if not success else None
        final_state = UIState.COMPLETED if success else UIState.CANCELLED
        self._transition_state(final_state, stats=stats)

        if not success:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("0/0 (0%)")

            if error_msg:
                # Crash/exception — show a clear error dialog and keep the message
                self.log_output.setText(f"Harvest failed: {error_msg}")
                self.log_output.setProperty("state", "error")
                self.log_output.style().unpolish(self.log_output)
                self.log_output.style().polish(self.log_output)
                QMessageBox.critical(
                    self,
                    "Harvest Error",
                    f"The harvest encountered an error and could not complete:\n\n{error_msg}",
                )
            else:
                self.log_output.setText("Ready...")
        else:
            self.log_output.setText("Harvest complete. View results in Dashboard.")

            # Force progress bar to 100% on success
            self.progress_bar.setValue(100)
            total = self.total_count or 0
            if total > 0:
                self.lbl_progress_text.setText(f"{total} / {total}  (100%)")

            # Change progress bar green
            self.progress_bar.setProperty("state", "success")
            self.progress_bar.style().unpolish(self.progress_bar)
            self.progress_bar.style().polish(self.progress_bar)

        self.harvest_finished.emit(success, stats)

    def _update_banner_paths(self):
        """Update banner file button labels and output folder label to match current run."""
        if not self._run_live_paths:
            return
        success_path = Path(self._run_live_paths.get("successful", ""))
        failed_path = Path(self._run_live_paths.get("failed", ""))
        invalid_path = Path(self._run_live_paths.get("invalid", ""))
        self.btn_banner_success.setText(success_path.name)
        self.btn_banner_failed.setText(failed_path.name)
        self.btn_banner_invalid.setText(invalid_path.name)
        base_dir = "data"
        parent = success_path.parent
        if parent.name == base_dir or str(parent) == base_dir:
            out_label = f"Saved to: {base_dir}/"
        else:
            out_label = f"Saved to: {base_dir}/{parent.name}/"
        self.lbl_banner_out.setText(out_label)

    def _open_output_folder_path(self, folder: Path):
        """Open a specific folder in the system file manager."""
        import os
        folder = folder.resolve()
        folder.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(str(folder))
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", str(folder)])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", str(folder)])

    def _open_output_folder(self):
        """Open the data folder in Explorer."""
        out_path = Path("data").resolve()
        out_path.mkdir(parents=True, exist_ok=True)
        import os

        if os.name == "nt":
            os.startfile(str(out_path))
        elif sys.platform == "darwin":
            import subprocess

            subprocess.Popen(["open", str(out_path)])
        else:
            import subprocess

            subprocess.Popen(["xdg-open", str(out_path)])

    def _open_file_in_explorer(self, relative_path: str):
        """Open a specific file in the default associated application."""
        file_path = Path(relative_path).resolve()
        if not file_path.exists():
            QMessageBox.warning(
                self, "Not Found", f"File does not exist:\n{file_path.name}"
            )
            return

        import os

        if os.name == "nt":
            os.startfile(str(file_path))
        elif sys.platform == "darwin":
            import subprocess

            subprocess.Popen(["open", str(file_path)])
        else:
            import subprocess

            subprocess.Popen(["xdg-open", str(file_path)])

    def set_advanced_mode(self, val):
        pass

    def stop_harvest(self):
        """Public method used by window close handlers."""
        self._stop_harvest()

    # ── MARC Import ────────────────────────────────────────────────────────────

    def _browse_marc_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select MARC File",
            "",
            "MARC Files (*.mrc *.marc *.xml);;All Files (*)",
        )
        if path:
            self._marc_path_edit.setText(path)
            self._btn_import_marc.setEnabled(True)
            self._btn_clear_marc.setVisible(True)
            self._marc_status_label.setText("Click 'Import Records' to import call numbers into the database and save results.")

    def _clear_marc_file(self):
        self._marc_path_edit.clear()
        self._btn_import_marc.setEnabled(False)
        self._btn_clear_marc.setVisible(False)
        self._marc_status_label.setText("Select a MARC file (.mrc / .xml) to import into the database and export results.")
        for attr in ("_marc_stat_records", "_marc_stat_callnums", "_marc_stat_matched", "_marc_stat_unmatched"):
            getattr(self, attr).setText("—")

    def _import_marc_file(self):
        path = self._marc_path_edit.text().strip()
        if not path:
            return

        # ── Task 2: ask the user for a source name ─────────────────────────────
        default_source = Path(path).stem
        source_name, ok = QInputDialog.getText(
            self,
            "MARC Import — Source Name",
            "Enter a source name to store with the imported records\n"
            "(e.g. the library catalog or system the file came from):",
            text=default_source,
        )
        if not ok:
            return
        source_name = source_name.strip() or default_source

        self._btn_import_marc.setEnabled(False)

        # ── Step 1: parse ──────────────────────────────────────────────────────
        self._marc_status_label.setText("Step 1/3 — Reading MARC file…")
        QApplication.processEvents()

        try:
            records = self._parse_marc_records(path)
        except Exception as exc:
            self._marc_status_label.setText(f"Error reading MARC file: {exc}")
            self._btn_import_marc.setEnabled(True)
            return

        total_records = len(records)
        if total_records == 0:
            self._marc_status_label.setText("No records found in the MARC file.")
            self._btn_import_marc.setEnabled(True)
            return

        self._marc_status_label.setText(
            f"Step 2/3 — Processing {total_records:,} records…"
        )
        QApplication.processEvents()

        # ── Step 2: determine mode and output path ─────────────────────────────
        config = {}
        if self._config_getter:
            try:
                config = self._config_getter() or {}
            except Exception:
                pass
        mode = (config.get("call_number_mode", "lccn") or "lccn").strip().lower()

        profile = "default"
        if self._profile_getter:
            try:
                profile = _safe_filename(self._profile_getter() or "default")
            except Exception:
                pass
        date_str = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        live_dir = Path("data") / profile
        live_dir.mkdir(parents=True, exist_ok=True)
        out_path = live_dir / f"{profile}-marc-import-{date_str}.tsv"

        if mode == "nlmcn":
            headers = ["ISBN", "NLM", "NLM Source", "Date"]
        elif mode == "both":
            headers = ["ISBN", "LCCN", "LCCN Source", "Classification", "NLM", "NLM Source", "Date"]
        else:
            headers = ["ISBN", "LCCN", "LCCN Source", "Classification", "Date"]

        selected_rows, parsed_records, written, skipped, no_isbn = _prepare_marc_import_records(
            records,
            mode=mode,
            source_name=source_name,
        )
        date_added = now_datetime_str()

        profile_name = None
        if self._profile_getter:
            try:
                profile_name = self._profile_getter() or None
            except Exception:
                profile_name = None

        db_path = "data/lccn_harvester.sqlite3"
        if self._db_path_getter:
            try:
                db_path = str(self._db_path_getter())
            except Exception:
                pass

        marc_service = MarcImportService(
            db_path=db_path,
            profile_manager=ProfileManager(),
            profile_name=profile_name,
        )
        db_summary = marc_service.persist_records(
            parsed_records,
            source_name=source_name,
            import_date=date_added,
            save_source_to_active_profile=True,
        )

        with open(out_path, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh, delimiter="\t")
            writer.writerow(headers)
            for i, (isbn, lccn, nlmcn) in enumerate(selected_rows, 1):
                if mode == "nlmcn":
                    row = [isbn or "", nlmcn, source_name, date_added]
                elif mode == "both":
                    classification = _extract_lc_classification(lccn or "")
                    row = [
                        isbn or "",
                        lccn or "", source_name if lccn else "",
                        classification,
                        nlmcn or "", source_name if nlmcn else "",
                        date_added,
                    ]
                else:
                    classification = _extract_lc_classification(lccn)
                    row = [isbn or "", lccn, source_name, classification, date_added]
                writer.writerow(row)
                # Update status every 500 records so the UI stays responsive
                if i % 500 == 0:
                    self._marc_status_label.setText(
                        f"Step 2/3 — Processed {i:,} / {total_records:,}…"
                    )
                    QApplication.processEvents()

        # ── Step 3: write CSV copy ─────────────────────────────────────────────
        self._marc_status_label.setText("Step 3/3 — Writing CSV copy…")
        QApplication.processEvents()
        with open(out_path, encoding="utf-8-sig", newline="") as _tsv:
            _rows = list(csv.reader(_tsv, delimiter="\t"))
        _write_csv_rows(_rows, str(out_path.with_suffix(".csv")))

        # ── Update status label + MARC stats panel ─────────────────────────────
        self._marc_status_label.setText(
            f"Done — {db_summary.main_rows:,} saved to database, {written:,} exported, {skipped:,} skipped  →  {out_path.name}"
        )
        self._marc_stat_records.setText(f"{total_records:,}")
        self._marc_stat_callnums.setText(f"{written:,}")
        self._marc_stat_matched.setText(f"{db_summary.main_rows:,}")
        self._marc_stat_unmatched.setText(f"{skipped + db_summary.skipped_records:,}")
        self._btn_import_marc.setEnabled(True)

        # ── Summary dialog ─────────────────────────────────────────────────────
        mode_label = {"lccn": "LCCN Only", "nlmcn": "NLM Only", "both": "Both (LCCN & NLM)"}.get(mode, mode)
        summary_lines = [
            f"<b>MARC Import Complete</b>",
            "",
            f"<b>Source:</b> {source_name}",
            f"<b>File:</b> {Path(path).name}",
            f"<b>Mode:</b> {mode_label}",
            "",
            f"<b>Total records in file:</b> {total_records:,}",
            f"<b>Saved to database (main):</b> {db_summary.main_rows:,}",
            f"<b>Saved to database (attempted):</b> {db_summary.attempted_rows:,}",
            f"<b>Exported to file:</b> {written:,}",
            f"<b>Skipped</b> (no call number for mode): {skipped:,}",
            f"<b>Missing ISBN</b> (not saved to database): {no_isbn:,}",
            "",
            f"<b>Output:</b> {out_path.name}",
        ]
        dlg = QMessageBox(self)
        dlg.setWindowTitle("MARC Import — Summary")
        dlg.setIcon(QMessageBox.Icon.Information)
        dlg.setTextFormat(Qt.TextFormat.RichText)
        dlg.setText("<br>".join(summary_lines))
        dlg.setStandardButtons(QMessageBox.StandardButton.Ok)
        open_btn = dlg.addButton("Open Output Folder", QMessageBox.ButtonRole.ActionRole)
        dlg.exec()
        if dlg.clickedButton() == open_btn:
            self._open_output_folder_path(live_dir)

    def _parse_marc_records(self, path: str) -> list:
        """Parse a binary .mrc or MARCXML file and return (isbn, lccn, nlmcn) tuples."""
        import pymarc
        from src.utils.call_number_normalizer import normalize_call_number

        file_path = Path(path)
        results = []

        def _extract(record):
            # ISBN from 020 $a (prefer) then $z
            isbn = None
            for code in ("a", "z"):
                for field in record.get_fields("020"):
                    for raw in field.get_subfields(code):
                        raw = raw.split()[0].replace("-", "").strip() if raw.split() else ""
                        norm = normalize_isbn(raw)
                        if norm:
                            isbn = norm
                            break
                if isbn:
                    break

            # LCCN from 050 $a + $b
            lccn = None
            f050 = record.get_fields("050")
            if f050:
                a_vals = f050[0].get_subfields("a")
                b_vals = f050[0].get_subfields("b")
                lccn = normalize_call_number(a_vals, b_vals) or None

            # NLM from 060 $a + $b
            nlmcn = None
            f060 = record.get_fields("060")
            if f060:
                a_vals = f060[0].get_subfields("a")
                b_vals = f060[0].get_subfields("b")
                nlmcn = normalize_call_number(a_vals, b_vals) or None

            return isbn, lccn, nlmcn

        if file_path.suffix.lower() == ".xml":
            for rec in pymarc.parse_xml_to_array(str(file_path)):
                if rec is not None:
                    results.append(_extract(rec))
        else:
            with open(file_path, "rb") as fh:
                reader = pymarc.MARCReader(fh, to_unicode=True, force_utf8=True)
                for rec in reader:
                    if rec is not None:
                        results.append(_extract(rec))

        return results
