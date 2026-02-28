"""
Module: harvest_tab_v2.py
V2 Harvest Tab: Functional Core with Professional UI.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QTextEdit, QProgressBar,
    QCheckBox, QSpinBox, QFrame, QGridLayout, QMessageBox, QFileDialog, QLineEdit, QSizePolicy, QListWidget, QScrollArea
)
from datetime import datetime, timedelta, timezone
from PyQt6.QtCore import Qt, QTimer, QTime, pyqtSignal, QMimeData, QUrl, QSize
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QCursor, QShortcut, QKeySequence
from pathlib import Path
from enum import Enum, auto
import csv
import sys
import json
import threading
# Add src to path for utils import
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.isbn_validator import normalize_isbn

from .icons import get_icon, SVG_HARVEST, SVG_INPUT, SVG_ACTIVITY
# from .harvest_tab import HarvestWorker  # REMOVED: Using internal HarvestWorkerV2 for separation

# Add imports for Worker
from PyQt6.QtCore import QThread
from src.harvester.run_harvest import run_harvest, parse_isbn_file
from src.harvester.targets import create_target_from_config
from src.harvester.orchestrator import HarvestCancelled
from src.database import DatabaseManager
from datetime import datetime
from src.utils import messages

class HarvestWorkerV2(QThread):
    """Background worker thread for harvest operations (V2)."""

    progress_update = pyqtSignal(str, str, str, str)  # isbn, status, source, message
    harvest_complete = pyqtSignal(bool, dict)  # success, statistics (can include 'cancelled': True)
    status_message = pyqtSignal(str)
    started = pyqtSignal()
    milestone_reached = pyqtSignal(str, int)  # milestone_type, value
    stats_update = pyqtSignal(dict)  # real-time statistics update

    def __init__(self, input_file, config, targets, advanced_settings=None, bypass_retry_isbns=None):
        super().__init__()
        self.input_file = input_file
        self.config = config
        self.targets = targets
        self.advanced_settings = advanced_settings or {}
        self.bypass_retry_isbns = set(bypass_retry_isbns or [])
        self._stop_requested = False
        self._pause_requested = False
        self._live_results_lock = threading.Lock()
        self._live_result_handles = {}

    def run(self):
        """Run the harvest operation in background thread."""
        try:
            print("DEBUG: HarvestWorkerV2 started run() method.")
            self.started.emit()
            self.status_message.emit(messages.HarvestMessages.starting)

            # Read and validate ISBNs
            isbns, invalid_list = self._read_and_validate_isbns()
            total = len(isbns)
            invalid_count = len(invalid_list)
            print(f"DEBUG: HarvestWorkerV2 read {total} valid ISBNs, {invalid_count} invalid.")

            # Overwrite live result files at the start of each run
            self._prepare_live_result_files()
            self._write_invalid_live_rows(invalid_list)

            # Record invalid stats
            if invalid_count > 0:
                 self._record_invalid_isbns(invalid_list)

            if total == 0:
                print("DEBUG: HarvestWorkerV2 found no valid ISBNs.")
                self.status_message.emit(messages.HarvestMessages.no_valid_isbns)
                self.harvest_complete.emit(False, {"total": 0, "found": 0, "failed": 0})
                return

            # Track stats for GUI updates
            self.stats = {"total": total, "found": 0, "failed": 0, "cached": 0, "skipped": 0}
            self.processed_count = 0

            # Create progress callback
            def progress_callback(event: str, payload: dict):
                if self._stop_requested:
                    raise HarvestCancelled("Harvest cancelled by user")

                isbn = payload.get("isbn", "")
                
                # print(f"DEBUG: Worker callback event: {event} for {isbn}") # Verbose debug

                if event == "isbn_start":
                    self.progress_update.emit(isbn, "processing", "", messages.HarvestMessages.processing_isbn)

                elif event == "cached":
                    self.progress_update.emit(isbn, "cached", "Cache", messages.HarvestMessages.found_in_cache)
                    self._append_live_success(
                        isbn,
                        payload.get("source") or "Cache",
                        "Found in cache",
                        lccn=payload.get("lccn"),
                        nlmcn=payload.get("nlmcn"),
                    )
                    self._update_processed()

                elif event == "skip_retry":
                    self.progress_update.emit(isbn, "skipped", "", messages.HarvestMessages.skipped_recent_failure)
                    retry_days = payload.get("retry_days", self.config.get("retry_days", 7))
                    self._append_live_failed(
                        isbn,
                        f"Skipped due to retry window ({retry_days} days)",
                        "RetryRule",
                        retry_days=retry_days,
                        other_errors=[f"RetryRule: Skipped due to retry window ({retry_days} days)"],
                    )
                    self._update_processed()

                elif event == "target_start":
                    target_name = payload.get("target") or payload.get("target_name", "")
                    self.progress_update.emit(
                        isbn,
                        "trying",
                        target_name,
                        messages.HarvestMessages.checking_target.format(target=target_name),
                    )

                elif event == "success":
                    source = payload.get("target", "")
                    self.progress_update.emit(isbn, "found", source, "Found")
                    self._append_live_success(
                        isbn,
                        payload.get("source") or source or "Target",
                        "Found",
                        lccn=payload.get("lccn"),
                        nlmcn=payload.get("nlmcn"),
                    )
                    self._update_processed()

                elif event == "failed":
                    error = payload.get("last_error") or payload.get("error", "No results")
                    source = payload.get("last_target") or "All"
                    self.progress_update.emit(isbn, "failed", source, error)
                    self._append_live_failed(
                        isbn,
                        error,
                        source,
                        retry_days=self.config.get("retry_days", 7),
                        not_found_targets=payload.get("not_found_targets"),
                        z3950_unsupported_targets=payload.get("z3950_unsupported_targets"),
                        offline_targets=payload.get("offline_targets"),
                        other_errors=payload.get("other_errors"),
                    )
                    self._update_processed()
                
                elif event == "stats":
                    self.stats["total"] = payload.get("total", self.stats["total"])
                    self.stats["found"] = payload.get("successes", 0)
                    self.stats["failed"] = payload.get("failures", 0)
                    self.stats["cached"] = payload.get("cached", 0)
                    self.stats["skipped"] = payload.get("skipped", 0)
                    # Force stats update to UI
                    self.stats_update.emit(self.stats.copy())

            # Build targets list from config
            targets = self._build_targets()
            
            # Print target info
            if targets:
                print(f"DEBUG: HarvestWorkerV2 using {len(targets)} targets: {[t.name for t in targets]}")
            else:
                print("DEBUG: HarvestWorkerV2 using NO targets (or default placeholders).")

            # Run the harvest pipeline
            retry_days = self.config.get("retry_days", 7)
            call_number_mode = self.config.get("call_number_mode", "lccn")
            try:
                max_workers = max(1, int(self.advanced_settings.get("parallel_workers", 1)))
            except Exception:
                max_workers = 1

            print(
                f"DEBUG: HarvestWorkerV2 calling run_harvest with db_path='data/lccn_harvester.sqlite3' "
                f"retry={retry_days} mode={call_number_mode} workers={max_workers}"
            )

            summary = run_harvest(
                input_path=Path(self.input_file),
                dry_run=False,
                db_path="data/lccn_harvester.sqlite3",
                retry_days=retry_days,
                targets=targets,
                bypass_retry_isbns=self.bypass_retry_isbns,
                progress_cb=progress_callback,
                cancel_check=lambda: self._check_cancel_and_pause(),
                max_workers=max_workers,
                call_number_mode=call_number_mode,
            )
            print(f"DEBUG: HarvestWorkerV2 SUMMARY: {summary}")
            
            # Final stats
            final_stats = {
                "total": summary.total_isbns,
                "found": summary.successes,
                "failed": summary.failures,
                "cached": summary.cached_hits,
                "skipped": summary.skipped_recent_fail,
            }

            self.status_message.emit(messages.HarvestMessages.harvest_completed.format(
                successes=summary.successes, failures=summary.failures))
            self.harvest_complete.emit(True, final_stats)
            print("DEBUG: HarvestWorkerV2 completed successfully.")

        except HarvestCancelled:
            self.status_message.emit("Harvest cancelled by user.")
            stats = self.stats.copy() if hasattr(self, "stats") else {"total": 0, "found": 0, "failed": 0}
            stats["cancelled"] = True
            self.harvest_complete.emit(False, stats)
        except Exception as e:
            import traceback
            error_msg = f"Error: {str(e)}\\n{traceback.format_exc()}"
            print(f"DEBUG: HarvestWorkerV2 CRASHED: {error_msg}")
            self.status_message.emit(error_msg)
            self.harvest_complete.emit(False, {"total": 0, "found": 0, "failed": 0})
        finally:
            self._close_live_result_files()

    def _update_processed(self):
        """Update processed count and emit stats/milestones."""
        self.processed_count += 1

        # Check milestones
        self._check_milestone(self.processed_count, self.stats["total"])

        # Emit stats update for UI
        if self.processed_count % 5 == 0 or self.processed_count == self.stats["total"]:
            self.stats_update.emit(self.stats.copy())

    def _prepare_live_result_files(self):
        """Create/overwrite per-run TSV output files."""
        out_dir = Path("data")
        out_dir.mkdir(parents=True, exist_ok=True)
        files = {
            "successful": (out_dir / "successful.tsv", ["ISBN", "Call No.", "Title", "Pub Year", "Source"]),
            "invalid": (out_dir / "invalid.tsv", ["ISBN"]),
            "failed": (
                out_dir / "failed.tsv",
                ["ISBN", "Not Found", "Z39.50 Unsupported", "Offline", "Other Errors", "Next Try"],
            ),
        }
        self._close_live_result_files()
        for key, (path, header) in files.items():
            fh = open(path, "w", encoding="utf-8", newline="")
            writer = csv.writer(fh, delimiter="\t")
            writer.writerow(header)
            fh.flush()
            self._live_result_handles[key] = fh

    def _close_live_result_files(self):
        for fh in self._live_result_handles.values():
            try:
                fh.flush()
                fh.close()
            except Exception:
                pass
        self._live_result_handles = {}

    def _append_live_row(self, bucket, row):
        fh = self._live_result_handles.get(bucket)
        if fh is None:
            return
        with self._live_results_lock:
            writer = csv.writer(fh, delimiter="\t")
            writer.writerow(row)
            fh.flush()

    def _write_invalid_live_rows(self, invalid_list):
        for raw_isbn in invalid_list or []:
            self._append_live_row("invalid", [raw_isbn])

    def _append_live_success(self, isbn, source, message, lccn=None, nlmcn=None):
        call_parts = [v for v in [lccn, nlmcn] if v]
        call_no = " | ".join(call_parts) if call_parts else (message or "")
        self._append_live_row(
            "successful",
            [isbn, call_no, "", "", source or "-"],
        )

    def _compute_next_try_value(self, isbn, retry_days):
        try:
            retry_days = int(retry_days or 0)
        except Exception:
            retry_days = 0
        if retry_days <= 0:
            return ""
        try:
            db = DatabaseManager("data/lccn_harvester.sqlite3")
            att = db.get_attempted(isbn)
            if att and att.last_attempted:
                base_dt = datetime.fromisoformat(att.last_attempted)
            else:
                base_dt = datetime.now(timezone.utc)
            if base_dt.tzinfo is None:
                base_dt = base_dt.replace(tzinfo=timezone.utc)
            return (base_dt + timedelta(days=retry_days)).astimezone().strftime("%Y-%m-%d %H:%M:%S")
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
        def _fmt_targets(values):
            vals = [str(v).strip() for v in (values or []) if str(v).strip()]
            if not vals:
                return ""
            return "[" + " | ".join(vals) + "]"

        retry_days = self.config.get("retry_days", 7) if retry_days is None else retry_days
        not_found = _fmt_targets(not_found_targets)
        z3950_unsupported = _fmt_targets(z3950_unsupported_targets)
        offline = _fmt_targets(offline_targets)
        other = " ; ".join(other_errors or [])
        # Preserve reason if it doesn't map cleanly
        if (not not_found and not z3950_unsupported and not offline) and reason:
            other = reason if not other else f"{other} ; {reason}"
        self._append_live_row(
            "failed",
            [
                isbn,
                not_found,
                z3950_unsupported,
                offline,
                other,
                self._compute_next_try_value(isbn, retry_days),
            ],
        )

    def _read_and_validate_isbns(self):
        """Read and validate ISBNs using the centralized parser."""
        try:
            parsed = parse_isbn_file(Path(self.input_file))
            if parsed.invalid_isbns:
                self.status_message.emit(messages.HarvestMessages.invalid_isbns_count.format(count=len(parsed.invalid_isbns)))
            return parsed.unique_valid, parsed.invalid_isbns
        except Exception as e:
            self.status_message.emit(messages.HarvestMessages.error_reading_file.format(error=str(e)))
            return [], []

    def _record_invalid_isbns(self, invalid_list):
        """Record invalid ISBNs in DB so they appear in stats."""
        if not invalid_list: return
        
        try:
            db = DatabaseManager("data/lccn_harvester.sqlite3")
            with db.transaction() as conn:
                for raw_isbn in invalid_list:
                    # Upsert into attempted with 'Invalid' error
                    # We use a placeholder target 'Validation'
                    conn.execute(
                        "INSERT OR ABORT INTO attempted (isbn, last_target, last_attempted, fail_count, last_error) "
                        "VALUES (?, ?, ?, 1, 'Invalid ISBN') "
                        "ON CONFLICT(isbn) DO UPDATE SET "
                        "last_attempted=excluded.last_attempted, fail_count=fail_count+1, last_error='Invalid ISBN'",
                        (raw_isbn[:20], "Validation", datetime.now().isoformat()),
                    )
        except Exception as e:
            print(f"DEBUG: Failed to record invalid ISBNs: {e}")

    def _build_targets(self):
        """Build list of harvest targets from targets configuration."""
        if not self.targets:
            return None  # Orchestrator will use PlaceholderTarget

        try:
            selected_targets = [t for t in self.targets if t.get("selected", True)]
            sorted_targets = sorted(selected_targets, key=lambda x: x.get("rank", 999))
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
                    target = create_target_from_config(cfg)
                    target_instances.append(target)
                except Exception as e:
                    self.status_message.emit(messages.HarvestMessages.failed_create_target.format(
                        name=target_config.get("name"), error=str(e)))

            return target_instances if target_instances else None

        except Exception as e:
            self.status_message.emit(messages.HarvestMessages.error_building_targets.format(error=str(e)))
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

    def _check_milestone(self, processed, total):
        """Check if a milestone has been reached and emit signal."""
        if processed == 100:
            self.milestone_reached.emit("100_processed", 100)
        elif processed == 500:
            self.milestone_reached.emit("500_processed", 500)
        elif processed == 1000:
            self.milestone_reached.emit("1000_processed", 1000)

        if total > 0:
            percent = (processed / total) * 100
            if 49.5 <= percent < 50.5 and processed == int(total * 0.5):
                self.milestone_reached.emit("50_percent", processed)
            elif 74.5 <= percent < 75.5 and processed == int(total * 0.75):
                self.milestone_reached.emit("75_percent", processed)
            elif 89.5 <= percent < 90.5 and processed == int(total * 0.9):
                self.milestone_reached.emit("90_percent", processed)

class DroppableGroupBox(QGroupBox):
    """A group box that accepts drag and drop (for the compact upload card)."""
    file_dropped = pyqtSignal(str)

    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.setAcceptDrops(True)
        self.normal_style = """
            QGroupBox {
                border: 1px solid #363a4f;
                border-radius: 8px;
                margin-top: 1ex;
                background-color: #1e2030;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
                color: #cad3f5;
            }
        """
        self.setStyleSheet(self.normal_style)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path.endswith(('.tsv', '.txt', '.csv')):
                    event.acceptProposedAction()
                    self.setStyleSheet(self.normal_style.replace("#363a4f", "#7bc96f").replace("#1e2030", "#1f2a22"))
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self.normal_style)

    def dropEvent(self, event: QDropEvent):
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        valid_files = [f for f in files if f.endswith(('.tsv', '.txt', '.csv'))]

        if valid_files:
            file_path = valid_files[0]
            self.file_dropped.emit(file_path)
            self.setStyleSheet(self.normal_style.replace("#363a4f", "#7bc96f").replace("#1e2030", "#243329"))
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(500, lambda: self.setStyleSheet(self.normal_style))
            event.acceptProposedAction()
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Invalid File", "Please drop a valid TSV, TXT, or CSV file.")
            event.ignore()
            self.setStyleSheet(self.normal_style)

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
    milestone_reached = pyqtSignal(str, int)
    progress_updated = pyqtSignal(str, str, str, str) # isbn, status, source, message

    # Signals to request data from main window
    request_start_harvest = pyqtSignal() 

    def __init__(self):
        super().__init__()
        self.worker = None
        self.is_running = False
        self.current_state = UIState.IDLE
        self.input_file = None
        
        # External data sources (set by Main Window)
        self._config_getter = None
        self._targets_getter = None
        
        self.processed_count = 0
        self.total_count = 0 
        self._shortcut_modifier = "Meta" if sys.platform == "darwin" else "Ctrl"
        
        self._setup_ui()
        self._setup_shortcuts()

    def set_data_sources(self, config_getter, targets_getter):
        """Set callbacks to retrieve config and selected targets."""
        self._config_getter = config_getter
        self._targets_getter = targets_getter

    def on_targets_changed(self, targets):
        """Handle target selection changes from TargetsTab."""
        self._check_start_conditions()

    def _setup_ui(self):
        # Outer layout: scrollable content area + sticky action bar at the bottom
        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _outer.setSpacing(0)
        _scroll = QScrollArea()
        _scroll.setWidgetResizable(True)
        _scroll.setFrameShape(QFrame.Shape.NoFrame)
        _scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        _scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        _scr_content = QWidget()
        _scroll.setWidget(_scr_content)
        _outer.addWidget(_scroll, 1)

        layout = QVBoxLayout(_scr_content)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        # 1. Header Area
        header_layout = QHBoxLayout()
        title = QLabel("Harvest Execution")
        title.setProperty("class", "CardTitle")
        title.setStyleSheet("font-size: 18px;")
        
        self.status_pill = QLabel("IDLE")
        self.status_pill.setProperty("class", "StatusPill")
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_pill.setAccessibleName("Harvest status")
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.status_pill)
        layout.addLayout(header_layout)

        # Banner (Hidden initially)
        self.banner_frame = QFrame()
        self.banner_frame.setStyleSheet("background-color: #24273a; border-radius: 8px; border: 1px solid #a6da95;")
        self.banner_frame.setVisible(False)
        banner_layout = QVBoxLayout(self.banner_frame)
        banner_layout.setContentsMargins(16, 16, 16, 16)
        
        banner_top = QHBoxLayout()
        lbl_banner_title = QLabel("✅ Harvest Completed")
        lbl_banner_title.setStyleSheet("color: #a6da95; font-size: 16px; font-weight: bold;")
        self.lbl_banner_stats = QLabel("Success: 0 | Failed: 0 | Invalid: 0")
        self.lbl_banner_stats.setStyleSheet("color: #cad3f5; font-size: 14px;")
        
        banner_top.addWidget(lbl_banner_title)
        banner_top.addStretch()
        banner_top.addWidget(self.lbl_banner_stats)
        
        banner_bottom = QHBoxLayout()
        self.lbl_banner_out = QLabel("Saved to: data/exports/")
        self.lbl_banner_out.setStyleSheet("color: #a5adcb; font-size: 13px;")
        
        btn_banner_folder = QPushButton("Open Folder")
        btn_banner_folder.setProperty("class", "SecondaryButton")
        btn_banner_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_banner_folder.clicked.connect(self._open_output_folder)
        
        btn_open_success = QPushButton("success.tsv")
        btn_open_success.setProperty("class", "SecondaryButton")
        btn_open_success.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open_success.clicked.connect(lambda: self._open_file_in_explorer("data/exports/success.tsv"))
        
        btn_open_failed = QPushButton("failed.tsv")
        btn_open_failed.setProperty("class", "SecondaryButton")
        btn_open_failed.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open_failed.clicked.connect(lambda: self._open_file_in_explorer("data/exports/failed.tsv"))
        
        btn_open_invalid = QPushButton("invalid.tsv")
        btn_open_invalid.setProperty("class", "SecondaryButton")
        btn_open_invalid.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open_invalid.clicked.connect(lambda: self._open_file_in_explorer("data/exports/invalid.tsv"))
        
        banner_bottom.addWidget(self.lbl_banner_out)
        banner_bottom.addStretch()
        banner_bottom.addWidget(btn_open_success)
        banner_bottom.addWidget(btn_open_failed)
        banner_bottom.addWidget(btn_open_invalid)
        banner_bottom.addWidget(btn_banner_folder)
        
        banner_layout.addLayout(banner_top)
        banner_layout.addLayout(banner_bottom)
        layout.addWidget(self.banner_frame)

        # 2. Top Row: Run Setup (Slim Card)
        self.input_card = DroppableGroupBox("Run Setup")
        self.input_card.file_dropped.connect(self.set_input_file)
        
        input_layout = QVBoxLayout(self.input_card)
        input_layout.setContentsMargins(16, 16, 16, 16)
        input_layout.setSpacing(12)
        
        # Setup Grid
        setup_grid = QGridLayout()
        setup_grid.setColumnStretch(1, 1)
        
        # Row 0: Input File
        lbl_input = QLabel("Input file:")
        lbl_input.setStyleSheet("color: #a5adcb; font-size: 13px; font-weight: bold;")
        
        file_input_layout = QHBoxLayout()
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setPlaceholderText("No file selected... (drag & drop TSV/CSV/TXT here)")
        self.file_path_edit.setReadOnly(True)
        self.file_path_edit.setStyleSheet("background-color: transparent; color: #cad3f5; border: none; font-size: 14px;")
        
        self.btn_browse = QPushButton("Choose file...")
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
        
        # Row 1: Target
        lbl_target_head = QLabel("Target:")
        lbl_target_head.setStyleSheet("color: #a5adcb; font-size: 13px; font-weight: bold;")
        
        target_layout = QHBoxLayout()
        self.lbl_setup_target = QLabel("No targets selected (Check Targets tab)")
        self.lbl_setup_target.setStyleSheet("color: #cad3f5; font-size: 14px;")
        
        self.btn_go_targets = QPushButton("Go to Targets")
        self.btn_go_targets.setProperty("class", "SecondaryButton")
        self.btn_go_targets.setCursor(Qt.CursorShape.PointingHandCursor)
        # Main window will hook this up if needed, or we just rely on the user clicking the tab
        self.btn_go_targets.setVisible(False) 
        
        target_layout.addWidget(self.lbl_setup_target)
        target_layout.addWidget(self.btn_go_targets)
        target_layout.addStretch()
        
        setup_grid.addWidget(lbl_target_head, 1, 0)
        setup_grid.addLayout(target_layout, 1, 1)
        
        # Row 2: Output
        lbl_out_head = QLabel("Output:")
        lbl_out_head.setStyleSheet("color: #a5adcb; font-size: 13px; font-weight: bold;")
        
        out_layout = QHBoxLayout()
        self.lbl_setup_output = QLabel("Will save TSV files to: data/exports/")
        self.lbl_setup_output.setStyleSheet("color: #cad3f5; font-size: 14px;")
        
        btn_open_out = QPushButton("Open Folder")
        btn_open_out.setProperty("class", "SecondaryButton")
        btn_open_out.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open_out.clicked.connect(self._open_output_folder)
        
        out_layout.addWidget(self.lbl_setup_output)
        out_layout.addWidget(btn_open_out)
        out_layout.addStretch()
        
        setup_grid.addWidget(lbl_out_head, 2, 0)
        setup_grid.addLayout(out_layout, 2, 1)
        
        input_layout.addLayout(setup_grid)
        layout.addWidget(self.input_card)

        # 3. Middle Row: Stats & Run Status
        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(20)
        
        # Left: 6 Stat Tiles
        self.stats_group = QGroupBox("File stats")
        stats_grid = QGridLayout(self.stats_group)
        stats_grid.setContentsMargins(16, 16, 16, 16)
        stats_grid.setSpacing(16)
        
        def create_tile(title):
            card = QFrame()
            card.setStyleSheet("background-color: #181926; border-radius: 6px;")
            clayout = QVBoxLayout(card)
            clayout.setContentsMargins(12, 12, 12, 12)
            
            lbl_title = QLabel(title)
            lbl_title.setStyleSheet("color: #a5adcb; font-size: 12px;")
            lbl_val = QLabel("-")
            lbl_val.setStyleSheet("color: #cad3f5; font-size: 20px; font-weight: bold;")
            lbl_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            
            clayout.addWidget(lbl_title)
            clayout.addWidget(lbl_val)
            return card, lbl_val
            
        tile_valid, self.lbl_val_loaded = create_tile("Valid ISBNs (unique)")
        tile_rows, self.lbl_val_rows_valid = create_tile("Valid ISBN rows")
        tile_dupes, self.lbl_val_duplicates = create_tile("Duplicate valid rows")
        tile_invalid, self.lbl_val_invalid = create_tile("Invalid ISBN rows")
        tile_size, self.lbl_val_size = create_tile("File size")
        tile_total, self.lbl_val_rows = create_tile("Total rows")
        
        stats_grid.addWidget(tile_valid, 0, 0)
        stats_grid.addWidget(tile_rows, 0, 1)
        stats_grid.addWidget(tile_dupes, 0, 2)
        stats_grid.addWidget(tile_invalid, 1, 0)
        stats_grid.addWidget(tile_size, 1, 1)
        stats_grid.addWidget(tile_total, 1, 2)
        
        middle_layout.addWidget(self.stats_group, stretch=2)
        
        # Right: Run Status Card
        self.run_status_group = QGroupBox("Run status")
        status_layout = QVBoxLayout(self.run_status_group)
        status_layout.setContentsMargins(16, 16, 16, 16)
        status_layout.setSpacing(12)
        
        def add_status_row(grid, row, title, val_widget):
            lbl = QLabel(title)
            lbl.setStyleSheet("color: #a5adcb; font-size: 13px;")
            grid.addWidget(lbl, row, 0)
            grid.addWidget(val_widget, row, 1)
            
        status_grid = QGridLayout()
        
        self.lbl_run_status = QLabel("Idle")
        self.lbl_run_status.setStyleSheet("color: #8aadf4; font-size: 14px; font-weight: bold;")
        self.lbl_run_progress = QLabel("0 / 0")
        self.lbl_run_progress.setStyleSheet("color: #cad3f5; font-size: 14px;")
        self.lbl_run_elapsed = QLabel("00:00:00")
        self.lbl_run_elapsed.setStyleSheet("color: #cad3f5; font-size: 14px;")
        
        add_status_row(status_grid, 0, "Status:", self.lbl_run_status)
        add_status_row(status_grid, 1, "Progress:", self.lbl_run_progress)
        add_status_row(status_grid, 2, "Elapsed:", self.lbl_run_elapsed)
        
        status_layout.addLayout(status_grid)
        status_layout.addStretch()
        
        middle_layout.addWidget(self.run_status_group, stretch=1)
        
        layout.addLayout(middle_layout)

        # Timer setup
        self.run_timer = QTimer(self)
        self.run_timer.timeout.connect(self._update_timer)
        self.run_time = QTime(0, 0, 0)
        self.timer_is_paused = False

        # 4. Bottom Row: Preview
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(20)
        
        # Collapsible Preview
        self.preview_group = QGroupBox("Preview (first 50 lines) • truncated")
        preview_layout = QVBoxLayout(self.preview_group)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setStyleSheet("""
            QTextEdit {
                background-color: #181926;
                border: 1px solid #363a4f;
                border-radius: 4px;
                padding: 10px;
                font-family: monospace;
                font-size: 13px;
                color: #cad3f5;
            }
        """)
        self.preview_text.setMinimumHeight(120)
        
        btn_copy_preview = QPushButton("Copy")
        btn_copy_preview.setProperty("class", "SecondaryButton")
        btn_copy_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy_preview.clicked.connect(self._copy_preview)
        
        preview_header = QHBoxLayout()
        preview_header.addStretch()
        preview_header.addWidget(btn_copy_preview)
        
        preview_layout.addLayout(preview_header)
        preview_layout.addWidget(self.preview_text)
        bottom_layout.addWidget(self.preview_group)
        
        layout.addLayout(bottom_layout)
        
        layout.addStretch()

        # 4. Sticky Bottom Action Bar
        action_frame = QFrame()
        action_frame.setProperty("class", "Card")
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(16, 16, 16, 16)
        
        # Left side: Status and Progress
        status_layout = QVBoxLayout()
        
        self.log_output = QLabel("Ready...")
        self.log_output.setStyleSheet("color: #cad3f5; font-size: 13px; font-weight: bold;")
        
        progress_layout = QHBoxLayout()
        self.lbl_counts = QLabel("0 / 0 processed")
        self.lbl_counts.setStyleSheet("color: #a5adcb; font-size: 12px;")
        
        progress_layout.addWidget(self.lbl_counts)
        progress_layout.addStretch()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar { background-color: #181926; height: 8px; border-radius: 4px; border: none; }
            QProgressBar::chunk { background-color: #8aadf4; border-radius: 4px; }
        """)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximumHeight(8)
        
        status_layout.addWidget(self.log_output)
        status_layout.addLayout(progress_layout)
        status_layout.addWidget(self.progress_bar)
        
        action_layout.addLayout(status_layout, stretch=2)
        
        # Right side: Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(12)
        
        self.btn_stop = QPushButton("Cancel")
        self.btn_stop.setProperty("class", "DangerButton")
        self.btn_stop.setMinimumHeight(40)
        self.btn_stop.setMinimumWidth(80)
        self.btn_stop.clicked.connect(self._stop_harvest)
        self.btn_stop.setEnabled(False)
        
        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setProperty("class", "SecondaryButton")
        self.btn_pause.setMinimumHeight(40)
        self.btn_pause.setMinimumWidth(80)
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_pause.setEnabled(False)
        
        self.btn_start = QPushButton("Start Harvest")
        self.btn_start.setProperty("class", "PrimaryButton")
        self.btn_start.setMinimumHeight(40)
        self.btn_start.setMinimumWidth(160)
        mod_name = "Cmd" if self._shortcut_modifier == "Meta" else "Ctrl"
        self.btn_start.setToolTip(f"Start harvest ({mod_name}+Enter)")
        self.btn_start.clicked.connect(self._on_start_clicked)
        self.btn_start.setEnabled(False)
        
        self.btn_new_run = QPushButton("New Harvest")
        self.btn_new_run.setProperty("class", "PrimaryButton")
        self.btn_new_run.setMinimumHeight(40)
        self.btn_new_run.setMinimumWidth(160)
        self.btn_new_run.clicked.connect(self._clear_input)
        self.btn_new_run.setVisible(False)
        
        self.lbl_start_helper = QLabel("")
        self.lbl_start_helper.setVisible(False)
        
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.btn_stop)
        buttons_layout.addWidget(self.btn_pause)
        buttons_layout.addWidget(self.btn_new_run)
        buttons_layout.addWidget(self.btn_start)
        
        action_layout.addLayout(buttons_layout, stretch=1)
        
        _outer.addWidget(action_frame)
        
        self._transition_state(UIState.IDLE)

    def _transition_state(self, state: UIState, **kwargs):
        """Unified UI state machine handling buttons, banners, and status pills."""
        self.current_state = state
        
        # Default all action buttons to hidden/disabled
        self.btn_start.setVisible(False)
        self.btn_pause.setVisible(False)
        self.btn_stop.setVisible(False)
        self.btn_new_run.setVisible(False)
        self.banner_frame.setVisible(False)
        
        # Update is_running flag based on state
        self.is_running = state in (UIState.RUNNING, UIState.PAUSED)
        
        if state == UIState.IDLE:
            self.status_pill.setText("IDLE")
            self.status_pill.setStyleSheet("background-color: #313244; color: #a5adcb;")
            self.lbl_run_status.setText("Idle")
            self.lbl_run_status.setStyleSheet("color: #a5adcb; font-size: 14px; font-weight: bold;")
            
            self.btn_start.setVisible(True)
            self.btn_start.setEnabled(False)
            self.btn_start.setText("Start Harvest")
            
        elif state == UIState.READY:
            self.status_pill.setText("READY")
            self.status_pill.setStyleSheet("background-color: #45475a; color: #b4befe;")
            self.lbl_run_status.setText("Ready")
            self.lbl_run_status.setStyleSheet("color: #b4befe; font-size: 14px; font-weight: bold;")
            
            self.btn_start.setVisible(True)
            self.btn_start.setEnabled(True)
            count = kwargs.get("count", "?")
            self.btn_start.setText(f"Start Harvest ({count} ISBNs)")
            
        elif state == UIState.RUNNING:
            self.status_pill.setText("RUNNING")
            self.status_pill.setStyleSheet("background-color: #8aadf4; color: #1e2030;")
            self.lbl_run_status.setText("Running")
            self.lbl_run_status.setStyleSheet("color: #8aadf4; font-size: 14px; font-weight: bold;")
            
            # Reset progress bar to blue
            self.progress_bar.setStyleSheet("""
                QProgressBar { background-color: #181926; height: 8px; border-radius: 4px; border: none; }
                QProgressBar::chunk { background-color: #8aadf4; border-radius: 4px; }
            """)
            
            self.btn_pause.setVisible(True)
            self.btn_pause.setEnabled(True)
            self.btn_pause.setText("Pause")
            self.btn_stop.setVisible(True)
            self.btn_stop.setEnabled(True)
            
        elif state == UIState.PAUSED:
            self.status_pill.setText("PAUSED")
            self.status_pill.setStyleSheet("background-color: #eeba0b; color: #1e2030;")
            self.lbl_run_status.setText("Paused")
            self.lbl_run_status.setStyleSheet("color: #eeba0b; font-size: 14px; font-weight: bold;")
            
            self.btn_pause.setVisible(True)
            self.btn_pause.setEnabled(True)
            self.btn_pause.setText("Resume")
            self.btn_stop.setVisible(True)
            self.btn_stop.setEnabled(True)
            
        elif state == UIState.ERROR:
            self.status_pill.setText("ERROR")
            self.status_pill.setStyleSheet("background-color: #313244; color: #ed8796;")
            self.lbl_run_status.setText("Error")
            self.lbl_run_status.setStyleSheet("color: #ed8796; font-size: 14px; font-weight: bold;")
            
            self.btn_start.setVisible(True)
            self.btn_start.setEnabled(False)
            self.btn_start.setText("Start Harvest")
            
        elif state in (UIState.COMPLETED, UIState.CANCELLED):
            is_success = state == UIState.COMPLETED
            color = "#a6da95" if is_success else "#ed8796"
            label = "COMPLETED" if is_success else "CANCELLED"
            
            self.status_pill.setText(label)
            self.status_pill.setStyleSheet(f"background-color: {color}; color: #1e1e2e;")
            self.lbl_run_status.setText(label.capitalize())
            self.lbl_run_status.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold;")
            
            self.btn_new_run.setVisible(True)
            
            if is_success:
                stats = kwargs.get("stats", {})
                succ = stats.get('found', 0) + stats.get('cached', 0)
                fail = stats.get('failed', 0)
                inv = stats.get('skipped', 0)  # approximations
                
                self.lbl_banner_stats.setText(f"Success: {succ} | Failed: {fail} | Skipped: {inv}")
                self.banner_frame.setVisible(True)

    def _setup_shortcuts(self):
        mod = self._shortcut_modifier
        QShortcut(QKeySequence(f"{mod}+O"), self, activated=self._browse_file)
        QShortcut(QKeySequence(f"{mod}+Return"), self, activated=self._on_start_clicked)
        QShortcut(QKeySequence(f"{mod}+."), self, activated=self._stop_harvest)

    def set_input_file(self, path):
        if not path:
            self._clear_input()
            return

        path_obj = Path(path)
        
        # Extension Check
        valid_exts = {'.tsv', '.txt', '.csv'}
        if path_obj.suffix.lower() not in valid_exts:
            self._set_invalid_state(path_obj.name, "Invalid file format (must be .tsv, .txt, .csv)")
            return

        # Content Check (Real Validation)
        try:
            size_kb = path_obj.stat().st_size / 1024
            sampled = path_obj.stat().st_size > 20 * 1024 * 1024  # 20 MB
            INFO_SAMPLE_MAX_LINES = 200_000

            parsed = parse_isbn_file(path_obj, max_lines=INFO_SAMPLE_MAX_LINES if sampled else 0)
            
            unique_valid = len(parsed.unique_valid)
            valid_rows = parsed.valid_count
            invalid_rows = len(parsed.invalid_isbns)
            duplicate_valid_rows = parsed.duplicate_count
            
            sample_note = ""
            if sampled:
                sample_note = f"\nNote: Large file detected. Stats based on first {INFO_SAMPLE_MAX_LINES:,} lines."

            print(f"DEBUG: Validation Results - Unique Valid: {unique_valid}, Invalid: {invalid_rows}")

            if valid_rows == 0:
                 msg = "File contains no valid ISBNs"
                 if invalid_rows > 0: msg += f" ({invalid_rows} invalid lines)"
                 self._set_invalid_state(path_obj.name, msg)
                 return

            # Success State
            self.input_file = path
            
            # Update Path Display
            self.file_path_edit.setText(str(path_obj))
            
            # Enable clear button and make it red
            self.btn_clear_file.setEnabled(True)
            self.btn_clear_file.setProperty("class", "DangerButton")
            self.btn_clear_file.style().unpolish(self.btn_clear_file)
            self.btn_clear_file.style().polish(self.btn_clear_file)
            
            # Labels and Preview
            self.lbl_counts.setText(f"0 / {unique_valid} processed")
            self.log_output.setText(f"Ready to harvest {unique_valid} unique ISBNs.")
            
            # File summary
            self.lbl_val_size.setText(f"{size_kb:.2f} KB")
            self.lbl_val_rows_valid.setText(str(valid_rows))
            self.lbl_val_rows.setText(str(valid_rows + invalid_rows))
            self.lbl_val_loaded.setText(str(unique_valid))
            
            # Red highlight if invalid > 0
            self.lbl_val_invalid.setText(str(invalid_rows))
            if invalid_rows > 0:
                self.lbl_val_invalid.setStyleSheet("color: #ed8796; font-size: 20px; font-weight: bold;")
            else:
                self.lbl_val_invalid.setStyleSheet("color: #cad3f5; font-size: 20px; font-weight: bold;")
                
            self.lbl_val_duplicates.setText(str(duplicate_valid_rows))
            
            self.file_path_edit.setText(path_obj.name)
            self.btn_clear_file.setVisible(True)
            self._load_file_preview()
            
            self._check_start_conditions(unique_valid)

        except Exception as e:
            self._set_invalid_state(path_obj.name, f"Error reading file: {e}")

    def _check_start_conditions(self, isbn_count=None):
        """Enable start button only if file is valid AND targets are selected."""
        # Get ISBN count if not passed (parse from label or store in member)
        if not self.input_file:
            self._transition_state(UIState.IDLE)
            return

        # Check targets
        targets = self._targets_getter() if self._targets_getter else []
        selected_targets = [t for t in targets if t.get("selected", True)]
        if not selected_targets:
            self._transition_state(UIState.ERROR)
            self.log_output.setText("Select at least one target in Targets tab.")
            return

        # Valid
        count_text = self.lbl_counts.text()
        count = count_text.replace("Loaded: ", "").replace(" ISBNs", "") if "Loaded" in count_text else "?"
        if isbn_count is not None: count = str(isbn_count)
        
        self._transition_state(UIState.READY, count=count)

    def _load_file_preview(self):
        """Load a snippet of the file for preview."""
        if not self.input_file:
            self.preview_text.clear()
            return
            
        path_obj = Path(self.input_file)
        if not path_obj.exists():
             self.preview_text.setPlainText("Error: File does not exist.")
             return
             
        try:
            with open(path_obj, 'r', encoding='utf-8-sig') as f:
                lines = list(islice(f, 20))
                preview_text = "".join(lines)
                if len(lines) == 20:
                     preview_text += "\n... (truncated)"
            self.preview_text.setPlainText(preview_text)
        except Exception as e:
            self.preview_text.setPlainText(f"Error reading file preview: {str(e)}")

    def _clear_input(self):
        """Reset input state."""
        self.input_file = None
        self.file_path_edit.clear()
        
        self.lbl_val_size.setText("-")
        self.lbl_val_rows_valid.setText("-")
        self.lbl_val_rows.setText("-")
        self.lbl_val_loaded.setText("-")
        self.lbl_val_invalid.setText("-")
        self.lbl_val_duplicates.setText("-")
        self.preview_text.clear()
        
        # Reset clear button
        self.btn_clear_file.setVisible(False)
        
        self.lbl_counts.setText("0 / 0 processed")
        self.log_output.setText("Ready...")
        self.log_output.setStyleSheet("color: #cad3f5; font-size: 13px; font-weight: bold;")
        
        self.lbl_val_invalid.setStyleSheet("color: #cad3f5; font-size: 20px; font-weight: bold;")
        
        self._transition_state(UIState.IDLE)

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
        
        self.lbl_counts.setText("0 / 0 processed")
        self.log_output.setText(error_msg)
        self.log_output.setStyleSheet("color: #ed8796; font-size: 13px; font-weight: bold;")
        
        self._transition_state(UIState.ERROR)

    def _show_sample_format(self):
        QMessageBox.information(
            self, 
            "Expected Format", 
            "The input file should be a TSV (Tab-Separated Values) or simple Text file.\n\n"
            "Format:\n"
            "• One ISBN per line\n"
            "• First column is used\n"
            "• Headers allowed (if line starts with 'ISBN')\n\n"
            "Example:\n"
            "978-3-16-148410-0\n"
            "0-306-40615-2\n"
            "9780306406157"
        )



    def _browse_file(self):
        """Open file picker (mimicking InputTab's filtering)."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select ISBN Input File",
            "",
            "All Files (*.*);;TSV Files (*.tsv);;Text Files (*.txt);;CSV Files (*.csv)"
        )
        if file_path:
            self.set_input_file(file_path)

    def _on_start_clicked(self):
        """Prepare and start harvest using external config."""
        if not self.input_file:
            print("DEBUG: _on_start_clicked called but no input_file.")
            return

        print(f"DEBUG: _on_start_clicked with input: {self.input_file}")
        
        # 1. Get Config
        config = self._config_getter() if self._config_getter else {"retry_days": 7, "call_number_mode": "lccn"}
        
        # 2. Get Targets
        targets = self._targets_getter() if self._targets_getter else []
        selected_targets = [t for t in targets if t.get("selected", True)]
        if not selected_targets:
            QMessageBox.warning(self, "No Targets", "Please select at least one target in the Targets tab.")
            return

        retry_days = int(config.get("retry_days", 7) or 0)
        bypass_retry_isbns = self._check_recent_not_found_isbns(retry_days)
        if bypass_retry_isbns is None:
            self.log_output.setText("Harvest cancelled: retry window still active for some ISBNs.")
            return

        # 3. Start Worker
        print(f"DEBUG: Starting worker with {len(selected_targets)} selected targets.")
        self._start_worker(config, targets, bypass_retry_isbns=bypass_retry_isbns)

    def _start_worker(self, config, targets, bypass_retry_isbns=None):
        if self.worker and self.worker.isRunning():
            return

        self.worker = HarvestWorkerV2(
            self.input_file,
            config,
            targets,
            advanced_settings=self._load_advanced_settings(),
            bypass_retry_isbns=bypass_retry_isbns,
        )
        self.worker.progress_update.connect(self._on_progress)
        self.worker.harvest_complete.connect(self._on_complete)
        self.worker.stats_update.connect(self._on_stats)
        self.worker.status_message.connect(self._on_status)
        self.worker.milestone_reached.connect(self.milestone_reached.emit)
        
        self.worker.start()
        
        self._transition_state(UIState.RUNNING)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0/0 (0%)")
        
        # Clear specific widgets for fresh run
        self.run_time = QTime(0, 0, 0)
        self.lbl_run_elapsed.setText("00:00:00")
        self.timer_is_paused = False
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
            self.status_pill.setText("CANCELLING...")
            self.lbl_run_status.setText("Cancelling...")
            self.lbl_run_status.setStyleSheet("color: #ed8796; font-size: 14px; font-weight: bold;")
            self.log_output.setText("Cancelling harvest (waiting for current thread)...")
            self.btn_stop.setEnabled(False) # Prevent double click
            self.btn_pause.setEnabled(False)

    def _toggle_pause(self):
        if self.worker:
            self.worker.toggle_pause()
            if self.worker._pause_requested:
                self._transition_state(UIState.PAUSED)
                self.log_output.setText("Harvest paused. Click Resume to continue.")
                self.timer_is_paused = True
            else:
                self._transition_state(UIState.RUNNING)
                self.log_output.setText("Harvest resumed...")
                self.timer_is_paused = False

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
            db = DatabaseManager("data/lccn_harvester.sqlite3")
            db.init_db()
            recent = []
            for isbn in self._iter_normalized_input_isbns():
                att = db.get_attempted(isbn)
                if att is None:
                    continue
                err = (att.last_error or "").lower()
                # Focus this dialog on previous not-found runs, per user expectation.
                if "not found" not in err:
                    continue
                if db.should_skip_retry(isbn, retry_days=retry_days):
                    recent.append((isbn, att))
        except Exception as e:
            self.log_output.setText(f"Warning: could not check retry window ({e})")
            return set()

        if not recent:
            return set()

        details = []
        for isbn, att in recent[:12]:
            last_attempted = att.last_attempted or "Unknown"
            try:
                last_dt = datetime.fromisoformat(last_attempted)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                next_dt = last_dt + timedelta(days=retry_days)
                next_str = next_dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
                last_str = last_dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                last_str = str(last_attempted)
                next_str = "Unknown"
            details.append(f"{isbn} | last not found: {last_str} | retry after: {next_str}")
        if len(recent) > 12:
            details.append(f"... and {len(recent) - 12} more")

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

        cancel_btn = msg.addButton("Cancel Harvest", QMessageBox.ButtonRole.RejectRole)
        keep_btn = msg.addButton("Continue (Keep Retry Rules)", QMessageBox.ButtonRole.AcceptRole)
        override_btn = msg.addButton("Override and Re-run Now", QMessageBox.ButtonRole.ActionRole)
        msg.setDefaultButton(cancel_btn)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == cancel_btn:
            return None
        if clicked == override_btn:
            return {isbn for isbn, _ in recent}
        return set()

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
        log_msg = f"{isbn}: {msg}"
        self.log_output.setText(log_msg)
        self.progress_updated.emit(isbn, status, source, msg)

    def _on_stats(self, stats):
        total = stats.get('total', 0)
        processed = stats.get('found', 0) + stats.get('failed', 0) + stats.get('cached', 0) + stats.get('skipped', 0)
        self.processed_count = processed
        self.total_count = total
        
        progress_str = f"{processed} / {total}"
        self.lbl_counts.setText(f"{progress_str} processed")
        self.lbl_run_progress.setText(progress_str)
        
        self.progress_bar.setFormat(f"{progress_str} (%p%)" if total > 0 else "0/0 (0%)")
        if total > 0:
            self.progress_bar.setValue(int(processed/total*100))

    def _on_status(self, msg):
        self.log_output.setText(msg)

    def _on_complete(self, success, stats):
        self.is_running = False
        self.run_timer.stop()
        
        final_state = UIState.COMPLETED if success else UIState.CANCELLED
        self._transition_state(final_state, stats=stats)
        
        if not success:
            # Reset UI progress and labels upon cancellation
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("0/0 (0%)")
            self.lbl_counts.setText("0 / 0 processed")
            self.lbl_run_progress.setText("0 / 0")
            self.log_output.setText("Ready...")
        else:
            self.log_output.setText("Harvest successfully completed. Exporting results...")
            self._auto_export_results()
            self.log_output.setText("Harvest successfully completed. Results exported to data/exports/")
            
            # Change progress bar green
            self.progress_bar.setStyleSheet("""
                QProgressBar { background-color: #181926; height: 8px; border-radius: 4px; border: none; }
                QProgressBar::chunk { background-color: #a6da95; border-radius: 4px; }
            """)
        
        self.harvest_finished.emit(success, stats)

    def _auto_export_results(self):
        """Automatically write success.tsv, failed.tsv, and invalid.tsv for THIS run only."""
        if not self.input_file:
            return
            
        try:
            parsed = parse_isbn_file(Path(self.input_file))
            invalid_list = parsed.invalid_isbns
            valid_list = parsed.unique_valid
            
            db = DatabaseManager("data/lccn_harvester.sqlite3")
            success_rows = []
            failed_rows = []
            
            with db.connect() as conn:
                for isbn in valid_list:
                    # Check main table
                    cur = conn.execute("SELECT isbn, lccn, nlmcn, classification, source, date_added FROM main WHERE isbn=?", (isbn,))
                    row = cur.fetchone()
                    if row:
                        success_rows.append(list(row))
                    else:
                        # Check attempted table
                        cur = conn.execute("SELECT isbn, last_target, last_attempted, fail_count, last_error FROM attempted WHERE isbn=?", (isbn,))
                        row = cur.fetchone()
                        if row:
                            failed_rows.append(list(row))
                        else:
                            # Not found in db? (cancelled before reaching)
                            failed_rows.append([isbn, "Unknown", "", 0, "Not processed"])
                            
            # Write to data/exports/
            export_dir = Path("data/exports")
            export_dir.mkdir(parents=True, exist_ok=True)
            
            with open(export_dir / "invalid.tsv", "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow(["ISBN", "Error"])
                for inv in invalid_list:
                    writer.writerow([inv, "Invalid format"])
                    
            with open(export_dir / "success.tsv", "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow(["ISBN", "LCCN", "NLMCN", "Classification", "Source", "Date Added"])
                writer.writerows(success_rows)
                
            with open(export_dir / "failed.tsv", "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow(["ISBN", "Last Target", "Last Attempted", "Fail Count", "Last Error"])
                writer.writerows(failed_rows)
                
        except Exception as e:
            print(f"DEBUG: Auto export failed: {e}")

    def _copy_preview(self):
        """Copy the preview contents to clipboard."""
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.preview_text.toPlainText())

    def _open_output_folder(self):
        """Open the data/exports map in Explorer."""
        out_path = Path("data/exports").resolve()
        out_path.mkdir(parents=True, exist_ok=True)
        import os
        if os.name == 'nt':
            os.startfile(str(out_path))
        elif sys.platform == 'darwin':
            import subprocess
            subprocess.Popen(['open', str(out_path)])
        else:
            import subprocess
            subprocess.Popen(['xdg-open', str(out_path)])

    def _open_file_in_explorer(self, relative_path: str):
        """Open a specific file in the default associated application."""
        file_path = Path(relative_path).resolve()
        if not file_path.exists():
            QMessageBox.warning(self, "Not Found", f"File does not exist:\n{file_path.name}")
            return
            
        import os
        if os.name == 'nt':
            os.startfile(str(file_path))
        elif sys.platform == 'darwin':
            import subprocess
            subprocess.Popen(['open', str(file_path)])
        else:
            import subprocess
            subprocess.Popen(['xdg-open', str(file_path)])
            
    def set_advanced_mode(self, val):
        pass

    def stop_harvest(self):
        """Public method used by window close handlers."""
        self._stop_harvest()
