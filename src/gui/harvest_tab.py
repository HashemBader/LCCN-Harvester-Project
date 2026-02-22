"""
Module: harvest_tab.py
Harvest execution and progress tracking tab with threading support.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QTextEdit, QProgressBar,
    QCheckBox, QSpinBox, QFrame, QGridLayout, QMessageBox, QDialog, QToolTip,
    QScrollArea, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QEvent, QPoint
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

# Add src to path for database import
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import DatabaseManager
from harvester.run_harvest import run_harvest, parse_isbn_file
from harvester.targets import create_target_from_config
from harvester.orchestrator import HarvestCancelled
from utils.isbn_validator import normalize_isbn
from utils import messages

from .progress_dialog import ProgressDialog
from .api_monitor_tab import APIMonitorTab, APICheckWorker

LARGE_INPUT_FILE_THRESHOLD_BYTES = 20 * 1024 * 1024  # 20 MB
VALIDATION_SAMPLE_ROWS = 200_000


class HarvestWorker(QThread):
    """Background worker thread for harvest operations."""

    progress_update = pyqtSignal(str, str, str, str)  # isbn, status, source, message
    harvest_complete = pyqtSignal(bool, dict)  # success, statistics
    status_message = pyqtSignal(str)
    started = pyqtSignal()
    milestone_reached = pyqtSignal(str, int)  # milestone_type, value
    stats_update = pyqtSignal(dict)  # real-time statistics update

    def __init__(
        self,
        input_file,
        config,
        targets,
        advanced_settings=None,
        bypass_retry_isbns=None,
        bypass_cache_isbns=None,
    ):
        super().__init__()
        self.input_file = input_file
        self.config = config
        self.targets = targets
        self.advanced_settings = advanced_settings or {}
        self.bypass_retry_isbns = set(bypass_retry_isbns or [])
        self.bypass_cache_isbns = set(bypass_cache_isbns or [])
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
                    raise HarvestCancelled("Harvest cancelled by user")

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
            call_number_mode = self.config.get("call_number_mode", "lccn")
            try:
                max_workers = max(1, int(self.advanced_settings.get("parallel_workers", 1)))
            except Exception:
                max_workers = 1
            self.status_message.emit(
                f"Using performance settings: workers={max_workers}, mode={call_number_mode}"
            )

            summary = run_harvest(
                input_path=Path(self.input_file),
                dry_run=False,
                db_path="data/lccn_harvester.sqlite3",
                retry_days=retry_days,
                targets=targets,
                bypass_retry_isbns=self.bypass_retry_isbns,
                bypass_cache_isbns=self.bypass_cache_isbns,
                progress_cb=progress_callback,
                cancel_check=lambda: self._stop_requested,
                max_workers=max_workers,
                call_number_mode=call_number_mode,
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

        except HarvestCancelled:
            self.status_message.emit("Harvest cancelled by user.")
            self.harvest_complete.emit(False, self.stats.copy() if hasattr(self, "stats") else {"total": 0, "found": 0, "failed": 0})
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
            input_path = Path(self.input_file)
            delimiter = "," if input_path.suffix.lower() == ".csv" else "\t"

            with open(input_path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f, delimiter=delimiter)
                valid_isbns = []
                invalid_count = 0

                for row in reader:
                    if self._stop_requested:
                        raise HarvestCancelled("Harvest cancelled by user")
                    isbn = (row[0] or "").strip() if row else ""
                    if not isbn or isbn.lower().startswith("isbn") or isbn.startswith("#"):
                        continue  # Skip empty lines, header, and comments

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
                    # Apply advanced network settings uniformly so retry/search behavior matches UI settings.
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
        self.processed_count = 0
        self.total_count = 0
        self._warned_no_input = False
        self._input_valid_count = 0
        self._targets_override = None
        self._config_getter = None
        self._targets_getter = None
        self.api_monitor_dialog = None
        self.api_monitor_widget = None
        self.quick_api_status = {
            "Library of Congress": None,
            "Harvard": None,
            "OpenLibrary": None,
        }
        self.hover_check_worker = None

        self._setup_ui()

    def _setup_ui(self):
        # Stable container:
        # - centered max-width content to avoid stretched/distorted fullscreen layout
        # - vertical scrolling when window is too short instead of clipping text/widgets
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        viewport = QWidget()
        viewport_layout = QHBoxLayout(viewport)
        viewport_layout.setContentsMargins(12, 10, 12, 10)
        viewport_layout.setSpacing(0)

        content = QWidget()
        content.setMaximumWidth(1480)
        layout = QVBoxLayout(content)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        viewport_layout.addStretch(1)
        viewport_layout.addWidget(content)
        viewport_layout.addStretch(1)
        scroll.setWidget(viewport)
        root_layout.addWidget(scroll)

        # Header with status
        header_layout = QHBoxLayout()

        title_label = QLabel("Harvest")
        title_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #c2d07f;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.status_badge = QLabel("Ready")
        self.status_badge.setStyleSheet(
            "color: #a7a59b; font-size: 13px; font-weight: bold; padding: 6px 12px; "
            "background-color: #242521; border-radius: 12px;"
        )
        header_layout.addWidget(self.status_badge)

        layout.addLayout(header_layout)

        # Live activity panel
        live_group = QGroupBox("Live Activity")
        live_layout = QVBoxLayout()

        self.current_isbn_label = QLabel("Current ISBN: —")
        self.current_isbn_label.setStyleSheet("color: #e8e6df; font-size: 13px;")
        self.current_isbn_label.setMinimumHeight(22)
        live_layout.addWidget(self.current_isbn_label)

        self.current_status_label = QLabel("Status: Idle")
        self.current_status_label.setStyleSheet("color: #a7a59b; font-size: 12px;")
        self.current_status_label.setMinimumHeight(20)
        live_layout.addWidget(self.current_status_label)

        self.current_target_label = QLabel("Target: —")
        self.current_target_label.setStyleSheet("color: #a7a59b; font-size: 12px;")
        self.current_target_label.setMinimumHeight(20)
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
        self.event_chip_wrap.setMinimumHeight(24)
        self.event_chip_wrap.setMaximumHeight(24)
        self.event_chip_layout = QHBoxLayout(self.event_chip_wrap)
        self.event_chip_layout.setContentsMargins(0, 0, 0, 0)
        self.event_chip_layout.setSpacing(6)
        live_layout.addWidget(self.event_chip_wrap)

        live_group.setLayout(live_layout)
        layout.addWidget(live_group)

        # Stats section
        stats_group = QGroupBox("Harvest Statistics")
        stats_layout = QGridLayout()
        stats_layout.setHorizontalSpacing(10)
        stats_layout.setVerticalSpacing(10)

        def create_stat_tile(label_text, initial="0"):
            tile = QFrame()
            tile.setObjectName("StatTile")
            tile.setStyleSheet(
                "QFrame#StatTile { background-color: #1b1c1a; border: 1px solid #2d2e2b; border-radius: 8px; }"
            )
            tile.setMinimumHeight(86)
            tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(10, 8, 10, 8)
            tile_layout.setSpacing(3)

            label = QLabel(label_text)
            label.setStyleSheet("color: #a7a59b; font-size: 11px;")
            label.setMinimumHeight(16)
            value = QLabel(initial)
            value.setStyleSheet("color: #e8e6df; font-size: 17px; font-weight: 700;")
            value.setAlignment(Qt.AlignmentFlag.AlignLeft)
            value.setMinimumHeight(30)
            value.setWordWrap(False)

            tile_layout.addWidget(label)
            tile_layout.addWidget(value)
            return tile, value

        total_tile, self.total_value = create_stat_tile("Total ISBNs")
        processed_tile, self.processed_value = create_stat_tile("Processed")
        found_tile, self.found_value = create_stat_tile("Found")
        failed_tile, self.failed_value = create_stat_tile("Failed")
        stats_layout.addWidget(total_tile, 0, 0)
        stats_layout.addWidget(processed_tile, 0, 1)
        stats_layout.addWidget(found_tile, 0, 2)
        stats_layout.addWidget(failed_tile, 0, 3)

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
        self.start_button.setMinimumHeight(42)
        self.start_button.setMinimumWidth(150)

        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self._stop_harvest)
        self.stop_button.setEnabled(False)
        self.stop_button.setMinimumHeight(42)
        self.stop_button.setMinimumWidth(110)

        self.detailed_progress_button = QPushButton("Detailed Progress")
        self.detailed_progress_button.clicked.connect(self._show_progress_dialog)
        self.detailed_progress_button.setEnabled(False)
        self.detailed_progress_button.setMinimumHeight(42)
        self.detailed_progress_button.setMinimumWidth(170)

        self.api_health_button = QPushButton("API Health")
        self.api_health_button.clicked.connect(self._show_api_monitor_popup)
        self.api_health_button.setObjectName("SecondaryButton")
        self.api_health_button.installEventFilter(self)
        self.api_health_button.setMinimumHeight(42)
        self.api_health_button.setMinimumWidth(130)

        buttons_layout.addWidget(self.start_button)
        buttons_layout.addWidget(self.stop_button)
        buttons_layout.addWidget(self.detailed_progress_button)
        buttons_layout.addWidget(self.api_health_button)
        buttons_layout.addStretch()

        control_layout.addLayout(buttons_layout)

        # Advanced options (collapsed by default)
        self.advanced_group = QGroupBox("Advanced Options")
        # Avoid checkable/collapsible groupbox title overlap on macOS.
        self.advanced_group.setCheckable(False)
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
        self.log_text.setMinimumHeight(95)
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
        layout.addWidget(log_group, 1)
        self._pulse_timers = {}
        self.setStyleSheet(
            self.styleSheet() +
            " QToolTip { background-color: #1f201d; color: #e8e6df; "
            "border: 1px solid #3a3b35; border-radius: 8px; padding: 8px; }"
        )

    def set_advanced_mode(self, enabled):
        """Enable/disable advanced mode features."""
        self.advanced_mode = enabled
        self.advanced_group.setVisible(enabled)

        if enabled:
            self._log("Advanced mode enabled.")

    def set_data_sources(self, config_getter, targets_getter):
        """Set optional callbacks to retrieve config/targets from host UI."""
        self._config_getter = config_getter
        self._targets_getter = targets_getter
        self._check_start_conditions()

    def on_targets_changed(self, targets):
        """Compatibility hook for external target update wiring."""
        self.set_targets(targets)

    def _validate_input_file(
        self, file_path: Path, max_rows: int | None = None
    ) -> tuple[int, int, str | None]:
        """Return valid/invalid ISBN counts and optional error for an input file."""
        valid_count = 0
        invalid_count = 0
        delimiter = "," if file_path.suffix.lower() == ".csv" else "\t"

        try:
            with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f, delimiter=delimiter)
                for i, row in enumerate(reader, start=1):
                    raw_isbn = (row[0] or "").strip() if row else ""
                    if not raw_isbn or raw_isbn.startswith("#") or raw_isbn.lower().startswith("isbn"):
                        continue

                    if normalize_isbn(raw_isbn):
                        valid_count += 1
                    else:
                        invalid_count += 1

                    if max_rows is not None and i >= max_rows:
                        break
        except Exception as e:
            return 0, 0, str(e)

        return valid_count, invalid_count, None

    def _check_start_conditions(self):
        """Enable start only when we have a valid file and selected targets."""
        if self.is_running:
            return

        has_file = bool(self.input_file)
        selected_targets = [t for t in (self._get_targets() or []) if t.get("selected", True)]

        if not has_file:
            self.start_button.setEnabled(False)
            self.start_button.setText("Start Harvest")
            self.start_button.setToolTip("Select an input file first")
            return

        if not selected_targets:
            self.start_button.setEnabled(False)
            self.start_button.setText("Start Harvest")
            self.start_button.setToolTip("Select at least one target first")
            return

        count = self._input_valid_count if self._input_valid_count > 0 else "?"
        self.start_button.setEnabled(True)
        self.start_button.setText(f"Start Harvest ({count} ISBNs)")
        self.start_button.setToolTip("")

    def set_input_file(self, file_path):
        """Set the input file for harvesting."""
        if not file_path:
            self.input_file = None
            self._input_valid_count = 0
            self._check_start_conditions()
            return

        path = Path(file_path)
        if not path.exists():
            self.input_file = None
            self._input_valid_count = 0
            self._check_start_conditions()
            self._log(f"Invalid input path: {file_path}")
            return

        if path.suffix.lower() not in {".tsv", ".txt", ".csv"}:
            self.input_file = None
            self._input_valid_count = 0
            self._check_start_conditions()
            self._log(f"Unsupported input format: {path.suffix}")
            return

        file_size = path.stat().st_size
        is_large_file = file_size > LARGE_INPUT_FILE_THRESHOLD_BYTES
        max_rows = VALIDATION_SAMPLE_ROWS if is_large_file else None
        valid_count, invalid_count, error = self._validate_input_file(path, max_rows=max_rows)
        if error:
            self.input_file = None
            self._input_valid_count = 0
            self._check_start_conditions()
            self._log(f"Error validating input file '{path.name}': {error}")
            return

        if valid_count <= 0:
            self.input_file = None
            self._input_valid_count = 0
            self._check_start_conditions()
            self._log(f"No valid ISBNs found in {path.name}")
            return

        self.input_file = str(path)
        if is_large_file:
            self._input_valid_count = 0
            self._log(
                f"Large file accepted: {path.name} ({file_size / (1024 * 1024):.1f} MB). "
                f"Validated first {VALIDATION_SAMPLE_ROWS:,} rows; full processing happens during harvest."
            )
        else:
            self._input_valid_count = valid_count
            if invalid_count > 0:
                self._log(f"Input file set: {path.name} ({valid_count} valid, {invalid_count} invalid rows)")
            else:
                self._log(f"Input file set: {path.name} ({valid_count} valid rows)")
        self._check_start_conditions()

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
        # Always apply saved advanced settings to runtime behavior.
        # Advanced mode controls UI visibility, not whether settings are honored.
        advanced_settings = self._get_advanced_settings()

        selected_targets = [t for t in (targets or []) if t.get("selected", True)]
        if not selected_targets:
            QMessageBox.warning(self, "No Targets", "Please select at least one target in the Targets tab.")
            self._log("Harvest cancelled: no selected targets")
            return

        if not self._confirm_input_duplicates_policy():
            self._log("Harvest cancelled by user")
            return

        bypass_cache_isbns = self._check_cached_success_isbns()
        if bypass_cache_isbns is None:
            self._log("Harvest cancelled by user")
            return
        if bypass_cache_isbns:
            self._log(f"Bypassing cache for {len(bypass_cache_isbns)} ISBN(s)")

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
            bypass_cache_isbns=bypass_cache_isbns,
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
        self.status_badge.setText("Running")
        self.status_badge.setStyleSheet(
            "color: #7bc96f; font-size: 14px; font-weight: bold; padding: 6px 12px; "
            "background-color: #1f2a22; border-radius: 12px;"
        )

        # Create progress dialog if advanced mode
        if self.advanced_mode:
            self._create_progress_dialog()

        self._log("Harvest started")
        self.harvest_started.emit()
        self.status_message.emit("Harvest started")

    def _check_cached_success_isbns(self):
        """Warn when ISBNs are already successful in cache and allow bypass."""
        if not self.input_file:
            return set()
        input_path = Path(self.input_file)
        if input_path.exists() and input_path.stat().st_size > LARGE_INPUT_FILE_THRESHOLD_BYTES:
            self._log("Large input detected: skipping pre-harvest cache scan for responsiveness.")
            return set()

        try:
            db = DatabaseManager()
            db.init_db()
            isbns = parse_isbn_file(input_path).unique_valid
        except Exception as e:
            self._log(f"Warning: could not check cached ISBNs - {e}")
            return set()

        cached = []
        for isbn in isbns:
            rec = db.get_main(isbn)
            if rec is not None:
                cached.append((isbn, rec))

        if not cached:
            return set()

        details = []
        for isbn, rec in cached[:12]:
            source = rec.source or "unknown source"
            lccn = rec.lccn or "-"
            nlmcn = rec.nlmcn or "-"
            details.append(f"{isbn} | source: {source} | LCCN: {lccn} | NLMCN: {nlmcn}")

        if len(cached) > 12:
            details.append(f"... and {len(cached) - 12} more")

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Duplicate ISBNs Found")
        msg.setText(f"{len(cached)} ISBN(s) already have successful results in cache.")
        msg.setInformativeText(
            "Use cache to avoid duplicate processing, or bypass cache to force a fresh lookup."
        )
        msg.setDetailedText("\n".join(details))

        cancel_btn = msg.addButton("Cancel Harvest", QMessageBox.ButtonRole.RejectRole)
        use_cache_btn = msg.addButton("Use Cached Results", QMessageBox.ButtonRole.AcceptRole)
        bypass_btn = msg.addButton("Bypass Cache and Re-harvest", QMessageBox.ButtonRole.ActionRole)
        msg.setDefaultButton(use_cache_btn)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == cancel_btn:
            return None
        if clicked == bypass_btn:
            return {isbn for isbn, _ in cached}
        return set()

    def _confirm_input_duplicates_policy(self) -> bool:
        """Warn when duplicate ISBN rows exist in the input file."""
        if not self.input_file:
            return True
        input_path = Path(self.input_file)
        if input_path.exists() and input_path.stat().st_size > LARGE_INPUT_FILE_THRESHOLD_BYTES:
            self._log("Large input detected: skipping duplicate pre-scan and de-duplicating during harvest.")
            return True

        try:
            counts = {}
            with open(self.input_file, "r", encoding="utf-8-sig") as f:
                for line in f:
                    raw = line.strip().split("\t")[0]
                    if not raw or raw.lower().startswith("isbn") or raw.startswith("#"):
                        continue
                    normalized = normalize_isbn(raw)
                    if not normalized:
                        continue
                    counts[normalized] = counts.get(normalized, 0) + 1
        except Exception as e:
            self._log(f"Warning: could not inspect duplicate ISBN rows - {e}")
            return True

        duplicates = [(isbn, count) for isbn, count in counts.items() if count > 1]
        if not duplicates:
            return True

        details = [f"{isbn} | repeated {count} times" for isbn, count in duplicates[:12]]
        if len(duplicates) > 12:
            details.append(f"... and {len(duplicates) - 12} more")

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Duplicate ISBN Rows Detected")
        msg.setText(f"{len(duplicates)} ISBN(s) are repeated in the input file.")
        msg.setInformativeText(
            "The harvester processes unique ISBNs only. Continue to de-duplicate automatically."
        )
        msg.setDetailedText("\n".join(details))
        cancel_btn = msg.addButton("Cancel Harvest", QMessageBox.ButtonRole.RejectRole)
        continue_btn = msg.addButton("Continue with De-duplication", QMessageBox.ButtonRole.AcceptRole)
        msg.setDefaultButton(continue_btn)
        msg.exec()
        return msg.clickedButton() != cancel_btn

    def _check_recent_failed_isbns(self, retry_days):
        """Block retry-window ISBNs unless user explicitly overrides."""
        if not self.input_file or retry_days <= 0:
            return set()
        input_path = Path(self.input_file)
        if input_path.exists() and input_path.stat().st_size > LARGE_INPUT_FILE_THRESHOLD_BYTES:
            self._log("Large input detected: skipping pre-harvest retry-window scan for responsiveness.")
            return set()

        try:
            db = DatabaseManager()
            db.init_db()
            isbns = parse_isbn_file(input_path).unique_valid
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
        msg.setWindowTitle("Retry Window Active")
        msg.setText(
            f"{len(recent)} ISBN(s) are still within the {retry_days}-day retry window."
        )
        msg.setInformativeText(
            "Retrying now may produce repeated failures.\n"
            "Cancel to keep the retry rule, or override to continue anyway."
        )
        msg.setDetailedText("\n".join(details))

        cancel_btn = msg.addButton("Cancel Harvest", QMessageBox.ButtonRole.RejectRole)
        bypass_btn = msg.addButton("Override and Retry", QMessageBox.ButtonRole.ActionRole)
        msg.setDefaultButton(cancel_btn)

        msg.exec()
        clicked = msg.clickedButton()
        if clicked == bypass_btn:
            return {isbn for isbn, _ in recent}
        return None

    def _stop_harvest(self):
        """Stop the harvest operation."""
        if self.worker:
            self._log("Stopping harvest...")
            self.worker.stop()
            self.stop_button.setEnabled(False)
            self.status_badge.setText("Stopping...")
            self.status_badge.setStyleSheet(
                "color: #f4b860; font-size: 14px; font-weight: bold; padding: 6px 12px; "
                "background-color: #2f2a1f; border-radius: 12px;"
            )

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

    def _show_api_monitor_popup(self):
        """Show API health monitor in a medium-sized popup."""
        if self.api_monitor_dialog is None:
            self.api_monitor_dialog = QDialog(self)
            self.api_monitor_dialog.setWindowTitle("API Health Monitor")
            self.api_monitor_dialog.setModal(False)
            self.api_monitor_dialog.resize(860, 500)

            layout = QVBoxLayout(self.api_monitor_dialog)
            self.api_monitor_widget = APIMonitorTab(compact=True)
            layout.addWidget(self.api_monitor_widget)

        if self.api_monitor_widget:
            self.api_monitor_widget.refresh_status()
            self.api_monitor_widget._check_all_apis()
            self.quick_api_status = self.api_monitor_widget.status_snapshot()

        self.api_monitor_dialog.show()
        self.api_monitor_dialog.raise_()
        self.api_monitor_dialog.activateWindow()

    def eventFilter(self, obj, event):
        """Show quick API lights when hovering API Health button."""
        if obj is self.api_health_button:
            if event.type() == QEvent.Type.Enter:
                self._show_api_health_hover_tooltip()
                self._refresh_quick_api_status_async()
            elif event.type() == QEvent.Type.Leave:
                QToolTip.hideText()
        return super().eventFilter(obj, event)

    def _show_api_health_hover_tooltip(self):
        """Show compact green/red API lights on hover."""
        statuses = self.quick_api_status

        def dot(state) -> str:
            if state is None:
                color = "#666666"
            else:
                color = "#00cc66" if state else "#ff3333"
            return f"<span style='color:{color}; font-size:14px;'>●</span>"

        html = (
            "<b>API Health</b><br>"
            f"{dot(statuses.get('Library of Congress'))} LOC&nbsp;&nbsp;&nbsp;"
            f"{dot(statuses.get('Harvard'))} Harvard&nbsp;&nbsp;&nbsp;"
            f"{dot(statuses.get('OpenLibrary'))} OpenLibrary"
        )
        QToolTip.showText(
            self.api_health_button.mapToGlobal(QPoint(0, self.api_health_button.height() + 2)),
            html,
            self.api_health_button,
        )

    def _get_quick_api_status(self):
        """Return cached quick API status."""
        return dict(self.quick_api_status)

    def _refresh_quick_api_status_async(self):
        """Refresh hover status lights asynchronously to avoid UI lag."""
        if self.api_monitor_widget is not None:
            self.quick_api_status = self.api_monitor_widget.status_snapshot()
            self._show_api_health_hover_tooltip()
            return

        if self.hover_check_worker and self.hover_check_worker.isRunning():
            return

        selected_map = {t.get("name"): t.get("selected", True) for t in (self._get_targets() or [])}
        enabled_names = []
        for api_name in self.quick_api_status.keys():
            if selected_map and not selected_map.get(api_name, True):
                self.quick_api_status[api_name] = None
            else:
                enabled_names.append(api_name)

        self.hover_check_worker = APICheckWorker(enabled_names, timeout=3)
        self.hover_check_worker.completed.connect(self._on_hover_check_completed)
        self.hover_check_worker.start()

    def _on_hover_check_completed(self, results):
        for name in self.quick_api_status.keys():
            if name in results:
                self.quick_api_status[name] = results[name].get("online", False)
        if self.api_health_button.underMouse():
            self._show_api_health_hover_tooltip()

    def _toggle_pause(self):
        """Toggle pause state of harvest."""
        if self.worker:
            self.worker.toggle_pause()

    def _on_harvest_started(self):
        """Handle harvest started."""
        self.processed_count = 0
        self.total_count = 0
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

        if status in {"cached", "skipped", "found", "failed"}:
            self.processed_count += 1

        self.current_isbn_label.setText(f"Current ISBN: {isbn}")
        status_text = status.capitalize()
        if source:
            status_text += f" • {source}"
        self.current_status_label.setText(f"Status: {status_text}")
        if source:
            self.current_target_label.setText(f"Target: {source}")

        self._add_event_chip(status, source, isbn)

        extra = f" - {source}" if source else ""
        if status in {"failed", "skipped"} and message:
            extra += f" | {message}"
        self._log(f"{isbn}: {status}{extra}")

    def _on_harvest_complete(self, success, statistics):
        """Handle harvest completion."""
        self.is_running = False
        self._check_start_conditions()
        self.stop_button.setEnabled(False)
        self.detailed_progress_button.setEnabled(False)

        self._update_stats(statistics)

        if success:
            self.status_badge.setText("Completed")
            self.status_badge.setStyleSheet(
                "color: #a9d48f; font-size: 14px; font-weight: bold; padding: 6px 12px; "
                "background-color: #243329; border-radius: 12px;"
            )
            self._log(f"Harvest completed - Found: {statistics.get('found', 0)}, Failed: {statistics.get('failed', 0)}")
        else:
            self.status_badge.setText("Stopped")
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
        attempted = found + failed

        self._set_stat_value(self.total_value, str(total))
        self._set_stat_value(self.processed_value, str(processed))
        self._set_stat_value(self.found_value, str(found))
        self._set_stat_value(self.failed_value, str(failed))

        if total > 0:
            progress_percent = (processed / total) * 100
            self.progress_bar.setValue(int(progress_percent))
            hit_rate = (found / attempted) * 100 if attempted else 0
            self.success_rate_label.setText(f"Success Rate: {hit_rate:.1f}%")
            self.processed_meta_label.setText(f"Processed: {processed}/{total}")
        else:
            self.progress_bar.setValue(0)
            self.success_rate_label.setText("Success Rate: 0%")
            self.processed_meta_label.setText("Processed: 0/0")

        self.total_count = total

    def _set_stat_value(self, label, value):
        """Set stat value with a subtle pulse."""
        if label.text() == value:
            return
        label.setText(value)
        label.setStyleSheet("color: #c2d07f; font-size: 18px; font-weight: 700;")
        if label in self._pulse_timers:
            self._pulse_timers[label].stop()
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda l=label: l.setStyleSheet("color: #e8e6df; font-size: 18px; font-weight: 700;"))
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

    def _get_config(self):
        """Get configuration from config tab."""
        if callable(self._config_getter):
            try:
                config = self._config_getter()
                if isinstance(config, dict) and config:
                    return config
            except Exception as e:
                self._log(f"Warning: external config getter failed - {e}")

        parent = self.parent()
        while parent and not hasattr(parent, "config_tab"):
            parent = parent.parent()

        if parent and hasattr(parent, "config_tab"):
            return parent.config_tab.get_config()

        return {
            "call_number_mode": "lccn",
            "collect_lccn": True,
            "collect_nlmcn": False,
            "retry_days": 7,
        }

    def _get_targets(self):
        """Get targets from targets tab."""
        if callable(self._targets_getter):
            try:
                targets = self._targets_getter()
                if targets is not None:
                    return targets
            except Exception as e:
                self._log(f"Warning: external targets getter failed - {e}")

        if self._targets_override is not None:
            return self._targets_override

        parent = self.parent()
        while parent and not hasattr(parent, "targets_tab"):
            parent = parent.parent()

        if parent and hasattr(parent, "targets_tab"):
            return parent.targets_tab.get_targets()

        return []

    def set_targets(self, targets):
        """Set targets from main window updates."""
        self._targets_override = targets or []
        self._check_start_conditions()
        if self.api_monitor_widget:
            self.api_monitor_widget.refresh_status()

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
