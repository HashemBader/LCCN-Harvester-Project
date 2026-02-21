"""
Module: harvest_tab_v2.py
V2 Harvest Tab: Functional Core with Professional UI.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QTextEdit, QProgressBar,
    QCheckBox, QSpinBox, QFrame, QGridLayout, QMessageBox, QFileDialog, QLineEdit, QSizePolicy
)
from datetime import datetime, timedelta, timezone
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QMimeData, QUrl, QSize
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QCursor, QShortcut, QKeySequence
from pathlib import Path
from itertools import islice
import csv
import sys
import json
# Add src to path for utils import
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.isbn_validator import normalize_isbn

from .icons import get_icon, SVG_HARVEST, SVG_INPUT, SVG_ACTIVITY
# from .harvest_tab import HarvestWorker  # REMOVED: Using internal HarvestWorkerV2 for separation

# Add imports for Worker
from PyQt6.QtCore import QThread
from src.harvester.run_harvest import run_harvest
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
                    self._update_processed()

                elif event == "skip_retry":
                    self.progress_update.emit(isbn, "skipped", "", messages.HarvestMessages.skipped_recent_failure)
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
                    self._update_processed()

                elif event == "failed":
                    error = payload.get("last_error") or payload.get("error", "No results")
                    source = payload.get("last_target") or "All"
                    self.progress_update.emit(isbn, "failed", source, error)
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

    def _update_processed(self):
        """Update processed count and emit stats/milestones."""
        self.processed_count += 1

        # Check milestones
        self._check_milestone(self.processed_count, self.stats["total"])

        # Emit stats update for UI
        if self.processed_count % 5 == 0 or self.processed_count == self.stats["total"]:
            self.stats_update.emit(self.stats.copy())

    def _read_and_validate_isbns(self):
        """Read and validate ISBNs from input file."""
        try:
            input_path = Path(self.input_file)
            delimiter = "," if input_path.suffix.lower() == ".csv" else "\t"

            with open(self.input_file, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f, delimiter=delimiter)
                valid_isbns = []
                invalid_list = []
                invalid_count = 0

                for row in reader:
                    raw_isbn = (row[0] or "").strip() if row else ""
                    if not raw_isbn or raw_isbn.lower().startswith("isbn") or raw_isbn.startswith("#"):
                        continue  # Skip header

                    normalized = normalize_isbn(raw_isbn)
                    if normalized:
                        valid_isbns.append(normalized)
                    else:
                        invalid_count += 1
                        invalid_list.append(raw_isbn)
                        self.status_message.emit(messages.HarvestMessages.invalid_isbn_skipped.format(isbn=raw_isbn))

                if invalid_count > 0:
                    self.status_message.emit(messages.HarvestMessages.invalid_isbns_count.format(count=invalid_count))

                return valid_isbns, invalid_list
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

class ClickableDropZone(QFrame):
    """A clickable and droppable frame widget (from original InputTab)."""
    clicked = pyqtSignal()
    file_dropped = pyqtSignal(str)  # Emits file path when dropped

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.normal_style = """
            QFrame {
                border: 3px dashed #f4b860;
                border-radius: 12px;
                background-color: #20262d;
            }
            QFrame:hover {
                background-color: #232a32;
                border-color: #5fb3a1;
            }
        """
        self.setStyleSheet(self.normal_style)

    def mousePressEvent(self, event):
        """Handle mouse press to trigger click signal."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter event."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path.endswith(('.tsv', '.txt', '.csv')):
                    event.acceptProposedAction()
                    self.setStyleSheet("""
                        QFrame {
                            border: 3px dashed #7bc96f;
                            border-radius: 12px;
                            background-color: #1f2a22;
                        }
                    """)
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        """Handle drag leave event."""
        self.setStyleSheet(self.normal_style)

    def dropEvent(self, event: QDropEvent):
        """Handle drop event."""
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        valid_files = [f for f in files if f.endswith(('.tsv', '.txt', '.csv'))]

        if valid_files:
            file_path = valid_files[0]
            self.file_dropped.emit(file_path)

            # Animate success
            self.setStyleSheet("""
                QFrame {
                    border: 3px solid #7bc96f;
                    border-radius: 12px;
                    background-color: #243329;
                }
            """)

            # Reset after delay
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(500, lambda: self.setStyleSheet(self.normal_style))

            event.acceptProposedAction()
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Invalid File",
                "Please drop a valid TSV, TXT, or CSV file."
            )
            event.ignore()
            self.setStyleSheet(self.normal_style)


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
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30,30,30,30)

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

        # 2. Input Section
        input_frame = QFrame()
        input_frame.setProperty("class", "Card")
        input_layout = QVBoxLayout(input_frame)

        # Drag & Drop Zone
        self.drop_zone = ClickableDropZone()
        self.drop_zone.setObjectName("DropZone")  # For styling
        self.drop_zone.clicked.connect(self._browse_file)  # Connect click to browse
        self.drop_zone.file_dropped.connect(self.set_input_file)  # Connect drop to handler

        drop_layout = QVBoxLayout()
        drop_icon = QLabel("📁")
        drop_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_icon.setStyleSheet("font-size: 48px; border: none; background: transparent;")

        drop_text = QLabel("Drag & Drop ISBN File Here\nor click anywhere to browse")
        drop_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_text.setStyleSheet("font-size: 14px; color: #f4b860; font-weight: bold; border: none; background: transparent;")

        drop_hint = QLabel("Supports: .tsv, .txt, .csv files")
        drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_hint.setStyleSheet("font-size: 11px; color: #a7a199; border: none; background: transparent;")

        drop_layout.addWidget(drop_icon)
        drop_layout.addWidget(drop_text)
        drop_layout.addWidget(drop_hint)
        drop_layout.setContentsMargins(16, 16, 16, 16)
        drop_layout.setSpacing(6)

        self.drop_zone.setLayout(drop_layout)
        input_layout.addWidget(self.drop_zone)

        # File selection group
        file_group = QGroupBox("Select Input File")
        file_layout = QVBoxLayout()

        # File path display and browse button
        path_layout = QHBoxLayout()
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setPlaceholderText("No file selected...")
        self.file_path_edit.setReadOnly(True)
        self.file_path_edit.setStyleSheet("background-color: #1e2030; color: #cad3f5; border: 1px solid #363a4f; padding: 5px; border-radius: 4px;")

        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.setProperty("class", "SecondaryButton")
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.clicked.connect(self._browse_file)

        self.btn_clear_file = QPushButton("Clear")
        self.btn_clear_file.setProperty("class", "SecondaryButton")
        self.btn_clear_file.setEnabled(False)
        self.btn_clear_file.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_file.setToolTip("Remove selected input file")
        self.btn_clear_file.setAccessibleName("Clear selected file")
        self.btn_clear_file.clicked.connect(self._clear_input)

        self.sample_link = QPushButton("Expected format?")
        self.sample_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sample_link.setStyleSheet("color: #8aadf4; border: none; text-decoration: underline;")
        self.sample_link.setAccessibleName("Show expected file format")
        self.sample_link.clicked.connect(self._show_sample_format)

        path_layout.addWidget(self.file_path_edit)
        path_layout.addWidget(self.btn_clear_file)
        path_layout.addWidget(self.sample_link)
        path_layout.addWidget(self.btn_browse)
        file_layout.addLayout(path_layout)

        file_group.setLayout(file_layout)
        input_layout.addWidget(file_group)

        # File Preview & Info Group (From old InputTab)
        self.preview_group = QGroupBox("File Preview & Information")
        preview_layout = QVBoxLayout(self.preview_group)

        self.info_label = QLabel("No file selected")
        self.info_label.setWordWrap(True)
        self.info_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.info_label.setStyleSheet("color: #cad3f5; font-size: 13px; margin-bottom: 5px;")

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("Select a file to preview its contents...")
        self.preview_text.setMaximumHeight(150)
        self.preview_text.setStyleSheet("background-color: #181926; border: 1px solid #363a4f; border-radius: 4px; padding: 5px;")

        preview_layout.addWidget(self.info_label)
        preview_layout.addWidget(self.preview_text)
        
        input_layout.addWidget(self.preview_group)
        
        layout.addWidget(input_frame)


        # 3. Progress / Stats (Card)
        stats_frame = QFrame()
        stats_frame.setProperty("class", "Card")
        stats_layout = QVBoxLayout(stats_frame)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar { background-color: #181926; height: 12px; border-radius: 6px; }
            QProgressBar::chunk { background-color: #8aadf4; border-radius: 6px; }
        """)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setAccessibleName("Harvest progress")
        
        meta_layout = QHBoxLayout()
        self.lbl_counts = QLabel("0 / 0")
        self.lbl_counts.setStyleSheet("color: #ffffff; font-weight: bold;")
        
        self.lbl_live_target = QLabel("Target: -")
        self.lbl_live_target.setStyleSheet("color: #a5adcb;")
        self.lbl_live_target.setVisible(False) # Hide until running
        
        meta_layout.addWidget(self.lbl_counts)
        meta_layout.addStretch()
        meta_layout.addWidget(self.lbl_live_target)
        
        stats_layout.addLayout(meta_layout)
        stats_layout.addWidget(self.progress_bar)
        
        # Log Output (hidden by default or small)
        self.log_output = QLabel("Ready...")
        self.log_output.setStyleSheet("color: #5b6078; font-size: 11px; margin-top: 5px;")
        self.log_output.setAccessibleName("Harvest status message")
        stats_layout.addWidget(self.log_output)
        
        layout.addWidget(stats_frame)

        # 4. Action Buttons (Bottom)
        action_layout = QHBoxLayout()
        
        start_layout = QVBoxLayout()
        self.btn_start = QPushButton("Start Harvest")
        self.btn_start.setProperty("class", "PrimaryButton")
        self.btn_start.setMinimumHeight(45)
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        
        mod_name = "Cmd" if self._shortcut_modifier == "Meta" else "Ctrl"
        self.btn_start.setToolTip(f"Start harvest ({mod_name}+Enter)")
        self.btn_start.setAccessibleName("Start harvest")
        self.btn_start.clicked.connect(self._on_start_clicked)
        self.btn_start.setEnabled(False)
        
        self.lbl_start_helper = QLabel("Select a valid TSV file to start.")
        self.lbl_start_helper.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_start_helper.setText("Select a valid TSV file to start.")
        self.lbl_start_helper.setStyleSheet("color: #5b6078; font-size: 11px;")
        
        self.btn_pause = QPushButton("Pa&use")
        self.btn_pause.setProperty("class", "SecondaryButton")
        self.btn_pause.setMinimumHeight(45)
        self.btn_pause.setToolTip(f"Pause or resume the harvest")
        self.btn_pause.setAccessibleName("Pause harvest")
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_pause.setEnabled(False)
        
        start_layout.addWidget(self.btn_start)
        start_layout.addWidget(self.lbl_start_helper)
        
        self.btn_stop = QPushButton("&Cancel")
        self.btn_stop.setProperty("class", "DangerButton")
        self.btn_stop.setMinimumHeight(45)
        self.btn_stop.setToolTip(f"Stop running harvest ({mod_name}+.)")
        self.btn_stop.setAccessibleName("Stop harvest")
        self.btn_stop.clicked.connect(self._stop_harvest)
        self.btn_stop.setEnabled(False)
        
        action_layout.addLayout(start_layout, stretch=3)
        action_layout.addWidget(self.btn_pause, stretch=1)
        action_layout.addWidget(self.btn_stop, stretch=1)
        
        layout.addLayout(action_layout)

        layout.addStretch()

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

            total_nonempty = 0
            candidate_rows = 0
            valid_rows = 0
            invalid_rows = 0
            seen = set()
            unique_valid = 0
            
            with open(path, 'r', encoding='utf-8-sig') as f:
                first_data_row_seen = False
                for i, line in enumerate(f, start=1):
                    raw_line = line.strip()
                    if not raw_line: continue
                    total_nonempty += 1
                    
                    # Split TSV/CSV - take first column
                    if '\t' in raw_line:
                        raw_isbn = raw_line.split('\t')[0].strip()
                    elif ',' in raw_line and path_obj.suffix.lower() == '.csv':
                        raw_isbn = raw_line.split(',')[0].strip()
                    else:
                        raw_isbn = raw_line
                    
                    if not raw_isbn: continue
                    if raw_isbn.startswith('#'): continue

                    if not first_data_row_seen and raw_isbn.lower() in {'isbn', 'isbns', 'isbn13', 'isbn10'}:
                        first_data_row_seen = True
                        continue
                    
                    first_data_row_seen = True
                    candidate_rows += 1

                    normalized = normalize_isbn(raw_isbn)
                    if not normalized:
                        invalid_rows += 1
                        continue
                    
                    valid_rows += 1
                    if normalized not in seen:
                        seen.add(normalized)
                        unique_valid += 1
                    
                    if sampled and i >= INFO_SAMPLE_MAX_LINES:
                        break
            
            duplicate_valid_rows = max(0, valid_rows - unique_valid)
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
            
            info_text = (
                f"File: {path_obj.name}\n"
                f"Size: {path_obj.stat().st_size / 1024:.2f} KB\n"
                f"Valid ISBNs (unique): {unique_valid}\n"
                f"Valid ISBN rows: {valid_rows}\n"
                f"Duplicate valid rows: {duplicate_valid_rows}\n"
                f"Invalid ISBN rows: {invalid_rows}"
                f"{sample_note}"
            )
            
            # Labels and Preview
            self.lbl_counts.setText(f"Loaded: {unique_valid} ISBNs")
            self.log_output.setText(f"Ready to harvest {unique_valid} unique ISBNs.")
            
            self.info_label.setText(info_text)
            self.info_label.setStyleSheet("color: #cad3f5; font-size: 13px; margin-bottom: 5px;")
            self.file_path_edit.setText(str(path_obj))
            self._load_file_preview()
            
            self._check_start_conditions(unique_valid)

        except Exception as e:
            self._set_invalid_state(path_obj.name, f"Error reading file: {e}")

    def _check_start_conditions(self, isbn_count=None):
        """Enable start button only if file is valid AND targets are selected."""
        # Get ISBN count if not passed (parse from label or store in member)
        # For simplicity, if input_file is set, we assume it has valid ISBNs (checked in set_input_file)
        if not self.input_file:
            self.btn_start.setEnabled(False)
            self.lbl_start_helper.setText("Select a valid TSV file to start.")
            return

        # Check targets
        targets = self._targets_getter() if self._targets_getter else []
        selected_targets = [t for t in targets if t.get("selected", True)]
        if not selected_targets:
            self.btn_start.setEnabled(False)
            self.lbl_start_helper.setText("Select at least one target in Targets tab.")
            return

        # Valid
        count_text = self.lbl_counts.text()
        count = count_text.replace("Loaded: ", "").replace(" ISBNs", "") if "Loaded" in count_text else "?"
        if isbn_count is not None: count = str(isbn_count)
        
        self.btn_start.setText(f"Start Harvest ({count} ISBNs)")
        self.btn_start.setEnabled(True)
        self.lbl_start_helper.setText("Ready to start.")

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
        self.info_label.setText("No file selected")
        self.info_label.setStyleSheet("color: #cad3f5; font-size: 13px; margin-bottom: 5px;")
        self.preview_text.clear()
        
        # Reset clear button
        self.btn_clear_file.setEnabled(False)
        self.btn_clear_file.setProperty("class", "SecondaryButton")
        self.btn_clear_file.style().unpolish(self.btn_clear_file)
        self.btn_clear_file.style().polish(self.btn_clear_file)
        
        self.lbl_counts.setText("Loaded: 0 ISBNs")
        self.log_output.setText("Ready...")
        
        self.btn_start.setText("Start Harvest")
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("Pa&use")
        self.lbl_start_helper.setText("Select a valid TSV file to start.")
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("Pa&use")
        self.lbl_start_helper.setText("Select a valid TSV file to start.")

    def _set_invalid_state(self, filename, error_msg):
        """Show error state."""
        self.input_file = None
        self.file_path_edit.setText(filename)
        self.info_label.setText(error_msg)
        self.info_label.setStyleSheet("color: #ed8796; font-size: 13px; margin-bottom: 5px;") # Red
        self.preview_text.clear()
        
        # Enable clear button but keep it grey for invalid state, or let's make it danger too so they can clear it out.
        self.btn_clear_file.setEnabled(True)
        self.btn_clear_file.setProperty("class", "DangerButton")
        self.btn_clear_file.style().unpolish(self.btn_clear_file)
        self.btn_clear_file.style().polish(self.btn_clear_file)
        
        self.lbl_counts.setText("Loaded: 0 ISBNs")
        self.log_output.setText(error_msg)
        
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("Pa&use")
        self.lbl_start_helper.setText("Fix input errors to start.")

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
        
        self.is_running = True
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_pause.setText("Pa&use")
        self.btn_stop.setEnabled(True)
        self.status_pill.setText("RUNNING")
        self.status_pill.setStyleSheet("background-color: #8aadf4; color: #1e2030;")
        
        self.harvest_started.emit()

    def _stop_harvest(self):
        if self.worker:
            self.worker.stop()
            self.status_pill.setText("CANCELLING...")
            self.log_output.setText("Cancelling harvest (waiting for current thread)...")
            self.btn_stop.setEnabled(False) # Prevent double click
            self.btn_pause.setEnabled(False)

    def _toggle_pause(self):
        if self.worker:
            self.worker.toggle_pause()
            if self.worker._pause_requested:
                self.btn_pause.setText("Res&ume")
                self.status_pill.setText("PAUSED")
                self.status_pill.setStyleSheet("background-color: #f38ba8; color: #1e2030;")
                self.log_output.setText("Harvest paused. Click Resume to continue.")
            else:
                self.btn_pause.setText("Pa&use")
                self.status_pill.setText("RUNNING")
                self.status_pill.setStyleSheet("background-color: #8aadf4; color: #1e2030;")
                self.log_output.setText("Harvest resumed...")

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
        # Only show target when running
        self.lbl_live_target.setVisible(True)
        self.lbl_live_target.setText(f"Target: {source or '-'}")
        self.log_output.setText(f"{isbn}: {msg}")
        self.progress_updated.emit(isbn, status, source, msg)

    def _on_stats(self, stats):
        total = stats.get('total', 0)
        processed = stats.get('found', 0) + stats.get('failed', 0) + stats.get('cached', 0) + stats.get('skipped', 0)
        self.processed_count = processed
        self.total_count = total
        
        self.lbl_counts.setText(f"{processed} / {total}")
        self.progress_bar.setFormat(f"{processed}/{total} (%p%)" if total > 0 else "0/0 (0%)")
        if total > 0:
            self.progress_bar.setValue(int(processed/total*100))

    def _on_status(self, msg):
        self.log_output.setText(msg)

    def _on_complete(self, success, stats):
        self.is_running = False
        self.btn_stop.setEnabled(False)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("Pa&use")
        self._check_start_conditions()
        
        final_status = "COMPLETED" if success else "CANCELLED"
        color = "#a6da95" if success else "#ed8796" # Green or Red
        
        if not success:
            # Reset UI progress and labels upon cancellation
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("0/0 (0%)")
            self.lbl_counts.setText("0 / 0")
            self.lbl_live_target.setVisible(False)
            self.log_output.setText("Ready...")
        
        self.status_pill.setText(final_status)
        self.status_pill.setStyleSheet(f"background-color: #363a4f; color: {color};")
        
        self.harvest_finished.emit(success, stats)

    def set_advanced_mode(self, val):
        pass

    def stop_harvest(self):
        """Public method used by window close handlers."""
        self._stop_harvest()
