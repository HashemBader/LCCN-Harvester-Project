"""
Module: database_browser_dialog.py
Full database browser — shows all rows across main, attempted, linked_isbns,
and subjects tables with live search and pagination.
"""
import sqlite3

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QWidget, QSizePolicy, QComboBox
)
from PyQt6.QtCore import Qt, QTimer

from database import DatabaseManager
from database.db_manager import yyyymmdd_to_iso_date

TABLE_COLUMNS = {
    "main":         ["isbn", "call_number", "call_number_type", "classification", "source", "date_added"],
    "attempted":    ["isbn", "last_target", "attempt_type", "last_attempted", "fail_count", "last_error"],
    "linked_isbns": ["lowest_isbn", "other_isbn"],
    "subjects":     ["id", "isbn", "field", "indicator2", "subject", "source", "date_added"],
}

# Index of the column used for source filtering (None = no source filter for that table)
SOURCE_COL_INDEX = {
    "main":         4,   # source
    "attempted":    1,   # last_target
    "linked_isbns": None,
    "subjects":     5,   # source
}

PAGE_SIZE = 200


class _TableTab(QWidget):
    """A single tab showing one DB table with search and pagination."""

    def __init__(self, table_name: str, db_path: str, parent=None):
        super().__init__(parent)
        self.table_name = table_name
        self.db_path = db_path
        self.columns = TABLE_COLUMNS[table_name]
        self._source_col: int | None = SOURCE_COL_INDEX.get(table_name)
        self._all_rows: list[tuple] = []
        self._filtered_rows: list[tuple] = []
        self._page = 0
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._apply_filter)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        # Top bar
        top = QHBoxLayout()
        top.setSpacing(8)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(f"Search {self.table_name}…")
        self.search_box.setMinimumHeight(36)
        self.search_box.setMaximumHeight(36)
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setStyleSheet("QLineEdit { padding: 4px 10px; }")
        self.search_box.textChanged.connect(lambda _: self._search_timer.start())
        top.addWidget(self.search_box, stretch=1)

        # Source filter — only shown for tables that have a source/target column
        if self._source_col is not None:
            col_label = self.columns[self._source_col].replace("_", " ").title()
            self.source_filter = QComboBox()
            self.source_filter.setMinimumHeight(36)
            self.source_filter.setMaximumHeight(36)
            self.source_filter.setMinimumWidth(180)
            self.source_filter.setToolTip(f"Filter by {col_label}")
            self.source_filter.setStyleSheet("QComboBox { padding: 4px 8px; }")
            self.source_filter.currentIndexChanged.connect(self._apply_filter)
            top.addWidget(self.source_filter)
        else:
            self.source_filter = None

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setProperty("class", "SecondaryButton")
        self.btn_refresh.setMinimumHeight(36)
        self.btn_refresh.setMinimumWidth(90)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.load_data)
        top.addWidget(self.btn_refresh)
        layout.addLayout(top)

        # Row info
        self.lbl_info = QLabel("Loading…")
        self.lbl_info.setProperty("class", "HelperText")
        layout.addWidget(self.lbl_info)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels([c.replace("_", " ").title() for c in self.columns])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(False)
        layout.addWidget(self.table, stretch=1)

        # Pagination
        pager = QHBoxLayout()
        self.btn_prev = QPushButton("← Prev")
        self.btn_prev.setProperty("class", "SecondaryButton")
        self.btn_prev.setMinimumHeight(32)
        self.btn_prev.setMinimumWidth(90)
        self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev.clicked.connect(self._prev_page)

        self.lbl_page = QLabel("Page 1")
        self.lbl_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_page.setProperty("class", "HelperText")

        self.btn_next = QPushButton("Next →")
        self.btn_next.setProperty("class", "SecondaryButton")
        self.btn_next.setMinimumHeight(32)
        self.btn_next.setMinimumWidth(90)
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.clicked.connect(self._next_page)

        pager.addWidget(self.btn_prev)
        pager.addStretch()
        pager.addWidget(self.lbl_page)
        pager.addStretch()
        pager.addWidget(self.btn_next)
        layout.addLayout(pager)

    def load_data(self):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cols = ", ".join(self.columns)
            rows = conn.execute(f"SELECT {cols} FROM {self.table_name}").fetchall()
            conn.close()
            self._all_rows = [tuple(r) for r in rows]
        except Exception as e:
            self._all_rows = []
            self.lbl_info.setText(f"Error: {e}")

        # Repopulate source filter dropdown with distinct values
        if self.source_filter is not None and self._source_col is not None:
            current = self.source_filter.currentText()
            distinct = sorted({
                str(row[self._source_col])
                for row in self._all_rows
                if row[self._source_col] is not None
            })
            self.source_filter.blockSignals(True)
            self.source_filter.clear()
            self.source_filter.addItem("All Sources")
            self.source_filter.addItems(distinct)
            # Restore previous selection if still present
            idx = self.source_filter.findText(current)
            self.source_filter.setCurrentIndex(idx if idx >= 0 else 0)
            self.source_filter.blockSignals(False)

        self._page = 0
        self._apply_filter()

    def _apply_filter(self):
        term = self.search_box.text().strip().lower()
        selected_source = (
            self.source_filter.currentText()
            if self.source_filter is not None and self.source_filter.currentIndex() > 0
            else None
        )

        rows = self._all_rows

        # Source filter (exact match on the source column)
        if selected_source and self._source_col is not None:
            rows = [r for r in rows if str(r[self._source_col]) == selected_source]

        # Text search across all columns
        if term:
            rows = [r for r in rows if any(term in str(cell).lower() for cell in r)]

        self._filtered_rows = rows
        self._page = 0
        self._render_page()

    def _format_cell(self, col_idx: int, cell: object) -> str:
        if cell is None:
            return ""
        column_name = self.columns[col_idx]
        if column_name in ("date_added", "last_attempted"):
            return yyyymmdd_to_iso_date(cell) or str(cell)
        return str(cell)

    def _render_page(self):
        total = len(self._filtered_rows)
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        start = self._page * PAGE_SIZE
        end = min(start + PAGE_SIZE, total)
        page_rows = self._filtered_rows[start:end]

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(page_rows))
        for r_idx, row in enumerate(page_rows):
            for c_idx, cell in enumerate(row):
                formatted = self._format_cell(c_idx, cell)
                item = QTableWidgetItem(formatted)
                item.setToolTip(formatted)
                self.table.setItem(r_idx, c_idx, item)
        self.table.setSortingEnabled(True)

        filtered_note = (
            f"filtered from {len(self._all_rows):,} total"
            if len(self._filtered_rows) != len(self._all_rows) else "total"
        )
        self.lbl_info.setText(
            f"{total:,} row{'s' if total != 1 else ''} ({filtered_note})"
            f"  —  showing {start + 1}–{end}"
        )
        self.lbl_page.setText(f"Page {self._page + 1} / {total_pages}")
        self.btn_prev.setEnabled(self._page > 0)
        self.btn_next.setEnabled(self._page < total_pages - 1)

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._render_page()

    def _next_page(self):
        total_pages = max(1, (len(self._filtered_rows) + PAGE_SIZE - 1) // PAGE_SIZE)
        if self._page < total_pages - 1:
            self._page += 1
            self._render_page()


class DatabaseBrowserDialog(QDialog):
    """Full database browser — one tab per database table."""

    def __init__(self, parent=None, db: DatabaseManager | None = None):
        super().__init__(parent)
        self.setWindowTitle("Database Browser")
        self.setMinimumSize(920, 640)
        self.resize(1100, 720)
        self._db = db or DatabaseManager()
        self._db.init_db()
        self._db_path = str(self._db.db_path)
        self._tabs: dict[str, _TableTab] = {}
        self._setup_ui()
        self._load_tab(0)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(12)

        # Header row
        hdr = QHBoxLayout()
        title = QLabel("Database Browser")
        title.setObjectName("DialogHeader")
        hdr.addWidget(title)
        hdr.addStretch()
        path_lbl = QLabel(self._db_path)
        path_lbl.setProperty("class", "HelperText")
        path_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        path_lbl.setToolTip(self._db_path)
        hdr.addWidget(path_lbl)
        root.addLayout(hdr)

        # Tabs
        self.tab_widget = QTabWidget()
        self.tab_widget.currentChanged.connect(self._load_tab)

        for tbl in TABLE_COLUMNS:
            tab = _TableTab(tbl, self._db_path, parent=self)
            self._tabs[tbl] = tab
            self.tab_widget.addTab(tab, tbl)

        root.addWidget(self.tab_widget, stretch=1)

        # Close button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setProperty("class", "SecondaryButton")
        close_btn.setMinimumHeight(38)
        close_btn.setMinimumWidth(100)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    def _load_tab(self, index: int):
        """Lazy-load table data when a tab is first shown."""
        tbl_names = list(TABLE_COLUMNS.keys())
        if index < len(tbl_names):
            tbl_name = tbl_names[index]
            tab = self._tabs.get(tbl_name)
            if tab and not tab._all_rows and not tab.search_box.text():
                tab.load_data()
