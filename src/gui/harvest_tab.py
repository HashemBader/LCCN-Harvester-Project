"""
Module: harvest_tab.py
Harvest execution and progress tracking tab with threading support.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QTextEdit, QProgressBar,
    QCheckBox, QSpinBox, QFrame, QGridLayout
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from datetime import datetime
from pathlib import Path
import time
import sys

# Add src to path for database import
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import DatabaseManager
from database.db_manager import MainRecord

from .progress_dialog import ProgressDialog


class HarvestWorker(QThread):
    """Background worker thread for harvest operations."""

    progress_update = pyqtSignal(str, str, str, str)  # isbn, status, source, message
    harvest_complete = pyqtSignal(bool, dict)  # success, statistics
    status_message = pyqtSignal(str)
    started = pyqtSignal()
    milestone_reached = pyqtSignal(str, int)  # milestone_type, value
    stats_update = pyqtSignal(dict)  # real-time statistics update

    def __init__(self, input_file, config, targets, advanced_settings=None):
        super().__init__()
        self.input_file = input_file
        self.config = config
        self.targets = targets
        self.advanced_settings = advanced_settings or {}
        self._stop_requested = False
        self._pause_requested = False

    def run(self):
        """Run the harvest operation in background thread."""
        try:
            self.started.emit()
            self.status_message.emit("Starting harvest...")

            # Initialize database
            db = DatabaseManager()
            db.init_db()

            # TODO: This is a placeholder - will be replaced with actual harvest logic
            # For now, simulate some work and SAVE TO DATABASE
            from time import sleep
            import random

            isbns = self._read_isbns()
            total = len(isbns)
            stats = {"total": total, "found": 0, "failed": 0}

            # Sample LCCNs for random assignment
            sample_lccns = [
                "QA76.73.P98", "QA76.73.J39", "QA76.625", "QA76.758",
                "QA76.76.D47", "QA76.9.D3", "T385", "Z253",
                "PR6066.R6", "PS3552.R354", "HF5415.5", "BF636.5"
            ]

            for i, isbn in enumerate(isbns):
                if self._stop_requested:
                    self.harvest_complete.emit(False, stats)
                    return

                while self._pause_requested and not self._stop_requested:
                    sleep(0.1)

                # Simulate processing
                sleep(0.1)  # Simulate API call

                # Random success/failure for demo (70% success rate)
                if random.random() > 0.3:
                    source = random.choice(["Cache", "LoC API", "Harvard API", "Z39.50: Yale"])
                    lccn = random.choice(sample_lccns)

                    # Save to database using MainRecord
                    try:
                        record = MainRecord(
                            isbn=isbn,
                            lccn=lccn,
                            nlmcn=None,
                            source=source
                        )
                        db.upsert_main(record)
                    except Exception as db_err:
                        self.status_message.emit(f"DB Error saving {isbn}: {db_err}")

                    self.progress_update.emit(isbn, "found", source, f"LCCN: {lccn}")
                    stats["found"] += 1
                else:
                    # Save failed attempt to database
                    try:
                        db.upsert_attempted(
                            isbn=isbn,
                            last_target="All",
                            last_error="No results found (simulated)"
                        )
                    except Exception as db_err:
                        self.status_message.emit(f"DB Error saving failed {isbn}: {db_err}")

                    self.progress_update.emit(isbn, "failed", "All", "No results")
                    stats["failed"] += 1

                # Check for milestones
                processed = i + 1
                self._check_milestone(processed, total)

                # Emit stats update every 5 ISBNs for smooth UI updates
                if processed % 5 == 0 or processed == total:
                    self.stats_update.emit(stats.copy())

            self.status_message.emit("Harvest completed - Results saved to database")
            self.harvest_complete.emit(True, stats)

        except Exception as e:
            self.status_message.emit(f"Error: {str(e)}")
            self.harvest_complete.emit(False, {})

    def _read_isbns(self):
        """Read ISBNs from input file."""
        try:
            with open(self.input_file, 'r', encoding='utf-8-sig') as f:
                isbns = []
                for line in f:
                    isbn = line.strip().split('\t')[0]  # First column
                    if isbn and not isbn.lower().startswith('isbn'):
                        isbns.append(isbn)
                return isbns
        except Exception as e:
            self.status_message.emit(f"Error reading file: {str(e)}")
            return []

    def stop(self):
        """Request worker to stop."""
        self._stop_requested = True

    def toggle_pause(self):
        """Toggle pause state."""
        self._pause_requested = not self._pause_requested

    def _check_milestone(self, processed, total):
        """Check if a milestone has been reached and emit signal."""
        # Count-based milestones
        if processed == 100:
            self.milestone_reached.emit("100_processed", 100)
        elif processed == 500:
            self.milestone_reached.emit("500_processed", 500)
        elif processed == 1000:
            self.milestone_reached.emit("1000_processed", 1000)

        # Percentage-based milestones
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

        # Speed tracking
        self.speed_timer = QTimer()
        self.speed_timer.timeout.connect(self._update_speed)
        self.last_processed = 0
        self.current_speed = 0

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(20)

        # Header with status
        header_layout = QHBoxLayout()

        title_label = QLabel("🚀 Harvest Execution")
        title_label.setStyleSheet("font-size: 20px; font-weight: bold; color: black; font-family: Arial, Helvetica;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.status_badge = QLabel("● Ready")
        self.status_badge.setStyleSheet("""
            color: #95a5a6;
            font-size: 14px;
            font-weight: bold;
            padding: 6px 12px;
            background-color: #ecf0f1;
            border-radius: 12px;
        """)
        header_layout.addWidget(self.status_badge)

        layout.addLayout(header_layout)

        # Simple stats section
        stats_group = QGroupBox("Harvest Statistics")
        stats_group.setStyleSheet("QGroupBox { color: black; font-weight: bold; font-family: Arial, Helvetica; }")
        stats_layout = QGridLayout()
        stats_layout.setSpacing(15)

        # Create simple stat displays
        def create_stat_display(label_text):
            container = QVBoxLayout()
            label = QLabel(label_text)
            label.setStyleSheet("color: #666666; font-size: 11px; font-family: Arial, Helvetica;")
            value = QLabel("0")
            value.setStyleSheet("color: black; font-size: 28px; font-weight: bold; font-family: Arial, Helvetica;")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            container.addWidget(label)
            container.addWidget(value)
            return container, value

        # Total ISBNs
        total_layout, self.total_value = create_stat_display("Total ISBNs")
        stats_layout.addLayout(total_layout, 0, 0)

        # Processed
        processed_layout, self.processed_value = create_stat_display("Processed")
        stats_layout.addLayout(processed_layout, 0, 1)

        # Found
        found_layout, self.found_value = create_stat_display("✓ Found")
        stats_layout.addLayout(found_layout, 0, 2)

        # Failed
        failed_layout, self.failed_value = create_stat_display("✗ Failed")
        stats_layout.addLayout(failed_layout, 0, 3)

        # Progress info
        progress_layout, self.progress_value = create_stat_display("Progress %")
        stats_layout.addLayout(progress_layout, 1, 0)

        # Time
        time_layout, self.time_label = create_stat_display("Elapsed Time")
        self.time_label.setText("00:00:00")
        self.time_label.setStyleSheet("color: black; font-size: 16px; font-weight: bold; font-family: Arial, Helvetica;")
        stats_layout.addLayout(time_layout, 1, 1)

        # Speed
        speed_layout, self.speed_label = create_stat_display("Speed (ISBN/s)")
        self.speed_label.setText("0")
        self.speed_label.setStyleSheet("color: black; font-size: 16px; font-weight: bold; font-family: Arial, Helvetica;")
        stats_layout.addLayout(speed_layout, 1, 2)

        # ETA
        eta_layout, self.eta_label = create_stat_display("ETA")
        self.eta_label.setText("--:--:--")
        self.eta_label.setStyleSheet("color: black; font-size: 16px; font-weight: bold; font-family: Arial, Helvetica;")
        stats_layout.addLayout(eta_layout, 1, 3)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # Control buttons
        control_group = QGroupBox("Controls")
        control_group.setStyleSheet("QGroupBox { color: black; font-weight: bold; font-family: Arial, Helvetica; }")
        control_layout = QVBoxLayout()

        buttons_layout = QHBoxLayout()

        self.start_button = QPushButton("Start Harvest")
        self.start_button.clicked.connect(self._start_harvest)
        self.start_button.setEnabled(False)
        self.start_button.setToolTip("Select an input file first")

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
        self.advanced_group.setStyleSheet("QGroupBox { color: black; font-weight: bold; font-family: Arial, Helvetica; }")
        self.advanced_group.setCheckable(True)
        self.advanced_group.setChecked(False)
        self.advanced_group.setVisible(False)  # Hidden until advanced mode

        advanced_layout = QVBoxLayout()

        parallel_layout = QHBoxLayout()
        parallel_label = QLabel("Parallel Workers:")
        parallel_label.setStyleSheet("color: black;")
        parallel_layout.addWidget(parallel_label)
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 10)
        self.parallel_spin.setValue(1)
        self.parallel_spin.setToolTip("Number of ISBNs to process in parallel")
        self.parallel_spin.setStyleSheet("color: black;")
        parallel_layout.addWidget(self.parallel_spin)
        parallel_layout.addStretch()
        advanced_layout.addLayout(parallel_layout)

        self.auto_export_check = QCheckBox("Auto-export results after harvest")
        self.auto_export_check.setChecked(True)
        self.auto_export_check.setStyleSheet("color: black;")
        advanced_layout.addWidget(self.auto_export_check)

        self.detailed_logging_check = QCheckBox("Enable detailed logging")
        self.detailed_logging_check.setChecked(False)
        self.detailed_logging_check.setStyleSheet("color: black;")
        advanced_layout.addWidget(self.detailed_logging_check)

        self.advanced_group.setLayout(advanced_layout)
        control_layout.addWidget(self.advanced_group)

        control_group.setLayout(control_layout)
        layout.addWidget(control_group)

        # Log output
        log_group = QGroupBox("Harvest Log")
        log_group.setStyleSheet("QGroupBox { color: black; font-weight: bold; font-family: Arial, Helvetica; }")
        log_layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("Harvest log will appear here...")
        self.log_text.setStyleSheet("""
            QTextEdit {
                color: black;
                background-color: white;
                border: 1px solid #e0e0e0;
            }
        """)

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
            self._log("ERROR: No input file selected")
            return

        # Get configuration from parent tabs
        config = self._get_config()
        targets = self._get_targets()
        advanced_settings = self._get_advanced_settings() if self.advanced_mode else {}

        # Create and start worker thread
        self.worker = HarvestWorker(self.input_file, config, targets, advanced_settings)
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
        self.status_badge.setStyleSheet("""
            color: #27ae60;
            font-size: 14px;
            font-weight: bold;
            padding: 6px 12px;
            background-color: #d5f4e6;
            border-radius: 12px;
        """)

        # Start timers
        self.start_time = time.time()
        self.speed_timer.start(1000)  # Update every second

        # Create progress dialog if advanced mode
        if self.advanced_mode:
            self._create_progress_dialog()

        self._log("Harvest started")
        self.harvest_started.emit()
        self.status_message.emit("Harvest started")

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
            with open(self.input_file, 'r', encoding='utf-8-sig') as f:
                lines = [line.strip() for line in f if line.strip()]
                # Remove header if present
                if lines and lines[0].lower().startswith('isbn'):
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
        # Reset stats
        self.processed_count = 0
        self.total_count = 0
        self.last_processed = 0
        self.current_speed = 0

    def _on_progress_update(self, isbn, status, source, message):
        """Handle progress update from worker."""
        # Update progress dialog if exists
        if self.progress_dialog:
            self.progress_dialog.update_progress(isbn, status, source, message)

        # Increment processed count
        self.processed_count += 1

        # Log
        self._log(f"{isbn}: {status}" + (f" - {source}" if source else ""))

    def _on_harvest_complete(self, success, statistics):
        """Handle harvest completion."""
        self.is_running = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.detailed_progress_button.setEnabled(False)

        # Stop speed timer
        self.speed_timer.stop()

        # Update stats with final values
        self._update_stats(statistics)

        if success:
            # Update status badge
            self.status_badge.setText("● Completed")
            self.status_badge.setStyleSheet("""
                color: #27ae60;
                font-size: 14px;
                font-weight: bold;
                padding: 6px 12px;
                background-color: #d5f4e6;
                border-radius: 12px;
            """)
            self._log(f"Harvest completed - Found: {statistics.get('found', 0)}, Failed: {statistics.get('failed', 0)}")
        else:
            # Update status badge
            self.status_badge.setText("● Stopped")
            self.status_badge.setStyleSheet("""
                color: #e74c3c;
                font-size: 14px;
                font-weight: bold;
                padding: 6px 12px;
                background-color: #fadbd8;
                border-radius: 12px;
            """)
            self._log("Harvest stopped by user")

        # Update progress dialog
        if self.progress_dialog:
            self.progress_dialog.harvest_completed(success)

        # Emit signal to main window
        self.harvest_finished.emit(success, statistics)

        # Auto-export if enabled
        if self.auto_export_check.isChecked() and success:
            self._log("Auto-export enabled - results saved to database")

    def _on_status_message(self, message):
        """Handle status message from worker."""
        self._log(message)

    def _update_stats(self, statistics):
        """Update the stat displays."""
        total = statistics.get('total', 0)
        found = statistics.get('found', 0)
        failed = statistics.get('failed', 0)
        processed = found + failed

        # Update simple stat labels
        self.total_value.setText(str(total))
        self.processed_value.setText(str(processed))
        self.found_value.setText(str(found))
        self.failed_value.setText(str(failed))

        # Update progress percentage
        if total > 0:
            progress_percent = (processed / total) * 100
            self.progress_value.setText(f"{progress_percent:.1f}%")
        else:
            self.progress_value.setText("0%")

        # Update total count
        self.total_count = total

    def _update_speed(self):
        """Update speed and time indicators."""
        if not self.is_running or not self.start_time:
            return

        # Calculate elapsed time
        elapsed = time.time() - self.start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        self.time_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

        # Calculate speed (ISBNs per second)
        if elapsed > 0:
            self.current_speed = self.processed_count / elapsed
            self.speed_label.setText(f"{self.current_speed:.1f}")

        # Calculate ETA
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
        # This would get config from the parent's config tab
        # For now, return default
        return {
            "collect_lccn": True,
            "collect_nlmcn": False,
            "retry_days": 7
        }

    def _get_targets(self):
        """Get targets from targets tab."""
        # This would get targets from the parent's targets tab
        # For now, return default
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
        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Harvest Log",
            f"harvest_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt);;All Files (*.*)"
        )

        if file_path:
            try:
                with open(file_path, 'w') as f:
                    f.write(self.log_text.toPlainText())
                QMessageBox.information(self, "Success", "Log saved successfully")
                self._log(f"Log saved to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save log: {str(e)}")

    def update_progress(self, current, total, found, failed):
        """Update progress statistics (for backward compatibility)."""
        self.total_label.setText(f"Total: {total}")
        self.processed_label.setText(f"Processed: {current}")
        self.found_label.setText(f"Found: {found}")
        self.failed_label.setText(f"Failed: {failed}")

        if total > 0:
            progress = int((current / total) * 100)
            self.progress_bar.setValue(progress)