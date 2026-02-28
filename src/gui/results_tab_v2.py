"""
Module: results_tab_v2.py
V2 Results Explorer with modern borderless design, filtering, and export.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QTableWidget, QTableWidgetItem,
    QLineEdit, QComboBox, QMessageBox, QFileDialog, QHeaderView
)
from PyQt6.QtCore import Qt
from datetime import datetime
from pathlib import Path
import csv
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import DatabaseManager
from .styles_v2 import CATPPUCCIN_THEME

class ResultsTabV2(QWidget):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager() # Initialize immediately
        self.db.init_db()
        self._setup_ui()
        self._load_all_results()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20) # Spacious V2 layout
        layout.setContentsMargins(20, 20, 20, 20)

        # =========================================================================
        # 1. Header (Consistent "PageTitle" style)
        # =========================================================================
        header_layout = QHBoxLayout()
        
        title_block = QVBoxLayout()
        title = QLabel("Results Explorer")
        title.setProperty("class", "PageTitle")

        subtitle = QLabel("Search, filter, and export your harvested data")
        subtitle.setProperty("class", "CardHelper")

        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        
        header_layout.addLayout(title_block)
        header_layout.addStretch()

        # Global Actions
        self.btn_clear = QPushButton("Clear All Results")
        self.btn_clear.setProperty("class", "DangerButton")
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.clicked.connect(self._clear_results)
        header_layout.addWidget(self.btn_clear)

        layout.addLayout(header_layout)

        # =========================================================================
        # 2. Controls Bar (Card)
        # =========================================================================
        controls_frame = QFrame()
        controls_frame.setProperty("class", "Card")
        controls_layout = QHBoxLayout(controls_frame)
        controls_layout.setSpacing(15)
        controls_layout.setContentsMargins(15, 15, 15, 15)

        # --- Filter Group ---
        filter_layout = QHBoxLayout()
        self.table_selector = QComboBox()
        self.table_selector.addItems(["Main Results (Successful)", "Failed Attempts"])
        self.table_selector.currentIndexChanged.connect(self._on_table_changed)
        self.table_selector.setMinimumWidth(220)
        self.table_selector.setProperty("class", "ComboBox") # Ensure style applies
        filter_layout.addWidget(QLabel("View:"))
        filter_layout.addWidget(self.table_selector)
        
        # --- Search Group ---
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search ISBN, Title, Author...")
        self.search_input.returnPressed.connect(self._search_results)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        
        self.btn_search = QPushButton("Search")
        self.btn_search.setProperty("class", "PrimaryButton")
        self.btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_search.clicked.connect(self._search_results)
        
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.btn_search)

        # --- Export Group ---
        export_layout = QHBoxLayout()
        self.btn_export_tsv = QPushButton("Export TSV")
        self.btn_export_tsv.setProperty("class", "SecondaryButton")
        self.btn_export_tsv.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_tsv.clicked.connect(lambda: self._export_results("tsv"))
        
        self.btn_export_csv = QPushButton("Export CSV")
        self.btn_export_csv.setProperty("class", "SecondaryButton")
        self.btn_export_csv.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_csv.clicked.connect(lambda: self._export_results("csv"))
        
        # Assemble Controls
        controls_layout.addLayout(filter_layout)
        controls_layout.addWidget(self._create_divider())
        controls_layout.addLayout(search_layout, stretch=1)
        controls_layout.addWidget(self._create_divider())
        controls_layout.addWidget(self.btn_export_tsv)
        controls_layout.addWidget(self.btn_export_csv)

        layout.addWidget(controls_frame)

        # =========================================================================
        # 3. Data Table (Card)
        # =========================================================================
        table_frame = QFrame()
        table_frame.setProperty("class", "Card")
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(0, 0, 0, 0) # Edge-to-edge table

        self.results_table = QTableWidget()
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setShowGrid(False) # Modern cleaner look
        self.results_table.setStyleSheet("border: none;") 
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.results_table.horizontalHeader().setStretchLastSection(True)
        
        table_layout.addWidget(self.results_table)

        # Footer (Status & Refresh)
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(15, 10, 15, 10)
        
        self.stats_label = QLabel("No data loaded")
        self.stats_label.setStyleSheet(f"color: {CATPPUCCIN_THEME['overlay1']};")
        
        self.btn_refresh = QPushButton("Refresh Table")
        self.btn_refresh.setFlat(True)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setStyleSheet(f"color: {CATPPUCCIN_THEME['sapphire']}; text-decoration: underline;")
        self.btn_refresh.clicked.connect(self._load_all_results)
        
        footer_layout.addWidget(self.stats_label)
        footer_layout.addStretch()
        footer_layout.addWidget(self.btn_refresh)
        
        table_layout.addLayout(footer_layout)
        
        layout.addWidget(table_frame)

    def _create_divider(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet(f"color: {CATPPUCCIN_THEME['surface1']};")
        return line

    # =========================================================================
    # Logic Methods
    # =========================================================================
    def refresh(self):
        """Public refresh method."""
        self._load_all_results()

    def _load_all_results(self):
        """Load data based on selector."""
        if not self.db: return
        
        try:
            is_failed = self.table_selector.currentIndex() == 1
            if is_failed:
                data = self.db.get_failed_attempts(limit=1000) # Cap at 1000 for UI perf
                headers = ["ISBN", "Last Target", "Last Attempt", "Fail Count", "Error", "Status"]
            else:
                data = self.db.get_all_results(limit=1000)
                headers = ["ISBN", "LCCN", "Title", "Author", "Pub. Year", "Publisher", "Source", "Created"]

            self._populate_table(data, headers)
            self.stats_label.setText(f"Showing {len(data)} records (Limit: 1000)")
            
        except Exception as e:
            QMessageBox.critical(self, "Database Error", str(e))

    def _populate_table(self, data, headers):
        """Fill table with raw dict data."""
        self.results_table.clear()
        self.results_table.setColumnCount(len(headers))
        self.results_table.setHorizontalHeaderLabels(headers)
        self.results_table.setRowCount(len(data))

        key_map = {
            "ISBN": "isbn",
            "LCCN": "lccn",
            "Title": "title",
            "Author": "author",
            "Pub. Year": "pub_year",
            "Publisher": "publisher",
            "Source": "source",
            "Created": "date_added",
            "Last Target": "last_target",
            "Last Attempt": "last_attempted",
            "Fail Count": "fail_count",
            "Error": "last_error",
            "Status": "status",
        }
        
        for row_idx, row_data in enumerate(data):
            for col_idx, header in enumerate(headers):
                key = key_map.get(header, "")
                
                val = row_data[key] if key in row_data.keys() else ""
                
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable) # Read-only
                
                # Check for "Status" column to colorize
                if key == "status":
                    lowered = str(val).lower()
                    if lowered == "failed":
                        item.setForeground(Qt.GlobalColor.red)
                    elif lowered in {"found", "success"}:
                        item.setForeground(Qt.GlobalColor.darkGreen)
                    elif lowered == "invalid":
                        item.setForeground(Qt.GlobalColor.darkYellow)
                
                self.results_table.setItem(row_idx, col_idx, item)

    def _on_table_changed(self, idx):
        self._load_all_results()

    def _clear_results(self):
        confirm = QMessageBox.question(
            self, "Confirm Clear", 
            "Are you sure you want to PERMANENTLY delete all results from the database?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.db.clear_all_results()
            self._load_all_results()
            QMessageBox.information(self, "Cleared", "Database has been wiped.")

    def _search_results(self):
        query = self.search_input.text().strip().lower()
        if not query:
            self._load_all_results()
            return
            
        # UI-side filtering for responsiveness (since we limit to 1000 anyway)
        # Or implement DB search if needed. For now, filter visible rows.
        
        match_count = 0
        for row in range(self.results_table.rowCount()):
            show = False
            for col in range(self.results_table.columnCount()):
                item = self.results_table.item(row, col)
                if item and query in item.text().lower():
                    show = True
                    break
            self.results_table.setRowHidden(row, not show)
            if show: match_count += 1
            
        self.stats_label.setText(f"Found {match_count} matches for '{query}'")

    def _on_search_text_changed(self, text):
        if not text:
            self._search_results() # Reset

    def _export_results(self, format_type):
        """Export results directly from DB (not limited by table cap)."""
        filename = f"lccn_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format_type}"
        path, _ = QFileDialog.getSaveFileName(self, "Export Results", filename, f"{format_type.upper()} Files (*.{format_type})")
        
        if not path: return

        try:
            is_failed = self.table_selector.currentIndex() == 1
            query_text = self.search_input.text().strip().lower()

            if is_failed:
                headers = ["ISBN", "Last Target", "Last Attempt", "Fail Count", "Error", "Status"]
                with self.db.connect() as conn:
                    if query_text:
                        like = f"%{query_text}%"
                        rows_raw = conn.execute(
                            """
                            SELECT isbn, last_target, last_attempted, fail_count, last_error, 'Failed' AS status
                            FROM attempted
                            WHERE lower(coalesce(isbn, '')) LIKE ?
                               OR lower(coalesce(last_target, '')) LIKE ?
                               OR lower(coalesce(last_error, '')) LIKE ?
                            ORDER BY last_attempted DESC
                            """,
                            (like, like, like),
                        ).fetchall()
                    else:
                        rows_raw = conn.execute(
                            """
                            SELECT isbn, last_target, last_attempted, fail_count, last_error, 'Failed' AS status
                            FROM attempted
                            ORDER BY last_attempted DESC
                            """
                        ).fetchall()
            else:
                headers = ["ISBN", "LCCN", "Title", "Author", "Pub. Year", "Publisher", "Source", "Created"]
                with self.db.connect() as conn:
                    if query_text:
                        like = f"%{query_text}%"
                        rows_raw = conn.execute(
                            """
                            SELECT isbn, lccn, title, author, pub_year, publisher, source, date_added
                            FROM main
                            WHERE lower(coalesce(isbn, '')) LIKE ?
                               OR lower(coalesce(title, '')) LIKE ?
                               OR lower(coalesce(author, '')) LIKE ?
                            ORDER BY date_added DESC
                            """,
                            (like, like, like),
                        ).fetchall()
                    else:
                        rows_raw = conn.execute(
                            """
                            SELECT isbn, lccn, title, author, pub_year, publisher, source, date_added
                            FROM main
                            ORDER BY date_added DESC
                            """
                        ).fetchall()

            rows = [list(row) for row in rows_raw]

            delimiter = '\t' if format_type == 'tsv' else ','
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=delimiter)
                writer.writerow(headers)
                writer.writerows(rows)
                
            QMessageBox.information(self, "Export Successful", f"Exported {len(rows)} records to {path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e)) 
