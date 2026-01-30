"""
Module: config_tab.py
Configuration settings tab.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QSpinBox, QGroupBox, QPushButton,
    QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
import json
from pathlib import Path


class ConfigTab(QWidget):
    config_changed = pyqtSignal(dict)  # Emits config when changed

    def __init__(self):
        super().__init__()
        self.config_file = Path("data/config.json")
        self.config = self._load_default_config()
        self._setup_ui()
        self._load_config()

    def _load_default_config(self):
        return {
            "collect_lccn": True,
            "collect_nlmcn": False,
            "retry_days": 7,
            "output_tsv": True,
            "output_invalid_isbn_file": True
        }

    def _setup_ui(self):
        layout = QVBoxLayout()

        # Title
        title_label = QLabel("Configuration Settings")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title_label)

        # Call Number Collection Settings
        collection_group = QGroupBox("Call Number Collection")
        collection_layout = QVBoxLayout()

        self.lccn_checkbox = QCheckBox("Collect Library of Congress Call Numbers (LCCN)")
        self.lccn_checkbox.setChecked(True)
        self.lccn_checkbox.stateChanged.connect(self._on_config_change)
        collection_layout.addWidget(self.lccn_checkbox)

        self.nlmcn_checkbox = QCheckBox("Collect NLM Call Numbers (NLMCN)")
        self.nlmcn_checkbox.stateChanged.connect(self._on_config_change)
        collection_layout.addWidget(self.nlmcn_checkbox)

        note_label = QLabel("Note: At least one call number type must be selected")
        note_label.setStyleSheet("font-size: 10px; font-style: italic; color: gray;")
        collection_layout.addWidget(note_label)

        collection_group.setLayout(collection_layout)
        layout.addWidget(collection_group)

        # Retry Settings
        retry_group = QGroupBox("Retry Settings")
        retry_layout = QHBoxLayout()

        retry_label = QLabel("Days before retrying failed ISBNs:")
        self.retry_spinbox = QSpinBox()
        self.retry_spinbox.setMinimum(0)
        self.retry_spinbox.setMaximum(365)
        self.retry_spinbox.setValue(7)
        self.retry_spinbox.setSuffix(" days")
        self.retry_spinbox.valueChanged.connect(self._on_config_change)

        retry_layout.addWidget(retry_label)
        retry_layout.addWidget(self.retry_spinbox)
        retry_layout.addStretch()

        retry_group.setLayout(retry_layout)
        layout.addWidget(retry_group)

        # Output Settings
        output_group = QGroupBox("Output Settings")
        output_layout = QVBoxLayout()

        self.tsv_checkbox = QCheckBox("Generate TSV output file")
        self.tsv_checkbox.setChecked(True)
        self.tsv_checkbox.stateChanged.connect(self._on_config_change)
        output_layout.addWidget(self.tsv_checkbox)

        self.invalid_isbn_checkbox = QCheckBox("Generate invalid ISBN file")
        self.invalid_isbn_checkbox.setChecked(True)
        self.invalid_isbn_checkbox.stateChanged.connect(self._on_config_change)
        output_layout.addWidget(self.invalid_isbn_checkbox)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # Save/Reset buttons
        button_layout = QHBoxLayout()

        self.save_button = QPushButton("Save Configuration")
        self.save_button.clicked.connect(self._save_config)

        self.reset_button = QPushButton("Reset to Defaults")
        self.reset_button.clicked.connect(self._reset_config)

        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.reset_button)
        button_layout.addStretch()

        layout.addLayout(button_layout)
        layout.addStretch()
        self.setLayout(layout)
        self.advanced_mode = False

    def set_advanced_mode(self, enabled):
        """Enable/disable advanced mode features."""
        self.advanced_mode = enabled
        # Config tab features are always visible for now

    def _on_config_change(self):
        # Ensure at least one call number type is selected
        if not self.lccn_checkbox.isChecked() and not self.nlmcn_checkbox.isChecked():
            self.lccn_checkbox.setChecked(True)
            QMessageBox.warning(
                self,
                "Invalid Configuration",
                "At least one call number type must be selected."
            )

    def _get_current_config(self):
        return {
            "collect_lccn": self.lccn_checkbox.isChecked(),
            "collect_nlmcn": self.nlmcn_checkbox.isChecked(),
            "retry_days": self.retry_spinbox.value(),
            "output_tsv": self.tsv_checkbox.isChecked(),
            "output_invalid_isbn_file": self.invalid_isbn_checkbox.isChecked()
        }

    def _save_config(self):
        self.config = self._get_current_config()

        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)

            self.config_changed.emit(self.config)
            QMessageBox.information(
                self,
                "Success",
                "Configuration saved successfully."
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save configuration: {str(e)}"
            )

    def _load_config(self):
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)

                # Update UI
                self.lccn_checkbox.setChecked(self.config.get("collect_lccn", True))
                self.nlmcn_checkbox.setChecked(self.config.get("collect_nlmcn", False))
                self.retry_spinbox.setValue(self.config.get("retry_days", 7))
                self.tsv_checkbox.setChecked(self.config.get("output_tsv", True))
                self.invalid_isbn_checkbox.setChecked(self.config.get("output_invalid_isbn_file", True))
        except Exception as e:
            QMessageBox.warning(
                self,
                "Warning",
                f"Failed to load configuration: {str(e)}\nUsing defaults."
            )

    def _reset_config(self):
        reply = QMessageBox.question(
            self,
            "Reset Configuration",
            "Are you sure you want to reset to default settings?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.config = self._load_default_config()
            self.lccn_checkbox.setChecked(True)
            self.nlmcn_checkbox.setChecked(False)
            self.retry_spinbox.setValue(7)
            self.tsv_checkbox.setChecked(True)
            self.invalid_isbn_checkbox.setChecked(True)

    def get_config(self):
        """Return current configuration."""
        return self._get_current_config()