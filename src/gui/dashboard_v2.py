"""
Module: dashboard_v2.py
Professional V2 Dashboard with Header, KPIs, Live Activity, and Recent Results.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QProgressBar, QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView,
    QGraphicsDropShadowEffect, QComboBox, QPushButton, QSizePolicy, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal, QUrl
from datetime import datetime
from pathlib import Path
from PyQt6.QtGui import QColor, QPixmap, QPainter, QPen, QDesktopServices

from database import DatabaseManager
from .theme_manager import ThemeManager
from .styles_v2 import CATPPUCCIN_DARK, CATPPUCCIN_LIGHT
from .icons import (
    get_pixmap, SVG_ACTIVITY, SVG_CHECK_CIRCLE, SVG_ALERT_CIRCLE, SVG_X_CIRCLE, SVG_DASHBOARD, SVG_SETTINGS
)

class DashboardCard(QFrame):
    """
    A single KPI card with Icon, Title, Value, Helper Text.
    """
    def __init__(self, title, icon_svg, accent_color="#8aadf4"):
        super().__init__()
        self.setProperty("class", "Card")
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
        self.table.setStyleSheet("background: transparent; border: none;")
        
        layout.addWidget(self.table)
    
    def update_data(self, records):
        """Records: list of dict(isbn, status, detail, time)"""
        mode = ThemeManager().get_theme()
        t = CATPPUCCIN_DARK if mode == "dark" else CATPPUCCIN_LIGHT
        
        self.table.setRowCount(0)
        for row_idx, r in enumerate(records):
            self.table.insertRow(row_idx)
            
            # ISBN
            item_isbn = QTableWidgetItem(r['isbn'])
            item_isbn.setForeground(QColor(t['text']))
            self.table.setItem(row_idx, 0, item_isbn)
            
            # Status
            status = r['status']
            item_status = QTableWidgetItem(status)
            if status == "Found":
                item_status.setForeground(QColor(t['success']))
            else:
                item_status.setForeground(QColor(t['danger']))
            self.table.setItem(row_idx, 1, item_status)
            
            # Detail (Truncated with Tooltip)
            detail_text = r.get('detail') or "-"
            item_detail = QTableWidgetItem(detail_text)
            item_detail.setForeground(QColor(t['text_muted']))
            item_detail.setToolTip(detail_text) # Full text on hover
            self.table.setItem(row_idx, 2, item_detail)

    def prepend_data(self, record: dict):
        """Insert a single new record at the top in real-time."""
        mode = ThemeManager().get_theme()
        t = CATPPUCCIN_DARK if mode == "dark" else CATPPUCCIN_LIGHT
        
        self.table.insertRow(0)
        
        item_isbn = QTableWidgetItem(record.get('isbn', ''))
        item_isbn.setForeground(QColor(t['text']))
        self.table.setItem(0, 0, item_isbn)
        
        status = record.get('status', '')
        item_status = QTableWidgetItem(status)
        if status == "Found":
            item_status.setForeground(QColor(t['success']))
        else:
            item_status.setForeground(QColor(t['danger']))
        self.table.setItem(0, 1, item_status)
        
        detail_text = record.get('detail') or "-"
        item_detail = QTableWidgetItem(detail_text)
        item_detail.setForeground(QColor(t['text_muted']))
        item_detail.setToolTip(detail_text)
        self.table.setItem(0, 2, item_detail)
        
        # Enforce exactly 10 visible history rows
        if self.table.rowCount() > 10:
            self.table.removeRow(10)


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
        self._baseline_stats = {'processed': 0, 'found': 0, 'failed': 0, 'invalid': 0}
        self._is_running = False  # Guard: prevents DB polling overwriting live stats
        # No result files until a harvest runs this session
        self.result_files = {
            "successful": None,
            "invalid": None,
            "failed": None,
        }
        self._setup_ui()
        
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
        _scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        _scr_content = QWidget()
        _scroll.setWidget(_scr_content)
        _outer.addWidget(_scroll)
        main_layout = QVBoxLayout(_scr_content)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(20)

        # 1. Header Bar
        header_layout = QHBoxLayout()
        
        self.lbl_run_status = QLabel("● IDLE")
        self.lbl_run_status.setProperty("class", "StatusPill")
        self.lbl_run_status.setProperty("state", "idle")
        
        self.lbl_last_run = QLabel("Last Run: Never")
        self.lbl_last_run.setProperty("class", "HelperText")
        
        header_layout.addWidget(self.lbl_run_status)
        header_layout.addWidget(self.lbl_last_run)
        header_layout.addStretch()
        
        main_layout.addLayout(header_layout)

        # 1b. Profile dock (right utility)
        profile_row = QHBoxLayout()
        profile_row.setContentsMargins(0, 0, 0, 0)
        profile_row.setSpacing(0)
        profile_row.addStretch()

        self.profile_panel = QFrame()
        self.profile_panel.setObjectName("DashboardProfilePanel")
        self.profile_panel.setMinimumHeight(74)
        self.profile_panel.setMaximumWidth(720)
        self.profile_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        profile_panel_layout = QHBoxLayout(self.profile_panel)
        profile_panel_layout.setContentsMargins(12, 10, 12, 10)
        profile_panel_layout.setSpacing(10)

        self.profile_icon = QLabel()
        self.profile_icon.setObjectName("DashboardProfileIcon")
        self.profile_icon.setFixedSize(30, 30)
        self.profile_icon.setPixmap(get_pixmap(SVG_SETTINGS, "#8aadf4", 18))
        self.profile_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        profile_panel_layout.addWidget(self.profile_icon)

        profile_text_col = QVBoxLayout()
        profile_text_col.setSpacing(1)

        self.profile_title = QLabel("PROFILES")
        self.profile_title.setObjectName("DashboardProfileEyebrow")
        profile_text_col.addWidget(self.profile_title)

        self.profile_meta = QLabel("0 saved")
        self.profile_meta.setObjectName("DashboardProfileMeta")
        profile_text_col.addWidget(self.profile_meta)

        profile_panel_layout.addLayout(profile_text_col)
        profile_panel_layout.addSpacing(4)

        self.profile_combo = ProfileSwitchCombo()
        self.profile_combo.setObjectName("DashboardProfileCombo")
        self.profile_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.profile_combo.setMinimumWidth(260)
        self.profile_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.profile_combo.setMaximumWidth(390)
        self.profile_combo.setToolTip("")
        self.profile_combo.currentTextChanged.connect(self._on_profile_combo_changed)
        profile_panel_layout.addWidget(self.profile_combo, 1)

        self.btn_new_profile = QPushButton("Manage Profiles")
        self.btn_new_profile.setObjectName("DashboardProfileAction")
        self.btn_new_profile.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new_profile.setMinimumWidth(142)
        self.btn_new_profile.setToolTip("")
        self.btn_new_profile.clicked.connect(self.create_profile_requested.emit)
        profile_panel_layout.addWidget(self.btn_new_profile)

        profile_row.addWidget(self.profile_panel)
        main_layout.addLayout(profile_row)

        # 2. KPI Cards Row
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(20)

        self.card_proc = DashboardCard("PROCESSED", SVG_ACTIVITY, "#8aadf4")
        self.card_found = DashboardCard("FOUND", SVG_CHECK_CIRCLE, "#a6da95")
        self.card_failed = DashboardCard("FAILED", SVG_X_CIRCLE, "#ed8796")
        self.card_invalid = DashboardCard("INVALID", SVG_ALERT_CIRCLE, "#fab387")
        
        kpi_layout.addWidget(self.card_proc)
        kpi_layout.addWidget(self.card_found)
        kpi_layout.addWidget(self.card_failed)
        kpi_layout.addWidget(self.card_invalid)
        
        main_layout.addLayout(kpi_layout)

        # 3. Main Content Split (Live vs Recent)
        content_split = QHBoxLayout()

        # Left: Live panel + result-file actions (40%)
        left_col = QVBoxLayout()
        left_col.setSpacing(14)
        left_col.addWidget(self._build_result_files_panel())
        left_col.addStretch()
        content_split.addLayout(left_col, stretch=2)
        
        # Right: Recent Results (60%)
        self.recent_panel = RecentResultsPanel()
        content_split.addWidget(self.recent_panel, stretch=3)
        
        main_layout.addLayout(content_split)
        
        main_layout.addStretch()
        self._refresh_result_file_buttons()

    def _build_result_files_panel(self):
        panel = QFrame()
        panel.setProperty("class", "Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("RESULT FILES")
        title.setProperty("class", "CardTitle")
        layout.addWidget(title)

        subtitle = QLabel("Live TSV files are created fresh for each harvest run.")
        subtitle.setProperty("class", "HelperText")
        layout.addWidget(subtitle)

        self.btn_open_successful = self._create_result_open_button("Open successful.tsv", "successful")
        self.btn_open_invalid = self._create_result_open_button("Open invalid.tsv", "invalid")
        self.btn_open_failed = self._create_result_open_button("Open failed.tsv", "failed")
        layout.addWidget(self.btn_open_successful)
        layout.addWidget(self.btn_open_invalid)
        layout.addWidget(self.btn_open_failed)

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
            "invalid":    Path(paths["invalid"])    if paths.get("invalid")    else None,
            "failed":     Path(paths["failed"])     if paths.get("failed")     else None,
        }
        self._refresh_result_file_buttons()

    def _refresh_result_file_buttons(self):
        if not hasattr(self, "btn_open_successful"):
            return
        mapping = {
            "successful": self.btn_open_successful,
            "invalid": self.btn_open_invalid,
            "failed": self.btn_open_failed,
        }
        for key, btn in mapping.items():
            path = self.result_files.get(key)
            enabled = path is not None and path.exists()
            btn.setEnabled(enabled)
            if path is not None:
                btn.setText(f"Open {path.name}")
            else:
                btn.setText(f"Open {key}.tsv")

    def _open_result_file(self, key):
        path = self.result_files[key]
        if not path.exists():
            QMessageBox.warning(self, "File Not Found", f"{path} does not exist yet.")
            self._refresh_result_file_buttons()
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
            QMessageBox.warning(self, "Open Failed", f"Could not open {path}.")

    def _read_offsets(self):
        try:
            import json
            with open("data/gui_offsets.json", "r") as f:
                return json.load(f)
        except Exception:
            return {"processed": 0, "found": 0, "failed": 0, "invalid": 0}

    def _write_offsets(self, offsets):
        import json
        with open("data/gui_offsets.json", "w") as f:
            json.dump(offsets, f)

    def _reset_dashboard_stats(self):
        """Reset dashboard counters visually via offset tracker."""
        if "RUNNING" in self.lbl_run_status.text():
            QMessageBox.information(self, "Harvest Running", "Stop the current harvest before resetting dashboard stats.")
            return

        confirm = QMessageBox.question(
            self,
            "Reset Dashboard Stats",
            "This resets dashboard numbers to zero visually without dropping records from the database. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            stats = self.db.get_global_stats()
            offsets = {
                "processed": int(stats.get("processed", 0)),
                "found": int(stats.get("found", 0)),
                "failed": int(stats.get("failed", 0)),
                "invalid": int(stats.get("invalid", 0))
            }
            self._write_offsets(offsets)
            self.refresh_data()
            # Also clear the Recent Results panel to visually reflect a clean slate
            self.recent_panel.update_data([])
            self.set_idle(None)
        except Exception as e:
            QMessageBox.warning(self, "Reset Failed", f"Could not reset dashboard stats: {e}")

    def refresh_data(self, run_stats=None):
        """Fetch latest stats from DB and update cards, or use provided run_stats."""
        try:
            self._refresh_result_file_buttons()
            
            if run_stats is not None:
                self.update_live_stats(run_stats)
            elif self._is_running:
                # Skip DB polling while a harvest is actively streaming live data
                return
            else:
                stats = self.db.get_global_stats()
                offsets = self._read_offsets()
                
                raw_proc = int(stats.get("processed", 0))
                raw_found = int(stats.get("found", 0))
                raw_failed = int(stats.get("failed", 0))
                raw_invalid = int(stats.get("invalid", 0))

                processed = max(0, raw_proc - offsets.get("processed", 0))
                found = max(0, raw_found - offsets.get("found", 0))
                failed = max(0, raw_failed - offsets.get("failed", 0))
                invalid = max(0, raw_invalid - offsets.get("invalid", 0))

                failed_noninvalid = max(0, failed - invalid)
                
                # Update Cards
                self.card_proc.set_data(processed, "Total records attempted")
                self.card_found.set_data(found, "Successfully harvested")
                self.card_failed.set_data(failed_noninvalid, "Errors or Not Found (excluding invalid)")
                self.card_invalid.set_data(invalid, "Invalid ISBNs")

            # Update Recent
            recent = self.db.get_recent_results(limit=10)
            self.recent_panel.update_data(recent)
            # Update "Last Run" from most recent DB activity
            last_run = "Last Run: Never"
            if recent:
                t = recent[0].get("time")
                if t:
                    try:
                        # Parse ISO format (handled by fromisoformat in newer python, or simplistic split)
                        # DB likely stores ISO string.
                        dt = datetime.fromisoformat(t)
                        # Format: "Oct 27, 10:30 AM" or "2024-10-27 10:30"
                        readable_time = dt.strftime("%Y-%m-%d %H:%M")
                        last_run = f"Last Run: {readable_time}"
                    except ValueError:
                        last_run = f"Last Run: {t}" # Fallback
            self.lbl_last_run.setText(last_run)

            # Live Status (Mocked for now, real connection via signals in Window)
            # Window sets this via callback, but here we can poll if we stored state in DB
            
        except Exception as e:
            print(f"Dashboard Refresh Error: {e}")

    def update_live_status(self, target, isbn, progress, msg):
        """Called by MainWindow during harvest."""
        pass

    def append_live_result(self, record: dict):
        """Receive a real-time ISBN result directly from the pipeline worker."""
        # Visual override to update "Last Run" instantly to now during active harvest
        dt = datetime.now()
        readable_time = dt.strftime("%Y-%m-%d %H:%M")
        self.lbl_last_run.setText(f"Last Run: {readable_time} (Live)")
        
        # Insert the row statically into the table
        self.recent_panel.prepend_data(record)

    def update_live_stats(self, stats):
        """Receive real-time statistics strictly from the RunStats object."""
        base = getattr(self, '_baseline_stats', {'processed': 0, 'found': 0, 'failed': 0, 'invalid': 0})
        
        # stats is a RunStats dataclass from run_harvest.py
        processed_live = getattr(stats, "processed_unique", 0)
        found_live = getattr(stats, "found", 0)
        failed_live = getattr(stats, "failed", 0) + getattr(stats, "skipped", 0)
        invalid_live = getattr(stats, "invalid", 0)
        
        # 'base["failed"]' is SELECT COUNT(*) FROM attempted (which contains both failed AND invalid).
        # 'failed_live' is strictly standard failures. 'invalid_live' is strictly invalid.
        # Likewise, 'processed_live' is strictly standard valid rows. For 'Processed' to equal everything:
        total_processed = base['processed'] + processed_live + invalid_live
        total_found = base['found'] + found_live
        total_invalid = base['invalid'] + invalid_live
        
        # Real historical failures = base['failed'] - base['invalid']
        historical_failed_only = max(0, base['failed'] - base['invalid'])
        total_failed_only = historical_failed_only + failed_live
        
        self.card_proc.set_data(total_processed, "Total records attempted")
        self.card_found.set_data(total_found, "Successfully harvested")
        self.card_failed.set_data(total_failed_only, "Errors or Not Found (excluding invalid)")
        self.card_invalid.set_data(total_invalid, "Invalid ISBNs")


    def set_profile_options(self, profiles, current_profile):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItems(profiles or [])
        idx = self.profile_combo.findText(current_profile or "")
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)
        self.profile_combo.blockSignals(False)
        count = len(profiles or [])
        self.profile_meta.setText(f"{count} saved profiles")

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
        
        # Snapshot the current DB stats as a baseline so live updates accumulate naturally
        try:
            stats = self.db.get_global_stats()
            offsets = self._read_offsets()
            raw_proc = int(stats.get("processed", 0))
            raw_found = int(stats.get("found", 0))
            raw_failed = int(stats.get("failed", 0))
            raw_invalid = int(stats.get("invalid", 0))

            self._baseline_stats = {
                "processed": max(0, raw_proc - offsets.get("processed", 0)),
                "found": max(0, raw_found - offsets.get("found", 0)),
                "failed": max(0, raw_failed - offsets.get("failed", 0)),
                "invalid": max(0, raw_invalid - offsets.get("invalid", 0))
            }
        except Exception:
            self._baseline_stats = {'processed': 0, 'found': 0, 'failed': 0, 'invalid': 0}

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
    
