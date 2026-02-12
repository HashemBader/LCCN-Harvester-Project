"""
Module: dashboard_v2.py
Professional V2 Dashboard with Header, KPIs, Live Activity, and Recent Results.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout,
    QProgressBar, QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView,
    QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QTimer, QSize
from datetime import datetime
from PyQt6.QtGui import QColor, QPixmap

from database import DatabaseManager
from .icons import (
    get_pixmap, SVG_ACTIVITY, SVG_CHECK_CIRCLE, SVG_ALERT_CIRCLE, SVG_X_CIRCLE, SVG_DASHBOARD
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
        self.lbl_helper.setStyleSheet("color: #a5adcb; font-size: 11px;")
        layout.addWidget(self.lbl_helper)

    def set_data(self, value, helper_text=""):
        self.lbl_value.setText(str(value))
        if helper_text:
            self.lbl_helper.setText(helper_text)

class LiveActivityPanel(QFrame):
    """
    Shows current harvesting state: Target, ISBN, Progress.
    """
    def __init__(self):
        super().__init__()
        self.setProperty("class", "Card")
        self.setObjectName("LivePanel") # Enable targeted vibrant styling
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header = QLabel("LIVE ACTIVITY")
        header.setProperty("class", "CardTitle")
        layout.addWidget(header)
        
        # Grid content
        grid = QGridLayout()
        grid.setSpacing(10)
        
        self.lbl_target = QLabel("-")
        self.lbl_isbn = QLabel("-")
        self.lbl_stage = QLabel("Idle")
        
        self._add_row(grid, 0, "Current Target", self.lbl_target)
        self._add_row(grid, 1, "Processing ISBN", self.lbl_isbn)
        
        layout.addLayout(grid)
        layout.addSpacing(10)
        
        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #181926; border-radius: 6px; height: 8px; text-align: center;
            }
            QProgressBar::chunk { background-color: #8aadf4; border-radius: 6px; }
        """)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Activity Text
        self.lbl_status_text = QLabel("Ready to start.")
        self.lbl_status_text.setStyleSheet("color: #cad3f5; font-size: 13px; margin-top: 5px;")
        layout.addWidget(self.lbl_status_text)
        
        layout.addStretch()

    def _add_row(self, layout, row, label, widget):
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #a5adcb; font-weight: 600;")
        widget.setStyleSheet("color: #ffffff; font-family: Consolas;")
        layout.addWidget(lbl, row, 0)
        layout.addWidget(widget, row, 1)

    def update_status(self, target, isbn, progress_pct, message):
        self.lbl_target.setText(target or "-")
        self.lbl_isbn.setText(isbn or "-")
        self.progress_bar.setValue(int(progress_pct))
        self.lbl_status_text.setText(message)

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
        self.table.setRowCount(0)
        for row_idx, r in enumerate(records):
            self.table.insertRow(row_idx)
            
            # ISBN
            item_isbn = QTableWidgetItem(r['isbn'])
            item_isbn.setForeground(QColor("#ffffff"))
            self.table.setItem(row_idx, 0, item_isbn)
            
            # Status
            status = r['status']
            item_status = QTableWidgetItem(status)
            if status == "Found":
                item_status.setForeground(QColor("#a6da95")) # Green
            else:
                item_status.setForeground(QColor("#ed8796")) # Red
            self.table.setItem(row_idx, 1, item_status)
            
            # Detail (Truncated with Tooltip)
            detail_text = r.get('detail') or "-"
            item_detail = QTableWidgetItem(detail_text)
            item_detail.setForeground(QColor("#a5adcb"))
            item_detail.setToolTip(detail_text) # Full text on hover
            self.table.setItem(row_idx, 2, item_detail)


class DashboardTabV2(QWidget):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.db.init_db()
        self._setup_ui()
        
        # Auto-refresh timer (2s for live feel)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_data)
        self.timer.start(2000)
        
        self.refresh_data()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(20)

        # 1. Header Bar
        header_layout = QHBoxLayout()
        
        self.lbl_run_status = QLabel("● IDLE")
        self.lbl_run_status.setStyleSheet("color: #a5adcb; font-weight: bold; padding: 5px 10px; background: #363a4f; border-radius: 6px;")
        
        self.lbl_last_run = QLabel("Last Run: Never")
        self.lbl_last_run.setStyleSheet("color: #a5adcb; margin-left: 10px;")
        
        header_layout.addWidget(self.lbl_run_status)
        header_layout.addWidget(self.lbl_last_run)
        header_layout.addStretch()
        
        main_layout.addLayout(header_layout)

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
        
        # Left: Live Panel (40%)
        self.live_panel = LiveActivityPanel()
        content_split.addWidget(self.live_panel, stretch=2)
        
        # Right: Recent Results (60%)
        self.recent_panel = RecentResultsPanel()
        content_split.addWidget(self.recent_panel, stretch=3)
        
        main_layout.addLayout(content_split)
        
        main_layout.addStretch()

    def refresh_data(self):
        """Fetch latest stats from DB and update cards."""
        try:
            stats = self.db.get_global_stats()
            
            # Update Cards
            self.card_proc.set_data(stats['processed'], "Total records attempted")
            self.card_found.set_data(stats['found'], "Successfully harvested")
            self.card_failed.set_data(stats['failed'], "Errors or Not Found")
            # Invalid logic tracked via specific error message in DB
            self.card_invalid.set_data(stats.get('invalid', 0), "Invalid ISBNs") 

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
        self.live_panel.update_status(target, isbn, progress, msg)
        

    def set_advanced_mode(self, enabled):
        pass

    def set_running(self):
        self.lbl_run_status.setText("● RUNNING")
        self.lbl_run_status.setStyleSheet(
            "color: #1e2030; font-weight: bold; padding: 5px 10px; background: #8aadf4; border-radius: 6px;"
        )

    def set_idle(self, success: bool | None = None):
        if success is True:
            self.lbl_run_status.setText("● COMPLETED")
            self.lbl_run_status.setStyleSheet(
                "color: #1e2030; font-weight: bold; padding: 5px 10px; background: #a6da95; border-radius: 6px;"
            )
        elif success is False:
            self.lbl_run_status.setText("● STOPPED")
            self.lbl_run_status.setStyleSheet(
                "color: #1e2030; font-weight: bold; padding: 5px 10px; background: #ed8796; border-radius: 6px;"
            )
        else:
            self.lbl_run_status.setText("● IDLE")
            self.lbl_run_status.setStyleSheet(
                "color: #a5adcb; font-weight: bold; padding: 5px 10px; background: #363a4f; border-radius: 6px;"
            )
    
