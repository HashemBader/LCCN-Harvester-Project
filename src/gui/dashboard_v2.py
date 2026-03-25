"""
Module: dashboard_v2.py
Professional V2 Dashboard with Header, KPIs, Live Activity, and Recent Results.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QBoxLayout, QLabel, QFrame,
    QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QPushButton, QSizePolicy, QMessageBox
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
        # Wrap content in a scroll area so widgets never get compressed on resize
        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _outer.setSpacing(0)
        _scroll = QScrollArea()
        _scroll.setWidgetResizable(True)
        _scroll.setFrameShape(QFrame.Shape.NoFrame)
        _scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        _scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        _scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        _scr_content = QWidget()
        _scr_content.setMinimumWidth(700)  # cards never compress below this
        _scroll.setWidget(_scr_content)
        _outer.addWidget(_scroll)
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
        # Use actual widget width; fall back to wide default on first paint
        self._apply_responsive_layout(self.width() or 1200)
        self._refresh_result_file_buttons()

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
                    "SELECT isbn, canonical_isbn FROM linked_isbns ORDER BY canonical_isbn, isbn"
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
                "processed": b_proc + int(stats.get("found", 0)) + int(stats.get("failed", 0)) + int(stats.get("cached", 0)) + int(stats.get("skipped", 0)),
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
    
