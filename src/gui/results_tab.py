"""
Module: results_tab.py
Results viewing and database query tab.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QTableWidget, QTableWidgetItem,
    QLineEdit, QComboBox, QMessageBox
)
from PyQt6.QtCore import Qt
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import DatabaseManager


class ResultsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.db = None
        self._setup_ui()
        self._init_database()

    def _setup_ui(self):
        layout = QVBoxLayout()

        # Title
        title_label = QLabel("Results Viewer")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title_label)

        # Search/Filter controls
        search_group = QGroupBox("Search & Filter")
        search_layout = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search ISBN...")

        self.table_selector = QComboBox()
        self.table_selector.addItems(["Main Results", "Failed Attempts"])

        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self._search_results)

        self.refresh_button = QPushButton("Refresh All")
        self.refresh_button.clicked.connect(self._load_all_results)

        search_layout.addWidget(QLabel("Table:"))
        search_layout.addWidget(self.table_selector)
        search_layout.addWidget(QLabel("ISBN:"))
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_button)
        search_layout.addWidget(self.refresh_button)

        search_group.setLayout(search_layout)
        layout.addWidget(search_group)

        # Results table
        results_group = QGroupBox("Database Results")
        results_layout = QVBoxLayout()

        self.results_table = QTableWidget()
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        results_layout.addWidget(self.results_table)

        # Stats
        self.stats_label = QLabel("No data loaded")
        results_layout.addWidget(self.stats_label)

        results_group.setLayout(results_layout)
        layout.addWidget(results_group)

        # Export button
        export_layout = QHBoxLayout()
        self.export_button = QPushButton("Export Results...")
        self.export_button.clicked.connect(self._export_results)
        self.export_button.setToolTip("Open export dialog with advanced options")

        self.quick_export_button = QPushButton("Quick Export TSV")
        self.quick_export_button.clicked.connect(self._quick_export)
        self.quick_export_button.setVisible(False)  # Hidden until advanced mode

        export_layout.addWidget(self.export_button)
        export_layout.addWidget(self.quick_export_button)
        export_layout.addStretch()
        layout.addLayout(export_layout)

        self.setLayout(layout)
        self.advanced_mode = False

    def _init_database(self):
        """Initialize database connection."""
        try:
            self.db = DatabaseManager()
            self.db.init_db()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Database Error",
                f"Failed to initialize database: {str(e)}"
            )

    def _load_all_results(self):
        """Load all results from selected table."""
        if not self.db:
            return

        try:
            table_name = "main" if self.table_selector.currentText() == "Main Results" else "attempted"

            with self.db.connect() as conn:
                if table_name == "main":
                    cursor = conn.execute("SELECT isbn, lccn, nlmcn, classification, source, date_added FROM main ORDER BY date_added DESC LIMIT 1000")
                    headers = ["ISBN", "LCCN", "NLMCN", "Classification", "Source", "Date Added"]
                else:
                    cursor = conn.execute("SELECT isbn, last_target, last_attempted, fail_count, last_error FROM attempted ORDER BY last_attempted DESC LIMIT 1000")
                    headers = ["ISBN", "Last Target", "Last Attempted", "Fail Count", "Last Error"]

                rows = cursor.fetchall()

            self._populate_table(rows, headers)
            self.stats_label.setText(f"Showing {len(rows)} records from '{table_name}' table")

        except Exception as e:
            QMessageBox.critical(
                self,
                "Database Error",
                f"Failed to load results: {str(e)}"
            )

    def _search_results(self):
        """Search for specific ISBN."""
        isbn = self.search_input.text().strip()
        if not isbn or not self.db:
            return

        try:
            table_name = "main" if self.table_selector.currentText() == "Main Results" else "attempted"

            with self.db.connect() as conn:
                if table_name == "main":
                    cursor = conn.execute(
                        "SELECT isbn, lccn, nlmcn, classification, source, date_added FROM main WHERE isbn LIKE ?",
                        (f"%{isbn}%",)
                    )
                    headers = ["ISBN", "LCCN", "NLMCN", "Classification", "Source", "Date Added"]
                else:
                    cursor = conn.execute(
                        "SELECT isbn, last_target, last_attempted, fail_count, last_error FROM attempted WHERE isbn LIKE ?",
                        (f"%{isbn}%",)
                    )
                    headers = ["ISBN", "Last Target", "Last Attempted", "Fail Count", "Last Error"]

                rows = cursor.fetchall()

            self._populate_table(rows, headers)
            self.stats_label.setText(f"Found {len(rows)} matching records")

        except Exception as e:
            QMessageBox.critical(
                self,
                "Database Error",
                f"Search failed: {str(e)}"
            )

    def _populate_table(self, rows, headers):
        """Populate table with data."""
        self.results_table.clear()
        self.results_table.setColumnCount(len(headers))
        self.results_table.setHorizontalHeaderLabels(headers)
        self.results_table.setRowCount(len(rows))

        for row_idx, row_data in enumerate(rows):
            for col_idx, value in enumerate(row_data):
                item = QTableWidgetItem(str(value) if value is not None else "")
                self.results_table.setItem(row_idx, col_idx, item)

        self.results_table.resizeColumnsToContents()

    def set_advanced_mode(self, enabled):
        """Enable/disable advanced mode features."""
        self.advanced_mode = enabled
        self.quick_export_button.setVisible(enabled)

    def _export_results(self):
        """Open export dialog."""
        from .export_dialog import ExportDialog

        dialog = ExportDialog(self)
        if dialog.exec() == ExportDialog.DialogCode.Accepted:
            export_config = dialog.get_export_config()
            # TODO: Perform actual export with config
            QMessageBox.information(
                self,
                "Export Started",
                f"Exporting to {export_config['output_path']}...\n\n"
                "Note: Full export implementation coming in integration phase."
            )

    def _quick_export(self):
        """Quick export to TSV with default settings."""
        from datetime import datetime
        from pathlib import Path

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        export_dir = Path("data/exports")
        export_dir.mkdir(parents=True, exist_ok=True)
        output_file = export_dir / f"quick_export_{timestamp}.tsv"

        QMessageBox.information(
            self,
            "Quick Export",
            f"Would export to:\n{output_file}\n\n"
            "Full implementation coming soon."
        )

    def refresh(self):
        """Refresh the results display."""
        self._load_all_results()