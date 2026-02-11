"""
Module: results_tab.py
Results viewing and database query tab.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QTableWidget, QTableWidgetItem,
    QLineEdit, QComboBox, QMessageBox, QSizePolicy, QFrame
)
from PyQt6.QtCore import Qt
from datetime import datetime, timezone
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import DatabaseManager
from harvester.export_manager import ExportManager


class ResultsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.db = None
        self._setup_ui()
        self._init_database()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(12)

        # Title
        title_label = QLabel("Database")
        title_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #c2d07f;")
        layout.addWidget(title_label)

        subtitle_label = QLabel("Review, search, and export harvested records")
        subtitle_label.setStyleSheet("color: #a7a59b; font-size: 12px;")
        layout.addWidget(subtitle_label)

        divider = QFrame()
        divider.setObjectName("SectionDivider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        # Search/Filter controls
        search_group = QGroupBox("Search & Filter")
        search_layout = QHBoxLayout()
        search_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by ISBN (press Enter)")
        self.search_input.returnPressed.connect(self._search_results)
        self.search_input.textChanged.connect(self._on_search_text_changed)

        self.table_selector = QComboBox()
        self.table_selector.addItems(["Successful Records", "Failed Attempts"])
        self.table_selector.currentIndexChanged.connect(self._on_table_changed)

        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self._search_results)
        self.search_button.setObjectName("PrimaryButton")

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._load_all_results)
        self.refresh_button.setToolTip("Reload data from database")

        self.clear_button = QPushButton("Clear Database")
        self.clear_button.clicked.connect(self._clear_results)
        self.clear_button.setToolTip("Delete all results from database")
        self.clear_button.setObjectName("DangerButton")

        search_layout.addWidget(QLabel("Table:"))
        search_layout.addWidget(self.table_selector)
        search_layout.addWidget(QLabel("ISBN:"))
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_button)
        search_layout.addWidget(self.refresh_button)
        search_layout.addWidget(self.clear_button)

        search_group.setLayout(search_layout)
        layout.addWidget(search_group)

        # Results table
        results_group = QGroupBox("Records")
        results_layout = QVBoxLayout()

        self.results_table = QTableWidget()
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.results_table.verticalHeader().setVisible(False)
        results_layout.addWidget(self.results_table)

        # Stats
        self.stats_label = QLabel("No data loaded")
        self.stats_label.setStyleSheet("color: #a7a59b; font-size: 11px;")
        results_layout.addWidget(self.stats_label)

        results_group.setLayout(results_layout)
        results_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(results_group, 1)

        # Export button
        export_layout = QHBoxLayout()
        self.export_button = QPushButton("Export Results...")
        self.export_button.clicked.connect(self._export_results)
        self.export_button.setToolTip("Open export dialog with advanced options")
        self.export_button.setObjectName("PrimaryButton")

        self.quick_export_button = QPushButton("Quick Export TSV")
        self.quick_export_button.clicked.connect(self._quick_export)
        self.quick_export_button.setVisible(False)
        self.quick_export_button.setObjectName("SecondaryButton")

        export_layout.addWidget(self.export_button)
        export_layout.addWidget(self.quick_export_button)
        export_layout.addStretch()
        layout.addLayout(export_layout)

        self.setLayout(layout)
        self.advanced_mode = False

    def _selected_table_name(self) -> str:
        return "main" if self.table_selector.currentIndex() == 0 else "attempted"

    def _init_database(self):
        """Initialize database connection."""
        try:
            self.db = DatabaseManager()
            self.db.init_db()
            self._load_all_results()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Database Error",
                f"Failed to initialize database: {str(e)}"
            )

    def _on_table_changed(self, index):
        """Handle table selector change - auto-load results."""
        self._load_all_results()

    def _on_search_text_changed(self, text):
        """Handle search text change - auto-load all when cleared."""
        if not text.strip():
            self._load_all_results()

    def _clear_results(self):
        """Clear all results from the database."""
        if not self.db:
            return

        reply = QMessageBox.question(
            self,
            "Clear All Results",
            "This will permanently delete ALL harvest results from the database:\n\n"
            "• All successful harvests (Successful Records)\n"
            "• All failed attempts (Failed Attempts)\n\n"
            "This action CANNOT be undone!\n\n"
            "Are you sure you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                with self.db.connect() as conn:
                    conn.execute("DELETE FROM main")
                    conn.execute("DELETE FROM attempted")
                    conn.commit()

                self.results_table.clear()
                self.results_table.setRowCount(0)
                self.stats_label.setText("All results cleared from database")

                QMessageBox.information(
                    self,
                    "Success",
                    "All results have been cleared from the database."
                )

                self._load_all_results()

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Database Error",
                    f"Failed to clear results: {str(e)}"
                )

    def _load_all_results(self):
        """Load all results from selected table."""
        if not self.db:
            return

        try:
            self.stats_label.setText("Loading...")

            table_name = self._selected_table_name()

            with self.db.connect() as conn:
                if table_name == "main":
                    cursor = conn.execute(
                        "SELECT isbn, lccn, nlmcn, classification, source, date_added "
                        "FROM main ORDER BY date_added DESC LIMIT 1000"
                    )
                    headers = ["ISBN", "LCCN", "NLMCN", "Classification", "Source", "Date Added", "Age (days)"]
                else:
                    cursor = conn.execute(
                        "SELECT isbn, last_target, last_attempted, fail_count, last_error "
                        "FROM attempted ORDER BY last_attempted DESC LIMIT 1000"
                    )
                    headers = ["ISBN", "Last Target", "Last Attempted", "Fail Count", "Last Error", "Age (days)"]

                rows = cursor.fetchall()

                # If there are no successful rows but failed attempts exist, switch automatically
                # so users immediately see what happened.
                if table_name == "main" and len(rows) == 0:
                    attempted_count = conn.execute("SELECT COUNT(*) FROM attempted").fetchone()[0]
                    if attempted_count > 0:
                        self.table_selector.blockSignals(True)
                        self.table_selector.setCurrentIndex(1)
                        self.table_selector.blockSignals(False)
                        self.stats_label.setText(
                            "No successful records yet. Showing Failed Attempts instead."
                        )
                        table_name = "attempted"
                        cursor = conn.execute(
                            "SELECT isbn, last_target, last_attempted, fail_count, last_error "
                            "FROM attempted ORDER BY last_attempted DESC LIMIT 1000"
                        )
                        headers = ["ISBN", "Last Target", "Last Attempted", "Fail Count", "Last Error", "Age (days)"]
                        rows = cursor.fetchall()

            rows = self._augment_rows(rows, table_name)

            self._populate_table(rows, headers)

            table_display = "Successful Records" if table_name == "main" else "Failed Attempts"
            if len(rows) == 0:
                self.stats_label.setText(f"No records found in {table_display}")
            elif len(rows) == 1000:
                self.stats_label.setText(f"Showing {len(rows)} most recent records from {table_display} (limit reached)")
            else:
                self.stats_label.setText(f"Showing {len(rows)} records from {table_display}")

        except Exception as e:
            QMessageBox.critical(
                self,
                "Database Error",
                f"Failed to load results: {str(e)}"
            )
            self.stats_label.setText("Error loading data")

    def _search_results(self):
        """Search for specific ISBN."""
        isbn = self.search_input.text().strip()
        if not isbn:
            self._load_all_results()
            return

        if not self.db:
            return

        try:
            self.stats_label.setText(f"Searching for '{isbn}'...")

            table_name = self._selected_table_name()

            with self.db.connect() as conn:
                if table_name == "main":
                    cursor = conn.execute(
                        "SELECT isbn, lccn, nlmcn, classification, source, date_added "
                        "FROM main WHERE isbn LIKE ?",
                        (f"%{isbn}%",)
                    )
                    headers = ["ISBN", "LCCN", "NLMCN", "Classification", "Source", "Date Added", "Age (days)"]
                else:
                    cursor = conn.execute(
                        "SELECT isbn, last_target, last_attempted, fail_count, last_error "
                        "FROM attempted WHERE isbn LIKE ?",
                        (f"%{isbn}%",)
                    )
                    headers = ["ISBN", "Last Target", "Last Attempted", "Fail Count", "Last Error", "Age (days)"]

                rows = cursor.fetchall()

            rows = self._augment_rows(rows, table_name)

            self._populate_table(rows, headers)

            table_display = "Successful Records" if table_name == "main" else "Failed Attempts"
            if len(rows) == 0:
                self.stats_label.setText(f"No matches found for '{isbn}' in {table_display}")
            else:
                self.stats_label.setText(f"Found {len(rows)} matching record(s) for '{isbn}' in {table_display}")

        except Exception as e:
            QMessageBox.critical(
                self,
                "Database Error",
                f"Search failed: {str(e)}"
            )
            self.stats_label.setText("Search error")

    def _populate_table(self, rows, headers):
        """Populate table with data."""
        from PyQt6.QtWidgets import QHeaderView

        self.results_table.clear()
        self.results_table.setColumnCount(len(headers))
        self.results_table.setHorizontalHeaderLabels(headers)
        self.results_table.setRowCount(len(rows))

        for row_idx, row_data in enumerate(rows):
            for col_idx, value in enumerate(row_data):
                item = QTableWidgetItem(str(value) if value is not None else "")
                item.setForeground(Qt.GlobalColor.white)
                self.results_table.setItem(row_idx, col_idx, item)

        # Smart column sizing (stretch last column for the new info column)
        header = self.results_table.horizontalHeader()
        header.setStretchLastSection(True)
        if headers:
            for i in range(len(headers) - 1):
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(len(headers) - 1, QHeaderView.ResizeMode.Stretch)

    def _augment_rows(self, rows, table_name):
        """Add a useful info column so the extra space is meaningful."""
        augmented = []
        now = datetime.now(timezone.utc)

        if table_name == "main":
            for row in rows:
                date_added = row[5] if len(row) > 5 else None
                age_days = ""
                if date_added:
                    try:
                        dt = datetime.fromisoformat(date_added)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        age_days = str((now - dt).days)
                    except Exception:
                        age_days = ""
                augmented.append(list(row) + [age_days])
        else:
            for row in rows:
                last_attempted = row[2] if len(row) > 2 else None
                age_days = ""
                if last_attempted:
                    try:
                        dt = datetime.fromisoformat(last_attempted)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        age_days = str((now - dt).days)
                    except Exception:
                        age_days = ""
                augmented.append(list(row) + [age_days])

        return augmented

    def set_advanced_mode(self, enabled):
        """Enable/disable advanced mode features."""
        self.advanced_mode = enabled
        self.quick_export_button.setVisible(enabled)

    def _export_results(self):
        """Open export dialog."""
        from .export_dialog import ExportDialog

        dialog = ExportDialog(self)
        if dialog.exec() == ExportDialog.DialogCode.Accepted:
            # ExportDialog already performs the export and shows result messaging.
            # Just refresh the table in case user exported freshly harvested data.
            self._load_all_results()

    def _quick_export(self):
        """Quick export to TSV with default settings."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_dir = Path("data/exports")
            export_dir.mkdir(parents=True, exist_ok=True)
            output_file = export_dir / f"quick_export_{timestamp}.tsv"

            export_config = {
                "source": "main",
                "format": "tsv",
                "columns": ["isbn", "lccn", "nlmcn", "classification", "source", "date_added"],
                "output_path": str(output_file),
                "include_header": True,
            }

            export_manager = ExportManager()
            result = export_manager.export(export_config)

            if result.get("success"):
                files = result.get("files", [])
                QMessageBox.information(
                    self,
                    "Quick Export Successful",
                    f"Data exported to:\n{files[0] if files else output_file}",
                )
            else:
                QMessageBox.critical(
                    self,
                    "Export Failed",
                    f"Quick export failed: {result.get('message', 'Unknown error')}",
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Error",
                f"An error occurred during quick export:\n{str(e)}",
            )

    def refresh(self):
        """Refresh the results display."""
        self._load_all_results()

    def showEvent(self, event):
        """Auto-refresh when tab is shown."""
        super().showEvent(event)
        if self.results_table.rowCount() == 0:
            self._load_all_results()
