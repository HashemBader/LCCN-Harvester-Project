"""
Module: export_dialog.py
Advanced export options dialog.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QCheckBox, QComboBox,
    QLineEdit, QFileDialog, QListWidget, QListWidgetItem,
    QDialogButtonBox, QMessageBox, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import Qt
from pathlib import Path
from datetime import datetime


class ExportDialog(QDialog):
    """Advanced export configuration dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Results")
        self.setMinimumSize(600, 550)
        self.export_path = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()

        # Export source selection
        source_group = QGroupBox("Export Source")
        source_layout = QVBoxLayout()

        self.source_button_group = QButtonGroup()

        self.main_radio = QRadioButton("Main Results (successful harvests)")
        self.main_radio.setChecked(True)
        self.source_button_group.addButton(self.main_radio)
        source_layout.addWidget(self.main_radio)

        self.attempted_radio = QRadioButton("Failed Attempts")
        self.source_button_group.addButton(self.attempted_radio)
        source_layout.addWidget(self.attempted_radio)

        self.both_radio = QRadioButton("Both (separate files)")
        self.source_button_group.addButton(self.both_radio)
        source_layout.addWidget(self.both_radio)

        source_group.setLayout(source_layout)
        layout.addWidget(source_group)

        # Format selection
        format_group = QGroupBox("Export Format")
        format_layout = QHBoxLayout()

        format_layout.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems([
            "Tab-Separated Values (TSV)",
            "Comma-Separated Values (CSV)",
            "JSON",
            "Excel (XLSX)"
        ])
        self.format_combo.currentTextChanged.connect(self._on_format_changed)
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()

        format_group.setLayout(format_layout)
        layout.addWidget(format_group)

        # Column selection
        columns_group = QGroupBox("Columns to Export")
        columns_layout = QVBoxLayout()

        # Select all/none buttons
        select_buttons = QHBoxLayout()

        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self._select_all_columns)

        self.select_none_btn = QPushButton("Select None")
        self.select_none_btn.clicked.connect(self._select_no_columns)

        select_buttons.addWidget(self.select_all_btn)
        select_buttons.addWidget(self.select_none_btn)
        select_buttons.addStretch()

        columns_layout.addLayout(select_buttons)

        # Column list
        self.columns_list = QListWidget()
        self.columns_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)

        # Main table columns
        main_columns = [
            ("ISBN", True),
            ("LCCN", True),
            ("NLMCN", True),
            ("Classification", True),
            ("Source", True),
            ("Date Added", False)
        ]

        for col_name, checked in main_columns:
            item = QListWidgetItem(col_name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self.columns_list.addItem(item)

        columns_layout.addWidget(self.columns_list)
        columns_group.setLayout(columns_layout)
        layout.addWidget(columns_group)

        # Output options
        options_group = QGroupBox("Output Options")
        options_layout = QVBoxLayout()

        self.include_header_check = QCheckBox("Include column headers")
        self.include_header_check.setChecked(True)
        options_layout.addWidget(self.include_header_check)

        self.pretty_print_check = QCheckBox("Pretty print JSON (if JSON format)")
        self.pretty_print_check.setChecked(True)
        self.pretty_print_check.setEnabled(False)
        options_layout.addWidget(self.pretty_print_check)

        self.open_after_check = QCheckBox("Open file after export")
        self.open_after_check.setChecked(False)
        options_layout.addWidget(self.open_after_check)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # Output file selection
        file_group = QGroupBox("Output File")
        file_layout = QVBoxLayout()

        file_select_layout = QHBoxLayout()

        self.file_path_edit = QLineEdit()
        self.file_path_edit.setPlaceholderText("Select output file...")
        self.file_path_edit.setReadOnly(True)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._browse_output_file)

        file_select_layout.addWidget(self.file_path_edit)
        file_select_layout.addWidget(self.browse_btn)

        file_layout.addLayout(file_select_layout)

        # Auto-generate path button
        self.auto_path_btn = QPushButton("Auto-generate filename")
        self.auto_path_btn.clicked.connect(self._auto_generate_path)
        file_layout.addWidget(self.auto_path_btn)

        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_export)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)
        self.setLayout(layout)

        # Auto-generate initial path
        self._auto_generate_path()

    def _on_format_changed(self, format_text):
        """Handle format selection change."""
        is_json = "JSON" in format_text
        self.pretty_print_check.setEnabled(is_json)

        # Update file extension
        if self.export_path:
            path = Path(self.export_path)
            stem = path.stem

            if "TSV" in format_text:
                ext = ".tsv"
            elif "CSV" in format_text:
                ext = ".csv"
            elif "JSON" in format_text:
                ext = ".json"
            elif "XLSX" in format_text:
                ext = ".xlsx"
            else:
                ext = ".txt"

            self.export_path = str(path.parent / (stem + ext))
            self.file_path_edit.setText(self.export_path)

    def _select_all_columns(self):
        """Select all columns for export."""
        for i in range(self.columns_list.count()):
            item = self.columns_list.item(i)
            item.setCheckState(Qt.CheckState.Checked)

    def _select_no_columns(self):
        """Deselect all columns."""
        for i in range(self.columns_list.count()):
            item = self.columns_list.item(i)
            item.setCheckState(Qt.CheckState.Unchecked)

    def _browse_output_file(self):
        """Browse for output file location."""
        format_text = self.format_combo.currentText()

        if "TSV" in format_text:
            filter_str = "TSV Files (*.tsv);;All Files (*.*)"
            default_ext = ".tsv"
        elif "CSV" in format_text:
            filter_str = "CSV Files (*.csv);;All Files (*.*)"
            default_ext = ".csv"
        elif "JSON" in format_text:
            filter_str = "JSON Files (*.json);;All Files (*.*)"
            default_ext = ".json"
        elif "XLSX" in format_text:
            filter_str = "Excel Files (*.xlsx);;All Files (*.*)"
            default_ext = ".xlsx"
        else:
            filter_str = "All Files (*.*)"
            default_ext = ".txt"

        default_filename = f"lccn_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}{default_ext}"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Export File",
            default_filename,
            filter_str
        )

        if file_path:
            self.export_path = file_path
            self.file_path_edit.setText(file_path)

    def _auto_generate_path(self):
        """Auto-generate export file path."""
        format_text = self.format_combo.currentText()

        if "TSV" in format_text:
            ext = ".tsv"
        elif "CSV" in format_text:
            ext = ".csv"
        elif "JSON" in format_text:
            ext = ".json"
        elif "XLSX" in format_text:
            ext = ".xlsx"
        else:
            ext = ".txt"

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if self.both_radio.isChecked():
            filename = f"lccn_export_all_{timestamp}{ext}"
        elif self.attempted_radio.isChecked():
            filename = f"lccn_export_failed_{timestamp}{ext}"
        else:
            filename = f"lccn_export_results_{timestamp}{ext}"

        # Default to data/exports directory
        export_dir = Path("data/exports")
        export_dir.mkdir(parents=True, exist_ok=True)

        self.export_path = str(export_dir / filename)
        self.file_path_edit.setText(self.export_path)

    def _validate_export(self):
        """Validate export configuration."""
        if not self.export_path:
            QMessageBox.warning(
                self,
                "No Output File",
                "Please select an output file."
            )
            return False

        # Check if at least one column is selected
        has_selected = False
        for i in range(self.columns_list.count()):
            if self.columns_list.item(i).checkState() == Qt.CheckState.Checked:
                has_selected = True
                break

        if not has_selected:
            QMessageBox.warning(
                self,
                "No Columns Selected",
                "Please select at least one column to export."
            )
            return False

        return True

    def _on_export(self):
        """Handle export button click."""
        if not self._validate_export():
            return

        # TODO: Implement actual export logic
        # For now, show success message
        config = self.get_export_config()

        QMessageBox.information(
            self,
            "Export",
            f"Export configured:\n\n"
            f"Source: {config['source']}\n"
            f"Format: {config['format']}\n"
            f"Columns: {len(config['columns'])}\n"
            f"Output: {config['output_path']}\n\n"
            f"Note: Export functionality will be fully implemented in integration phase."
        )

        self.accept()

    def get_export_config(self):
        """Return export configuration."""
        # Get selected columns
        selected_columns = []
        for i in range(self.columns_list.count()):
            item = self.columns_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_columns.append(item.text())

        # Determine source
        if self.main_radio.isChecked():
            source = "main"
        elif self.attempted_radio.isChecked():
            source = "attempted"
        else:
            source = "both"

        # Determine format
        format_text = self.format_combo.currentText()
        if "TSV" in format_text:
            format_type = "tsv"
        elif "CSV" in format_text:
            format_type = "csv"
        elif "JSON" in format_text:
            format_type = "json"
        else:
            format_type = "xlsx"

        return {
            "source": source,
            "format": format_type,
            "columns": selected_columns,
            "output_path": self.export_path,
            "include_header": self.include_header_check.isChecked(),
            "pretty_print": self.pretty_print_check.isChecked(),
            "open_after": self.open_after_check.isChecked()
        }