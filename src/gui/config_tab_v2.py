"""
Module: config_tab_v2.py
V2 Configuration Tab with modern borderless design and clean form layout.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QComboBox, QCheckBox, 
    QSpinBox, QMessageBox, QInputDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.profile_manager import ProfileManager
from .icons import get_icon, get_pixmap, SVG_SETTINGS, SVG_HARVEST
from .styles_v2 import CATPPUCCIN_THEME

class ConfigTabV2(QWidget):
    config_changed = pyqtSignal(dict)
    profile_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.profile_manager = ProfileManager()
        self.current_profile_name = self.profile_manager.get_active_profile()
        self.has_unsaved_changes = False
        self._setup_ui()
        self._load_profile(self.current_profile_name)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)

        # =========================================================================
        # 1. Header
        # =========================================================================
        header_layout = QHBoxLayout()
        title_block = QVBoxLayout()
        title = QLabel("Configuration")
        title.setProperty("class", "PageTitle")
        title.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {CATPPUCCIN_THEME['text']};")
        
        subtitle = QLabel("Manage profiles and global settings")
        subtitle.setStyleSheet(f"font-size: 14px; color: {CATPPUCCIN_THEME['subtext0']};")
        
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        
        header_layout.addLayout(title_block)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # =========================================================================
        # 2. Profile Section (Card)
        # =========================================================================
        profile_frame = QFrame()
        profile_frame.setProperty("class", "Card")
        profile_layout = QHBoxLayout(profile_frame)
        profile_layout.setSpacing(20)
        profile_layout.setContentsMargins(20, 20, 20, 20)
        
        # Icon
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap(SVG_SETTINGS, CATPPUCCIN_THEME['blue']))
        profile_layout.addWidget(icon_lbl)
        
        # Selector
        info_layout = QVBoxLayout()
        lbl = QLabel("Active Profile")
        lbl.setStyleSheet(f"font-weight: bold; color: {CATPPUCCIN_THEME['text']};")
        
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(250)
        self.profile_combo.setProperty("class", "ComboBox")
        self._refresh_profile_list()
        self.profile_combo.currentTextChanged.connect(self._on_profile_selected)
        
        info_layout.addWidget(lbl)
        info_layout.addWidget(self.profile_combo)
        profile_layout.addLayout(info_layout)
        
        profile_layout.addStretch()
        
        # Actions
        btn_layout = QHBoxLayout()
        
        self.btn_new = QPushButton("New Profile")
        self.btn_new.setProperty("class", "SecondaryButton")
        self.btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new.clicked.connect(self._create_new_profile)
        
        self.btn_save = QPushButton("Save Changes")
        self.btn_save.setProperty("class", "PrimaryButton")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setEnabled(False) # Initially disabled
        self.btn_save.clicked.connect(self._save_current_profile)
        
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setProperty("class", "DangerButton")
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.clicked.connect(self._delete_current_profile)
        
        btn_layout.addWidget(self.btn_new)
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_delete)
        
        profile_layout.addLayout(btn_layout)
        
        layout.addWidget(profile_frame)

        # =========================================================================
        # 3. Settings Form (Card)
        # =========================================================================
        settings_frame = QFrame()
        settings_frame.setProperty("class", "Card")
        settings_layout = QVBoxLayout(settings_frame)
        settings_layout.setSpacing(20)
        settings_layout.setContentsMargins(25, 25, 25, 25)
        
        settings_title = QLabel("Global Settings")
        settings_title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {CATPPUCCIN_THEME['text']}; margin-bottom: 10px;")
        settings_layout.addWidget(settings_title)

        # Form Grid
        form_layout = QVBoxLayout()
        form_layout.setSpacing(15)

        # Retry Days
        retry_row = QHBoxLayout()
        retry_lbl = QLabel("Retry Interval (Days)")
        retry_lbl.setStyleSheet(f"color: {CATPPUCCIN_THEME['text']};")
        retry_desc = QLabel("Skip ISBNs that failed recently")
        retry_desc.setStyleSheet(f"color: {CATPPUCCIN_THEME['subtext0']}; font-size: 12px;")
        
        desc_layout = QVBoxLayout()
        desc_layout.addWidget(retry_lbl)
        desc_layout.addWidget(retry_desc)
        
        self.spin_retry = QSpinBox()
        self.spin_retry.setRange(0, 365)
        self.spin_retry.setValue(7)
        self.spin_retry.setFixedWidth(100)
        self.spin_retry.valueChanged.connect(self._on_setting_changed)
        # Style spinbox? Maybe later. For now let stylesheet handle generic QSpinBox if any
        
        retry_row.addLayout(desc_layout)
        retry_row.addStretch()
        retry_row.addWidget(self.spin_retry)
        
        form_layout.addLayout(retry_row)
        form_layout.addWidget(self._create_divider())
        
        # Batch Size
        batch_row = QHBoxLayout()
        batch_lbl = QLabel("Batch Size")
        batch_lbl.setStyleSheet(f"color: {CATPPUCCIN_THEME['text']};")
        batch_desc = QLabel("Number of ISBNs processed per transaction")
        batch_desc.setStyleSheet(f"color: {CATPPUCCIN_THEME['subtext0']}; font-size: 12px;")
        
        batch_desc_layout = QVBoxLayout()
        batch_desc_layout.addWidget(batch_lbl)
        batch_desc_layout.addWidget(batch_desc)
        
        self.spin_batch = QSpinBox()
        self.spin_batch.setRange(1, 1000)
        self.spin_batch.setValue(50)
        self.spin_batch.setFixedWidth(100)
        self.spin_batch.valueChanged.connect(self._on_setting_changed)
        
        batch_row.addLayout(batch_desc_layout)
        batch_row.addStretch()
        batch_row.addWidget(self.spin_batch)
        
        form_layout.addLayout(batch_row)
        
        settings_layout.addLayout(form_layout)
        layout.addWidget(settings_frame)
        
        layout.addStretch()

    def _create_divider(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet(f"background-color: {CATPPUCCIN_THEME['surface1']}; max-height: 1px;")
        return line

    # =========================================================================
    # Logic Methods (Adapted from original ConfigTab)
    # =========================================================================
    def _refresh_profile_list(self):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        profiles = self.profile_manager.list_profiles()
        self.profile_combo.addItems(profiles)
        
        current = self.profile_manager.get_active_profile()
        idx = self.profile_combo.findText(current)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)
        
        self.profile_combo.blockSignals(False)

    def _load_profile(self, profile_name):
        self.current_profile_name = profile_name
        config = self.profile_manager.load_profile(profile_name)
        
        # Populate UI
        self.spin_retry.blockSignals(True)
        self.spin_batch.blockSignals(True)
        
        self.spin_retry.setValue(config.get("retry_days", 7))
        self.spin_batch.setValue(config.get("batch_size", 50))
        
        self.spin_retry.blockSignals(False)
        self.spin_batch.blockSignals(False)
        
        self.has_unsaved_changes = False
        self.btn_save.setEnabled(False)
        self.profile_changed.emit(profile_name)
        self.config_changed.emit(config)

    def _on_profile_selected(self, name):
        if not name: return
        if self.has_unsaved_changes:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Save them before switching?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Cancel:
                self.profile_combo.blockSignals(True)
                self.profile_combo.setCurrentText(self.current_profile_name)
                self.profile_combo.blockSignals(False)
                return
            if reply == QMessageBox.StandardButton.Yes:
                self._save_current_profile()
        
        self.profile_manager.set_active_profile(name)
        self._load_profile(name)

    def _on_setting_changed(self):
        self.has_unsaved_changes = True
        self.btn_save.setEnabled(True)

    def _save_current_profile(self):
        config = {
            "retry_days": self.spin_retry.value(),
            "batch_size": self.spin_batch.value()
        }
        self.profile_manager.save_profile(self.current_profile_name, config)
        self.has_unsaved_changes = False
        self.btn_save.setEnabled(False)
        self.config_changed.emit(config)
        QMessageBox.information(self, "Saved", f"Profile '{self.current_profile_name}' saved.")

    def _create_new_profile(self):
        name, ok = QInputDialog.getText(self, "New Profile", "Profile Name:")
        if ok and name:
            if name in self.profile_manager.list_profiles():
                QMessageBox.warning(self, "Error", "Profile already exists.")
                return
            
            # Create with defaults
            default_config = {"retry_days": 7, "batch_size": 50}
            self.profile_manager.save_profile(name, default_config)
            self._refresh_profile_list()
            self.profile_combo.setCurrentText(name) # Will trigger load

    def _delete_current_profile(self):
        if self.current_profile_name == "default":
            QMessageBox.warning(self, "Error", "Cannot delete default profile.")
            return
            
        confirm = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete profile '{self.current_profile_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.profile_manager.delete_profile(self.current_profile_name)
            self._refresh_profile_list()
            # It will auto-select default or first available

    def get_config(self):
        """Public accessor for other tabs."""
        return {
            "retry_days": self.spin_retry.value(),
            "batch_size": self.spin_batch.value()
        }
