"""
Module: advanced_settings_dialog.py
Advanced settings dialog for power user.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QWidget, QLabel, QSpinBox, QCheckBox, QGroupBox,
    QPushButton, QComboBox, QLineEdit, QDialogButtonBox
)
from PyQt6.QtCore import Qt
from pathlib import Path
import json


class AdvancedSettingsDialog(QDialog):
    """Advanced configuration options for power users."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Advanced Settings")
        self.setMinimumSize(600, 500)
        self.settings_file = Path("data/advanced_settings.json")
        self.settings = self._load_settings()
        self._setup_ui()

    def _load_settings(self):
        """Load advanced settings from file."""
        defaults = {
            "parallel_workers": 1,
            "connection_timeout": 30,
            "max_retries": 3,
            "retry_delay": 5,
            "enable_caching": True,
            "cache_ttl_days": 30,
            "enable_logging": True,
            "log_level": "INFO",
            "batch_size": 100,
            "enable_api_throttling": True,
            "api_delay_ms": 500,
            "show_api_responses": False,
            "enable_statistics": True
        }

        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
        except Exception:
            pass

        return defaults

    def _save_settings(self):
        """Save advanced settings to file."""
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Failed to save advanced settings: {e}")

    def _setup_ui(self):
        layout = QVBoxLayout()

        # Create tab widget for organized settings
        tabs = QTabWidget()

        # Performance Tab
        performance_tab = self._create_performance_tab()
        tabs.addTab(performance_tab, "Performance")

        # Network Tab
        network_tab = self._create_network_tab()
        tabs.addTab(network_tab, "Network")

        # Caching Tab
        caching_tab = self._create_caching_tab()
        tabs.addTab(caching_tab, "Caching")

        # Logging Tab
        logging_tab = self._create_logging_tab()
        tabs.addTab(logging_tab, "Logging")

        layout.addWidget(tabs)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.RestoreDefaults
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).clicked.connect(self._save_and_close)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).clicked.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self._restore_defaults)

        layout.addWidget(buttons)
        self.setLayout(layout)

    def _create_performance_tab(self):
        """Create performance settings tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        # Parallel Processing
        parallel_group = QGroupBox("Parallel Processing")
        parallel_layout = QVBoxLayout()

        workers_layout = QHBoxLayout()
        workers_layout.addWidget(QLabel("Parallel Workers:"))
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 10)
        self.workers_spin.setValue(self.settings["parallel_workers"])
        self.workers_spin.setToolTip("Number of ISBNs to process in parallel (1 = sequential)")
        workers_layout.addWidget(self.workers_spin)
        workers_layout.addStretch()
        parallel_layout.addLayout(workers_layout)

        warning = QLabel("⚠️ Note: Values > 1 may trigger rate limiting on APIs")
        warning.setStyleSheet("color: orange; font-size: 10px;")
        parallel_layout.addWidget(warning)

        parallel_group.setLayout(parallel_layout)
        layout.addWidget(parallel_group)

        # Batch Processing
        batch_group = QGroupBox("Batch Processing")
        batch_layout = QHBoxLayout()

        batch_layout.addWidget(QLabel("Batch Size:"))
        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(10, 1000)
        self.batch_spin.setValue(self.settings["batch_size"])
        self.batch_spin.setToolTip("Number of records to process before committing to database")
        batch_layout.addWidget(self.batch_spin)
        batch_layout.addStretch()

        batch_group.setLayout(batch_layout)
        layout.addWidget(batch_group)

        # Statistics
        stats_group = QGroupBox("Statistics")
        stats_layout = QVBoxLayout()

        self.enable_stats_check = QCheckBox("Enable detailed statistics tracking")
        self.enable_stats_check.setChecked(self.settings["enable_statistics"])
        self.enable_stats_check.setToolTip("Track per-target success rates and timing")
        stats_layout.addWidget(self.enable_stats_check)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _create_network_tab(self):
        """Create network settings tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        # Timeouts
        timeout_group = QGroupBox("Connection Timeouts")
        timeout_layout = QVBoxLayout()

        conn_layout = QHBoxLayout()
        conn_layout.addWidget(QLabel("Connection Timeout:"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setValue(self.settings["connection_timeout"])
        self.timeout_spin.setSuffix(" seconds")
        conn_layout.addWidget(self.timeout_spin)
        conn_layout.addStretch()
        timeout_layout.addLayout(conn_layout)

        timeout_group.setLayout(timeout_layout)
        layout.addWidget(timeout_group)

        # Retries
        retry_group = QGroupBox("Retry Logic")
        retry_layout = QVBoxLayout()

        max_retries_layout = QHBoxLayout()
        max_retries_layout.addWidget(QLabel("Max Retries:"))
        self.max_retries_spin = QSpinBox()
        self.max_retries_spin.setRange(0, 10)
        self.max_retries_spin.setValue(self.settings["max_retries"])
        max_retries_layout.addWidget(self.max_retries_spin)
        max_retries_layout.addStretch()
        retry_layout.addLayout(max_retries_layout)

        retry_delay_layout = QHBoxLayout()
        retry_delay_layout.addWidget(QLabel("Retry Delay:"))
        self.retry_delay_spin = QSpinBox()
        self.retry_delay_spin.setRange(1, 60)
        self.retry_delay_spin.setValue(self.settings["retry_delay"])
        self.retry_delay_spin.setSuffix(" seconds")
        retry_delay_layout.addWidget(self.retry_delay_spin)
        retry_delay_layout.addStretch()
        retry_layout.addLayout(retry_delay_layout)

        retry_group.setLayout(retry_layout)
        layout.addWidget(retry_group)

        # API Throttling
        throttle_group = QGroupBox("API Throttling")
        throttle_layout = QVBoxLayout()

        self.throttle_check = QCheckBox("Enable API request throttling")
        self.throttle_check.setChecked(self.settings["enable_api_throttling"])
        throttle_layout.addWidget(self.throttle_check)

        delay_layout = QHBoxLayout()
        delay_layout.addWidget(QLabel("Delay between requests:"))
        self.api_delay_spin = QSpinBox()
        self.api_delay_spin.setRange(0, 5000)
        self.api_delay_spin.setValue(self.settings["api_delay_ms"])
        self.api_delay_spin.setSuffix(" ms")
        delay_layout.addWidget(self.api_delay_spin)
        delay_layout.addStretch()
        throttle_layout.addLayout(delay_layout)

        throttle_group.setLayout(throttle_layout)
        layout.addWidget(throttle_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _create_caching_tab(self):
        """Create caching settings tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        cache_group = QGroupBox("Database Caching")
        cache_layout = QVBoxLayout()

        self.caching_check = QCheckBox("Enable database caching")
        self.caching_check.setChecked(self.settings["enable_caching"])
        self.caching_check.setToolTip("Check database before querying external sources")
        cache_layout.addWidget(self.caching_check)

        ttl_layout = QHBoxLayout()
        ttl_layout.addWidget(QLabel("Cache TTL:"))
        self.cache_ttl_spin = QSpinBox()
        self.cache_ttl_spin.setRange(1, 365)
        self.cache_ttl_spin.setValue(self.settings["cache_ttl_days"])
        self.cache_ttl_spin.setSuffix(" days")
        self.cache_ttl_spin.setToolTip("How long to trust cached results")
        ttl_layout.addWidget(self.cache_ttl_spin)
        ttl_layout.addStretch()
        cache_layout.addLayout(ttl_layout)

        cache_group.setLayout(cache_layout)
        layout.addWidget(cache_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _create_logging_tab(self):
        """Create logging settings tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        log_group = QGroupBox("Logging Configuration")
        log_layout = QVBoxLayout()

        self.logging_check = QCheckBox("Enable detailed logging")
        self.logging_check.setChecked(self.settings["enable_logging"])
        log_layout.addWidget(self.logging_check)

        level_layout = QHBoxLayout()
        level_layout.addWidget(QLabel("Log Level:"))
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.log_level_combo.setCurrentText(self.settings["log_level"])
        level_layout.addWidget(self.log_level_combo)
        level_layout.addStretch()
        log_layout.addLayout(level_layout)

        log_group.setLayout(log_layout)
        layout.addWidget(log_group)


        debug_group = QGroupBox("Debug Features")
        debug_layout = QVBoxLayout()

        self.show_responses_check = QCheckBox("Show raw API responses in log")
        self.show_responses_check.setChecked(self.settings["show_api_responses"])
        self.show_responses_check.setToolTip("Display full API JSON/XML responses (verbose)")
        debug_layout.addWidget(self.show_responses_check)

        debug_group.setLayout(debug_layout)
        layout.addWidget(debug_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _save_and_close(self):
        """Save settings and close dialog."""
        # Update settings from UI
        self.settings["parallel_workers"] = self.workers_spin.value()
        self.settings["connection_timeout"] = self.timeout_spin.value()
        self.settings["max_retries"] = self.max_retries_spin.value()
        self.settings["retry_delay"] = self.retry_delay_spin.value()
        self.settings["enable_caching"] = self.caching_check.isChecked()
        self.settings["cache_ttl_days"] = self.cache_ttl_spin.value()
        self.settings["enable_logging"] = self.logging_check.isChecked()
        self.settings["log_level"] = self.log_level_combo.currentText()
        self.settings["batch_size"] = self.batch_spin.value()
        self.settings["enable_api_throttling"] = self.throttle_check.isChecked()
        self.settings["api_delay_ms"] = self.api_delay_spin.value()
        self.settings["show_api_responses"] = self.show_responses_check.isChecked()
        self.settings["enable_statistics"] = self.enable_stats_check.isChecked()

        self._save_settings()
        self.accept()

    def _restore_defaults(self):
        """Restore default settings."""
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "Restore Defaults",
            "Reset all advanced settings to defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.settings = self._load_settings().__class__.__dict__.copy()
            # Update UI with defaults
            self.workers_spin.setValue(1)
            self.timeout_spin.setValue(30)
            self.max_retries_spin.setValue(3)
            self.retry_delay_spin.setValue(5)
            self.caching_check.setChecked(True)
            self.cache_ttl_spin.setValue(30)
            self.logging_check.setChecked(True)
            self.log_level_combo.setCurrentText("INFO")
            self.batch_spin.setValue(100)
            self.throttle_check.setChecked(True)
            self.api_delay_spin.setValue(500)
            self.show_responses_check.setChecked(False)
            self.enable_stats_check.setChecked(True)

    def get_settings(self):
        """Return current settings."""
        return self.settings.copy()
