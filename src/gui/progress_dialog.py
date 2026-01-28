"""
Module: progress_dialog.py
Detailed progress tracking dialog for harvest operations.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QTextEdit, QPushButton, QGroupBox,
    QTableWidget, QTableWidgetItem, QTabWidget, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor
from datetime import datetime
import time


class ProgressDialog(QDialog):
    """Advanced progress tracking dialog with real-time statistics."""

    cancel_requested = pyqtSignal()
    pause_requested = pyqtSignal()

    def __init__(self, parent=None, advanced_mode=False):
        super().__init__(parent)
        self.setWindowTitle("Harvest Progress")
        self.setMinimumSize(900, 700)
        self.setModal(False)  # Allow interaction with main window
        self.advanced_mode = advanced_mode
        self.start_time = None
        self.is_paused = False

        # Statistics
        self.stats = {
            "total": 0,
            "processed": 0,
            "found": 0,
            "failed": 0,
            "cached": 0,
            "api_found": 0,
            "z3950_found": 0,
            "elapsed_time": 0,
            "rate": 0.0
        }

        # Target statistics for advanced mode
        self.target_stats = {}

        self._setup_ui()
        self._start_timer()

    def _setup_ui(self):
        layout = QVBoxLayout()

        # Header with overall status
        header_group = QGroupBox("Overall Progress")
        header_layout = QVBoxLayout()

        # Current operation
        self.current_label = QLabel("Initializing...")
        self.current_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        header_layout.addWidget(self.current_label)

        # Overall progress bar
        self.overall_progress = QProgressBar()
        self.overall_progress.setTextVisible(True)
        header_layout.addWidget(self.overall_progress)

        # Statistics row
        stats_layout = QHBoxLayout()

        self.processed_label = QLabel("Processed: 0/0")
        self.found_label = QLabel("Found: 0")
        self.failed_label = QLabel("Failed: 0")
        self.rate_label = QLabel("Rate: 0/s")

        stats_layout.addWidget(self.processed_label)
        stats_layout.addWidget(self.found_label)
        stats_layout.addWidget(self.failed_label)
        stats_layout.addWidget(self.rate_label)
        stats_layout.addStretch()

        header_layout.addLayout(stats_layout)
        header_group.setLayout(header_layout)
        layout.addWidget(header_group)

        # Advanced mode features
        if self.advanced_mode:
            # Tabs for different views
            tabs = QTabWidget()

            # Log tab
            log_tab = self._create_log_tab()
            tabs.addTab(log_tab, "Activity Log")

            # Target statistics tab
            target_stats_tab = self._create_target_stats_tab()
            tabs.addTab(target_stats_tab, "Target Statistics")

            # Performance metrics tab
            performance_tab = self._create_performance_tab()
            tabs.addTab(performance_tab, "Performance")

            layout.addWidget(tabs)
        else:
            # Simple log view
            log_group = QGroupBox("Activity Log")
            log_layout = QVBoxLayout()

            self.log_text = QTextEdit()
            self.log_text.setReadOnly(True)
            self.log_text.setMaximumHeight(300)
            log_layout.addWidget(self.log_text)

            log_group.setLayout(log_layout)
            layout.addWidget(log_group)

        # Control buttons
        button_layout = QHBoxLayout()

        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self._on_pause_clicked)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel_clicked)

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        self.close_button.setEnabled(False)  # Enabled when harvest completes

        button_layout.addWidget(self.pause_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addStretch()
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def _create_log_tab(self):
        """Create activity log tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        # Filter controls
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))

        self.log_filter_combo = QPushButton("All")  # Simplified for now
        filter_layout.addWidget(self.log_filter_combo)
        filter_layout.addStretch()

        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(self._clear_log)
        filter_layout.addWidget(clear_btn)

        layout.addLayout(filter_layout)

        # Log text area
        self.log_text_advanced = QTextEdit()
        self.log_text_advanced.setReadOnly(True)
        self.log_text_advanced.setFont(QFont("Courier", 9))
        layout.addWidget(self.log_text_advanced)

        widget.setLayout(layout)
        return widget

    def _create_target_stats_tab(self):
        """Create target statistics tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Per-Target Success Rates:"))

        self.target_table = QTableWidget()
        self.target_table.setColumnCount(5)
        self.target_table.setHorizontalHeaderLabels([
            "Target", "Queries", "Found", "Failed", "Success Rate"
        ])
        self.target_table.setAlternatingRowColors(True)

        layout.addWidget(self.target_table)
        widget.setLayout(layout)
        return widget

    def _create_performance_tab(self):
        """Create performance metrics tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        # Time statistics
        time_group = QGroupBox("Time Statistics")
        time_layout = QVBoxLayout()

        self.elapsed_label = QLabel("Elapsed: 0:00:00")
        self.estimated_label = QLabel("Estimated Remaining: Unknown")
        self.avg_time_label = QLabel("Average per ISBN: 0.0s")

        time_layout.addWidget(self.elapsed_label)
        time_layout.addWidget(self.estimated_label)
        time_layout.addWidget(self.avg_time_label)

        time_group.setLayout(time_layout)
        layout.addWidget(time_group)

        # Source breakdown
        source_group = QGroupBox("Source Breakdown")
        source_layout = QVBoxLayout()

        self.cached_label = QLabel("From Cache: 0 (0%)")
        self.api_label = QLabel("From APIs: 0 (0%)")
        self.z3950_label = QLabel("From Z39.50: 0 (0%)")

        source_layout.addWidget(self.cached_label)
        source_layout.addWidget(self.api_label)
        source_layout.addWidget(self.z3950_label)

        source_group.setLayout(source_layout)
        layout.addWidget(source_group)

        # Memory/Resource usage (placeholder)
        resource_group = QGroupBox("Resource Usage")
        resource_layout = QVBoxLayout()

        self.memory_label = QLabel("Memory: N/A")
        self.threads_label = QLabel("Active Threads: 1")

        resource_layout.addWidget(self.memory_label)
        resource_layout.addWidget(self.threads_label)

        resource_group.setLayout(resource_layout)
        layout.addWidget(resource_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _start_timer(self):
        """Start timer for updating elapsed time and rate."""
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_time_display)
        self.timer.start(1000)  # Update every second

    def _update_time_display(self):
        """Update elapsed time and rate display."""
        if not self.start_time:
            return

        elapsed = time.time() - self.start_time
        self.stats["elapsed_time"] = elapsed

        # Calculate rate
        if elapsed > 0 and self.stats["processed"] > 0:
            self.stats["rate"] = self.stats["processed"] / elapsed
            self.rate_label.setText(f"Rate: {self.stats['rate']:.2f}/s")

        # Update elapsed time display in advanced mode
        if self.advanced_mode and hasattr(self, 'elapsed_label'):
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            seconds = int(elapsed % 60)
            self.elapsed_label.setText(f"Elapsed: {hours}:{minutes:02d}:{seconds:02d}")

            # Estimate remaining time
            if self.stats["processed"] > 0:
                remaining = self.stats["total"] - self.stats["processed"]
                if self.stats["rate"] > 0:
                    est_seconds = remaining / self.stats["rate"]
                    est_minutes = int(est_seconds // 60)
                    est_seconds = int(est_seconds % 60)
                    self.estimated_label.setText(
                        f"Estimated Remaining: {est_minutes}:{est_seconds:02d}"
                    )

                # Average time per ISBN
                avg_time = elapsed / self.stats["processed"]
                self.avg_time_label.setText(f"Average per ISBN: {avg_time:.2f}s")

    def start_harvest(self, total_isbns):
        """Initialize harvest with total count."""
        self.stats["total"] = total_isbns
        self.stats["processed"] = 0
        self.stats["found"] = 0
        self.stats["failed"] = 0
        self.start_time = time.time()
        self.overall_progress.setMaximum(total_isbns)
        self._update_displays()

    def update_progress(self, isbn, status, source=None, message=""):
        """Update progress with current ISBN status."""
        self.stats["processed"] += 1

        if status == "found":
            self.stats["found"] += 1
            if source:
                if "cache" in source.lower():
                    self.stats["cached"] += 1
                elif "z39" in source.lower() or "z3950" in source.lower():
                    self.stats["z3950_found"] += 1
                else:
                    self.stats["api_found"] += 1

                # Update target stats
                if source not in self.target_stats:
                    self.target_stats[source] = {"queries": 0, "found": 0, "failed": 0}
                self.target_stats[source]["queries"] += 1
                self.target_stats[source]["found"] += 1

        elif status == "failed":
            self.stats["failed"] += 1
            if source:
                if source not in self.target_stats:
                    self.target_stats[source] = {"queries": 0, "found": 0, "failed": 0}
                self.target_stats[source]["queries"] += 1
                self.target_stats[source]["failed"] += 1

        self.current_label.setText(f"Processing: {isbn}")
        self._update_displays()
        self._log(f"{isbn} - {status.upper()}" + (f" ({source})" if source else "") + (f": {message}" if message else ""))

        # Update target statistics table in advanced mode
        if self.advanced_mode:
            self._update_target_table()
            self._update_source_breakdown()

    def _update_displays(self):
        """Update all display elements."""
        self.overall_progress.setValue(self.stats["processed"])
        self.processed_label.setText(f"Processed: {self.stats['processed']}/{self.stats['total']}")
        self.found_label.setText(f"Found: {self.stats['found']}")
        self.failed_label.setText(f"Failed: {self.stats['failed']}")

    def _update_target_table(self):
        """Update target statistics table."""
        if not hasattr(self, 'target_table'):
            return

        self.target_table.setRowCount(len(self.target_stats))

        for row, (target, stats) in enumerate(self.target_stats.items()):
            self.target_table.setItem(row, 0, QTableWidgetItem(target))
            self.target_table.setItem(row, 1, QTableWidgetItem(str(stats["queries"])))
            self.target_table.setItem(row, 2, QTableWidgetItem(str(stats["found"])))
            self.target_table.setItem(row, 3, QTableWidgetItem(str(stats["failed"])))

            if stats["queries"] > 0:
                success_rate = (stats["found"] / stats["queries"]) * 100
                rate_item = QTableWidgetItem(f"{success_rate:.1f}%")
                if success_rate >= 70:
                    rate_item.setForeground(QColor("green"))
                elif success_rate >= 40:
                    rate_item.setForeground(QColor("orange"))
                else:
                    rate_item.setForeground(QColor("red"))
                self.target_table.setItem(row, 4, rate_item)

        self.target_table.resizeColumnsToContents()

    def _update_source_breakdown(self):
        """Update source breakdown labels."""
        if not hasattr(self, 'cached_label'):
            return

        total_found = self.stats["found"]
        if total_found > 0:
            cached_pct = (self.stats["cached"] / total_found) * 100
            api_pct = (self.stats["api_found"] / total_found) * 100
            z3950_pct = (self.stats["z3950_found"] / total_found) * 100

            self.cached_label.setText(f"From Cache: {self.stats['cached']} ({cached_pct:.1f}%)")
            self.api_label.setText(f"From APIs: {self.stats['api_found']} ({api_pct:.1f}%)")
            self.z3950_label.setText(f"From Z39.50: {self.stats['z3950_found']} ({z3950_pct:.1f}%)")

    def _log(self, message):
        """Add message to log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"

        if self.advanced_mode and hasattr(self, 'log_text_advanced'):
            self.log_text_advanced.append(log_entry)
        elif hasattr(self, 'log_text'):
            self.log_text.append(log_entry)

    def _clear_log(self):
        """Clear the log."""
        if hasattr(self, 'log_text_advanced'):
            self.log_text_advanced.clear()

    def _on_pause_clicked(self):
        """Handle pause button click."""
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_button.setText("Resume")
            self._log("Harvest paused by user")
        else:
            self.pause_button.setText("Pause")
            self._log("Harvest resumed")
        self.pause_requested.emit()

    def _on_cancel_clicked(self):
        """Handle cancel button click."""
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "Cancel Harvest",
            "Are you sure you want to cancel the harvest?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._log("Harvest cancelled by user")
            self.cancel_requested.emit()

    def harvest_completed(self, success=True):
        """Mark harvest as completed."""
        self.timer.stop()
        self.pause_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.close_button.setEnabled(True)

        if success:
            self.current_label.setText("✓ Harvest Completed Successfully!")
            self.current_label.setStyleSheet("font-size: 12px; font-weight: bold; color: green;")
            self._log("Harvest completed successfully")
        else:
            self.current_label.setText("✗ Harvest Cancelled or Failed")
            self.current_label.setStyleSheet("font-size: 12px; font-weight: bold; color: red;")

    def get_statistics(self):
        """Return final statistics."""
        return {
            **self.stats,
            "target_stats": self.target_stats.copy()
        }