"""Dashboard page with KPIs, live activity, and recent results.

``DashboardTab`` is the home page of the application.  It displays four KPI
cards (Processed, Successful, Failed, Invalid) that update in real time as a
harvest runs, a panel for opening the live result files, a recent-results
table, and an embedded Linked ISBNs management sub-page.

The dashboard also hosts a profile selector so the user can switch active
profiles without navigating to the Configure page.

Design notes:
- Stats are stored in ``session_stats`` and only come from the live
  ``live_stats_ready`` signal (``RunStats`` dataclass) or from the final
  ``harvest_finished`` dict; the 2-second auto-refresh timer updates the
  result-file button states (enabled/disabled), not the KPI counts, during a run.
- A ``QStackedWidget`` (``_main_stack``) is used to swap between the main
  dashboard view (index 0) and the Linked ISBNs sub-page (index 1).
- Responsive layout breakpoint: below 900 px the KPI cards move to a 2×2 grid
  and the two content columns stack vertically.
- The status pill (``lbl_run_status``) uses a ``state`` dynamic property
  (``"idle"``, ``"running"``, ``"paused"``, ``"success"``, ``"error"``) so
  QSS can colour it without any inline style overrides.
"""
import logging
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QBoxLayout, QLabel, QFrame,
    QComboBox, QPushButton, QSizePolicy, QMessageBox, QStackedWidget,
    QLineEdit, QTextEdit, QFormLayout
)
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices

from src.database import DatabaseManager
from .combo_boxes import ConsistentComboBox
from .icons import (
    get_icon, get_pixmap, SVG_ACTIVITY, SVG_CHECK_CIRCLE, SVG_ALERT_CIRCLE,
    SVG_X_CIRCLE, SVG_DASHBOARD, SVG_FOLDER_OPEN
)
from .database_browser_dialog import DatabaseBrowserDialog
from .dashboard_components import (
    DashboardCard,
    ProfileSwitchCombo,
    RecentResultsPanel,
    problems_button_label,
    safe_filename,
    truncate_text,
    write_csv_copy,
)

logger = logging.getLogger(__name__)


class DashboardTab(QWidget):
    """Home-page widget showing live harvest KPIs, result file shortcuts, and recent results.

    The widget is structured around a ``QStackedWidget`` (``_main_stack``) with
    two pages:
    - Page 0: the main dashboard (header, KPI cards, result-files panel, recent-results).
    - Page 1: the Linked ISBNs sub-page (query, link, and rewrite operations).

    Key instance variables:
        db (DatabaseManager): Shared database handle, initialised at construction.
        result_files (dict): Maps bucket keys to ``Path`` objects for the current run's
            output files.  Populated by ``set_result_files`` when a harvest starts.
        session_stats (dict): Live counters for the current view session.
        session_recent (list[dict]): Up to 10 most-recent harvest result rows.
        _is_running (bool): True while a harvest is active; guards the refresh timer
            from overwriting live KPI counts.
        _responsive_mode (str | None): Tracks whether the layout is ``"compact"``
            or ``"wide"`` to avoid redundant grid rebuilds in ``resizeEvent``.

    Signals:
        profile_selected(str): Emitted when the user picks a profile in the dashboard combo.
        create_profile_requested(): Emitted when the user clicks the "New Profile" affordance.
        page_title_changed(str): Emitted to ask ModernMainWindow to update the page-title label
            (used when switching to/from the Linked ISBNs sub-page).
    """

    # Emitted when the user picks a profile from the dashboard combo box.
    profile_selected = pyqtSignal(str)
    # Emitted when the user clicks the "New Profile" affordance in the header.
    create_profile_requested = pyqtSignal()
    # Emitted to ask ModernMainWindow to update its page-title label (e.g. "Dashboard" vs "Linked ISBNs").
    page_title_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        # Shared database manager; init_db() is idempotent so it is safe to call at construction.
        self.db = DatabaseManager()
        self.db.init_db()
        # No result files until a harvest runs this session; keys must match HarvestWorker.live_paths.
        self.result_files = {
            "successful": None,
            "invalid": None,
            "failed": None,
            "problems": None,
            "linked": None,
            "profile_dir": None,
        }
        self.current_profile = "default"
        self._baseline_stats = {
            "processed": 0,
            "found": 0,
            "failed": 0,
            "invalid": 0,
        }
        self.session_stats = {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "invalid": 0,
        }
        # True while a harvest is active; prevents refresh_data from overwriting live KPI counters.
        self._is_running = False
        self.session_recent = []
        self.last_run_text = "Last Run: Never"
        # Tracks the current responsive layout mode ("compact" or "wide"); avoids redundant re-layouts.
        self._responsive_mode = None
        self._setup_ui()

        # Polls every 2 s to keep result-file button states and the last-run label current.
        # Note: KPI counts are updated via signals, not here.
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_data)
        self.timer.start(2000)
        
        self.refresh_data()

    def _setup_ui(self):
        """Build the full dashboard UI.

        Layout structure (top to bottom):
        1. ``_main_stack`` (``QStackedWidget``) fills the whole widget.
           - Index 0: main dashboard page (header, KPI grid, content split).
           - Index 1: Linked ISBNs sub-page (built by ``_build_linked_isbn_page``).

        Within the dashboard page:
        - Header bar: status pill (``lbl_run_status``) + last-run label.
        - KPI grid (``kpi_layout``): responsive 1×4 or 2×2 placement managed by
          ``_apply_responsive_layout``.
        - Content split (``content_split``): left column (result files panel +
          Browse DB button) and right column (recent results + Linked ISBNs button).
        """
        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _outer.setSpacing(0)

        # QStackedWidget holds the full-page dashboard (index 0) and the Linked ISBNs sub-page (index 1).
        # Navigating between them is done via _go_to_linked_isbn_page / _go_to_dashboard.
        self._main_stack = QStackedWidget()
        _outer.addWidget(self._main_stack)

        # ── Page 0: Dashboard ──────────────────────────────────────
        _dash_page = QWidget()
        _dash_layout = QVBoxLayout(_dash_page)
        _dash_layout.setContentsMargins(0, 0, 0, 0)
        _dash_layout.setSpacing(0)
        _scr_content = QWidget()
        _scr_content.setMinimumWidth(700)
        _dash_layout.addWidget(_scr_content)
        self._main_stack.addWidget(_dash_page)

        # Page 1 built after the dashboard content so self.db is ready
        main_layout = QVBoxLayout(_scr_content)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(16)

        # 1. Header Bar
        header_layout = QHBoxLayout()
        
        self.lbl_run_status = QLabel("● IDLE")
        self.lbl_run_status.setProperty("class", "StatusPill")
        self.lbl_run_status.setProperty("state", "idle")
        
        self.lbl_last_run = QLabel("Last Run: Never")
        self.lbl_last_run.setProperty("class", "HelperText")
        self.lbl_last_run.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.lbl_last_run.setWordWrap(False)
        
        header_layout.addWidget(self.lbl_run_status)
        header_layout.addWidget(self.lbl_last_run, 1)
        header_layout.addStretch()
        
        main_layout.addLayout(header_layout)

        # 2. KPI Cards Row
        self.kpi_layout = QGridLayout()
        self.kpi_layout.setSpacing(20)

        self.card_proc = DashboardCard("PROCESSED", SVG_ACTIVITY, "#8aadf4")
        self.card_proc.setMinimumWidth(160)
        self.card_found = DashboardCard("SUCCESSFUL", SVG_CHECK_CIRCLE, "#a6da95")
        self.card_found.setMinimumWidth(160)
        self.card_failed = DashboardCard("FAILED", SVG_X_CIRCLE, "#ed8796")
        self.card_failed.setMinimumWidth(160)
        self.card_invalid = DashboardCard("INVALID", SVG_ALERT_CIRCLE, "#fab387")
        self.card_invalid.setMinimumWidth(160)
        
        main_layout.addLayout(self.kpi_layout)

        # 3. Main Content Split (Result files vs Recent)
        self.content_split = QHBoxLayout()
        self.content_split.setSpacing(20)

        left_col = QVBoxLayout()
        left_col.setSpacing(14)
        self.result_files_panel = self._build_result_files_panel()
        left_col.addWidget(self.result_files_panel)
        self.btn_browse_db = QPushButton("Browse Database")
        self.btn_browse_db.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse_db.setMinimumHeight(42)
        self.btn_browse_db.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_browse_db.setProperty("class", "SecondaryButton")
        self.btn_browse_db.setToolTip("Browse all records in the harvester database")
        self.btn_browse_db.clicked.connect(self._open_database_browser)
        left_col.addWidget(self.btn_browse_db)
        self.left_col = left_col
        self.content_split.addLayout(left_col, stretch=1)

        right_col = QVBoxLayout()
        right_col.setSpacing(14)
        self.recent_panel = RecentResultsPanel()
        self.recent_panel.setMinimumWidth(320)
        right_col.addWidget(self.recent_panel)
        self.btn_linked_isbns = QPushButton("Linked ISBNs")
        self.btn_linked_isbns.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_linked_isbns.setMinimumHeight(42)
        self.btn_linked_isbns.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_linked_isbns.setProperty("class", "SecondaryButton")
        self.btn_linked_isbns.setToolTip("Query, link, or merge linked ISBN rows")
        self.btn_linked_isbns.clicked.connect(self._go_to_linked_isbn_page)
        right_col.addWidget(self.btn_linked_isbns)
        self.right_col = right_col
        self.content_split.addLayout(right_col, stretch=1)
        
        main_layout.addLayout(self.content_split)
        
        main_layout.addStretch()
        self._apply_responsive_layout(self.width() or 1200)
        QTimer.singleShot(0, self._sync_panel_heights)
        self._refresh_result_file_buttons()

        # ── Page 1: Linked ISBNs full panel ───────────────────────
        self._main_stack.addWidget(self._build_linked_isbn_page())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout(event.size().width())
        self._sync_panel_heights()

    def _apply_responsive_layout(self, width: int):
        """Rearrange KPI cards and content columns based on available width.

        Below 900 px the four KPI cards are shown in a 2×2 grid and the
        content columns stack vertically.  At 900 px and above the cards sit
        in a single row and the columns are laid out side by side.

        Args:
            width: Current widget width in pixels.
        """
        mode = "compact" if width < 900 else "wide"
        if mode == self._responsive_mode:
            return
        self._responsive_mode = mode

        # Remove all items from the grid without deleting the widgets so they can be re-added.
        while self.kpi_layout.count():
            self.kpi_layout.takeAt(0)

        if mode == "compact":
            self.kpi_layout.addWidget(self.card_proc, 0, 0)
            self.kpi_layout.addWidget(self.card_found, 0, 1)
            self.kpi_layout.addWidget(self.card_failed, 1, 0)
            self.kpi_layout.addWidget(self.card_invalid, 1, 1)
            self.content_split.setDirection(QBoxLayout.Direction.TopToBottom)
        else:
            self.kpi_layout.addWidget(self.card_proc, 0, 0)
            self.kpi_layout.addWidget(self.card_found, 0, 1)
            self.kpi_layout.addWidget(self.card_failed, 0, 2)
            self.kpi_layout.addWidget(self.card_invalid, 0, 3)
            self.content_split.setDirection(QBoxLayout.Direction.LeftToRight)

        for col in range(4):
            self.kpi_layout.setColumnStretch(col, 0)
        if mode == "compact":
            self.kpi_layout.setColumnStretch(0, 1)
            self.kpi_layout.setColumnStretch(1, 1)
        else:
            for col in range(4):
                self.kpi_layout.setColumnStretch(col, 1)
        self._sync_panel_heights()

    def _sync_panel_heights(self):
        """Lock the result-files panel and recent-results panel to the same height.

        Both panels sit side-by-side; forcing them to the same fixed height prevents one
        from expanding and pushing the other out of alignment.  Called after every resize
        and responsive-layout change.
        """
        if not hasattr(self, "result_files_panel") or not hasattr(self, "recent_panel"):
            return
        # Take the larger of the two natural heights so neither panel is clipped.
        panel_height = max(
            self.result_files_panel.sizeHint().height(),
            self.recent_panel.sizeHint().height(),
        )
        if panel_height > 0:
            self.result_files_panel.setMinimumHeight(panel_height)
            self.result_files_panel.setMaximumHeight(panel_height)
            self.recent_panel.setMinimumHeight(panel_height)
            self.recent_panel.setMaximumHeight(panel_height)

    def _build_result_files_panel(self):
        """Build the Result Files card.

        Contains:
        - Header row: "RESULT FILES" title, TSV/CSV format combo, folder-open button.
        - Subtitle helper text.
        - Four file-open buttons (successful, failed, invalid, problem targets).
        - Linked ISBNs open button.
        - Reset Dashboard Stats danger button.

        Returns:
            Configured ``QFrame`` with the "Card" QSS class.
        """
        panel = QFrame()
        panel.setProperty("class", "Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("RESULT FILES")
        title.setProperty("class", "CardTitle")
        header.addWidget(title)
        header.addStretch()

        # Format combo: switching between TSV and CSV triggers a button-state refresh
        # so the correct file extension is checked for existence.
        self.format_combo = ConsistentComboBox(popup_object_name="ResultFormatComboPopup", max_visible_items=2)
        self.format_combo.setObjectName("ResultFormatCombo")
        self.format_combo.addItems(["TSV (.tsv)", "CSV (.csv)"])
        self.format_combo.setToolTip("Select the file format to open")
        self.format_combo.currentTextChanged.connect(self._refresh_result_file_buttons)
        header.addWidget(self.format_combo)
        
        self.btn_open_profile_folder = QPushButton()
        self.btn_open_profile_folder.setIcon(get_icon(SVG_FOLDER_OPEN, "#f4c542"))
        self.btn_open_profile_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_profile_folder.setMinimumSize(36, 36)
        self.btn_open_profile_folder.setToolTip("Open this profile's results folder")
        self.btn_open_profile_folder.setProperty("class", "IconButton")
        self.btn_open_profile_folder.clicked.connect(self._open_profile_folder)
        header.addWidget(self.btn_open_profile_folder)
        layout.addLayout(header)

        subtitle = QLabel("Live results are created fresh for each harvest run.")
        subtitle.setProperty("class", "HelperText")
        layout.addWidget(subtitle)

        self.btn_open_successful = self._create_result_open_button("Open successful", "successful")
        self.btn_open_failed = self._create_result_open_button("Open failed", "failed")
        self.btn_open_invalid = self._create_result_open_button("Open invalid", "invalid")
        self.btn_open_problems = self._create_result_open_button("Open problem targets", "problems")
        
        layout.addWidget(self.btn_open_successful)
        layout.addWidget(self.btn_open_failed)
        layout.addWidget(self.btn_open_invalid)
        layout.addWidget(self.btn_open_problems)

        self.btn_open_linked_isbns = QPushButton("Open linked ISBNs")
        self.btn_open_linked_isbns.setProperty("class", "SecondaryButton")
        self.btn_open_linked_isbns.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_linked_isbns.setMinimumHeight(42)
        self.btn_open_linked_isbns.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_open_linked_isbns.setEnabled(False)
        self.btn_open_linked_isbns.setToolTip(
            "Export the ISBN → canonical ISBN mapping table and open it"
        )
        self.btn_open_linked_isbns.clicked.connect(lambda: self._open_result_file("linked"))
        layout.addWidget(self.btn_open_linked_isbns)

        self.btn_reset_stats = QPushButton("Reset Dashboard Stats")
        self.btn_reset_stats.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_stats.setMinimumHeight(42)
        self.btn_reset_stats.setProperty("class", "DangerButton")
        self.btn_reset_stats.clicked.connect(self._reset_dashboard_stats)
        layout.addWidget(self.btn_reset_stats)
        return panel

    def _create_result_open_button(self, text, key):
        """Build a disabled-by-default button that opens the result file for *key*.

        The button is enabled once a harvest run creates the file; this is checked
        each time ``_refresh_result_file_buttons`` runs.

        Args:
            text: Button label text.
            key: Dict key into ``self.result_files`` (e.g. ``"successful"``).

        Returns:
            The configured ``QPushButton``.
        """
        btn = QPushButton(text)
        btn.setProperty("class", "SecondaryButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(42)
        btn.setEnabled(False)
        # Lambda captures `key` by value so each button opens its own file.
        btn.clicked.connect(lambda: self._open_result_file(key))
        return btn


    def set_result_files(self, paths: dict):
        """Store the live output file paths for the current run and refresh button states.

        Called by ``ModernMainWindow`` when the worker emits ``result_files_ready``
        at harvest start.

        Args:
            paths: Dict mapping bucket keys (``"successful"``, ``"failed"``,
                   ``"invalid"``, ``"problems"``, ``"linked"``, ``"profile_dir"``)
                   to absolute path strings.
        """
        self.result_files = {
            "successful": Path(paths["successful"]) if paths.get("successful") else None,
            "invalid": Path(paths["invalid"]) if paths.get("invalid") else None,
            "failed": Path(paths["failed"]) if paths.get("failed") else None,
            "problems": Path(paths["problems"]) if paths.get("problems") else None,
            "linked": Path(paths["linked"]) if paths.get("linked") else None,
            "profile_dir": Path(paths["profile_dir"]) if paths.get("profile_dir") else self._profile_dir_path(),
        }
        self._refresh_result_file_buttons()

    def _refresh_result_file_buttons(self):
        """Enable/disable and re-label result file buttons based on what exists on disk.

        Called after every harvest event and on the auto-refresh timer tick.
        The correct file extension (.tsv or .csv) is determined from the format combo.
        """
        if not hasattr(self, "btn_open_successful"):
            return
        default_labels = {
            "successful": "Open successful",
            "failed": "Open failed",
            "invalid": "Open invalid",
            "problems": "Open problem targets",
            "linked": "Open linked ISBNs",
        }
        mapping = {
            "successful": self.btn_open_successful,
            "failed": self.btn_open_failed,
            "invalid": self.btn_open_invalid,
            "problems": self.btn_open_problems,
            "linked": self.btn_open_linked_isbns,
        }
        
        is_csv = getattr(self, "format_combo", None) and self.format_combo.currentText().startswith("CSV")
        ext = ".csv" if is_csv else ".tsv"
        
        for key, btn in mapping.items():
            path = self.result_files.get(key)
            if path is not None:
                # Check for the correct extension file
                check_path = path.with_suffix(ext)
                
                # If CSV is requested but not finalized, we can enable the button as long as the base TSV exists.
                if key == "linked":
                    enabled = self._result_file_has_content(path.with_suffix(ext))
                elif is_csv:
                    enabled = path.exists() 
                else:
                    enabled = check_path.exists()
                    
                btn.setEnabled(enabled)
                
                btn.setText(default_labels[key])
            else:
                btn.setEnabled(False)
        profile_dir = self.result_files.get("profile_dir") or self._profile_dir_path()
        self.btn_open_profile_folder.setEnabled(profile_dir is not None and profile_dir.exists())

    def _result_file_has_content(self, path: Path | None) -> bool:
        """Return True if the file exists and contains at least one data row (beyond a header).

        Args:
            path: Path to check, or ``None``.

        Returns:
            ``True`` if the file has two or more lines, ``False`` otherwise.
        """
        if path is None or not path.exists():
            return False
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as handle:
                next(handle, None)   # skip header
                return next(handle, None) is not None
        except Exception:
            return False

    def _open_result_file(self, key):
        """Open the result file for *key* in the default system application.

        If the user has selected CSV format and only a TSV exists on disk, a CSV
        copy is generated on the fly before opening.

        Args:
            key: Result bucket key — one of ``"successful"``, ``"failed"``,
                 ``"invalid"``, ``"problems"``, ``"linked"``.
        """
        path = self.result_files[key]
        is_csv = getattr(self, "format_combo", None) and self.format_combo.currentText().startswith("CSV")
        ext = ".csv" if is_csv else ".tsv"
        target_path = path.with_suffix(ext)

        # Generate on the fly if CSV is selected mid-harvest.
        if is_csv and not target_path.exists() and path.exists():
            try:
                write_csv_copy(str(path), str(target_path))
            except Exception as e:
                QMessageBox.warning(self, "CSV Not Ready", f"Could not generate live CSV view:\n{e}")
                return

        if not target_path.exists():
            QMessageBox.warning(self, "File Not Found", f"{target_path} does not exist yet.")
            self._refresh_result_file_buttons()
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_path.resolve()))):
            QMessageBox.warning(self, "Open Failed", f"Could not open {target_path}.")

    def _export_linked_isbns(self):
        """Export the ``linked_isbns`` DB table to a timestamped TSV or CSV file and open it.

        Queries ``linked_isbns`` ordered by canonical ISBN, writes both a TSV and (if CSV
        mode is selected) a CSV copy into the active profile's data directory, then opens
        the file with the default system application.  Shows an informational dialog if
        the table is empty.
        """
        import csv as _csv
        from datetime import datetime as _dt

        is_csv = getattr(self, "format_combo", None) and self.format_combo.currentText().startswith("CSV")
        ext = ".csv" if is_csv else ".tsv"

        # Query the database
        try:
            with self.db.connect() as conn:
                rows = conn.execute(
                    "SELECT other_isbn AS isbn, lowest_isbn AS canonical_isbn "
                    "FROM linked_isbns ORDER BY lowest_isbn, other_isbn"
                ).fetchall()
        except Exception as exc:
            QMessageBox.warning(self, "Export Failed", f"Could not read linked ISBNs:\n{exc}")
            return

        if not rows:
            QMessageBox.information(
                self,
                "No Linked ISBNs",
                "The linked ISBNs table is empty.\n\n"
                "Linked ISBNs are recorded when the harvester resolves a call number "
                "via an alternate ISBN for the same edition.",
            )
            return

        # Write export file into the profile folder
        out_dir = self._profile_dir_path()
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = _dt.now().strftime("%Y-%m-%d-%H-%M-%S")
        out_path = out_dir / f"{safe_filename(self.current_profile)}-linked-isbns-{stamp}{ext}"

        try:
            delimiter = "," if is_csv else "\t"
            with open(out_path, "w", newline="", encoding="utf-8-sig") as fh:
                writer = _csv.writer(fh, delimiter=delimiter)
                writer.writerow(["ISBN", "Canonical ISBN"])
                writer.writerows(rows)
        except Exception as exc:
            QMessageBox.warning(self, "Export Failed", f"Could not write file:\n{exc}")
            return

        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_path.resolve()))):
            QMessageBox.warning(self, "Open Failed", f"Exported to {out_path} but could not open it.")

    def _profile_dir_path(self) -> Path:
        """Return the ``data/<profile>`` directory path for the active profile."""
        return Path("data") / safe_filename(self.current_profile)

    def _open_profile_folder(self):
        """Open the active profile's output directory in the default file manager."""
        path = self.result_files.get("profile_dir") or self._profile_dir_path()
        if not path.exists():
            QMessageBox.warning(self, "Folder Not Found", f"{path} does not exist yet.")
            self._refresh_result_file_buttons()
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
            QMessageBox.warning(self, "Open Failed", f"Could not open {path}.")

    def _reset_dashboard_stats(self):
        """Prompt the user and, if confirmed, clear all in-memory session counters.

        Guards against resetting while a harvest is actively running.
        Delegates the actual clear to ``reset_dashboard_stats`` and then
        refreshes the UI and resets the status pill to IDLE.
        """
        if "RUNNING" in self.lbl_run_status.text():
            QMessageBox.information(self, "Harvest Running", "Stop the current harvest before resetting dashboard stats.")
            return
        confirm = QMessageBox.question(
            self,
            "Reset Dashboard Stats",
            "This resets the dashboard stats and recent results shown here. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.reset_dashboard_stats()
        self.refresh_data()
        self.set_idle(None)

    def _open_database_browser(self):
        """Open the DatabaseBrowserDialog as a modal window."""
        dialog = DatabaseBrowserDialog(parent=self, db=self.db)
        dialog.exec()

    def _go_to_linked_isbn_page(self):
        """Switch the main stack to the Linked ISBNs sub-page (index 1)."""
        self._main_stack.setCurrentIndex(1)
        # Notify the window so the page-title label reads "Linked ISBNs" instead of "Dashboard".
        self.page_title_changed.emit("Linked ISBNs")

    def _go_to_dashboard(self):
        """Return to the main dashboard page (index 0)."""
        self._main_stack.setCurrentIndex(0)
        self.page_title_changed.emit("Dashboard")

    # ------------------------------------------------------------------
    # Linked ISBNs sub-page (embedded in the dashboard stack)
    # ------------------------------------------------------------------
    def _build_linked_isbn_page(self) -> QWidget:
        """Build and return the Linked ISBNs sub-page widget (stack index 1).

        Layout:
        - Back button row at the top.
        - Subtitle helper text.
        - Two-column body:
          - Left (Query): ISBN lookup form and read-only result display.
          - Right (Link + Rewrite): two QFormLayouts separated by a divider,
            each with a pair of ISBN inputs and a corresponding action button.
        - Status bar at the bottom for feedback messages.

        Returns:
            Fully built ``QWidget`` to be added to ``_main_stack`` at index 1.
        """
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 16)
        root.setSpacing(16)

        # ── Back button (replaces the page title row) ──────────────
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        btn_back = QPushButton("← Back to Dashboard")
        btn_back.setProperty("class", "SecondaryButton")
        btn_back.setMinimumHeight(36)
        btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_back.clicked.connect(self._go_to_dashboard)
        hdr.addWidget(btn_back)
        hdr.addStretch()
        root.addLayout(hdr)

        sub = QLabel(
            "Query which ISBNs are linked together, manually link two ISBNs, "
            "or consolidate existing rows under the lowest ISBN."
        )
        sub.setProperty("class", "HelperText")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # ── Two-column layout: Query left | Link+Rewrite right ─────
        cols = QHBoxLayout()
        cols.setSpacing(24)

        # Left column — Query
        left = QFrame()
        left.setProperty("class", "Card")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(10)

        lbl_q = QLabel("QUERY")
        lbl_q.setProperty("class", "CardTitle")
        left_layout.addWidget(lbl_q)

        q_row = QHBoxLayout()
        q_row.setSpacing(8)
        self._li_query_input = QLineEdit()
        self._li_query_input.setPlaceholderText("Enter any ISBN…")
        self._li_query_input.setMinimumHeight(36)
        self._li_query_input.setMaximumHeight(36)
        self._li_query_input.setStyleSheet("QLineEdit { padding: 4px 10px; }")
        self._li_query_input.returnPressed.connect(self._li_run_query)
        q_row.addWidget(self._li_query_input, stretch=1)
        btn_q = QPushButton("Look Up")
        btn_q.setProperty("class", "PrimaryButton")
        btn_q.setMinimumHeight(36)
        btn_q.setMinimumWidth(90)
        btn_q.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_q.clicked.connect(self._li_run_query)
        q_row.addWidget(btn_q)
        left_layout.addLayout(q_row)

        self._li_query_result = QTextEdit()
        self._li_query_result.setReadOnly(True)
        self._li_query_result.setPlaceholderText("Results appear here…")
        self._li_query_result.setProperty("class", "TerminalViewport")
        left_layout.addWidget(self._li_query_result, stretch=1)
        cols.addWidget(left, stretch=1)

        # Right column — Link + Rewrite
        right = QFrame()
        right.setProperty("class", "Card")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(14)

        # Link section
        lbl_link = QLabel("LINK TWO ISBNs")
        lbl_link.setProperty("class", "CardTitle")
        right_layout.addWidget(lbl_link)

        hint_link = QLabel(
            "Mark <b>Other</b> as a variant of <b>Lowest</b>. "
            "Only the mapping is stored — no rows are moved."
        )
        hint_link.setProperty("class", "HelperText")
        hint_link.setWordWrap(True)
        right_layout.addWidget(hint_link)

        link_form = QFormLayout()
        link_form.setSpacing(8)
        link_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        link_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        _isbn_style = "QLineEdit { padding: 4px 10px; }"
        self._li_link_lowest = QLineEdit()
        self._li_link_lowest.setPlaceholderText("Canonical / lowest ISBN")
        self._li_link_lowest.setMinimumHeight(34)
        self._li_link_lowest.setMaximumHeight(34)
        self._li_link_lowest.setStyleSheet(_isbn_style)
        link_form.addRow("Lowest ISBN:", self._li_link_lowest)
        self._li_link_other = QLineEdit()
        self._li_link_other.setPlaceholderText("Variant / higher ISBN")
        self._li_link_other.setMinimumHeight(34)
        self._li_link_other.setMaximumHeight(34)
        self._li_link_other.setStyleSheet(_isbn_style)
        link_form.addRow("Other ISBN:", self._li_link_other)
        right_layout.addLayout(link_form)

        btn_link_row = QHBoxLayout()
        btn_link_row.addStretch()
        btn_link = QPushButton("Save Link")
        btn_link.setProperty("class", "SecondaryButton")
        btn_link.setMinimumHeight(36)
        btn_link.setMinimumWidth(120)
        btn_link.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_link.clicked.connect(self._li_run_link)
        btn_link_row.addWidget(btn_link)
        right_layout.addLayout(btn_link_row)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        right_layout.addWidget(div)

        # Rewrite section
        lbl_rw = QLabel("REWRITE TO LOWEST ISBN")
        lbl_rw.setProperty("class", "CardTitle")
        right_layout.addWidget(lbl_rw)

        hint_rw = QLabel(
            "Move all <b>main</b> and <b>attempted</b> rows from Other onto Lowest, "
            "merging call numbers and fail counts."
        )
        hint_rw.setProperty("class", "HelperText")
        hint_rw.setWordWrap(True)
        right_layout.addWidget(hint_rw)

        rw_form = QFormLayout()
        rw_form.setSpacing(8)
        rw_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        rw_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._li_rw_lowest = QLineEdit()
        self._li_rw_lowest.setPlaceholderText("Keep this ISBN")
        self._li_rw_lowest.setMinimumHeight(34)
        self._li_rw_lowest.setMaximumHeight(34)
        self._li_rw_lowest.setStyleSheet(_isbn_style)
        rw_form.addRow("Lowest ISBN:", self._li_rw_lowest)
        self._li_rw_other = QLineEdit()
        self._li_rw_other.setPlaceholderText("Merge this ISBN into lowest")
        self._li_rw_other.setMinimumHeight(34)
        self._li_rw_other.setMaximumHeight(34)
        self._li_rw_other.setStyleSheet(_isbn_style)
        rw_form.addRow("Other ISBN:", self._li_rw_other)
        right_layout.addLayout(rw_form)

        btn_rw_row = QHBoxLayout()
        btn_rw_row.addStretch()
        btn_rw = QPushButton("Rewrite && Merge")
        btn_rw.setProperty("class", "DangerButton")
        btn_rw.setMinimumHeight(36)
        btn_rw.setMinimumWidth(150)
        btn_rw.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_rw.setToolTip("Moves rows in the database — cannot be undone.")
        btn_rw.clicked.connect(self._li_run_rewrite)
        btn_rw_row.addWidget(btn_rw)
        right_layout.addLayout(btn_rw_row)

        right_layout.addStretch()
        cols.addWidget(right, stretch=1)
        root.addLayout(cols, stretch=1)

        # Status bar
        self._li_status = QLabel("")
        self._li_status.setProperty("class", "HelperText")
        self._li_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._li_status)

        return page

    def _li_set_status(self, msg: str, error: bool = False):
        """Show a feedback message at the bottom of the Linked ISBNs sub-page.

        Args:
            msg: Human-readable result or error description.
            error: When ``True`` the text is rendered in red; green otherwise.
        """
        # Inline style overrides the theme colour for this single feedback label only.
        color = "#ef4444" if error else "#22c55e"
        self._li_status.setText(msg)
        self._li_status.setStyleSheet(f"color: {color};")

    def _li_run_query(self):
        """Look up the canonical lowest ISBN and all siblings for the entered ISBN.

        Queries ``DatabaseManager.get_lowest_isbn`` and ``get_linked_isbns``, formats
        the results as plain text, and populates ``_li_query_result``.
        """
        isbn = self._li_query_input.text().strip()
        if not isbn:
            self._li_set_status("Please enter an ISBN.", error=True)
            return
        try:
            lowest = self.db.get_lowest_isbn(isbn)
            linked = self.db.get_linked_isbns(isbn)
            lines = []
            if lowest != isbn:
                lines.append(f"Canonical lowest ISBN for '{isbn}':  {lowest}")
            else:
                lines.append(f"'{isbn}' is already the canonical lowest (or unlinked).")
            if linked:
                lines.append(f"\nISBNs linked under '{isbn}':")
                for other in linked:
                    lines.append(f"  • {other}")
            else:
                lines.append(f"\nNo other ISBNs are linked under '{isbn}'.")
            self._li_query_result.setPlainText("\n".join(lines))
            self._li_set_status("Query complete.")
        except Exception as exc:
            self._li_query_result.setPlainText(f"Error: {exc}")
            self._li_set_status(str(exc), error=True)

    def _li_run_link(self):
        """Save a lowest → other ISBN mapping via ``DatabaseManager.upsert_linked_isbn``."""
        lowest = self._li_link_lowest.text().strip()
        other = self._li_link_other.text().strip()
        if not lowest or not other:
            self._li_set_status("Both fields are required.", error=True)
            return
        if lowest == other:
            self._li_set_status("ISBNs must be different.", error=True)
            return
        try:
            self.db.upsert_linked_isbn(lowest_isbn=lowest, other_isbn=other)
            self._li_link_lowest.clear()
            self._li_link_other.clear()
            self._li_set_status(f"Linked: '{other}'  →  '{lowest}'")
        except Exception as exc:
            self._li_set_status(str(exc), error=True)

    def _li_run_rewrite(self):
        """Merge all records from the *other* ISBN onto the *lowest* ISBN in the DB.

        Calls ``DatabaseManager.rewrite_to_lowest_isbn``, which moves rows in both
        the ``main`` and ``attempted`` tables.  This is a destructive operation and
        cannot be undone; the button is styled as ``DangerButton`` to signal this.
        """
        lowest = self._li_rw_lowest.text().strip()
        other = self._li_rw_other.text().strip()
        if not lowest or not other:
            self._li_set_status("Both fields are required.", error=True)
            return
        if lowest == other:
            self._li_set_status("ISBNs must be different.", error=True)
            return
        try:
            self.db.rewrite_to_lowest_isbn(lowest_isbn=lowest, other_isbn=other)
            self._li_rw_lowest.clear()
            self._li_rw_other.clear()
            self._li_set_status(f"Rewritten: '{other}' merged into '{lowest}'.")
        except Exception as exc:
            self._li_set_status(str(exc), error=True)

    def refresh_data(self):
        """Refresh dashboard UI state from in-memory session data.

        Called on the 2-second auto-refresh timer and after harvest events.
        Updates result-file button states, KPI labels, recent-results table,
        and the last-run label.  Does *not* re-query the database.
        """
        try:
            self._refresh_result_file_buttons()
            self._render_session_stats()
            self.recent_panel.update_data(self.session_recent)
            self.lbl_last_run.setText(self.last_run_text)
        except Exception:
            logger.exception("Dashboard refresh failed.")

    def update_live_status(self, target, isbn, progress, msg):
        """Update the last-event label with a truncated progress message.

        Connected to ``HarvestTab.progress_updated`` via ``ModernMainWindow``.
        Called for every per-ISBN progress event during a live harvest.

        Args:
            target: Target name string (currently unused in this display path).
            isbn: The ISBN being processed (currently unused in this display path).
            progress: Progress fraction or count (currently unused in this display path).
            msg: Human-readable status message to display.
        """
        self.last_run_text = truncate_text(f"Last Event: {msg}", 140)
        self.lbl_last_run.setText(self.last_run_text)

    def record_harvest_event(self, isbn: str, status: str, detail: str):
        """Record a harvest event into the recent-results list.

        Only terminal outcome statuses are recorded; intermediate or informational
        statuses are silently ignored.

        Args:
            isbn: The processed ISBN.
            status: Outcome string from the worker (``"found"``, ``"failed"``,
                    ``"cached"``, ``"skipped"``).
            detail: Human-readable explanation to show in the detail column.
        """
        if status not in ("found", "failed", "cached", "skipped"):
            return
        self._append_recent_result(isbn, status, detail)

    def apply_run_stats(self, stats):
        """Accept either a dict (legacy) or a RunStats dataclass and update session_stats.

        The harvester can emit either a raw dict (older code path) or the newer ``RunStats``
        dataclass embedded under the ``"run_stats"`` key.  Both shapes are normalised into
        the same ``session_stats`` dict.

        Args:
            stats: Either a ``RunStats`` dataclass or a dict containing harvest summary keys.
        """
        # Prefer the embedded RunStats object when available in a dict
        if isinstance(stats, dict) and hasattr(stats.get("run_stats"), 'processed_unique'):
            stats = stats["run_stats"]
        if hasattr(stats, 'processed_unique'):  # RunStats dataclass
            found = getattr(stats, 'found', 0)
            failed = getattr(stats, 'failed', 0)
            skipped = getattr(stats, 'skipped', 0)
            invalid = getattr(stats, 'invalid', 0)
            processed = found + failed + skipped
            self.session_stats = {
                "processed": processed,
                "successful": found,
                "failed": failed + skipped,
                "invalid": invalid,
            }
        else:  # legacy dict
            stats = stats or {}
            successful = int(stats.get("found", 0)) + int(stats.get("cached", 0))
            failed = int(stats.get("failed", 0)) + int(stats.get("skipped", 0))
            self.session_stats = {
                "processed": successful + failed,
                "successful": successful,
                "failed": failed,
                "invalid": int(stats.get("invalid", 0)),
            }
        self._render_session_stats()

    def update_live_stats(self, stats):
        """Live update session stats from a RunStats object emitted by the worker.

        Connected to ``HarvestWorker.stats_update`` via ``live_stats_ready``.  Called every
        5 ISBNs so the KPI cards stay current without a per-ISBN DB round-trip.

        Args:
            stats: A ``RunStats`` dataclass.  Non-dataclass values are silently ignored.
        """
        if not hasattr(stats, 'processed_unique'):
            return  # Only handle RunStats dataclass
            
        found = getattr(stats, 'found', 0)
        failed = getattr(stats, 'failed', 0)
        skipped = getattr(stats, 'skipped', 0)
        invalid = getattr(stats, 'invalid', 0)
        processed = found + failed + skipped
        self.session_stats = {
            "processed": processed,
            "successful": found,
            "failed": failed + skipped,
            "invalid": invalid,
        }
        self._render_session_stats()

    def reset_dashboard_stats(self):
        """Clear all in-memory session counters and the recent-results list.

        Does not touch the SQLite database; only the displayed dashboard state is reset.
        """
        self._baseline_stats = {
            "processed": 0,
            "found": 0,
            "failed": 0,
            "invalid": 0,
        }
        self.session_stats = {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "invalid": 0,
        }
        self.session_recent = []
        self.last_run_text = "Last Run: Never"
        self.recent_panel.update_data([])
        self.lbl_last_run.setText(self.last_run_text)
        self._render_session_stats()

    def _append_recent_result(self, isbn: str, status: str, detail: str):
        """Prepend a single result row to the session recent-results list and refresh the panel.

        The list is capped at 10 entries (most recent first).  Status strings are
        normalised to one of three display labels: ``"Successful"``, ``"Linked ISBN"``,
        or ``"Failed"``.

        Args:
            isbn: The processed ISBN string.
            status: Raw outcome string from the worker.
            detail: Additional context for the detail column.
        """
        normalized = status.strip().lower() if status else ""
        if normalized in ("found", "cached", "successful"):
            status_label = "Successful"
        elif normalized in ("linked isbn", "linked_isbn", "linked"):  # preserve linked ISBN events
            status_label = "Linked ISBN"
        else:
            status_label = "Failed"
        self.session_recent.insert(
            0,
            {
                "isbn": isbn or "-",
                "status": status_label,
                "detail": detail or "-",
                "time": datetime.now().isoformat(),
            },
        )
        # Cap at 10 entries (most recent first) to avoid unbounded memory growth.
        self.session_recent = self.session_recent[:10]
        self.recent_panel.update_data(self.session_recent)

    def _render_session_stats(self):
        """Push the current ``session_stats`` values to the four KPI cards."""
        self.card_proc.set_data(self.session_stats["processed"], "Processed in this dashboard view")
        self.card_found.set_data(self.session_stats["successful"], "Successfully harvested")
        self.card_failed.set_data(self.session_stats["failed"], "Failed or skipped in this dashboard view")
        self.card_invalid.set_data(self.session_stats["invalid"], "Invalid ISBNs in this run")

    def set_profile_options(self, profiles, current_profile):
        """Update the active profile and clear stale session state when the profile changes.

        Called by ``ModernMainWindow`` whenever the profile list or active profile changes.

        Args:
            profiles: Full list of available profile names (currently unused but kept for
                      forward compatibility with a profile combo in the dashboard).
            current_profile: The newly active profile name.
        """
        incoming = current_profile or "default"
        profile_changed = incoming != self.current_profile
        self.current_profile = incoming
        if profile_changed:
            # A different profile has its own DB and result files — discard the old state.
            self.reset_dashboard_stats()
            self.result_files = {
                "successful": None,
                "invalid": None,
                "failed": None,
                "problems": None,
                "linked": None,
                "profile_dir": None,
            }
        self.result_files["profile_dir"] = self._profile_dir_path()
        self._refresh_result_file_buttons()

    def _on_profile_combo_changed(self, name):
        """Relay profile-combo selection to the main window via the ``profile_selected`` signal."""
        if name:
            self.profile_selected.emit(name)
        

    def set_advanced_mode(self, enabled):
        """Called by the main window when the advanced-mode toggle changes.

        No UI changes are required for the Dashboard tab; this method exists so
        ``ModernMainWindow`` can iterate over all tabs uniformly.
        """

    def set_running(self):
        """Switch the dashboard status pill to RUNNING and reset in-session counters.

        Called by ``ModernMainWindow._on_harvest_started`` at the start of each run so
        the dashboard shows a clean slate for the new harvest.
        """
        self._is_running = True  # Prevents the 2-s timer from overwriting live KPI counts.
        self.session_stats = {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "invalid": 0,
        }
        self.session_recent = []
        self.recent_panel.update_data([])
        self._refresh_result_file_buttons()
        self.lbl_run_status.setText("● RUNNING")
        self.lbl_run_status.setProperty("state", "running")
        self._refresh_status_style()

    def set_paused(self, is_paused: bool):
        """Update the dashboard status pill to reflect a pause or resume.

        Args:
            is_paused: ``True`` to show PAUSED, ``False`` to show RUNNING.
        """
        if is_paused:
            self.lbl_run_status.setText("● PAUSED")
            self.lbl_run_status.setProperty("state", "paused")
        else:
            self.lbl_run_status.setText("● RUNNING")
            self.lbl_run_status.setProperty("state", "running")
        self._refresh_status_style()

    def set_idle(self, success: bool | None = None):
        """Transition the dashboard status pill to a terminal state after a harvest ends.

        Args:
            success: ``True`` → COMPLETED, ``False`` → Cancelled/Error, ``None`` → IDLE.
        """
        self._is_running = False
        self._refresh_result_file_buttons()
        if success is True:
            self.lbl_run_status.setText("● COMPLETED")
            self.lbl_run_status.setProperty("state", "success")
        elif success is False:
            self.lbl_run_status.setText("● Cancelled")
            self.lbl_run_status.setProperty("state", "error")
        else:
            self.lbl_run_status.setText("● IDLE")
            self.lbl_run_status.setProperty("state", "idle")
        self._refresh_status_style()
        
    def _refresh_status_style(self):
        """Force Qt to re-evaluate the ``state`` property selector on the status pill.

        Qt caches dynamic property lookups; calling ``unpolish`` followed by ``polish``
        invalidates that cache so the correct QSS color rule (idle/running/paused/success/error)
        is applied immediately after a ``setProperty("state", ...)`` call.
        """
        # unpolish removes the cached style; polish re-applies rules using the new property value.
        self.lbl_run_status.style().unpolish(self.lbl_run_status)
        self.lbl_run_status.style().polish(self.lbl_run_status)


