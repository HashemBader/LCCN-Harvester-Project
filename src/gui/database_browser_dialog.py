"""
Module: database_browser_dialog.py
Full database browser — shows all rows across main, attempted, linked_isbns,
and subjects tables with live search, pagination, and MARC file import.
"""
import sqlite3
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QWidget, QSizePolicy, QFileDialog, QTextEdit,
    QFormLayout, QFrame, QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt, QTimer

from database import DatabaseManager

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
                item = QTableWidgetItem("" if cell is None else str(cell))
                item.setToolTip("" if cell is None else str(cell))
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


class _MarcImportTab(QWidget):
    """Tab for importing MARC JSON or MARCXML files into the database."""

    def __init__(self, db_path: str, on_import_done=None, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self._on_import_done = on_import_done
        self._selected_file: str = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        # Description
        desc = QLabel(
            "Import MARC records from a JSON or MARCXML file directly into the database. "
            "Records with a call number go into <b>main</b>; records without go into <b>attempted</b>."
        )
        desc.setProperty("class", "HelperText")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)

        # Form
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # File picker
        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        self.lbl_file = QLabel("No file selected")
        self.lbl_file.setProperty("class", "HelperText")
        self.lbl_file.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.lbl_file.setWordWrap(False)

        btn_browse = QPushButton("Browse…")
        btn_browse.setProperty("class", "SecondaryButton")
        btn_browse.setMinimumHeight(36)
        btn_browse.setMinimumWidth(100)
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse.clicked.connect(self._pick_file)
        file_row.addWidget(self.lbl_file, stretch=1)
        file_row.addWidget(btn_browse)
        form.addRow("MARC File:", file_row)

        # Source name
        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("e.g. WorldCat, Manual MARC Import…")
        self.source_input.setMinimumHeight(36)
        form.addRow("Source Name:", self.source_input)

        layout.addLayout(form)

        # Import button
        self.btn_import = QPushButton("Import MARC File")
        self.btn_import.setProperty("class", "PrimaryButton")
        self.btn_import.setMinimumHeight(42)
        self.btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import.setEnabled(False)
        self.btn_import.clicked.connect(self._run_import)
        layout.addWidget(self.btn_import)

        # Results log
        lbl_log = QLabel("IMPORT LOG")
        lbl_log.setProperty("class", "CardTitle")
        layout.addWidget(lbl_log)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Import results appear here…")
        self.log.setProperty("class", "TerminalViewport")
        self.log.setMinimumHeight(160)
        layout.addWidget(self.log, stretch=1)

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select MARC File",
            "",
            "MARC Files (*.json *.xml *.mrc);;JSON Files (*.json);;XML Files (*.xml);;All Files (*)"
        )
        if path:
            self._selected_file = path
            self.lbl_file.setText(Path(path).name)
            self.lbl_file.setToolTip(path)
            self.btn_import.setEnabled(True)

    def _run_import(self):
        if not self._selected_file:
            return

        import sys
        import xml.etree.ElementTree as ET

        file_path = Path(self._selected_file)
        source = self.source_input.text().strip() or file_path.stem
        self.log.clear()
        self.log.append(f"Importing: {file_path.name}")
        self.log.append(f"Source:    {source}")
        self.log.append("")

        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from harvester.marc_import import MarcImportService
            import json

            service = MarcImportService(db_path=self.db_path)
            suffix = file_path.suffix.lower()

            if suffix == ".json":
                raw = json.loads(file_path.read_text(encoding="utf-8"))
                records_list = raw if isinstance(raw, list) else raw.get("records", [raw])
                summary = service.import_json_records(records_list, source_name=source, save_source_to_active_profile=False)
            elif suffix in (".xml", ".mrc"):
                tree = ET.parse(str(file_path))
                root = tree.getroot()
                # Support both bare <record> lists and wrapped collections
                ns = {}
                tag = root.tag
                if tag.endswith("collection") or tag.endswith("Collection"):
                    records_elements = list(root)
                elif tag.endswith("record") or tag.endswith("Record"):
                    records_elements = [root]
                else:
                    # Try to find record children regardless of namespace
                    records_elements = [
                        child for child in root
                        if child.tag.endswith("record") or child.tag.endswith("Record")
                    ] or list(root)
                summary = service.import_xml_records(records_elements, source_name=source, save_source_to_active_profile=False)
            else:
                self.log.append("Unsupported file type. Use .json or .xml")
                return

            self.log.append(f"Written to main table:      {summary.main_rows}")
            self.log.append(f"Written to attempted table: {summary.attempted_rows}")
            self.log.append(f"Skipped (no ISBN):          {summary.skipped_records}")
            self.log.append("")
            self.log.append("Import complete. Click Refresh on other tabs to see new rows.")

            if self._on_import_done:
                self._on_import_done()

        except Exception as exc:
            self.log.append(f"Error: {exc}")


class DatabaseBrowserDialog(QDialog):
    """Full database browser — one tab per table, plus MARC import."""

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

        marc_tab = _MarcImportTab(
            db_path=self._db_path,
            on_import_done=self._refresh_all_table_tabs,
            parent=self,
        )
        self.tab_widget.addTab(marc_tab, "MARC Import")
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

    def _refresh_all_table_tabs(self):
        """Reload all table tabs (called after MARC import)."""
        for tab in self._tabs.values():
            tab.load_data()
