"""
Module: dashboard_v2.py
Professional V2 Dashboard with Header, KPIs, Live Activity, and Recent Results.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QBoxLayout, QLabel, QFrame,
    QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QPushButton, QSizePolicy, QMessageBox, QStackedWidget,
    QLineEdit, QTextEdit, QFormLayout
)
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal, QUrl
from datetime import datetime
from pathlib import Path
from PyQt6.QtGui import QColor, QPainter, QPen, QDesktopServices

from database import DatabaseManager
from .combo_boxes import ConsistentComboBox
from .icons import (
    get_icon, get_pixmap, SVG_ACTIVITY, SVG_CHECK_CIRCLE, SVG_ALERT_CIRCLE,
    SVG_X_CIRCLE, SVG_DASHBOARD, SVG_FOLDER_OPEN
)
from .database_browser_dialog import DatabaseBrowserDialog


def _write_csv_copy(tsv_path: str, csv_path: str) -> None:
    """Convert a TSV file to a UTF-8 CSV file for spreadsheet apps."""
    import csv

    with open(tsv_path, newline="", encoding="utf-8") as source:
        rows = csv.reader(source, delimiter="\t")
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as target:
            writer = csv.writer(target)
            writer.writerows(rows)


def _safe_filename(s: str) -> str:
    cleaned = "".join("_" if c in '\\/:*?"<>| ' else c for c in (s or "").strip())
    cleaned = cleaned.strip("_")
    return cleaned or "default"


def _problems_button_label(
    profile_name: str | None,
    file_name: str | None = None,
    include_profile: bool = False,
) -> str:
    return "Open targets problems"


def _truncate_text(text: str, limit: int = 110) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."

class DashboardCard(QFrame):
    """
    A single KPI card with Icon, Title, Value, Helper Text.
    """
    def __init__(self, title, icon_svg, accent_color="#8aadf4"):
        super().__init__()
        self.setProperty("class", "Card")
        self.setMinimumWidth(220)
        self._setup_ui(title, icon_svg, accent_color)

    def _setup_ui(self, title, icon_svg, accent_color):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(5)
        
        # Header: Title + Icon
        header_layout = QHBoxLayout()
        lbl_title = QLabel(title)
        lbl_title.setProperty("class", "CardTitle")
        
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap(icon_svg, accent_color, 24))
        
        header_layout.addWidget(lbl_title)
        header_layout.addStretch()
        header_layout.addWidget(icon_lbl)
        
        layout.addLayout(header_layout)
        
        # Value
        self.lbl_value = QLabel("0")
        self.lbl_value.setProperty("class", "CardValue")
        layout.addWidget(self.lbl_value)
        
        # Helper Text
        self.lbl_helper = QLabel("Total records")
        self.lbl_helper.setProperty("class", "CardHelper")
        layout.addWidget(self.lbl_helper)

    def set_data(self, value, helper_text=""):
        self.lbl_value.setText(str(value))
        if helper_text:
            self.lbl_helper.setText(helper_text)

class RecentResultsPanel(QFrame):
    """
    Table showing last 10 outcomes.
    """
    def __init__(self):
        super().__init__()
        self.setProperty("class", "Card")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        header = QLabel("RECENT RESULTS")
        header.setProperty("class", "CardTitle")
        layout.addWidget(header)
        
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["ISBN", "Status", "Detail"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setWordWrap(False)
        self.table.setStyleSheet("background: transparent; border: none;")
        
        layout.addWidget(self.table)
    
    def update_data(self, records):
        """Records: list of dict(isbn, status, detail, time)"""
        self.table.setRowCount(0)
        for row_idx, r in enumerate(records):
            self.table.insertRow(row_idx)
            
            # ISBN
            item_isbn = QTableWidgetItem(r['isbn'])
            # We don't force a white foreground so it remains visible in Light Mode
            self.table.setItem(row_idx, 0, item_isbn)
            
            # Status
            status = r['status']
            item_status = QTableWidgetItem(status)
            if status == "Successful":
                item_status.setForeground(QColor("#4CAF50")) # Safe accessible green
            else:
                item_status.setForeground(QColor("#E53935")) # Safe accessible red
            self.table.setItem(row_idx, 1, item_status)
            
            # Detail (Truncated with Tooltip)
            detail_text = r.get('detail') or "-"
            item_detail = QTableWidgetItem(_truncate_text(detail_text, 90))
            item_detail.setForeground(QColor("#a5adcb"))
            item_detail.setToolTip(detail_text) # Full text on hover
            self.table.setItem(row_idx, 2, item_detail)


class ProfileSwitchCombo(QComboBox):
    """Dashboard profile switcher with a guaranteed visible chevron affordance."""

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#e6eaf6"), 2))
        cx = self.width() - 21
        cy = self.height() // 2 + 1
        s = 5
        painter.drawLine(cx - s, cy - 2, cx, cy + 3)
        painter.drawLine(cx, cy + 3, cx + s, cy - 2)
        painter.end()


class DashboardTabV2(QWidget):
    profile_selected = pyqtSignal(str)
    create_profile_requested = pyqtSignal()
    page_title_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.db.init_db()
        # No result files until a harvest runs this session
        self.result_files = {
            "successful": None,
            "invalid": None,
            "failed": None,
            "problems": None,
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
        self._is_running = False  # Guard: live RunStats stream prevents tab-switch overwrite
        self.session_recent = []
        self.last_run_text = "Last Run: Never"
        self._responsive_mode = None
        self._setup_ui()
        
        # Auto-refresh timer (2s for live feel)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_data)
        self.timer.start(2000)
        
        self.refresh_data()

    def _setup_ui(self):
        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _outer.setSpacing(0)

        # Top-level stack: 0 = dashboard, 1 = Linked ISBNs panel
        self._main_stack = QStackedWidget()
        _outer.addWidget(self._main_stack)

        # ── Page 0: Dashboard ──────────────────────────────────────
        _dash_page = QWidget()
        _dash_layout = QVBoxLayout(_dash_page)
        _dash_layout.setContentsMargins(0, 0, 0, 0)
        _dash_layout.setSpacing(0)

        _scroll = QScrollArea()
        _scroll.setWidgetResizable(True)
        _scroll.setFrameShape(QFrame.Shape.NoFrame)
        _scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        _scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        _scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        _scr_content = QWidget()
        _scr_content.setMinimumWidth(700)  # cards never compress below this
        _scroll.setWidget(_scr_content)
        _dash_layout.addWidget(_scroll)
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

        # Left: result-file actions
        left_col = QVBoxLayout()
        left_col.setSpacing(14)
        left_col.addWidget(self._build_result_files_panel())
        left_col.addStretch()
        self.left_col = left_col
        self.content_split.addLayout(left_col, stretch=2)
        
        # Right: Recent Results (60%)
        self.recent_panel = RecentResultsPanel()
        self.recent_panel.setMinimumWidth(320)
        self.recent_panel.setMinimumHeight(280)  # stays visible when stacked in compact mode
        self.content_split.addWidget(self.recent_panel, stretch=3)
        
        main_layout.addLayout(self.content_split)
        
        main_layout.addStretch()
        self._apply_responsive_layout(self.width() or 1200)
        self._refresh_result_file_buttons()

        # ── Page 1: Linked ISBNs full panel ───────────────────────
        self._main_stack.addWidget(self._build_linked_isbn_page())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout(event.size().width())

    def _apply_responsive_layout(self, width: int):
        mode = "compact" if width < 900 else "wide"
        if mode == self._responsive_mode:
            return
        self._responsive_mode = mode

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

    def _build_result_files_panel(self):
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

        # Format Switch
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
        self.btn_open_problems = self._create_result_open_button(
            _problems_button_label(self.current_profile, include_profile=False).replace(".tsv", ""),
            "problems",
        )
        
        layout.addWidget(self.btn_open_successful)
        layout.addWidget(self.btn_open_failed)
        layout.addWidget(self.btn_open_invalid)
        layout.addWidget(self.btn_open_problems)

        self.btn_open_linked_isbns = QPushButton("Export linked ISBNs")
        self.btn_open_linked_isbns.setProperty("class", "SecondaryButton")
        self.btn_open_linked_isbns.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_linked_isbns.setMinimumHeight(42)
        self.btn_open_linked_isbns.setToolTip(
            "Export the ISBN → canonical ISBN mapping table and open it"
        )
        self.btn_open_linked_isbns.clicked.connect(self._export_linked_isbns)
        layout.addWidget(self.btn_open_linked_isbns)

        self.btn_browse_db = QPushButton("Browse Database")
        self.btn_browse_db.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse_db.setMinimumHeight(42)
        self.btn_browse_db.setProperty("class", "SecondaryButton")
        self.btn_browse_db.setToolTip("Browse all records in the harvester database")
        self.btn_browse_db.clicked.connect(self._open_database_browser)
        layout.addWidget(self.btn_browse_db)

        self.btn_linked_isbns = QPushButton("Linked ISBNs")
        self.btn_linked_isbns.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_linked_isbns.setMinimumHeight(42)
        self.btn_linked_isbns.setProperty("class", "SecondaryButton")
        self.btn_linked_isbns.setToolTip("Query, link, or merge linked ISBN rows")
        self.btn_linked_isbns.clicked.connect(self._go_to_linked_isbn_page)
        layout.addWidget(self.btn_linked_isbns)

        self.btn_reset_stats = QPushButton("Reset Dashboard Stats")
        self.btn_reset_stats.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_stats.setMinimumHeight(42)
        self.btn_reset_stats.setProperty("class", "DangerButton")
        self.btn_reset_stats.clicked.connect(self._reset_dashboard_stats)
        layout.addWidget(self.btn_reset_stats)
        return panel

    def _create_result_open_button(self, text, key):
        btn = QPushButton(text)
        btn.setProperty("class", "SecondaryButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(42)
        btn.setEnabled(False)
        btn.clicked.connect(lambda: self._open_result_file(key))
        return btn


    def set_result_files(self, paths: dict):
        """Called when a new harvest starts with the paths of the live output files."""
        self.result_files = {
            "successful": Path(paths["successful"]) if paths.get("successful") else None,
            "invalid": Path(paths["invalid"]) if paths.get("invalid") else None,
            "failed": Path(paths["failed"]) if paths.get("failed") else None,
            "problems": Path(paths["problems"]) if paths.get("problems") else None,
            "profile_dir": Path(paths["profile_dir"]) if paths.get("profile_dir") else self._profile_dir_path(),
        }
        self._refresh_result_file_buttons()

    def _refresh_result_file_buttons(self):
        if not hasattr(self, "btn_open_successful"):
            return
        default_labels = {
            "successful": "Open successful",
            "failed": "Open failed",
            "invalid": "Open invalid",
            "problems": "Open targets problems",
        }
        mapping = {
            "successful": self.btn_open_successful,
            "failed": self.btn_open_failed,
            "invalid": self.btn_open_invalid,
            "problems": self.btn_open_problems,
        }
        
        is_csv = getattr(self, "format_combo", None) and self.format_combo.currentText().startswith("CSV")
        ext = ".csv" if is_csv else ".tsv"
        
        for key, btn in mapping.items():
            path = self.result_files.get(key)
            if path is not None:
                # Check for the correct extension file
                check_path = path.with_suffix(ext)
                
                # If CSV is requested but not finalized, we can enable the button as long as the base TSV exists.
                if is_csv:
                    enabled = path.exists() 
                else:
                    enabled = check_path.exists()
                    
                btn.setEnabled(enabled)
                
                # Append extension cleanly
                base_label = default_labels[key]
                btn.setText(f"{base_label}{ext}")
            else:
                btn.setEnabled(False)
        profile_dir = self.result_files.get("profile_dir") or self._profile_dir_path()
        self.btn_open_profile_folder.setEnabled(profile_dir is not None and profile_dir.exists())

    def _open_result_file(self, key):
        path = self.result_files[key]
        is_csv = getattr(self, "format_combo", None) and self.format_combo.currentText().startswith("CSV")
        ext = ".csv" if is_csv else ".tsv"
        target_path = path.with_suffix(ext)

        # Generate on the fly if CSV is selected mid-harvest.
        if is_csv and not target_path.exists() and path.exists():
            try:
                _write_csv_copy(str(path), str(target_path))
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
        """Export the linked_isbns table to a TSV/CSV file and open it."""
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
        out_path = out_dir / f"linked-isbns-{stamp}{ext}"

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
        return Path("data") / _safe_filename(self.current_profile)

    def _open_profile_folder(self):
        path = self.result_files.get("profile_dir") or self._profile_dir_path()
        if not path.exists():
            QMessageBox.warning(self, "Folder Not Found", f"{path} does not exist yet.")
            self._refresh_result_file_buttons()
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
            QMessageBox.warning(self, "Open Failed", f"Could not open {path}.")

    def _reset_dashboard_stats(self):
        """Reset only the visible dashboard state."""
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
        dialog = DatabaseBrowserDialog(parent=self, db=self.db)
        dialog.exec()

    def _go_to_linked_isbn_page(self):
        self._main_stack.setCurrentIndex(1)
        self.page_title_changed.emit("Linked ISBNs")

    def _go_to_dashboard(self):
        self._main_stack.setCurrentIndex(0)
        self.page_title_changed.emit("Dashboard")

    # ------------------------------------------------------------------
    # Linked ISBNs sub-page (embedded in the dashboard stack)
    # ------------------------------------------------------------------
    def _build_linked_isbn_page(self) -> QWidget:
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
        color = "#ef4444" if error else "#22c55e"
        self._li_status.setText(msg)
        self._li_status.setStyleSheet(f"color: {color};")

    def _li_run_query(self):
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
        """Refresh dashboard-only state without repopulating cleared results."""
        try:
            self._refresh_result_file_buttons()
            self._render_session_stats()
            self.recent_panel.update_data(self.session_recent)
            self.lbl_last_run.setText(self.last_run_text)
        except Exception as e:
            print(f"Dashboard Refresh Error: {e}")

    def update_live_status(self, target, isbn, progress, msg):
        """Called by MainWindow during harvest."""
        self.last_run_text = _truncate_text(f"Last Event: {msg}", 140)
        self.lbl_last_run.setText(self.last_run_text)

    def record_harvest_event(self, isbn: str, status: str, detail: str):
        if status not in ("found", "failed", "cached", "skipped"):
            return
        self.session_stats["processed"] += 1
        if status in ("found", "cached"):
            self.session_stats["successful"] += 1
        elif status in ("failed", "skipped"):
            self.session_stats["failed"] += 1
        self._append_recent_result(isbn, status, detail)
        self._render_session_stats()

    def apply_run_stats(self, stats):
        """Accept either a dict (legacy) or a RunStats dataclass."""
        # Prefer the embedded RunStats object when available in a dict
        if isinstance(stats, dict) and hasattr(stats.get("run_stats"), 'processed_unique'):
            stats = stats["run_stats"]
        base = getattr(self, '_baseline_stats', {})
        b_proc = base.get('processed', 0)
        b_found = base.get('found', 0)
        b_failed_total = base.get('failed', 0)
        b_invalid = base.get('invalid', 0)
        b_true_failed = max(0, b_failed_total - b_invalid)

        if hasattr(stats, 'processed_unique'):  # RunStats dataclass
            found = getattr(stats, 'found', 0)
            failed = getattr(stats, 'failed', 0)
            skipped = getattr(stats, 'skipped', 0)
            invalid = getattr(stats, 'invalid', 0)
            processed = getattr(stats, 'processed_unique', 0) + invalid
            self.session_stats = {
                "processed": b_proc + processed,
                "successful": b_found + found,
                "failed": b_true_failed + failed + skipped,
                "invalid": b_invalid + invalid,
            }
        else:  # legacy dict
            stats = stats or {}
            self.session_stats = {
                "processed": b_proc + int(stats.get("found", 0)) + int(stats.get("failed", 0)) + int(stats.get("cached", 0)) + int(stats.get("skipped", 0)) + int(stats.get("invalid", 0)),
                "successful": b_found + int(stats.get("found", 0)) + int(stats.get("cached", 0)),
                "failed": b_true_failed + int(stats.get("failed", 0)) + int(stats.get("skipped", 0)),
                "invalid": b_invalid + int(stats.get("invalid", 0)),
            }
        self._render_session_stats()

    def update_live_stats(self, stats):
        """Live update session_stats from a RunStats object emitted by HarvestWorkerV2."""
        if not hasattr(stats, 'processed_unique'):
            return  # Only handle RunStats dataclass
            
        base = getattr(self, '_baseline_stats', {})
        b_proc = base.get('processed', 0)
        b_found = base.get('found', 0)
        b_failed_total = base.get('failed', 0)
        b_invalid = base.get('invalid', 0)
        b_true_failed = max(0, b_failed_total - b_invalid)
        
        found = getattr(stats, 'found', 0)
        failed = getattr(stats, 'failed', 0)
        skipped = getattr(stats, 'skipped', 0)
        invalid = getattr(stats, 'invalid', 0)
        processed = getattr(stats, 'processed_unique', 0) + invalid
        self.session_stats = {
            "processed": b_proc + processed,
            "successful": b_found + found,
            "failed": b_true_failed + failed + skipped,
            "invalid": b_invalid + invalid,
        }
        self._render_session_stats()

    def reset_dashboard_stats(self):
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
        status_label = "Successful" if status.lower() in ("found", "cached", "successful") else "Failed"
        self.session_recent.insert(
            0,
            {
                "isbn": isbn or "-",
                "status": status_label,
                "detail": detail or "-",
                "time": datetime.now().isoformat(),
            },
        )
        self.session_recent = self.session_recent[:10]
        self.recent_panel.update_data(self.session_recent)

    def _render_session_stats(self):
        self.card_proc.set_data(self.session_stats["processed"], "Processed in this dashboard view")
        self.card_found.set_data(self.session_stats["successful"], "Successfully harvested")
        self.card_failed.set_data(self.session_stats["failed"], "Failed or skipped in this dashboard view")
        self.card_invalid.set_data(self.session_stats["invalid"], "Invalid ISBNs in this run")

    def set_profile_options(self, profiles, current_profile):
        incoming = current_profile or "default"
        profile_changed = incoming != self.current_profile
        self.current_profile = incoming
        if profile_changed:
            self.reset_dashboard_stats()
            self.result_files = {
                "successful": None,
                "invalid": None,
                "failed": None,
                "problems": None,
                "profile_dir": None,
            }
        self.result_files["profile_dir"] = self._profile_dir_path()
        self._refresh_result_file_buttons()

    def _on_profile_combo_changed(self, name):
        if name:
            self.profile_selected.emit(name)
        

    def set_advanced_mode(self, enabled):
        pass

    def set_running(self):
        self._is_running = True
        self._refresh_result_file_buttons()
        self.lbl_run_status.setText("● RUNNING")
        self.lbl_run_status.setProperty("state", "running")
        self._refresh_status_style()

    def set_paused(self, is_paused: bool):
        if is_paused:
            self.lbl_run_status.setText("● PAUSED")
            self.lbl_run_status.setProperty("state", "paused")
        else:
            self.lbl_run_status.setText("● RUNNING")
            self.lbl_run_status.setProperty("state", "running")
        self._refresh_status_style()

    def set_idle(self, success: bool | None = None):
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
        self.lbl_run_status.style().unpolish(self.lbl_run_status)
        self.lbl_run_status.style().polish(self.lbl_run_status)
    
