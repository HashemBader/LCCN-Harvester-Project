"""Full read-only database browser dialog with live search and pagination.

``DatabaseBrowserDialog`` opens a ``QTabWidget`` with one tab per SQLite table
(``main``, ``attempted``, ``linked_isbns``).  Each tab is backed by a
``_TableTab`` widget that:

* Loads all rows for its table from the database in one query.
* Supports full-text search across all columns with a 250 ms debounce timer.
* Supports an optional source/target column filter dropdown.
* Pages results in blocks of ``PAGE_SIZE`` rows for performance.

Tabs are loaded lazily — data is only fetched from the database when the tab
is first shown, so opening the dialog does not block on large datasets.

Module-level constants:
    ``TABLE_COLUMNS`` — ordered column lists for each table.
    ``SOURCE_COL_INDEX`` — index of the filterable source column per table,
        or ``None`` for tables without one.
    ``PAGE_SIZE`` — number of rows displayed per page.
"""
import sqlite3

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QWidget, QSizePolicy, QComboBox
)
from PyQt6.QtCore import Qt, QTimer

from database import DatabaseManager
from src.database.db_manager import yyyymmdd_to_iso_date

# --- Table column definitions ---
# Each entry maps a table name to the ordered list of columns that are both
# queried from SQLite and displayed as ``QTableWidget`` columns (left to right).
# Changing column order here changes both the SQL SELECT order and the display.
TABLE_COLUMNS = {
    # Col 0: isbn           Col 1: call_number  Col 2: call_number_type
    # Col 3: classification  Col 4: source       Col 5: date_added (YYYYMMDD → ISO)
    "main":         ["isbn", "call_number", "call_number_type", "classification", "source", "date_added"],
    # Col 0: isbn  Col 1: last_target  Col 2: attempt_type  Col 3: last_attempted
    # Col 4: fail_count  Col 5: last_error
    "attempted":    ["isbn", "last_target", "attempt_type", "last_attempted", "fail_count", "last_error"],
    # Col 0: lowest_isbn  Col 1: other_isbn
    "linked_isbns": ["lowest_isbn", "other_isbn"],
}

# Maps each table to the zero-based index of the column used for the source
# filter dropdown.  None means the table has no filterable source column.
SOURCE_COL_INDEX = {
    "main":         4,   # source — the API/Z39.50 target that returned the record
    "attempted":    1,   # last_target — the target that was tried last
    "linked_isbns": None,
}

PAGE_SIZE = 200


class _TableTab(QWidget):
    """One tab inside ``DatabaseBrowserDialog`` representing a single DB table.

    Holds all rows in memory (``_all_rows``) after the first load and applies
    search/source filters client-side via ``_apply_filter`` to avoid repeated
    DB round-trips during typing.

    Attributes:
        table_name: Name of the SQLite table this tab displays.
        db_path: Absolute path to the SQLite database file.
        columns: Ordered list of column names to query and display.
    """

    def __init__(self, table_name: str, db_path: str, parent=None):
        """Initialise the tab but do not load data yet (lazy loading).

        Args:
            table_name: One of the keys in ``TABLE_COLUMNS``.
            db_path: Path to the SQLite database file.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.table_name = table_name
        self.db_path = db_path
        self.columns = TABLE_COLUMNS[table_name]
        # Index of the source/target column used for the dropdown filter, or None.
        self._source_col: int | None = SOURCE_COL_INDEX.get(table_name)
        self._all_rows: list[tuple] = []      # all rows loaded from the DB
        self._filtered_rows: list[tuple] = [] # subset after search + source filter
        self._page = 0
        # Debounce timer so _apply_filter is not called on every individual keystroke.
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)   # 250 ms debounce
        self._search_timer.timeout.connect(self._apply_filter)
        self._setup_ui()

    def _setup_ui(self):
        """Build the tab layout: search bar, optional source filter, table, pagination controls.

        The source-filter dropdown is only added for tables whose column is
        listed in ``SOURCE_COL_INDEX`` (currently ``main`` and ``attempted``).
        The ``QTableWidget`` has sorting enabled after each page render but
        is disabled during row population to avoid O(n log n) per-cell re-sorts.
        """
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
        """Fetch all rows for this table from the SQLite database.

        Results are stored in ``_all_rows`` as plain tuples for memory
        efficiency.  After loading, the source filter dropdown is repopulated
        with the distinct values found in the source column, and the filter is
        re-applied to refresh the displayed page.

        Any SQLite error is displayed in the row-info label rather than raising
        so the dialog remains usable even when the database is locked or corrupt.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cols = ", ".join(self.columns)
            rows = conn.execute(f"SELECT {cols} FROM {self.table_name}").fetchall()
            conn.close()
            # Convert sqlite3.Row objects to plain tuples for lightweight storage.
            self._all_rows = [tuple(r) for r in rows]
        except Exception as e:
            self._all_rows = []
            self.lbl_info.setText(f"Error: {e}")

        # Repopulate source/target filter dropdown after each load.
        if self.source_filter is not None and self._source_col is not None:
            current = self.source_filter.currentText()
            distinct = sorted({
                str(row[self._source_col])
                for row in self._all_rows
                if row[self._source_col] is not None
            })
            # Block signals while repopulating to avoid triggering _apply_filter
            # multiple times during the clear+addItems sequence.
            self.source_filter.blockSignals(True)
            self.source_filter.clear()
            self.source_filter.addItem("All Sources")
            self.source_filter.addItems(distinct)
            # Restore the user's previous selection if it still exists.
            idx = self.source_filter.findText(current)
            self.source_filter.setCurrentIndex(idx if idx >= 0 else 0)
            self.source_filter.blockSignals(False)

        self._page = 0
        self._apply_filter()

    def _apply_filter(self):
        """Apply the current search term and source filter to ``_all_rows``.

        Filtering is performed in-memory so no additional DB queries are needed.
        The results are stored in ``_filtered_rows`` and the display is reset to
        page 0.
        """
        term = self.search_box.text().strip().lower()
        # index > 0 means a specific source was chosen; index == 0 is "All Sources".
        selected_source = (
            self.source_filter.currentText()
            if self.source_filter is not None and self.source_filter.currentIndex() > 0
            else None
        )

        rows = self._all_rows

        # Exact-match filter on the designated source/target column.
        if selected_source and self._source_col is not None:
            rows = [r for r in rows if str(r[self._source_col]) == selected_source]

        # Substring search across every column value.
        if term:
            rows = [r for r in rows if any(term in str(cell).lower() for cell in r)]

        self._filtered_rows = rows
        self._page = 0
        self._render_page()

    def _format_cell(self, col_idx: int, cell: object) -> str:
        """Format a raw cell value for display in the table.

        Date columns stored as ``YYYYMMDD`` integers are converted to ISO-8601
        strings (``YYYY-MM-DD``) via ``yyyymmdd_to_iso_date``; all other values
        are converted with ``str()``.

        Args:
            col_idx: Zero-based index of the column in ``self.columns``.
            cell: Raw cell value from the database row tuple.

        Returns:
            A display string, or ``""`` for ``None`` values.
        """
        if cell is None:
            return ""
        column_name = self.columns[col_idx]
        # Convert compact integer dates to the more readable ISO format.
        if column_name in ("date_added", "last_attempted"):
            return yyyymmdd_to_iso_date(cell) or str(cell)
        return str(cell)

    def _render_page(self):
        """Populate the QTableWidget with the current page of filtered rows.

        Sorting is temporarily disabled during population to prevent the table
        from re-sorting after every individual ``setItem`` call, which would be
        both incorrect and slow.
        """
        total = len(self._filtered_rows)
        # Ceiling division to compute total page count.
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        start = self._page * PAGE_SIZE
        end = min(start + PAGE_SIZE, total)
        page_rows = self._filtered_rows[start:end]

        # Disable sorting while populating to avoid O(n log n) re-sort per cell.
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(page_rows))
        for r_idx, row in enumerate(page_rows):
            for c_idx, cell in enumerate(row):
                formatted = self._format_cell(c_idx, cell)
                item = QTableWidgetItem(formatted)
                item.setToolTip(formatted)  # tooltip shows full value for truncated cells
                self.table.setItem(r_idx, c_idx, item)
        # Re-enable sorting so the user can click column headers to sort.
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
        """Move to the previous page of filtered results if one exists."""
        if self._page > 0:
            self._page -= 1
            self._render_page()

    def _next_page(self):
        """Move to the next page of filtered results if one exists."""
        total_pages = max(1, (len(self._filtered_rows) + PAGE_SIZE - 1) // PAGE_SIZE)
        if self._page < total_pages - 1:
            self._page += 1
            self._render_page()


class DatabaseBrowserDialog(QDialog):
    """Top-level database browser dialog — one ``_TableTab`` per database table.

    Accepts an optional ``DatabaseManager`` instance so callers can pass the
    same live DB connection used by the harvest engine.  If none is provided a
    new one is created and initialised.
    """

    def __init__(self, parent=None, db: DatabaseManager | None = None):
        """Initialise the dialog, build the tab widget, and load the first tab.

        Args:
            parent: Optional parent widget for modal positioning.
            db: An initialised ``DatabaseManager`` instance; a new one is
                created if not supplied.
        """
        super().__init__(parent)
        self.setWindowTitle("Database Browser")
        self.setMinimumSize(920, 640)
        self.resize(1100, 720)
        self._db = db or DatabaseManager()
        self._db.init_db()                      # ensure schema exists before querying
        self._db_path = str(self._db.db_path)
        self._tabs: dict[str, _TableTab] = {}   # table_name → _TableTab widget
        self._setup_ui()
        self._load_tab(0)                        # eager-load the first visible tab

    def _setup_ui(self):
        """Build the dialog layout: header row, tabbed table area, close button.

        One ``_TableTab`` is created per key in ``TABLE_COLUMNS`` and added to
        ``self.tab_widget``.  The ``currentChanged`` signal connects to
        ``_load_tab`` so data is fetched lazily when a tab is first activated.
        """
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
        """Lazy-load table data the first time a tab becomes visible.

        Only triggers a DB fetch if the tab has no rows yet and the search box
        is empty, so a tab that was already loaded (or has an active search)
        is not needlessly re-fetched.

        Args:
            index: Zero-based index of the newly active tab in ``QTabWidget``.
        """
        tbl_names = list(TABLE_COLUMNS.keys())
        if index < len(tbl_names):
            tbl_name = tbl_names[index]
            tab = self._tabs.get(tbl_name)
            # Only load if the tab is empty and has no pending search query.
            if tab and not tab._all_rows and not tab.search_box.text():
                tab.load_data()
