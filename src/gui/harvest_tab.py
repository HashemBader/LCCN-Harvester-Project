"""Harvest execution page — input selection, run controls, and live progress display.

``HarvestTab`` is the main UI for starting and monitoring harvest runs.  It owns
the run-setup card (active profile label, input file, local run overrides), the
MARC Import card, the File Statistics card, the File Preview table, and the
action bar (Start/Pause/Cancel buttons with a thin progress bar).

The actual harvesting work is done by ``HarvestWorker`` (defined in
``harvest_support.py``) which runs in a ``QThread``.  ``HarvestTab`` wires the
worker's signals to its own slot methods and propagates higher-level events to
``ModernMainWindow`` via the signals declared on this class.

Key design decisions:
- UI state is managed through ``_transition_state(UIState)`` rather than ad hoc
  ``setEnabled``/``setVisible`` calls.  Every meaningful transition goes through
  this single method.
- Data sources (config, targets, profile, DB path) are injected lazily via
  ``set_data_sources`` so the tab is constructable without knowing the profile
  manager or config tab at import time.
- Live output files are opened once at harvest start and kept open for
  incremental writes; they are closed and converted to CSV in the worker's
  ``finally`` block.
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
from datetime import datetime, timedelta
from PyQt6.QtCore import Qt, QTimer, QTime, pyqtSignal, QSize, QUrl
from PyQt6.QtGui import QShortcut, QKeySequence, QColor, QBrush, QDesktopServices
from pathlib import Path
from enum import Enum, auto
from itertools import islice
import csv
import hashlib
import logging
import sys
import json

from .icons import SVG_HARVEST, SVG_INPUT, SVG_ACTIVITY
from .input_tab import ClickableDropZone
from .harvest_support import (
    DroppableGroupBox,
    HarvestWorker,
    _extract_call_number_classification,
    _extract_lc_classification,
    _looks_like_header_cell,
    _prepare_marc_import_records,
    _safe_filename,
)

from src.harvester.marc_import import MarcImportService
from src.harvester.run_harvest import parse_isbn_file
from src.database import DatabaseManager, now_datetime_str
from src.config.profile_manager import ProfileManager
from src.utils.isbn_validator import normalize_isbn
from .theme_manager import ThemeManager

logger = logging.getLogger(__name__)


def _friendly_error(exc: Exception) -> str:
    """Convert a technical exception into a plain-language message for end users."""
    msg = str(exc).lower()
    if "database is locked" in msg:
        return "The database is currently in use by another process. Please wait a moment and try again."
    if "no such table" in msg or "no such column" in msg:
        return "The database is missing required data. Try re-opening the application."
    if "disk" in msg or "no space" in msg:
        return "Your disk is full. Free up some space and try again."
    if "permission" in msg or "access is denied" in msg:
        return "Access denied. Check that you have permission to read/write the file or folder."
    if "file not found" in msg or "no such file" in msg:
        return "A required file could not be found. It may have been moved or deleted."
    if "corrupt" in msg or "malformed" in msg:
        return "The file appears to be corrupted. Try using a different file."
    if "timeout" in msg or "timed out" in msg:
        return "The operation timed out. Check your network connection and try again."
    if "connect" in msg or "network" in msg or "socket" in msg:
        return "Could not connect to the server. Check your internet connection."
    return "An unexpected error occurred. Please try again or contact support."


class UIState(Enum):
    """All possible states for the Harvest tab UI state machine.

    Transitions are managed exclusively by ``HarvestTab._transition_state``, which
    adjusts button visibility, banner colours, and ``is_running`` in one place.
    """

    IDLE = auto()       # No file loaded; Start button present but disabled.
    READY = auto()      # File loaded and targets available; Start button enabled.
    RUNNING = auto()    # Worker is actively processing ISBNs.
    PAUSED = auto()     # Worker is paused; Resume/Cancel available.
    COMPLETED = auto()  # Run finished successfully.
    ERROR = auto()      # Run ended with an unhandled exception.
    CANCELLED = auto()  # User cancelled the run mid-flight.


class HarvestTab(QWidget):
    """Harvest execution page widget.

    Signals:
        harvest_started(): Emitted when the worker thread begins processing.
        harvest_finished(bool, dict): Emitted when the run ends.  First argument
            indicates overall success; second is a stats dict (may include
            ``"cancelled": True`` or ``"error": str`` keys).
        harvest_reset(): Emitted when the user starts a new harvest session
            (pressing "New Harvest"), used to reset the sidebar pill to Idle.
        harvest_paused(bool): ``True`` = just paused, ``False`` = just resumed.
        progress_updated(isbn, status, source, message): Fired per ISBN for live
            dashboard activity feed updates.
        result_files_ready(dict): Emitted with the output file path dict so the
            dashboard can enable its "Open results" buttons as soon as files exist.
        live_result_ready(dict): Per-ISBN dict with ``isbn``, ``status``,
            ``detail`` for the dashboard recent-results table.
        live_stats_ready(RunStats): Batch stats dataclass emitted every 5 ISBNs
            for live KPI card updates without a DB round-trip.
        request_start_harvest(): Reserved for future delegation of the start
            action to the main window.
    """

    harvest_started = pyqtSignal()
    # (success: bool, stats: dict) — emitted after the worker thread ends, whether by completion,
    # cancellation, or error.  ``stats`` always contains "total", "found", "failed", "invalid".
    harvest_finished = pyqtSignal(bool, dict)
    # Emitted by _clear_input so the main window can reset the sidebar harvest-status pill to Idle.
    harvest_reset = pyqtSignal()
    # True = just paused, False = just resumed.
    harvest_paused = pyqtSignal(bool)
    # (isbn, status, source, message) — per-ISBN live feed for the dashboard activity label.
    progress_updated = pyqtSignal(str, str, str, str)
    # Emitted once at harvest start with the dict of per-bucket output file path strings.
    result_files_ready = pyqtSignal(dict)
    # Per-ISBN result dict {isbn, status, detail} for the dashboard recent-results panel.
    live_result_ready = pyqtSignal(dict)
    # Emitted every 5 ISBNs with a RunStats dataclass for live KPI card updates.
    live_stats_ready = pyqtSignal(object)

    # Reserved for future delegation of the start action to the main window.
    request_start_harvest = pyqtSignal()

    def __init__(self):
        """Initialise instance variables and build the UI.

        Key instance variables set here:
            worker (HarvestWorker | None): Active worker thread; ``None`` between runs.
            is_running (bool): Convenience flag; ``True`` when state is RUNNING or PAUSED.
            current_state (UIState): Current state-machine state.
            input_file (str | None): Absolute path of the currently loaded ISBN file.
            _last_session_* (list): Snapshots of worker result lists copied at run end.
            _run_live_paths (dict): Per-run output file path strings; populated in
                ``_start_worker`` and emitted via ``result_files_ready``.
            _config_getter / _targets_getter / _profile_getter / _db_path_getter:
                Callables injected by ``ModernMainWindow`` via ``set_data_sources``.
            _shortcut_modifier (str): ``"Meta"`` on macOS, ``"Ctrl"`` elsewhere.
        """
        super().__init__()
        self.worker = None      # Active HarvestWorker thread (None between runs).
        self.is_running = False # Convenience flag mirrors current_state in {RUNNING, PAUSED}.
        self.current_state = UIState.IDLE
        self.input_file = None  # Absolute path string of the currently loaded ISBN file.
        self._marc_selected_path = None
        # Session snapshots copied from the worker at harvest completion for later inspection.
        self._last_session_success = []
        self._last_session_failed = []
        self._last_session_invalid = []
        # Per-run output file paths dict; populated in _start_worker, emitted via result_files_ready.
        self._run_live_paths = {}
        # Callable dependencies injected by ModernMainWindow via set_data_sources().
        self._config_getter = None   # () -> dict
        self._targets_getter = None  # () -> list[dict]
        self._profile_getter = None  # () -> str
        self._db_path_getter = None  # () -> str | Path

        self.processed_count = 0  # ISBNs processed so far in the current run.
        self.total_count = 0       # Total unique valid ISBNs in the loaded file.
        # Platform-specific modifier key for keyboard shortcuts (Cmd on macOS, Ctrl elsewhere).
        self._shortcut_modifier = "Meta" if sys.platform == "darwin" else "Ctrl"

        self._setup_ui()
        self._setup_shortcuts()
        self._update_scrollbar_policy()

    def set_data_sources(self, config_getter, targets_getter, profile_getter=None, db_path_getter=None):
        """Inject lazy data-source callbacks so the tab can be constructed before the app is fully initialised.

        Called by ``ModernMainWindow.__init__`` after all tabs are created.

        Args:
            config_getter: Callable ``() -> dict`` returning the active profile's settings.
            targets_getter: Callable ``() -> list[dict]`` returning the current target list.
            profile_getter: Optional callable ``() -> str`` returning the active profile name.
            db_path_getter: Optional callable ``() -> str | Path`` returning the DB path.
        """
        self._config_getter = config_getter
        self._targets_getter = targets_getter
        self._profile_getter = profile_getter
        self._db_path_getter = db_path_getter
        self._refresh_active_profile_label()

    def _refresh_active_profile_label(self):
        """Refresh the read-only profile label shown on the Harvest setup card."""
        if not hasattr(self, "lbl_active_profile"):
            return
        profile_name = "Default Settings"
        if self._profile_getter:
            try:
                profile_name = self._profile_getter() or profile_name
            except Exception:
                pass
        self.lbl_active_profile.setText(f"Active profile: {profile_name}")

    def on_targets_changed(self, targets):
        """Re-evaluate the Start button state when the user changes target selections.

        Connected to ``TargetsTab`` via ``ModernMainWindow``.  Ignored while a harvest
        is running, paused, or showing a terminal result so mid-run target changes
        cannot corrupt the active worker's target list.

        Args:
            targets: Updated list of target config dicts (currently unused; presence
                     check is done in ``_check_start_conditions``).
        """
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
        """Build the full harvest-tab UI.

        Layout (top to bottom):
        1. Header bar — section title and subtitle.
        2. Status banner — live state text (READY / RUNNING / etc.) and summary stats.
        3. 2×2 grid — Run Setup (top-left), File Statistics (top-right),
           MARC Import (bottom-left), File Preview (bottom-right).
        4. Action bar — status pill, elapsed timer, progress counter, log label,
           and action buttons (Start / Pause / Cancel / New Harvest) over a thin
           progress bar.
        """
        # Direct layout — no scroll area; everything must fit in one screen.
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
        # Keep the top row pinned neatly under the status banner. The upper
        # cards should use their natural height, while the lower row absorbs
        # the remaining vertical space when the action/completion area is shown.
        self.content_grid = QGridLayout()
        self.content_grid.setContentsMargins(0, 6, 0, 0)
        self.content_grid.setSpacing(12)
        self.content_grid.setColumnStretch(0, 1)
        self.content_grid.setColumnStretch(1, 1)
        self.content_grid.setRowStretch(0, 0)
        self.content_grid.setRowStretch(1, 1)

        # ── LEFT: Run Setup card ───────────────────────────────────────────────
        self.input_card = DroppableGroupBox("Run Setup")
        self.input_card.file_dropped.connect(self.set_input_file)
        self.input_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        input_layout = QVBoxLayout(self.input_card)
        input_layout.setContentsMargins(16, 10, 16, 10)
        input_layout.setSpacing(6)

        setup_grid = QGridLayout()
        setup_grid.setSpacing(6)
        setup_grid.setColumnStretch(1, 1)

        self.lbl_active_profile = QLabel("Active profile: Default Settings")
        self.lbl_active_profile.setProperty("class", "HelperText")
        self.lbl_active_profile.setToolTip("Runs use the active profile's Configure settings.")
        setup_grid.addWidget(self.lbl_active_profile, 0, 0, 1, 2)

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
        setup_grid.addWidget(lbl_input, 1, 0)
        setup_grid.addLayout(file_input_layout, 1, 1)

        self.chk_marc_only = QCheckBox("MARC only for this run")
        self.chk_marc_only.setToolTip(
            "Use the active Configure rules and search only records already imported into the local database"
        )
        self.chk_marc_only.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_marc_only.setMinimumHeight(32)
        self.chk_marc_only.toggled.connect(self._on_marc_only_toggled)
        setup_grid.addWidget(self.chk_marc_only, 2, 1)

        self.chk_db_only = QCheckBox("Database only for this run")
        self.chk_db_only.setToolTip("Skip APIs and Z39.50 targets and search only the existing SQLite database")
        self.chk_db_only.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_db_only.setMinimumHeight(32)
        self.chk_db_only.toggled.connect(self._on_db_only_toggled)
        setup_grid.addWidget(self.chk_db_only, 3, 1)
        self._apply_db_only_checkbox_style()
        input_layout.addLayout(setup_grid)
        input_layout.addStretch()

        # ── MARC Import card (bottom-left) ────────────────────────────────────
        marc_card = QGroupBox("MARC Import")
        marc_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        marc_vbox = QVBoxLayout(marc_card)
        marc_vbox.setContentsMargins(14, 12, 14, 14)
        marc_vbox.setSpacing(10)

        # 1. Four stat tiles in a row
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

        # 2. Drop zone — expands to fill remaining space
        self._marc_drop_zone = DroppableGroupBox(
            "",
            accepted_extensions=(".mrc", ".marc", ".xml"),
            invalid_message="Please drop a valid MARC file (.mrc, .marc, or .xml).",
        )
        self._marc_drop_zone.file_dropped.connect(self._set_marc_file)
        self._marc_drop_zone.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._marc_drop_zone.setProperty("class", "MarcDropZone")
        drop_zone_vbox = QVBoxLayout(self._marc_drop_zone)
        self._marc_hint_label = QLabel("Drop .mrc or .xml file here")
        self._marc_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._marc_hint_label.setWordWrap(True)
        self._marc_hint_label.setStyleSheet("font-size: 13px;")
        self._marc_status_label = self._marc_hint_label
        drop_zone_vbox.addWidget(self._marc_hint_label)
        self._marc_progress_bar = QProgressBar()
        self._marc_progress_bar.setProperty("class", "TerminalProgressBar")
        self._marc_progress_bar.setProperty("state", "idle")
        self._marc_progress_bar.setRange(0, 100)
        self._marc_progress_bar.setValue(0)
        self._marc_progress_bar.setTextVisible(False)
        self._marc_progress_bar.setVisible(False)
        self._marc_progress_bar.setFixedHeight(8)
        drop_zone_vbox.addWidget(self._marc_progress_bar)
        marc_vbox.addWidget(self._marc_drop_zone, stretch=1)

        # 3. File display plus actions at bottom
        marc_file_box = QVBoxLayout()
        marc_file_box.setSpacing(6)
        self._marc_path_edit = QLineEdit()
        self._marc_path_edit.setReadOnly(True)
        self._marc_path_edit.setPlaceholderText("No MARC file selected… (.mrc binary or .xml MARCXML)")
        self._marc_path_edit.setProperty("class", "LineEdit")
        self._marc_path_edit.setMinimumWidth(0)
        self._marc_path_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        marc_file_box.addWidget(self._marc_path_edit)

        marc_file_row = QHBoxLayout()
        marc_file_row.setSpacing(6)
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
        marc_file_row.addStretch()
        marc_file_row.addWidget(self._btn_clear_marc)
        marc_file_row.addWidget(self._btn_browse_marc)
        marc_file_row.addWidget(self._btn_import_marc)
        marc_file_box.addLayout(marc_file_row)
        marc_vbox.addLayout(marc_file_box)

        self.stats_card = QGroupBox("File Statistics")
        self.stats_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        stats_card_layout = QVBoxLayout(self.stats_card)
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
        # Placeholder column headers shown before any file is loaded.
        self.preview_table.setColumnCount(2)
        self.preview_table.setHorizontalHeaderLabels(["ISBN", "Status"])
        self.preview_table.setRowCount(0)
        preview_frame_layout.addWidget(self.preview_table, stretch=1)

        # Keep preview_text as hidden attribute for backward compat
        self.info_label = QLabel("No file selected")
        self.info_label.setVisible(False)
        self.preview_text = QTextEdit()
        self.preview_text.setVisible(False)

        self.content_grid.addWidget(self.input_card, 0, 0)
        self.content_grid.addWidget(self.stats_card, 0, 1)
        self.content_grid.addWidget(marc_card, 1, 0)
        self.content_grid.addWidget(preview_frame, 1, 1)

        layout.addLayout(self.content_grid, stretch=1)

        # ── 4. Status pill + elapsed timer ────────────────────────────────────
        self.lbl_run_status = QLabel("Idle")
        self.lbl_run_status.setProperty("class", "StatusPill")
        self.lbl_run_elapsed = QLabel("00:00:00")
        self.lbl_run_elapsed.setProperty("class", "ActivityValue")

        # Elapsed-time timer: fires every 1 000 ms to increment lbl_run_elapsed.
        # timer_is_paused stops the count while the harvest is paused.
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

        BTN_H = 36  # Uniform height for all action-bar buttons, in pixels.

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

        # Thin 6 px progress bar at the bottom of the action card.
        # The "state" dynamic property ("running", "success", "idle") drives QSS colour.
        self.progress_bar = QProgressBar()
        self.progress_bar.setProperty("class", "TerminalProgressBar")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)  # intentionally slim — purely decorative/informational
        self.progress_bar.setStyleSheet(
            "QProgressBar { border-radius: 3px; } QProgressBar::chunk { border-radius: 3px; }"
        )
        action_layout.addWidget(self.progress_bar)
        layout.addWidget(action_frame)

        self._transition_state(UIState.IDLE)

    def _confirm_db_only_without_targets(self) -> bool:
        """Ask the user to confirm running with no targets (database-only mode).

        Shown when the user clicks Start with zero selected targets.  An informational
        message explains that the run will search only the existing SQLite database.

        Returns:
            ``True`` if the user accepted (will run DB-only), ``False`` if cancelled.
        """
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
        """Central state machine: update every piece of UI that depends on the run state.

        All button visibility, banner colour, status label text, and ``is_running``
        flag changes go through here.  Calling code should never set these properties
        directly; always call this method instead.

        Args:
            state: The new ``UIState`` to transition to.
            **kwargs: Optional per-state data (e.g. ``count=<int>`` for READY to
                      display the ISBN count on the Start button).
        """
        self.current_state = state

        # Default all action buttons to hidden/disabled
        self.btn_start.setVisible(False)
        self.btn_pause.setVisible(False)
        self.btn_stop.setVisible(False)
        self.btn_new_run.setVisible(False)

        # Update is_running flag based on state
        self.is_running = state in (UIState.RUNNING, UIState.PAUSED)
        input_controls_enabled = not self.is_running
        self.btn_browse.setEnabled(input_controls_enabled)
        self.btn_clear_file.setEnabled(input_controls_enabled and not self.btn_clear_file.isHidden())

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

                # Revert any terminal-state colour (green/red) back to the default "running" style.
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

        # Force QSS to re-evaluate the "state" property on the banner and pill labels.
        # unpolish + polish is the canonical way to refresh dynamic-property-driven QSS rules.
        self.banner_frame.style().unpolish(self.banner_frame)
        self.banner_frame.style().polish(self.banner_frame)
        self.lbl_run_status.style().unpolish(self.lbl_run_status)
        self.lbl_run_status.style().polish(self.lbl_run_status)
        self.lbl_banner_title.style().unpolish(self.lbl_banner_title)
        self.lbl_banner_title.style().polish(self.lbl_banner_title)
        # Clear the inline orange style on the Pause button when we leave the active states.
        if state not in (UIState.RUNNING, UIState.PAUSED):
            self.btn_pause.setStyleSheet("")

        self.lbl_banner_title.setText(title_text)
        self.lbl_banner_stats.setVisible(show_stats)

    def _setup_shortcuts(self):
        """Register keyboard shortcuts for common harvest actions.

        Uses the platform-appropriate modifier (Cmd on macOS, Ctrl elsewhere):
        - Mod+O: Browse for input file.
        - Mod+Enter: Start harvest.
        - Mod+.: Cancel harvest.
        """
        mod = self._shortcut_modifier
        QShortcut(QKeySequence(f"{mod}+O"), self, activated=self._browse_file)
        QShortcut(QKeySequence(f"{mod}+Return"), self, activated=self._on_start_clicked)
        QShortcut(QKeySequence(f"{mod}+."), self, activated=self._stop_harvest)

    def _update_scrollbar_policy(self):
        """Reserved hook called on every resize event. Currently no scroll-policy adjustment is needed."""

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scrollbar_policy()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            self._update_scrollbar_policy()

    def set_input_file(self, path):
        """Load an ISBN input file, validate it, and update all related UI controls.

        Parses the file with ``parse_isbn_file`` (sampling the first 200 k lines for
        files > 20 MB), populates the File Statistics tiles, runs the preview table,
        and calls ``_check_start_conditions`` to decide whether to enable Start.

        If the file contains no valid ISBNs, the UI transitions to the ERROR state
        and the input is not stored.

        Args:
            path: Absolute path string, or empty/``None`` to clear the current file.
        """
        if self.current_state in (UIState.RUNNING, UIState.PAUSED):
            return

        if not path:
            self._clear_input()
            return

        # If the user picks a new file after a run, reset only the harvest setup UI.
        # Dashboard results stay visible until another harvest actually starts.
        if self.current_state in (UIState.COMPLETED, UIState.CANCELLED):
            self._clear_input(emit_reset=False)

        path_obj = Path(path)

        # Extension filtering is not enforced here; parse_isbn_file returns 0 valid rows
        # for binary/non-text files, which triggers the "no valid ISBNs" error path below.

        # Content Check (Real Validation)
        try:
            size_kb = path_obj.stat().st_size / 1024
            # For files larger than 20 MB, parse only the first 200 k lines to keep the UI responsive.
            sampled = path_obj.stat().st_size > 20 * 1024 * 1024  # 20 MB threshold
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

            # Show the invalid count in red when non-zero; unpolish/polish forces the QSS re-evaluation.
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
            self._load_file_preview()

            self._check_start_conditions(unique_valid)

        except Exception as e:
            self._set_invalid_state(path_obj.name, _friendly_error(e))

    def _check_start_conditions(self, isbn_count=None):
        """Evaluate whether the Start button should be enabled.

        The only pre-flight requirement checked here is that a valid input file is
        loaded.  Target availability is validated at harvest time in
        ``_on_start_clicked`` so the user is not blocked from loading a file before
        configuring targets.

        Args:
            isbn_count: Optional override for the displayed ISBN count (used after a
                fresh file load to avoid re-parsing just to get the count).
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
            self._show_preview_message("Could not load preview.")

    def _show_preview_message(self, msg: str):
        """Show a single-cell message in the preview table."""
        self.preview_table.setColumnCount(1)
        self.preview_table.setRowCount(1)
        self.preview_table.setHorizontalHeaderLabels(["Info"])
        self.preview_table.setItem(0, 0, QTableWidgetItem(msg))

    def _apply_db_only_checkbox_style(self):
        """Apply a theme-aware text colour to the DB-only checkbox label.

        ``QCheckBox`` text colour can be overridden by global QSS rules that make it
        invisible on certain themes; this method ensures the local-run option labels
        are always readable by reading the active theme from ``ThemeManager`` and
        applying an explicit inline style.
        """
        is_dark = ThemeManager().get_theme() == "dark"
        text_color = "#f9fafb" if is_dark else "#000000"
        style = (
            "QCheckBox {"
            "  color: " + text_color + ";"
            "  font-size: 13px;"
            "  font-weight: 700;"
            "  spacing: 10px;"
            "  padding: 5px 0;"
            "}"
            "QCheckBox::indicator {"
            "  width: 16px;"
            "  height: 16px;"
            "}"
        )
        for checkbox in (getattr(self, "chk_marc_only", None), getattr(self, "chk_db_only", None)):
            if checkbox is not None:
                checkbox.setStyleSheet(style)

    def _on_marc_only_toggled(self, checked: bool):
        """Keep MARC-only and database-only run overrides mutually exclusive."""
        if checked and hasattr(self, "chk_db_only") and self.chk_db_only.isChecked():
            self.chk_db_only.blockSignals(True)
            self.chk_db_only.setChecked(False)
            self.chk_db_only.blockSignals(False)

    def _on_db_only_toggled(self, checked: bool):
        """Keep database-only and MARC-only run overrides mutually exclusive."""
        if checked and hasattr(self, "chk_marc_only") and self.chk_marc_only.isChecked():
            self.chk_marc_only.blockSignals(True)
            self.chk_marc_only.setChecked(False)
            self.chk_marc_only.blockSignals(False)

    def _load_file_preview(self):
        """Populate the preview table with the first 20 valid ISBN rows from the input file.

        Reads lines one at a time, normalises the first column as an ISBN, skips a
        recognised header row (via ``_looks_like_header_cell``), and stops once 20
        rows have been collected.  Each row shows the raw cell text and a colour-coded
        "Valid"/"Invalid" status in the second column.
        """
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
            self._show_preview_message("Could not load preview.")

    def _copy_preview_content(self):
        """Copy the preview table's data columns (excluding Status) to the clipboard as TSV."""
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
        The selected input file is preserved for the current GUI session so the
        user can pick a profile after choosing an ISBN file without reselecting it.
        """
        if self.current_state in (UIState.RUNNING, UIState.PAUSED):
            return
        self._refresh_active_profile_label()
        self.run_timer.stop()
        self.run_time = QTime(0, 0, 0)
        self.lbl_run_elapsed.setText("00:00:00")
        self.timer_is_paused = False
        self.processed_count = 0
        self.total_count = 0
        self.lbl_progress_text.setText("0 / 0")
        self.progress_bar.setValue(0)
        self.log_output.setText("Ready...")
        self.log_output.setProperty("state", "idle")
        self.log_output.style().unpolish(self.log_output)
        self.log_output.style().polish(self.log_output)

        if self.input_file and Path(self.input_file).exists():
            self._check_start_conditions()
        else:
            self._clear_input(emit_reset=False)
        self.harvest_reset.emit()

    def _clear_input(self, *args, emit_reset=True):
        """Reset all input-related UI controls and session state to a clean IDLE baseline.

        Clears the file path, File Statistics tiles, preview table, progress bar,
        and log label.  Forces QSS re-evaluation on dynamic-property widgets
        (``log_output``, ``lbl_val_invalid``, ``progress_bar``) via unpolish/polish.
        Emits ``harvest_reset`` to notify the main window to reset the sidebar pill
        unless ``emit_reset`` is false.
        """
        if self.current_state in (UIState.RUNNING, UIState.PAUSED):
            return

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
        # Restore the preview table to the same empty baseline shown on first load.
        self.preview_table.clearContents()
        self.preview_table.setColumnCount(2)
        self.preview_table.setRowCount(0)
        self.preview_table.setHorizontalHeaderLabels(["ISBN", "Status"])
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
        if emit_reset:
            self.harvest_reset.emit()

    def _set_invalid_state(self, filename, error_msg):
        """Display an error state when the loaded file contains no valid ISBNs.

        Clears stats tiles, shows the error message in the log label (red via QSS
        ``"error"`` state), and transitions to ``UIState.ERROR``.

        Args:
            filename: Name of the file (for display in the path edit only).
            error_msg: Human-readable description of the problem.
        """
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
        self.preview_text.setText(error_msg)

        self.progress_bar.setFormat("0 / 0")
        self.log_output.setText(error_msg)
        self.log_output.setProperty("state", "error")
        self.log_output.style().unpolish(self.log_output)
        self.log_output.style().polish(self.log_output)

        self._transition_state(UIState.ERROR)

    def _browse_file(self):
        """Open the system file picker and load the selected ISBN input file."""
        if self.current_state in (UIState.RUNNING, UIState.PAUSED):
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select ISBN Input File",
            "",
            "All Files (*.*);;Excel Files (*.xlsx *.xls);;TSV Files (*.tsv);;Text Files (*.txt);;CSV Files (*.csv)",
        )
        if file_path:
            self.set_input_file(file_path)

    def _on_start_clicked(self):
        """Validate pre-conditions and delegate to ``_start_worker`` to begin a harvest run.

        Steps performed:
        1. Retrieve the active profile config via ``_config_getter``.
        2. Query the DB for ISBNs still within the retry window (``_check_recent_not_found_isbns``).
        3. Normalize ``call_number_mode`` from the active Configure profile.
        4. Map the profile stop rule to internal ``stop_rule`` / ``both_stop_policy`` values.
        5. Check selected targets; show a confirmation if none are selected and the user
           opts to continue (DB-only mode).
        6. Call ``_start_worker``.
        """
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
        
        # Use Configure as the source of truth for call-number mode and stop rule.
        configured_mode = (config.get("call_number_mode", "lccn") or "lccn").strip().lower()
        mode_text = {
            "nlmcn": "NLM Only",
            "both": "Both (LCCN & NLM)",
        }.get(configured_mode, "LCCN Only")
        if mode_text == "NLM Only":
            config["call_number_mode"] = "nlmcn"
            config["both_stop_policy"] = "nlmcn"
            config["db_only"] = False
        elif mode_text == "Both (LCCN & NLM)":
            config["call_number_mode"] = "both"
            config["db_only"] = False
            saved_stop_rule = (config.get("stop_rule", "stop_either") or "stop_either").strip().lower()
            stop_text = {
                "stop_lccn": "Stop if LCCN found",
                "stop_nlmcn": "Stop if NLMCN found",
                "continue_both": "Continue until both found",
            }.get(saved_stop_rule, "Stop if either found")

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
        else:
            config["call_number_mode"] = "lccn"
            config["both_stop_policy"] = "lccn"
            config["db_only"] = False

        # 2. Get Targets
        targets = self._targets_getter() if self._targets_getter else []
        selected_targets = [t for t in targets if t.get("selected", True)]
        explicit_marc_only = self.chk_marc_only.isChecked()
        explicit_db_only = self.chk_db_only.isChecked()

        if explicit_marc_only:
            config["db_only"] = True
            self.log_output.setText(
                "MARC-only mode enabled for this run. Using the active profile rules."
            )
        elif explicit_db_only:
            config["db_only"] = True
            self.log_output.setText(
                "Database-only mode enabled for this run. Skipping live targets."
            )
        elif not selected_targets:
            if not self._confirm_db_only_without_targets():
                self.log_output.setText("Harvest cancelled: no targets selected.")
                return
            config["db_only"] = True
            self.log_output.setText(
                "No targets selected. Running against the existing database only."
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
        """Instantiate and start the harvest worker thread for a new run.

        Computes unique timestamped output file paths for this run, emits
        ``result_files_ready`` so the dashboard can enable its file-open buttons,
        wires all worker signals, and starts the ``QThread``.

        Args:
            config: Settings dict (retry_days, call_number_mode, etc.).
            targets: List of target config dicts from TargetsTab.
            bypass_retry_isbns: Optional set of ISBNs to rerun despite the retry window.
        """
        # Guard against double-click launching a second worker on top of a running one.
        if self.worker and self.worker.isRunning():
            return

        self.run_timer.stop()
        self.run_time = QTime(0, 0, 0)
        self.lbl_run_elapsed.setText("00:00:00")
        self.timer_is_paused = False

        # Compute timestamped output file names for this run.
        profile = "default"
        if self._profile_getter:
            try:
                profile = _safe_filename(self._profile_getter() or "default")
            except Exception:
                pass
        date_str = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        # Use a per-run timestamp so repeated harvests never overwrite previous output.
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

        self.worker = HarvestWorker(
            self.input_file,
            config,
            targets,
            advanced_settings=self._load_advanced_settings(),
            bypass_retry_isbns=bypass_retry_isbns,
            live_paths=self._run_live_paths,
            db_path=db_path,
        )
        # Signal wiring: all worker → UI connections use queued cross-thread delivery.
        # stats_update is connected twice:
        #   1. _on_stats: updates the local progress bar / counter label.
        #   2. live_stats_ready.emit: re-emits the RunStats dataclass to the dashboard
        #      KPI cards without an extra DB query.
        self.worker.progress_update.connect(self._on_progress)
        self.worker.harvest_complete.connect(self._on_complete)
        self.worker.stats_update.connect(self._on_stats)
        self.worker.stats_update.connect(self.live_stats_ready.emit)
        self.worker.status_message.connect(self._on_status)
        # Re-emit per-ISBN live results directly to the dashboard's recent-results panel.
        self.worker.live_result.connect(self.live_result_ready.emit)

        self._transition_state(UIState.RUNNING)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0/0 (0%)")

        self.worker.start()
        # Elapsed timer fires every 1 000 ms to update lbl_run_elapsed.
        self.run_timer.start(1000)

        self.harvest_started.emit()

    def _update_timer(self):
        """Increment ``run_time`` by one second and refresh the elapsed label.

        No-op when the harvest is paused (``timer_is_paused`` is ``True``) so the
        displayed elapsed time freezes during a pause.
        """
        if not self.timer_is_paused:
            self.run_time = self.run_time.addSecs(1)
            self.lbl_run_elapsed.setText(self.run_time.toString("hh:mm:ss"))

    def _stop_harvest(self):
        """Request a clean cancellation of the running harvest.

        Sets the worker's ``_stop_requested`` flag (which causes ``progress_callback``
        to raise ``HarvestCancelled`` at the next ISBN boundary), stops the elapsed
        timer, and updates labels/buttons to show a "CANCELLING…" state while the
        worker finishes its current ISBN.
        """
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
        """Pause or resume the running harvest worker.

        Reads the worker's new ``_pause_requested`` state immediately after toggling
        to decide which UIState to transition to.  The elapsed timer is also paused/
        resumed to keep the reported time accurate.
        """
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
        """Yield normalized ISBNs from the currently loaded input file.

        Skips blank rows, rows whose first cell starts with ``#`` (comment), and
        rows that look like a header (first cell starts with ``isbn``).  Uses a comma
        delimiter for ``.csv`` files and tab for everything else.

        Yields:
            Normalised ISBN strings (digits only, no hyphens).
        """
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

    @staticmethod
    def _parse_retry_attempted_datetime(value):
        """Parse retry-attempt storage formats into a datetime, or ``None``."""
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value.astimezone().replace(tzinfo=None) if value.tzinfo else value

        text = str(value).strip()
        if not text:
            return None
        if text.endswith(".0") and text[:-2].isdigit():
            text = text[:-2]
        if text.isdigit() and len(text) == 8:
            return datetime(int(text[:4]), int(text[4:6]), int(text[6:8]))

        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone().replace(tzinfo=None) if parsed.tzinfo else parsed

    @classmethod
    def _format_retry_window_dates(cls, last_attempted, retry_days: int):
        """Return display strings for the last-attempt and next retry dates."""
        last_dt = cls._parse_retry_attempted_datetime(last_attempted)
        if last_dt is None:
            last_str = str(last_attempted) if last_attempted is not None else "Unknown"
            return last_str, "Unknown"
        try:
            retry_days = int(retry_days or 0)
        except Exception:
            retry_days = 0
        next_dt = last_dt + timedelta(days=retry_days)
        return last_dt.strftime("%Y-%m-%d"), next_dt.strftime("%Y-%m-%d")

    def _check_recent_not_found_isbns(self, retry_days: int):
        """Warn the user when ISBNs in the input file are still within the retry window.

        Queries the DB for any ISBNs from the input file that have a recent "not found"
        failure within the configured retry window and shows a dialog offering three choices:

        - **Override and Re-run Now**: returns a set of those ISBNs so the worker bypasses the
          retry check for them.
        - **Continue (Keep Retry Rules)**: returns an empty set — those ISBNs will be skipped by
          the worker as normal.
        - **Cancel Harvest**: returns ``None`` — the harvest is aborted before starting.

        Args:
            retry_days: Number of days in the retry window (from the active profile config).

        Returns:
            - ``set()`` — proceed with retry rules intact.
            - ``set(str)`` — proceed but bypass retry for the returned ISBNs.
            - ``None`` — abort; user cancelled.
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
            last_str, next_str = self._format_retry_window_dates(att.last_attempted, retry_days)
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
        """Return ``True`` if *error_text* represents a "not found" outcome eligible for retry.

        These are the patterns that should trigger the retry-window warning dialog, as
        opposed to connectivity or server errors that would be handled separately.

        Args:
            error_text: Raw error string from a harvest attempt record.

        Returns:
            ``True`` if the error indicates a negative lookup (no call number found).
        """
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
        """Load the advanced settings JSON file if it exists.

        The advanced settings file (``data/advanced_settings.json``) stores
        optional overrides for ``parallel_workers``, ``connection_timeout``, and
        ``max_retries``.  Returns an empty dict on any error so the worker falls
        back to its own defaults.

        Returns:
            Dict of advanced setting overrides, or ``{}`` if the file is absent or invalid.
        """
        settings_path = Path("data/advanced_settings.json")
        if not settings_path.exists():
            return {}
        try:
            return json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _on_progress(self, isbn, status, source, msg):
        """Update the log label and re-emit the progress signal to the main window.

        Connected to ``HarvestWorker.progress_update``.

        Args:
            isbn: The ISBN that just produced an event.
            status: Short status string (e.g. ``"found"``, ``"failed"``).
            source: Target name that produced the result.
            msg: Human-readable log line to display.
        """
        log_msg = msg
        self.log_output.setText(log_msg)
        # Re-emit so ModernMainWindow can relay the event to the dashboard activity label.
        self.progress_updated.emit(isbn, status, source, msg)

    def _on_stats(self, stats):
        """Update the progress counter and bar when a RunStats batch update arrives.

        Connected to both ``HarvestWorker.stats_update`` and indirectly to the dashboard
        via the ``live_stats_ready`` re-emission in ``_start_worker``.

        Args:
            stats: A ``RunStats`` dataclass or legacy dict (getattr/get used for compat).
        """
        # Use getattr so this slot also handles a legacy dict payload gracefully.
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
        """Display a status message in the action-bar log label.

        Connected to ``HarvestWorker.status_message``.  Used for high-level
        lifecycle messages (starting, completed, cancelled) rather than per-ISBN
        progress events.

        Args:
            msg: Human-readable status line.
        """
        self.log_output.setText(msg)

    def _on_complete(self, success, stats):
        """Handle harvest completion, cancellation, or error from the worker thread.

        Connected to ``HarvestWorker.harvest_complete``.  Snapshots the worker's
        session result lists, transitions the UI state, updates the progress bar,
        and emits ``harvest_finished`` to the main window.

        Args:
            success: ``True`` if the run completed without error/cancellation.
            stats: Summary dict with keys "total", "found", "failed", "invalid",
                   and optionally "error" (str) or "cancelled" (True).
        """
        self.is_running = False
        self.run_timer.stop()

        # Snapshot session results from the worker thread BEFORE any subsequent DB query
        # overwrites them (the worker object persists until the next run).
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
                # Keep the full technical message in the log for debugging,
                # but show a plain-language dialog to the user.
                self.log_output.setText(f"Harvest stopped unexpectedly. See details below.\n\n{error_msg}")
                self.log_output.setProperty("state", "error")
                self.log_output.style().unpolish(self.log_output)
                self.log_output.style().polish(self.log_output)
                QMessageBox.critical(
                    self,
                    "Harvest Stopped",
                    "The harvest stopped unexpectedly and could not complete.\n\n"
                    "This is usually caused by a database access issue or a problem writing output files. "
                    "Check that the output folder exists and that you have write permission, then try again.",
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

            # Switch the progress bar to the green "success" QSS style.
            self.progress_bar.setProperty("state", "success")
            self.progress_bar.style().unpolish(self.progress_bar)
            self.progress_bar.style().polish(self.progress_bar)

        self.harvest_finished.emit(success, stats)

    def _update_banner_paths(self):
        """Update banner file-button labels and the output folder label for the current run.

        Reads ``_run_live_paths`` (populated in ``_start_worker``) and sets the text
        on the banner success/failed/invalid buttons to the filename portion of each path.
        """
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
        """Open *folder* in the platform's native file manager.

        Uses Qt's cross-platform ``QDesktopServices`` helper so the same code
        path works across macOS, Windows, and Linux desktop environments.
        Creates the folder first if it does not exist.

        Args:
            folder: ``Path`` object for the directory to open.
        """
        folder = folder.resolve()
        folder.mkdir(parents=True, exist_ok=True)
        self._open_local_path(folder, missing_title="Folder Not Found", open_title="Open Failed")

    def _open_output_folder(self):
        """Open the top-level ``data/`` folder in the platform's native file manager."""
        out_path = Path("data").resolve()
        out_path.mkdir(parents=True, exist_ok=True)
        self._open_local_path(out_path, missing_title="Folder Not Found", open_title="Open Failed")

    def _open_file_in_explorer(self, relative_path: str):
        """Open a specific file in the default associated application."""
        file_path = Path(relative_path).resolve()
        self._open_local_path(file_path, missing_title="Not Found", open_title="Open Failed")

    def _open_local_path(self, path: Path, *, missing_title: str, open_title: str) -> bool:
        """Open a local file or folder using Qt's platform-native shell integration.

        Args:
            path: Path to the file or directory to open.
            missing_title: Dialog title used if the path does not exist.
            open_title: Dialog title used if the OS declines to open the path.

        Returns:
            ``True`` when the path was handed off to the OS successfully,
            ``False`` otherwise.
        """
        path = path.resolve()
        if not path.exists():
            QMessageBox.warning(self, missing_title, f"Path does not exist:\n{path.name}")
            return False
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(self, open_title, f"Could not open:\n{path}")
            return False
        return True

    def set_advanced_mode(self, val):
        """Called by the main window when the advanced-mode toggle changes.

        No UI changes are needed for HarvestTab; this method exists so
        ``ModernMainWindow`` can iterate over all tabs uniformly.
        """

    def stop_harvest(self):
        """Public entry point for stopping the harvest, used by window close handlers."""
        self._stop_harvest()

    # ── MARC Import ────────────────────────────────────────────────────────────

    def _browse_marc_file(self):
        """Open a file picker for MARC files (.mrc binary or .xml MARCXML)."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select MARC File",
            "",
            "MARC Files (*.mrc *.marc *.xml);;All Files (*)",
        )
        if path:
            self._set_marc_file(path)

    def _set_marc_file(self, path: str):
        """Populate the MARC controls after browse or drag-and-drop."""
        self._marc_selected_path = path
        file_name = Path(path).name
        self._marc_path_edit.setText(file_name)
        self._marc_path_edit.setToolTip(path)
        self._btn_import_marc.setEnabled(True)
        self._btn_clear_marc.setVisible(True)
        self._marc_hint_label.setText("Click Run to import call numbers into the database.")
        self._set_marc_import_progress(0, state="idle", visible=False)

    def _clear_marc_file(self):
        """Reset all MARC-import controls to their default (no file selected) state."""
        self._marc_selected_path = None
        self._marc_path_edit.clear()
        self._marc_path_edit.setToolTip("")
        self._btn_import_marc.setEnabled(False)
        self._btn_clear_marc.setVisible(False)
        self._marc_hint_label.setText("Drop .mrc or .xml file here")
        self._set_marc_import_progress(0, state="idle", visible=False)
        for attr in ("_marc_stat_records", "_marc_stat_callnums", "_marc_stat_matched", "_marc_stat_unmatched"):
            getattr(self, attr).setText("—")

    @staticmethod
    def _compute_file_hash(path: str) -> str:
        """Return a stable SHA-256 hash for the selected MARC file."""
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _resolve_marc_source_conflict(
        self,
        db_path: str,
        source_name: str,
        parsed_records: list,
    ) -> tuple[bool | None, list]:
        """Check for ISBN overlap between the new file and existing DB records.

        Compares ISBNs inside the new file against ISBNs already stored under
        *source_name* in the database.  Returns a ``(replace_existing, records)``
        tuple where *replace_existing* is ``None`` to abort, ``True`` to replace
        the existing source, or ``False`` to insert; and *records* is the
        (possibly filtered) list to persist.
        """
        import sqlite3 as _sqlite3

        # Collect ISBNs from the new file's parsed records.
        new_isbns: set[str] = set()
        for r in parsed_records:
            for isbn in r.isbns:
                clean = isbn.replace("-", "").strip()
                if clean:
                    new_isbns.add(clean)

        if not new_isbns:
            return False, parsed_records

        # Query existing ISBNs stored under this source name.
        try:
            conn = _sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT DISTINCT isbn FROM main WHERE source = ?", (source_name,)
            ).fetchall()
            conn.close()
            existing_isbns: set[str] = {r[0].replace("-", "").strip() for r in rows if r[0]}
        except Exception:
            return False, parsed_records

        if not existing_isbns:
            return False, parsed_records

        overlap = new_isbns & existing_isbns
        new_only = new_isbns - existing_isbns

        if not overlap:
            # All ISBNs from this file are new — import silently.
            return False, parsed_records

        # Some ISBNs already exist under this source name — ask the user.
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Duplicate ISBNs Found")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText(
            f"{len(overlap)} ISBN(s) from this file are already imported under '{source_name}'.\n"
            f"{len(new_only)} ISBN(s) are new.\n\n"
            f"Import only the new ones, import all records, or cancel?"
        )
        new_only_btn = dialog.addButton("Import New Only", QMessageBox.ButtonRole.AcceptRole)
        all_btn = dialog.addButton("Import All", QMessageBox.ButtonRole.ActionRole)
        dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(new_only_btn)
        dialog.exec()

        clicked = dialog.clickedButton()
        if clicked == new_only_btn:
            filtered = [
                r for r in parsed_records
                if any(isbn.replace("-", "").strip() in new_only for isbn in r.isbns)
            ]
            return False, filtered
        if clicked == all_btn:
            return False, parsed_records
        return None, parsed_records

    def _set_marc_import_progress(
        self,
        value: int,
        *,
        state: str = "running",
        visible: bool = True,
    ) -> None:
        """Update the MARC-only progress bar without touching harvest state."""
        if not hasattr(self, "_marc_progress_bar"):
            return

        self._marc_progress_bar.setVisible(visible)
        self._marc_progress_bar.setValue(max(0, min(100, int(value))))
        self._marc_progress_bar.setProperty("state", state)
        self._marc_progress_bar.style().unpolish(self._marc_progress_bar)
        self._marc_progress_bar.style().polish(self._marc_progress_bar)

    def _import_marc_file(self):
        """Run the three-step MARC import pipeline for the currently selected file.

        Steps:
        1. Ask the user for a human-readable source name (via ``QInputDialog``).
        2. Parse the MARC file with ``_parse_marc_records``; show an error and
           return early if parsing fails or the file is empty.
        3. Filter/transform records via ``_prepare_marc_import_records`` using the
           active call-number mode.
        4. Persist parsed records to the database via ``MarcImportService``.
        5. Write a TSV export to the profile's data directory.
        6. Update the MARC stat tiles and show a rich-text summary dialog.
        """
        path = self._marc_path_edit.text().strip()
        if not path:
            return

        # Ask the user for a source name to store with the imported records.
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
            self._marc_status_label.setText("Could not read the MARC file. Make sure it is a valid .mrc or .xml file.")
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
            headers = ["ISBN", "NLM", "NLM Source", "NLM Classification", "Date"]
        elif mode == "both":
            headers = [
                "ISBN",
                "LCCN",
                "LCCN Source",
                "Classification",
                "NLM",
                "NLM Source",
                "NLM Classification",
                "Date",
            ]
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
                    nlm_classification = _extract_call_number_classification(nlmcn or "")
                    row = [isbn or "", nlmcn, source_name, nlm_classification, date_added]
                elif mode == "both":
                    classification = _extract_lc_classification(lccn or "")
                    nlm_classification = _extract_call_number_classification(nlmcn or "")
                    row = [
                        isbn or "",
                        lccn or "", source_name if lccn else "",
                        classification,
                        nlmcn or "", source_name if nlmcn else "",
                        nlm_classification,
                        date_added,
                    ]
                else:
                    classification = _extract_lc_classification(lccn)
                    row = [isbn or "", lccn, source_name, classification, date_added]
                writer.writerow(row)
                # Yield to the event loop every 500 rows so the UI stays responsive
                # during large imports (calling processEvents avoids a frozen window).
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
        

    def _run_marc_import(self):
        """Run the MARC import pipeline for the currently selected file."""
        path = (self._marc_selected_path or "").strip()
        if not path:
            return

        default_source = Path(path).stem
        source_name, ok = QInputDialog.getText(
            self,
            "MARC Import - Source Name",
            "Enter a source name to store with the imported records\n"
            "(e.g. the library catalog or system the file came from):",
            text=default_source,
        )
        if not ok:
            return
        source_name = source_name.strip() or default_source

        self._btn_import_marc.setEnabled(False)
        self._set_marc_import_progress(5)
        self._marc_hint_label.setText("Step 1/3 - Reading MARC file...")
        QApplication.processEvents()

        try:
            records = self._parse_marc_records(path)
        except Exception as exc:
            self._marc_hint_label.setText("Could not read the MARC file. Make sure it is a valid .mrc or .xml file.")
            self._btn_import_marc.setEnabled(True)
            self._set_marc_import_progress(100, state="error")
            return

        total_records = len(records)
        if total_records == 0:
            self._marc_hint_label.setText("No records found in the MARC file.")
            self._btn_import_marc.setEnabled(True)
            self._set_marc_import_progress(100, state="error")
            return

        self._marc_hint_label.setText(f"Step 2/3 - Processing {total_records:,} records...")
        self._set_marc_import_progress(30)
        QApplication.processEvents()

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
            headers = ["ISBN", "NLM", "NLM Source", "NLM Classification", "Date"]
        elif mode == "both":
            headers = [
                "ISBN",
                "LCCN",
                "LCCN Source",
                "Classification",
                "NLM",
                "NLM Source",
                "NLM Classification",
                "Date",
            ]
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

        source_file_hash = self._compute_file_hash(path)
        replace_existing_source, parsed_records = self._resolve_marc_source_conflict(
            db_path, source_name, parsed_records
        )
        if replace_existing_source is None:
            self._btn_import_marc.setEnabled(True)
            self._marc_hint_label.setText("Import cancelled.")
            self._set_marc_import_progress(100, state="error")
            return

        selected_rows = [
            (
                record.isbns[0] if getattr(record, "isbns", ()) else "",
                record.lccn,
                record.nlmcn,
            )
            for record in parsed_records
        ]
        written = len(selected_rows)
        no_isbn = sum(1 for record in parsed_records if not getattr(record, "isbns", ()))

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
            source_file_name=Path(path).name,
            source_file_hash=source_file_hash,
            replace_existing_source=replace_existing_source,
        )

        with open(out_path, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh, delimiter="\t")
            writer.writerow(headers)
            for i, (isbn, lccn, nlmcn) in enumerate(selected_rows, 1):
                if mode == "nlmcn":
                    nlm_classification = _extract_call_number_classification(nlmcn or "")
                    row = [isbn or "", nlmcn, source_name, nlm_classification, date_added]
                elif mode == "both":
                    classification = _extract_lc_classification(lccn or "")
                    nlm_classification = _extract_call_number_classification(nlmcn or "")
                    row = [
                        isbn or "",
                        lccn or "", source_name if lccn else "",
                        classification,
                        nlmcn or "", source_name if nlmcn else "",
                        nlm_classification,
                        date_added,
                    ]
                else:
                    classification = _extract_lc_classification(lccn)
                    row = [isbn or "", lccn, source_name, classification, date_added]
                writer.writerow(row)
                if i % 500 == 0:
                    self._marc_hint_label.setText(
                        f"Step 2/3 - Processed {i:,} / {total_records:,}..."
                    )
                    if selected_rows:
                        self._set_marc_import_progress(30 + int((i / len(selected_rows)) * 50))
                    QApplication.processEvents()

        self._marc_hint_label.setText("Step 3/3 - Finalizing TSV export...")
        self._set_marc_import_progress(90)
        QApplication.processEvents()
        self._marc_hint_label.setText(
            f"Done - {db_summary.main_rows:,} saved to database, {written:,} exported, "
            f"{skipped:,} skipped -> {out_path.name}"
        )
        self._set_marc_import_progress(100, state="success")
        self._marc_stat_records.setText(f"{total_records:,}")
        self._marc_stat_callnums.setText(f"{written:,}")
        self._marc_stat_matched.setText(f"{db_summary.main_rows:,}")
        self._marc_stat_unmatched.setText(f"{skipped + db_summary.skipped_records:,}")
        self._btn_import_marc.setEnabled(True)

        mode_label = {"lccn": "LCCN Only", "nlmcn": "NLM Only", "both": "Both (LCCN & NLM)"}.get(mode, mode)
        summary_lines = [
            "<b>MARC Import Complete</b>",
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
        dlg.setWindowTitle("MARC Import - Summary")
        dlg.setIcon(QMessageBox.Icon.Information)
        dlg.setTextFormat(Qt.TextFormat.RichText)
        dlg.setText("<br>".join(summary_lines))
        dlg.setStandardButtons(QMessageBox.StandardButton.Ok)
        open_btn = dlg.addButton("Open Output Folder", QMessageBox.ButtonRole.ActionRole)
        dlg.exec()
        if dlg.clickedButton() == open_btn:
            self._open_output_folder_path(live_dir)

    def _import_marc_file(self):
        """Run the MARC import pipeline and keep failures inside the GUI."""
        try:
            self._run_marc_import()
        except Exception as exc:
            logger.exception("MARC import failed.")
            self._btn_import_marc.setEnabled(True)
            self._marc_hint_label.setText("MARC import failed. Please check the file and try again.")
            self._set_marc_import_progress(100, state="error")
            QMessageBox.critical(
                self,
                "MARC Import Failed",
                "The MARC import could not be completed.\n\n"
                f"{_friendly_error(exc)}",
            )

    def _parse_marc_records(self, path: str) -> list:
        """Parse a binary MARC21 or MARCXML file and return (isbn, lccn, nlmcn) tuples.

        Fields extracted per record:
        - **020 $a / $z** — ISBN (preferred subfield $a; falls back to $z).
        - **050 $a + $b** — LC call number (LCCN).
        - **060 $a + $b** — NLM call number (NLMCN).

        Args:
            path: Absolute path to the MARC file.  ``.xml`` extension is treated
                  as MARCXML; all other extensions are treated as binary MARC21.

        Returns:
            List of ``(isbn, lccn, nlmcn)`` tuples; any field may be ``None``.
        """
        import pymarc
        from src.utils.call_number_normalizer import normalize_call_number

        file_path = Path(path)
        results = []

        def _extract(record):
            # ISBN: prefer 020 $a (primary ISBN); fall back to 020 $z (cancelled/invalid ISBN).
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
            # MARCXML path: pymarc parses the whole file into an array.
            for rec in pymarc.parse_xml_to_array(str(file_path)):
                if rec is not None:
                    results.append(_extract(rec))
        else:
            # Binary MARC21 path: streaming reader with UTF-8 forced for modern records.
            with open(file_path, "rb") as fh:
                reader = pymarc.MARCReader(fh, to_unicode=True, force_utf8=True)
                for rec in reader:
                    if rec is not None:
                        results.append(_extract(rec))

        return results
