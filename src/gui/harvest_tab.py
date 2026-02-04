"""
Module: harvest_tab.py
Harvest execution and progress tracking tab with threading support.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QTextEdit, QProgressBar,
    QCheckBox, QSpinBox, QFrame, QGridLayout, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
import sys

# Add src to path for database import
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import DatabaseManager
from harvester.run_harvest import run_harvest, read_isbns_from_tsv
from harvester.targets import create_target_from_config
from utils.isbn_validator import normalize_isbn
from utils import messages

from .progress_dialog import ProgressDialog


class HarvestWorker(QThread):
    """Background worker thread for harvest operations."""

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
            self.started.emit()
            self.status_message.emit(messages.HarvestMessages.starting)

            # Read and validate ISBNs
            isbns = self._read_and_validate_isbns()
            total = len(isbns)

            if total == 0:
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

            # Run the harvest pipeline
            retry_days = self.config.get("retry_days", 7)

            summary = run_harvest(
                input_path=Path(self.input_file),
                dry_run=False,
                db_path="data/lccn_harvester.sqlite3",
                retry_days=retry_days,
                targets=targets,
                bypass_retry_isbns=self.bypass_retry_isbns,
                progress_cb=progress_callback,
            )

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

        except Exception as e:
            import traceback
            error_msg = f"Error: {str(e)}\n{traceback.format_exc()}"
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
            with open(self.input_file, "r", encoding="utf-8-sig") as f:
                valid_isbns = []
                invalid_count = 0

                for line in f:
                    isbn = line.strip().split("\t")[0]  # First column
                    if not isbn or isbn.lower().startswith("isbn"):
                        continue  # Skip empty lines and header

                    normalized = normalize_isbn(isbn)
                    if normalized:
                        valid_isbns.append(normalized)
                    else:
                        invalid_count += 1
                        self.status_message.emit(messages.HarvestMessages.invalid_isbn_skipped.format(isbn=isbn))

                if invalid_count > 0:
                    self.status_message.emit(messages.HarvestMessages.invalid_isbns_count.format(count=invalid_count))

                return valid_isbns
        except Exception as e:
            self.status_message.emit(messages.HarvestMessages.error_reading_file.format(error=str(e)))
            return []

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


class HarvestTab(QWidget):
    harvest_started = pyqtSignal()
    harvest_finished = pyqtSignal(bool, dict)  # success, statistics
    status_message = pyqtSignal(str)
    milestone_reached = pyqtSignal(str, int)  # milestone_type, value

    def __init__(self):
        super().__init__()
        self.is_running = False
        self.input_file = None
        self.worker = None
        self.progress_dialog = None
        self.advanced_mode = False
        self.start_time = None
        self.processed_count = 0
        self.total_count = 0
        self._warned_no_input = False

        # Speed tracking
        self.speed_timer = QTimer()
        self.speed_timer.timeout.connect(self._update_speed)
        self.last_processed = 0
        self.current_speed = 0

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(18)

        # Header with status
        header_layout = QHBoxLayout()

        title_label = QLabel("🚀 Harvest Execution")
        title_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #c2d07f;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.status_badge = QLabel("● Ready")
        self.status_badge.setStyleSheet(
            "color: #a7a59b; font-size: 14px; font-weight: bold; padding: 6px 12px; "
            "background-color: #242521; border-radius: 12px;"
        )
        header_layout.addWidget(self.status_badge)

        layout.addLayout(header_layout)

        # Live activity panel
        live_group = QGroupBox("Live Activity")
        live_layout = QVBoxLayout()

        self.current_isbn_label = QLabel("Current ISBN: —")
        self.current_isbn_label.setStyleSheet("color: #e8e6df; font-size: 13px;")
        live_layout.addWidget(self.current_isbn_label)

        self.current_status_label = QLabel("Status: Idle")
        self.current_status_label.setStyleSheet("color: #a7a59b; font-size: 12px;")
        live_layout.addWidget(self.current_status_label)

        self.current_target_label = QLabel("Target: —")
        self.current_target_label.setStyleSheet("color: #a7a59b; font-size: 12px;")
        live_layout.addWidget(self.current_target_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        live_layout.addWidget(self.progress_bar)

        live_meta = QHBoxLayout()
        self.success_rate_label = QLabel("Success Rate: 0%")
        self.success_rate_label.setStyleSheet("color: #a9d48f; font-size: 12px;")
        live_meta.addWidget(self.success_rate_label)
        live_meta.addStretch()
        self.processed_meta_label = QLabel("Processed: 0/0")
        self.processed_meta_label.setStyleSheet("color: #a7a59b; font-size: 12px;")
        live_meta.addWidget(self.processed_meta_label)
        live_layout.addLayout(live_meta)

        self.event_chip_wrap = QFrame()
        self.event_chip_wrap.setStyleSheet("background: transparent;")
        self.event_chip_layout = QHBoxLayout(self.event_chip_wrap)
        self.event_chip_layout.setContentsMargins(0, 0, 0, 0)
        self.event_chip_layout.setSpacing(6)
        live_layout.addWidget(self.event_chip_wrap)

        live_group.setLayout(live_layout)
        layout.addWidget(live_group)

        # Stats section
        stats_group = QGroupBox("Harvest Statistics")
        stats_layout = QGridLayout()
        stats_layout.setSpacing(15)

        def create_stat_display(label_text):
            container = QVBoxLayout()
            label = QLabel(label_text)
            label.setStyleSheet("color: #a7a59b; font-size: 11px;")
            value = QLabel("0")
            value.setStyleSheet("color: #e8e6df; font-size: 28px; font-weight: bold;")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            container.addWidget(label)
            container.addWidget(value)
            return container, value

        total_layout, self.total_value = create_stat_display("Total ISBNs")
        stats_layout.addLayout(total_layout, 0, 0)

        processed_layout, self.processed_value = create_stat_display("Processed")
        stats_layout.addLayout(processed_layout, 0, 1)

        found_layout, self.found_value = create_stat_display("✓ Found")
        stats_layout.addLayout(found_layout, 0, 2)

        failed_layout, self.failed_value = create_stat_display("✗ Failed")
        stats_layout.addLayout(failed_layout, 0, 3)

        progress_layout, self.progress_value = create_stat_display("Progress %")
        stats_layout.addLayout(progress_layout, 1, 0)

        time_layout, self.time_label = create_stat_display("Elapsed Time")
        self.time_label.setText("00:00:00")
        self.time_label.setStyleSheet("color: #e8e6df; font-size: 16px; font-weight: bold;")
        stats_layout.addLayout(time_layout, 1, 1)

        speed_layout, self.speed_label = create_stat_display("Speed (ISBN/s)")
        self.speed_label.setText("0")
        self.speed_label.setStyleSheet("color: #e8e6df; font-size: 16px; font-weight: bold;")
        stats_layout.addLayout(speed_layout, 1, 2)

        eta_layout, self.eta_label = create_stat_display("ETA")
        self.eta_label.setText("--:--:--")
        self.eta_label.setStyleSheet("color: #e8e6df; font-size: 16px; font-weight: bold;")
        stats_layout.addLayout(eta_layout, 1, 3)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # Control buttons
        control_group = QGroupBox("Controls")
        control_layout = QVBoxLayout()

        buttons_layout = QHBoxLayout()

        self.start_button = QPushButton("Start Harvest")
        self.start_button.clicked.connect(self._start_harvest)
        self.start_button.setEnabled(False)
        self.start_button.setToolTip("Select an input file first")
        self.start_button.setObjectName("PrimaryButton")

        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self._stop_harvest)
        self.stop_button.setEnabled(False)

        self.detailed_progress_button = QPushButton("Show Detailed Progress...")
        self.detailed_progress_button.clicked.connect(self._show_progress_dialog)
        self.detailed_progress_button.setEnabled(False)

        buttons_layout.addWidget(self.start_button)
        buttons_layout.addWidget(self.stop_button)
        buttons_layout.addWidget(self.detailed_progress_button)
        buttons_layout.addStretch()

        control_layout.addLayout(buttons_layout)

        # Advanced options (collapsed by default)
        self.advanced_group = QGroupBox("Advanced Options")
        self.advanced_group.setCheckable(True)
        self.advanced_group.setChecked(False)
        self.advanced_group.setVisible(False)  # Hidden until advanced mode

        advanced_layout = QVBoxLayout()

        parallel_layout = QHBoxLayout()
        parallel_label = QLabel("Parallel Workers:")
        parallel_label.setStyleSheet("color: #e8e6df;")
        parallel_layout.addWidget(parallel_label)
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 10)
        self.parallel_spin.setValue(1)
        self.parallel_spin.setToolTip("Number of ISBNs to process in parallel")
        self.parallel_spin.setStyleSheet("color: #e8e6df;")
        parallel_layout.addWidget(self.parallel_spin)
        parallel_layout.addStretch()
        advanced_layout.addLayout(parallel_layout)

        self.auto_export_check = QCheckBox("Auto-export results after harvest")
        self.auto_export_check.setChecked(True)
        self.auto_export_check.setStyleSheet("color: #e8e6df;")
        advanced_layout.addWidget(self.auto_export_check)

        self.detailed_logging_check = QCheckBox("Enable detailed logging")
        self.detailed_logging_check.setChecked(False)
        self.detailed_logging_check.setStyleSheet("color: #e8e6df;")
        advanced_layout.addWidget(self.detailed_logging_check)

        self.advanced_group.setLayout(advanced_layout)
        control_layout.addWidget(self.advanced_group)

        control_group.setLayout(control_layout)
        layout.addWidget(control_group)

        # Log output
        log_group = QGroupBox("Harvest Log")
        log_layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("Harvest log will appear here...")
        self.log_text.setStyleSheet(
            "QTextEdit { color: #cfe3c0; background-color: #171716; border: 1px solid #2d2e2b; }"
        )

        log_layout.addWidget(self.log_text)

        # Log controls
        log_controls_layout = QHBoxLayout()

        self.clear_log_button = QPushButton("Clear Log")
        self.clear_log_button.clicked.connect(self._clear_log)

        self.save_log_button = QPushButton("Save Log...")
        self.save_log_button.clicked.connect(self._save_log)

        log_controls_layout.addWidget(self.clear_log_button)
        log_controls_layout.addWidget(self.save_log_button)
        log_controls_layout.addStretch()

        log_layout.addLayout(log_controls_layout)

        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        self.setLayout(layout)
        self._pulse_timers = {}

    def set_advanced_mode(self, enabled):
        """Enable/disable advanced mode features."""
        self.advanced_mode = enabled
        self.advanced_group.setVisible(enabled)

        if enabled:
            self._log("Advanced mode enabled - additional options available")

    def set_input_file(self, file_path):
        """Set the input file for harvesting."""
        self.input_file = file_path
        if file_path:
            self.start_button.setEnabled(True)
            self.start_button.setToolTip("")
            self._log(f"Input file set: {Path(file_path).name}")

    def _start_harvest(self):
        """Start the harvest operation."""
        if not self.input_file:
            QMessageBox.warning(
                self,
                messages.GuiMessages.err_title_no_input,
                messages.GuiMessages.err_body_no_input,
            )
            self._log(messages.GuiMessages.err_body_no_input)
            return

        # Get configuration from parent tabs
        config = self._get_config()
        targets = self._get_targets()
        advanced_settings = self._get_advanced_settings() if self.advanced_mode else {}
        bypass_retry_isbns = self._check_recent_failed_isbns(config.get("retry_days", 7))

        if bypass_retry_isbns is None:
            self._log("Harvest cancelled by user")
            return
        if bypass_retry_isbns:
            self._log(f"Bypassing retry delay for {len(bypass_retry_isbns)} ISBN(s)")

        # Create and start worker thread
        self.worker = HarvestWorker(
            self.input_file,
            config,
            targets,
            advanced_settings,
            bypass_retry_isbns=bypass_retry_isbns,
        )
        self.worker.progress_update.connect(self._on_progress_update)
        self.worker.harvest_complete.connect(self._on_harvest_complete)
        self.worker.status_message.connect(self._on_status_message)
        self.worker.started.connect(self._on_harvest_started)
        self.worker.milestone_reached.connect(self.milestone_reached.emit)  # Forward to main window
        self.worker.stats_update.connect(self._update_stats)  # Update animated stats in real-time

        self.worker.start()

        # Update UI state
        self.is_running = True
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.detailed_progress_button.setEnabled(True)

        # Update status badge
        self.status_badge.setText("● Running")
        self.status_badge.setStyleSheet(
            "color: #7bc96f; font-size: 14px; font-weight: bold; padding: 6px 12px; "
            "background-color: #1f2a22; border-radius: 12px;"
        )

        # Start timers
        self.start_time = time.time()
        self.speed_timer.start(1000)  # Update every second

        # Create progress dialog if advanced mode
        if self.advanced_mode:
            self._create_progress_dialog()

        self._log("Harvest started")
        self.harvest_started.emit()
        self.status_message.emit("Harvest started")

    def _check_recent_failed_isbns(self, retry_days):
        """Warn if ISBNs were attempted recently and allow bypass."""
        if not self.input_file or retry_days <= 0:
            return set()

        try:
            db = DatabaseManager()
            db.init_db()
            isbns = read_isbns_from_tsv(Path(self.input_file))
        except Exception as e:
            self._log(f"Warning: could not check recent failures - {e}")
            return set()

        recent = []
        for isbn in isbns:
            if db.should_skip_retry(isbn, retry_days=retry_days):
                att = db.get_attempted(isbn)
                recent.append((isbn, att))

        if not recent:
            return set()

        details = []
        for isbn, att in recent[:12]:
            last_attempted = att.last_attempted if att else None
            last_error = att.last_error if att else None
            if last_attempted:
                try:
                    last_dt = datetime.fromisoformat(last_attempted)
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                    next_dt = last_dt + timedelta(days=retry_days)
                    next_str = next_dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
                    last_str = last_dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    next_str = "Unknown"
                    last_str = last_attempted
            else:
                next_str = "Unknown"
                last_str = "Unknown"

            tail = f" | last: {last_str} | next: {next_str}"
            if last_error:
                tail += f" | error: {last_error}"
            details.append(f"{isbn}{tail}")

        if len(recent) > 12:
            details.append(f"... and {len(recent) - 12} more")

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Recent Failed ISBNs")
        msg.setText(
            f"{len(recent)} ISBN(s) were attempted within the last {retry_days} day(s)."
        )
        msg.setInformativeText(
            "These have not surpassed the expected retry date. "
            "You can skip them for now or bypass the delay and retry immediately."
        )
        msg.setDetailedText("\n".join(details))

        skip_btn = msg.addButton("Skip for now", QMessageBox.ButtonRole.AcceptRole)
        bypass_btn = msg.addButton("Bypass and retry", QMessageBox.ButtonRole.ActionRole)
        cancel_btn = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(skip_btn)

        msg.exec()
        clicked = msg.clickedButton()
        if clicked == cancel_btn:
            return None
        if clicked == bypass_btn:
            return {isbn for isbn, _ in recent}
        return set()

    def _stop_harvest(self):
        """Stop the harvest operation."""
        if self.worker:
            self._log("Stopping harvest...")
            self.worker.stop()

    def stop_harvest(self):
        """Public method to stop harvest (called from main window)."""
        self._stop_harvest()

    def _create_progress_dialog(self):
        """Create and show progress dialog."""
        self.progress_dialog = ProgressDialog(self, self.advanced_mode)
        self.progress_dialog.cancel_requested.connect(self._stop_harvest)
        self.progress_dialog.pause_requested.connect(self._toggle_pause)

        # Read ISBN count
        try:
            with open(self.input_file, "r", encoding="utf-8-sig") as f:
                lines = [line.strip() for line in f if line.strip()]
                if lines and lines[0].lower().startswith("isbn"):
                    lines = lines[1:]
                self.progress_dialog.start_harvest(len(lines))
        except Exception:
            pass

        self.progress_dialog.show()

    def _show_progress_dialog(self):
        """Show the progress dialog."""
        if not self.progress_dialog and self.is_running:
            self._create_progress_dialog()
        elif self.progress_dialog:
            self.progress_dialog.show()
            self.progress_dialog.raise_()

    def _toggle_pause(self):
        """Toggle pause state of harvest."""
        if self.worker:
            self.worker.toggle_pause()

    def _on_harvest_started(self):
        """Handle harvest started."""
        self.processed_count = 0
        self.total_count = 0
        self.last_processed = 0
        self.current_speed = 0
        self.progress_bar.setValue(0)
        self.current_isbn_label.setText("Current ISBN: —")
        self.current_status_label.setText("Status: Running")
        self.current_target_label.setText("Target: —")
        self.success_rate_label.setText("Success Rate: 0%")
        self.processed_meta_label.setText("Processed: 0/0")

    def _on_progress_update(self, isbn, status, source, message):
        """Handle progress update from worker."""
        if self.progress_dialog:
            self.progress_dialog.update_progress(isbn, status, source, message)

        self.processed_count += 1

        self.current_isbn_label.setText(f"Current ISBN: {isbn}")
        status_text = status.capitalize()
        if source:
            status_text += f" • {source}"
        self.current_status_label.setText(f"Status: {status_text}")
        if source:
            self.current_target_label.setText(f"Target: {source}")

        self._add_event_chip(status, source, isbn)

        self._log(f"{isbn}: {status}" + (f" - {source}" if source else ""))

    def _on_harvest_complete(self, success, statistics):
        """Handle harvest completion."""
        self.is_running = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.detailed_progress_button.setEnabled(False)

        self.speed_timer.stop()

        self._update_stats(statistics)

        if success:
            self.status_badge.setText("● Completed")
            self.status_badge.setStyleSheet(
                "color: #a9d48f; font-size: 14px; font-weight: bold; padding: 6px 12px; "
                "background-color: #243329; border-radius: 12px;"
            )
            self._log(f"Harvest completed - Found: {statistics.get('found', 0)}, Failed: {statistics.get('failed', 0)}")
        else:
            self.status_badge.setText("● Stopped")
            self.status_badge.setStyleSheet(
                "color: #d9a59c; font-size: 14px; font-weight: bold; padding: 6px 12px; "
                "background-color: #2b2322; border-radius: 12px;"
            )
            self._log("Harvest stopped by user")

        if not success and statistics.get("total", 0) == 0:
            QMessageBox.warning(
                self,
                messages.GuiMessages.err_title_no_valid_isbns,
                messages.GuiMessages.err_body_no_valid_isbns,
            )

        if self.progress_dialog:
            self.progress_dialog.harvest_completed(success)

        self.harvest_finished.emit(success, statistics)

        if self.auto_export_check.isChecked() and success:
            self._log("Auto-export enabled - results saved to database")

    def _on_status_message(self, message):
        """Handle status message from worker."""
        self._log(message)

    def _update_stats(self, statistics):
        """Update the stat displays."""
        total = statistics.get("total", 0)
        found = statistics.get("found", 0)
        failed = statistics.get("failed", 0)
        cached = statistics.get("cached", 0)
        skipped = statistics.get("skipped", 0)
        processed = found + failed + cached + skipped

        self._set_stat_value(self.total_value, str(total))
        self._set_stat_value(self.processed_value, str(processed))
        self._set_stat_value(self.found_value, str(found))
        self._set_stat_value(self.failed_value, str(failed))

        if total > 0:
            progress_percent = (processed / total) * 100
            self.progress_value.setText(f"{progress_percent:.1f}%")
            self.progress_bar.setValue(int(progress_percent))
            success_rate = (found / total) * 100 if total else 0
            self.success_rate_label.setText(f"Success Rate: {success_rate:.1f}%")
            self.processed_meta_label.setText(f"Processed: {processed}/{total}")
        else:
            self.progress_value.setText("0%")
            self.progress_bar.setValue(0)
            self.success_rate_label.setText("Success Rate: 0%")
            self.processed_meta_label.setText("Processed: 0/0")

        self.total_count = total

    def _set_stat_value(self, label, value):
        """Set stat value with a subtle pulse."""
        if label.text() == value:
            return
        label.setText(value)
        label.setStyleSheet("color: #c2d07f; font-size: 28px; font-weight: bold;")
        if label in self._pulse_timers:
            self._pulse_timers[label].stop()
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda l=label: l.setStyleSheet("color: #e8e6df; font-size: 28px; font-weight: bold;"))
        self._pulse_timers[label] = timer
        timer.start(220)

    def _add_event_chip(self, status, source, isbn):
        """Add a compact event chip to the live panel."""
        status_lower = (status or "").lower()
        if status_lower in {"processing", "trying"}:
            tone = "info"
            text = f"{isbn} • {source or 'Processing'}"
        elif status_lower in {"cached", "found", "success"}:
            tone = "success"
            text = f"{isbn} • Found"
        elif status_lower in {"failed"}:
            tone = "danger"
            text = f"{isbn} • Failed"
        elif status_lower in {"skipped"}:
            tone = "muted"
            text = f"{isbn} • Skipped"
        else:
            tone = "muted"
            text = f"{isbn} • {status.capitalize()}"

        chip = QLabel(text)
        chip.setStyleSheet(self._chip_style(tone))
        self.event_chip_layout.addWidget(chip)
        while self.event_chip_layout.count() > 6:
            old = self.event_chip_layout.takeAt(0).widget()
            if old:
                old.deleteLater()

    def _chip_style(self, tone):
        base = "padding: 4px 8px; border-radius: 10px; font-size: 10px;"
        if tone == "success":
            return base + " background-color: #243329; color: #a9d48f; border: 1px solid #2f3a31;"
        if tone == "danger":
            return base + " background-color: #2b2322; color: #d9a59c; border: 1px solid #3a2a2a;"
        if tone == "info":
            return base + " background-color: #242521; color: #c2d07f; border: 1px solid #2d2e2b;"
        return base + " background-color: #1f201d; color: #a7a59b; border: 1px solid #2d2e2b;"

    def _update_speed(self):
        """Update speed and time indicators."""
        if not self.is_running or not self.start_time:
            return

        elapsed = time.time() - self.start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        self.time_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

        if elapsed > 0:
            self.current_speed = self.processed_count / elapsed
            self.speed_label.setText(f"{self.current_speed:.1f}")

        if self.total_count > 0 and self.current_speed > 0:
            remaining = self.total_count - self.processed_count
            eta_seconds = remaining / self.current_speed
            eta_hours = int(eta_seconds // 3600)
            eta_minutes = int((eta_seconds % 3600) // 60)
            eta_secs = int(eta_seconds % 60)
            self.eta_label.setText(f"{eta_hours:02d}:{eta_minutes:02d}:{eta_secs:02d}")
        else:
            self.eta_label.setText("--:--:--")

    def _get_config(self):
        """Get configuration from config tab."""
        parent = self.parent()
        while parent and not hasattr(parent, "config_tab"):
            parent = parent.parent()

        if parent and hasattr(parent, "config_tab"):
            return parent.config_tab.get_config()

        return {
            "collect_lccn": True,
            "collect_nlmcn": False,
            "retry_days": 7,
        }

    def _get_targets(self):
        """Get targets from targets tab."""
        parent = self.parent()
        while parent and not hasattr(parent, "targets_tab"):
            parent = parent.parent()

        if parent and hasattr(parent, "targets_tab"):
            return parent.targets_tab.get_targets()

        return []

    def _get_advanced_settings(self):
        """Get advanced settings."""
        try:
            from .advanced_settings_dialog import AdvancedSettingsDialog
            dialog = AdvancedSettingsDialog(self)
            return dialog.get_settings()
        except Exception:
            return {}

    def _log(self, message):
        """Add a message to the log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")

    def _clear_log(self):
        """Clear the log."""
        self.log_text.clear()
        self._log("Log cleared")

    def _save_log(self):
        """Save log to file."""
        from PyQt6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Harvest Log",
            f"harvest_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt);;All Files (*.*)",
        )

        if file_path:
            try:
                with open(file_path, "w") as f:
                    f.write(self.log_text.toPlainText())
                QMessageBox.information(self, "Success", "Log saved successfully")
                self._log(f"Log saved to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save log: {str(e)}")

    def update_progress(self, current, total, found, failed):
        """Update progress statistics (for backward compatibility)."""
        self.total_value.setText(str(total))
        self.processed_value.setText(str(current))
        self.found_value.setText(str(found))
        self.failed_value.setText(str(failed))

        if total > 0:
            progress = int((current / total) * 100)
            self.progress_bar.setValue(progress)

    def showEvent(self, event):
        """Show a gentle warning if no input file is selected."""
        super().showEvent(event)
        if not self.input_file and not self._warned_no_input:
            QMessageBox.warning(
                self,
                messages.GuiMessages.err_title_no_input,
                messages.GuiMessages.err_body_no_input,
            )
            self._warned_no_input = True
