"""
Module: export_dialog.py
Advanced export options dialog.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QCheckBox, QComboBox,
    QLineEdit, QFileDialog, QListWidget, QListWidgetItem,
    QDialogButtonBox, QMessageBox, QRadioButton, QButtonGroup, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime
from harvester.export_manager import ExportManager


class ExportDialog(QDialog):
    """Advanced export configuration dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Results")
        self.setMinimumSize(640, 560)
        self.resize(760, 680)
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.export_path = None
        self._setup_ui()

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QFrame()
        layout = QVBoxLayout(content)

        # Export source selection
        source_group = QGroupBox("Export Source")
        source_layout = QVBoxLayout()

        self.source_button_group = QButtonGroup()

        self.main_radio = QRadioButton("Main Results (successful harvests)")
        self.main_radio.setChecked(True)
        self.source_button_group.addButton(self.main_radio)
        self.main_radio.toggled.connect(lambda checked: checked and self._auto_generate_path())
        source_layout.addWidget(self.main_radio)

        self.attempted_radio = QRadioButton("Failed Attempts")
        self.source_button_group.addButton(self.attempted_radio)
        self.attempted_radio.toggled.connect(lambda checked: checked and self._auto_generate_path())
        source_layout.addWidget(self.attempted_radio)

        self.both_radio = QRadioButton("Both (separate files)")
        self.source_button_group.addButton(self.both_radio)
        self.both_radio.toggled.connect(lambda checked: checked and self._auto_generate_path())
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
            "JSON"
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
        self.columns_list.setMinimumHeight(180)

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
        scroll.setWidget(content)
        root_layout.addWidget(scroll)

        # Auto-generate initial path
        self._auto_generate_path()

    def _selected_format(self):
        text = self.format_combo.currentText()
        if "CSV" in text:
            return "csv", ".csv", "CSV Files (*.csv);;All Files (*.*)"
        if "JSON" in text:
            return "json", ".json", "JSON Files (*.json);;All Files (*.*)"
        return "tsv", ".tsv", "TSV Files (*.tsv);;All Files (*.*)"

    def _on_format_changed(self, format_text):
        """Handle format selection change."""
        # Update file extension
        if self.export_path:
            path = Path(self.export_path)
            stem = path.stem
            _, ext, _ = self._selected_format()

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
        _, default_ext, filter_str = self._selected_format()

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

    def _prompt_save_location(self) -> bool:
        """
        Prompt user for save location when pressing OK.
        Returns True if a path was selected, False if cancelled.
        """
        _, default_ext, filter_str = self._selected_format()

        # Use currently shown path filename as the default suggestion.
        suggested = self.file_path_edit.text().strip()
        if not suggested:
            suggested = f"lccn_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}{default_ext}"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Choose Export Location",
            suggested,
            filter_str
        )

        if not file_path:
            return False

        # Ensure extension matches selected format.
        path = Path(file_path)
        if path.suffix.lower() != default_ext:
            file_path = str(path.with_suffix(default_ext))

        self.export_path = file_path
        self.file_path_edit.setText(file_path)
        return True

    def _auto_generate_path(self):
        """Auto-generate export file path."""
        _, ext, _ = self._selected_format()

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
        if not self._prompt_save_location():
            return

        if not self._validate_export():
            return

        config = self.get_export_config()
        
        try:
            # Show processing message or cursor?
            # For now, just run it
            manager = ExportManager()
            result = manager.export(config)
            
            if result["success"]:
                msg = result["message"]
                QMessageBox.information(self, "Export Successful", msg)
                
                if config["open_after"] and result.get("files"):
                    for file_path in result["files"]:
                        self._open_file(file_path)
                
                self.accept()
            else:
                QMessageBox.critical(self, "Export Failed", result["message"])
                
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"An unexpected error occurred: {str(e)}")

    def _open_file(self, file_path):
        """Open file with default system application."""
        try:
            if sys.platform == "win32":
                os.startfile(file_path)
            elif sys.platform == "darwin":
                subprocess.call(["open", file_path])
            else:
                subprocess.call(["xdg-open", file_path])
        except Exception as e:
            print(f"Failed to open file {file_path}: {e}")

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
        format_type, _, _ = self._selected_format()

        return {
            "source": source,
            "format": format_type,
            "columns": selected_columns,
            "output_path": self.export_path,
            "include_header": self.include_header_check.isChecked(),
            "open_after": self.open_after_check.isChecked()
        }
