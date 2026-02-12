"""
Module: harvest_tab_v2.py
V2 Harvest Tab: Functional Core with Professional UI.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QTextEdit, QProgressBar,
    QCheckBox, QSpinBox, QFrame, QGridLayout, QMessageBox, QFileDialog
)
from datetime import datetime
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QMimeData, QUrl, QSize
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QCursor
from pathlib import Path
import csv
import sys
# Add src to path for utils import
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.isbn_validator import normalize_isbn

from .icons import get_icon, SVG_HARVEST, SVG_INPUT, SVG_ACTIVITY
# from .harvest_tab import HarvestWorker  # REMOVED: Using internal HarvestWorkerV2 for separation

# Add imports for Worker
from PyQt6.QtCore import QThread
from harvester.run_harvest import run_harvest
from harvester.targets import create_target_from_config
from database import DatabaseManager
from datetime import datetime
from utils import messages

class HarvestWorkerV2(QThread):
    """Background worker thread for harvest operations (V2)."""

    progress_update = pyqtSignal(str, str, str, str)  # isbn, status, source, message
    harvest_complete = pyqtSignal(bool, dict)  # success, statistics
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
                    return

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

            print(f"DEBUG: HarvestWorkerV2 calling run_harvest with db_path='data/lccn_harvester.sqlite3' retry={retry_days}")

            summary = run_harvest(
                input_path=Path(self.input_file),
                dry_run=False,
                db_path="data/lccn_harvester.sqlite3",
                retry_days=retry_days,
                targets=targets,
                bypass_retry_isbns=self.bypass_retry_isbns,
                progress_cb=progress_callback,
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

            target_instances = []
            for target_config in sorted_targets:
                try:
                    target = create_target_from_config(target_config)
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

class DropZone(QFrame):
    """Clean blue dashed drop zone for file input."""
    file_dropped = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("DragZone") # Targeted by styles_v2.py
        self.setAcceptDrops(True)
        self.setMinimumHeight(100)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        icon = QLabel()
        icon.setPixmap(get_icon(SVG_INPUT, "#8aadf4").pixmap(32, 32))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_text = QLabel("Drag & Drop Input File Here\n(or click 'Browse')")
        self.lbl_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_text.setStyleSheet("color: #8aadf4; font-weight: 600;")
        
        layout.addWidget(icon)
        layout.addWidget(self.lbl_text)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("background-color: rgba(138, 173, 244, 0.15); border: 2px dashed #b7bdf8;")

    def dragLeaveEvent(self, event):
        self.setObjectName("DragZone") # Reset style
        self.setStyleSheet("") # Clear override

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0]
            path = url.toLocalFile()
            if path:
                self.file_dropped.emit(path)
        self.setObjectName("DragZone")
        self.setStyleSheet("")


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
        
        self._setup_ui()

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
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.status_pill)
        layout.addLayout(header_layout)

        # 2. Input Section (Card)
        input_frame = QFrame()
        input_frame.setProperty("class", "Card")
        input_layout = QVBoxLayout(input_frame)
        
        self.drop_zone = DropZone()
        self.drop_zone.file_dropped.connect(self.set_input_file)
        
        # File Pill (Hidden by default)
        self.file_pill = QFrame()
        self.file_pill.setObjectName("FilePill")
        self.file_pill.setStyleSheet("""
            #FilePill { background-color: #363a4f; border-radius: 8px; border: 1px solid #494d64; }
        """)
        self.file_pill.setVisible(False)
        pill_layout = QHBoxLayout(self.file_pill)
        pill_layout.setContentsMargins(10, 5, 10, 5)
        
        icon_label = QLabel("📄")
        self.lbl_pill_name = QLabel("filename.tsv")
        self.lbl_pill_name.setStyleSheet("color: #cad3f5; font-weight: bold;")
        self.lbl_pill_info = QLabel("(0 KB)")
        self.lbl_pill_info.setStyleSheet("color: #a5adcb;")
        
        btn_clear_file = QPushButton("✕")
        btn_clear_file.setFixedSize(20, 20)
        btn_clear_file.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear_file.setStyleSheet("color: #ed8796; border: none; font-weight: bold;")
        btn_clear_file.clicked.connect(self._clear_input)
        
        pill_layout.addWidget(icon_label)
        pill_layout.addWidget(self.lbl_pill_name)
        pill_layout.addWidget(self.lbl_pill_info)
        pill_layout.addStretch()
        pill_layout.addWidget(btn_clear_file)
        
        # Validation Badge & Browse Area
        controls_layout = QHBoxLayout()
        
        self.badge_validation = QLabel("")
        self.badge_validation.setVisible(False)
        
        btn_browse = QPushButton("Browse...")
        btn_browse.setProperty("class", "SecondaryButton")
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse.clicked.connect(self._browse_file)
        
        sample_link = QPushButton("Expected format?")
        sample_link.setCursor(Qt.CursorShape.PointingHandCursor)
        sample_link.setStyleSheet("color: #8aadf4; border: none; text-decoration: underline;")
        sample_link.clicked.connect(self._show_sample_format)
        
        controls_layout.addWidget(self.badge_validation)
        controls_layout.addStretch()
        controls_layout.addWidget(sample_link)
        controls_layout.addWidget(btn_browse)
        
        input_layout.addWidget(self.drop_zone)
        input_layout.addWidget(self.file_pill)
        input_layout.addLayout(controls_layout)
        
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
        self.progress_bar.setTextVisible(False)
        
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
        stats_layout.addWidget(self.log_output)
        
        layout.addWidget(stats_frame)

        # 4. Action Buttons (Bottom)
        action_layout = QHBoxLayout()
        
        start_layout = QVBoxLayout()
        self.btn_start = QPushButton("Start Harvest")
        self.btn_start.setProperty("class", "PrimaryButton")
        self.btn_start.setMinimumHeight(45)
        self.btn_start.setIcon(get_icon(SVG_HARVEST, "#1e2030"))
        self.btn_start.clicked.connect(self._on_start_clicked)
        self.btn_start.setEnabled(False)
        
        self.lbl_start_helper = QLabel("Select a valid TSV file to start.")
        self.lbl_start_helper.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_start_helper.setStyleSheet("color: #5b6078; font-size: 11px;")
        
        start_layout.addWidget(self.btn_start)
        start_layout.addWidget(self.lbl_start_helper)
        
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setProperty("class", "DangerButton")
        self.btn_stop.setMinimumHeight(45)
        self.btn_stop.clicked.connect(self._stop_harvest)
        self.btn_stop.setEnabled(False)
        
        action_layout.addLayout(start_layout, stretch=3)
        action_layout.addWidget(self.btn_stop, stretch=1)
        
        layout.addLayout(action_layout)

        layout.addStretch()

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
            line_count = 0
            valid_count = 0
            invalid_count = 0
            
            with open(path, 'r', encoding='utf-8-sig') as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped: continue
                    
                    # Check if header
                    if line_count == 0 and stripped.lower().startswith('isbn'):
                        line_count += 1
                        continue
                    
                    # Split TSV/CSV - take first column
                    # For CSV, splitting by comma might differ, but assuming TSV-like behavior for now or simple split
                    if '\t' in stripped:
                        raw_isbn = stripped.split('\t')[0]
                    elif ',' in stripped and path_obj.suffix.lower() == '.csv':
                        raw_isbn = stripped.split(',')[0]
                    else:
                        raw_isbn = stripped

                    # Validate
                    if normalize_isbn(raw_isbn):
                        valid_count += 1
                    else:
                        invalid_count += 1
                    
                    line_count += 1
            
            print(f"DEBUG: Validation Results - Valid: {valid_count}, Invalid: {invalid_count}, Total Lines: {line_count}")

            if valid_count == 0:
                 msg = "File contains no valid ISBNs"
                 if invalid_count > 0: msg += f" ({invalid_count} invalid lines)"
                 self._set_invalid_state(path_obj.name, msg)
                 return

            # Success State
            self.input_file = path
            
            # Update Pill
            self.drop_zone.setVisible(False)
            self.file_pill.setVisible(True)
            self.lbl_pill_name.setText(path_obj.name)
            self.lbl_pill_info.setText(f"({size_kb:.1f} KB • {valid_count} ISBNs)")
            
            # Badge
            if invalid_count > 0:
                self.badge_validation.setText(f"⚠️ {valid_count} valid ISBNs ({invalid_count} invalid)")
                self.badge_validation.setStyleSheet("color: #eed49f; font-weight: bold;") # Yellow
            else:
                self.badge_validation.setText("✅ Valid input")
                self.badge_validation.setStyleSheet("color: #a6da95; font-weight: bold;") # Green
            self.badge_validation.setVisible(True)

            # Labels
            self.lbl_counts.setText(f"Loaded: {valid_count} ISBNs")
            self.log_output.setText(f"Ready to harvest {valid_count} ISBNs.")
            
            self._check_start_conditions(valid_count)

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

    def _clear_input(self):
        """Reset input state."""
        self.input_file = None
        self.drop_zone.setVisible(True)
        self.file_pill.setVisible(False)
        self.badge_validation.setVisible(False)
        
        self.lbl_counts.setText("Loaded: 0 ISBNs")
        self.log_output.setText("Ready...")
        
        self.btn_start.setText("Start Harvest")
        self.btn_start.setEnabled(False)
        self.lbl_start_helper.setText("Select a valid TSV file to start.")

    def _set_invalid_state(self, filename, error_msg):
        """Show error state."""
        self.input_file = None
        
        # Show File Pill with RED text
        self.drop_zone.setVisible(False)
        self.file_pill.setVisible(True)
        self.lbl_pill_name.setText(filename)
        self.lbl_pill_name.setStyleSheet("color: #ed8796; font-weight: bold;") # Red pill text
        self.lbl_pill_info.setText("(Error)")
        
        self.badge_validation.setText(f"❌ {error_msg}")
        self.badge_validation.setStyleSheet("color: #ed8796; font-weight: bold;") # Red
        self.badge_validation.setVisible(True)
        
        self.lbl_counts.setText("Loaded: 0 ISBNs")
        self.log_output.setText(error_msg)
        
        self.btn_start.setEnabled(False)
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
        f, _ = QFileDialog.getOpenFileName(self, "Select Input", "", "Input Files (*.txt *.tsv *.csv)")
        if f:
            self.set_input_file(f)

    def _on_start_clicked(self):
        """Prepare and start harvest using external config."""
        if not self.input_file:
            print("DEBUG: _on_start_clicked called but no input_file.")
            return

        print(f"DEBUG: _on_start_clicked with input: {self.input_file}")
        
        # 1. Get Config
        config = self._config_getter() if self._config_getter else {"retry_days": 7}
        
        # 2. Get Targets
        targets = self._targets_getter() if self._targets_getter else []
        selected_targets = [t for t in targets if t.get("selected", True)]
        if not selected_targets:
            QMessageBox.warning(self, "No Targets", "Please select at least one target in the Targets tab.")
            return

        # 3. Start Worker
        print(f"DEBUG: Starting worker with {len(selected_targets)} selected targets.")
        self._start_worker(config, targets)

    def _start_worker(self, config, targets):
        if self.worker and self.worker.isRunning():
            return

        self.worker = HarvestWorkerV2(self.input_file, config, targets)
        self.worker.progress_update.connect(self._on_progress)
        self.worker.harvest_complete.connect(self._on_complete)
        self.worker.stats_update.connect(self._on_stats)
        self.worker.status_message.connect(self._on_status)
        self.worker.milestone_reached.connect(self.milestone_reached.emit)
        
        self.worker.start()
        
        self.is_running = True
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.status_pill.setText("RUNNING")
        self.status_pill.setStyleSheet("background-color: #8aadf4; color: #1e2030;")
        
        self.harvest_started.emit()

    def _stop_harvest(self):
        if self.worker:
            self.worker.stop()
            self.status_pill.setText("STOPPING...")
            self.log_output.setText("Stopping harvest (waiting for current thread)...")
            self.btn_stop.setEnabled(False) # Prevent double click

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
        if total > 0:
            self.progress_bar.setValue(int(processed/total*100))

    def _on_status(self, msg):
        self.log_output.setText(msg)

    def _on_complete(self, success, stats):
        self.is_running = False
        self._check_start_conditions()
        self.btn_stop.setEnabled(False)
        
        final_status = "COMPLETED" if success else "STOPPED"
        color = "#a6da95" if success else "#ed8796" # Green or Red
        
        self.status_pill.setText(final_status)
        self.status_pill.setStyleSheet(f"background-color: #363a4f; color: {color};")
        
        self.harvest_finished.emit(success, stats)

    def set_advanced_mode(self, val):
        pass

    def stop_harvest(self):
        """Public method used by window close handlers."""
        self._stop_harvest()
