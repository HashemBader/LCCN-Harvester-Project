"""
Module: harvest_tab.py
Harvest execution and progress tracking tab with threading support.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QTextEdit, QProgressBar,
    QCheckBox, QSpinBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from datetime import datetime
from pathlib import Path

from .progress_dialog import ProgressDialog


class HarvestWorker(QThread):
    """Background worker thread for harvest operations."""

    progress_update = pyqtSignal(str, str, str, str)  # isbn, status, source, message
    harvest_complete = pyqtSignal(bool, dict)  # success, statistics
    status_message = pyqtSignal(str)
    started = pyqtSignal()

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

            # TODO: This is a placeholder - will be replaced with actual harvest logic
            # For now, simulate some work
            from time import sleep
            import random

            isbns = self._read_isbns()
            stats = {"total": len(isbns), "found": 0, "failed": 0}

            for i, isbn in enumerate(isbns):
                if self._stop_requested:
                    self.harvest_complete.emit(False, stats)
                    return

                while self._pause_requested and not self._stop_requested:
                    sleep(0.1)

                # Simulate processing
                sleep(0.1)  # Simulate API call

                # Random success/failure for demo
                if random.random() > 0.3:
                    source = random.choice(["Cache", "LoC API", "Harvard API", "Z39.50"])
                    self.progress_update.emit(isbn, "found", source, "LCCN retrieved")
                    stats["found"] += 1
                else:
                    self.progress_update.emit(isbn, "failed", "All", "No results")
                    stats["failed"] += 1

            self.status_message.emit("Harvest completed")
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


class HarvestTab(QWidget):
    harvest_started = pyqtSignal()
    harvest_finished = pyqtSignal(bool, dict)  # success, statistics
    status_message = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.is_running = False
        self.input_file = None
        self.worker = None
        self.progress_dialog = None
        self.advanced_mode = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()

        # Title
        title_label = QLabel("Harvest Execution")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title_label)

        # Status group
        status_group = QGroupBox("Harvest Status")
        status_layout = QVBoxLayout()

        self.status_label = QLabel("Status: Ready")
        self.status_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        status_layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        status_layout.addWidget(self.progress_bar)

        # Stats
        stats_layout = QHBoxLayout()

        self.total_label = QLabel("Total: 0")
        self.processed_label = QLabel("Processed: 0")
        self.found_label = QLabel("Found: 0")
        self.failed_label = QLabel("Failed: 0")

        stats_layout.addWidget(self.total_label)
        stats_layout.addWidget(self.processed_label)
        stats_layout.addWidget(self.found_label)
        stats_layout.addWidget(self.failed_label)
        stats_layout.addStretch()

        status_layout.addLayout(stats_layout)
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Control buttons
        control_group = QGroupBox("Controls")
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
        self.advanced_group.setCheckable(True)
        self.advanced_group.setChecked(False)
        self.advanced_group.setVisible(False)  # Hidden until advanced mode

        advanced_layout = QVBoxLayout()

        parallel_layout = QHBoxLayout()
        parallel_layout.addWidget(QLabel("Parallel Workers:"))
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 10)
        self.parallel_spin.setValue(1)
        self.parallel_spin.setToolTip("Number of ISBNs to process in parallel")
        parallel_layout.addWidget(self.parallel_spin)
        parallel_layout.addStretch()
        advanced_layout.addLayout(parallel_layout)

        self.auto_export_check = QCheckBox("Auto-export results after harvest")
        self.auto_export_check.setChecked(True)
        advanced_layout.addWidget(self.auto_export_check)

        self.detailed_logging_check = QCheckBox("Enable detailed logging")
        self.detailed_logging_check.setChecked(False)
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

        self.worker.start()

        # Update UI state
        self.is_running = True
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.detailed_progress_button.setEnabled(True)
        self.status_label.setText("Status: Running...")

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
        pass  # Already handled in _start_harvest

    def _on_progress_update(self, isbn, status, source, message):
        """Handle progress update from worker."""
        # Update progress dialog if exists
        if self.progress_dialog:
            self.progress_dialog.update_progress(isbn, status, source, message)

        # Update stats
        # This would be better handled by accumulating stats...
        # For now, just log
        self._log(f"{isbn}: {status}" + (f" - {source}" if source else ""))

    def _on_harvest_complete(self, success, statistics):
        """Handle harvest completion."""
        self.is_running = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.detailed_progress_button.setEnabled(False)

        if success:
            self.status_label.setText("Status: Completed")
            self._log(f"Harvest completed - Found: {statistics.get('found', 0)}, Failed: {statistics.get('failed', 0)}")
        else:
            self.status_label.setText("Status: Stopped")
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
        self.status_message.emit(message)

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