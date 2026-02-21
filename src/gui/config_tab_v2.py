"""
Module: config_tab_v2.py
V2 Configuration Tab with modern borderless design and clean form layout.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QComboBox,
    QSpinBox, QMessageBox, QInputDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.profile_manager import ProfileManager
from .icons import get_pixmap, SVG_SETTINGS
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
        lbl = QLabel("&Active Profile")
        lbl.setStyleSheet(f"font-weight: bold; color: {CATPPUCCIN_THEME['text']};")
        
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(250)
        self.profile_combo.setProperty("class", "ComboBox")
        self.profile_combo.setAccessibleName("Active profile selector")
        self.profile_combo.setAccessibleDescription("Choose which saved profile is active.")
        self._refresh_profile_list()
        self.profile_combo.currentTextChanged.connect(self._on_profile_selected)
        lbl.setBuddy(self.profile_combo)
        
        info_layout.addWidget(lbl)
        info_layout.addWidget(self.profile_combo)
        profile_layout.addLayout(info_layout)
        
        profile_layout.addStretch()
        
        # Actions
        btn_layout = QHBoxLayout()
        
        self.btn_new = QPushButton("&New Profile")
        self.btn_new.setProperty("class", "SecondaryButton")
        self.btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new.setAccessibleName("Create profile")
        self.btn_new.setToolTip("Create a new profile from current settings")
        self.btn_new.clicked.connect(self._create_new_profile)
        
        self.btn_save = QPushButton("&Save Changes")
        self.btn_save.setProperty("class", "PrimaryButton")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setEnabled(False) # Initially disabled
        self.btn_save.setAccessibleName("Save profile changes")
        self.btn_save.setToolTip("Save current settings to the selected profile")
        self.btn_save.clicked.connect(self._save_current_profile)
        
        self.btn_delete = QPushButton("&Delete")
        self.btn_delete.setProperty("class", "DangerButton")
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setAccessibleName("Delete profile")
        self.btn_delete.setToolTip("Delete the selected profile")
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
        retry_lbl = QLabel("&Retry Interval (Days)")
        retry_lbl.setStyleSheet(f"color: {CATPPUCCIN_THEME['text']};")
        retry_desc = QLabel("Skip ISBNs that failed recently")
        retry_desc.setStyleSheet(f"color: {CATPPUCCIN_THEME['subtext0']}; font-size: 12px;")
        
        desc_layout = QVBoxLayout()
        desc_layout.addWidget(retry_lbl)
        desc_layout.addWidget(retry_desc)
        
        self.spin_retry = QSpinBox()
        self.spin_retry.setRange(0, 365)
        self.spin_retry.setValue(7)
        self.spin_retry.setSuffix(" days")
        self.spin_retry.setFixedWidth(100)
        self.spin_retry.setAccessibleName("Retry interval")
        self.spin_retry.setToolTip("Days to wait before retrying recently failed ISBNs")
        self.spin_retry.valueChanged.connect(self._on_setting_changed)
        retry_lbl.setBuddy(self.spin_retry)
        # Style spinbox? Maybe later. For now let stylesheet handle generic QSpinBox if any
        
        retry_row.addLayout(desc_layout)
        retry_row.addStretch()
        retry_row.addWidget(self.spin_retry)
        
        form_layout.addLayout(retry_row)
        form_layout.addWidget(self._create_divider())
        
        # Call Number Mode
        mode_row = QHBoxLayout()
        mode_lbl = QLabel("Call Number &Mode")
        mode_lbl.setStyleSheet(f"color: {CATPPUCCIN_THEME['text']};")
        mode_desc = QLabel("Choose which call number type is accepted during harvest")
        mode_desc.setStyleSheet(f"color: {CATPPUCCIN_THEME['subtext0']}; font-size: 12px;")

        mode_desc_layout = QVBoxLayout()
        mode_desc_layout.addWidget(mode_lbl)
        mode_desc_layout.addWidget(mode_desc)

        self.call_number_combo = QComboBox()
        self.call_number_combo.setFixedWidth(180)
        self.call_number_combo.setAccessibleName("Call number mode")
        self.call_number_combo.setAccessibleDescription("Choose whether to collect LCCN only, NLMCN only, or both.")
        self.call_number_combo.setToolTip("Select which call-number type is accepted during harvest")
        self.call_number_combo.addItem("LCCN only", "lccn")
        self.call_number_combo.addItem("NLMCN only", "nlmcn")
        self.call_number_combo.addItem("Both", "both")
        self.call_number_combo.currentTextChanged.connect(self._on_setting_changed)
        mode_lbl.setBuddy(self.call_number_combo)

        mode_row.addLayout(mode_desc_layout)
        mode_row.addStretch()
        mode_row.addWidget(self.call_number_combo)

        form_layout.addLayout(mode_row)
        
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
    def _extract_profile_settings(self, profile_data):
        """Normalize profile payloads from ProfileManager to a flat settings dict."""
        if not isinstance(profile_data, dict):
            return {}
        settings = profile_data.get("settings")
        if isinstance(settings, dict):
            return settings
        # Backward compatibility with any legacy flat payload
        return profile_data

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
        profile = self.profile_manager.load_profile(profile_name)
        config = self._extract_profile_settings(profile)
        
        # Populate UI
        self.spin_retry.blockSignals(True)
        self.call_number_combo.blockSignals(True)
        
        self.spin_retry.setValue(config.get("retry_days", 7))
        mode = self._mode_from_settings(config)
        idx = self.call_number_combo.findData(mode)
        self.call_number_combo.setCurrentIndex(idx if idx >= 0 else 0)
        
        self.spin_retry.blockSignals(False)
        self.call_number_combo.blockSignals(False)
        
        self.has_unsaved_changes = False
        self.btn_save.setEnabled(False)
        self.profile_changed.emit(profile_name)
        self.config_changed.emit(self.get_config())

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
        if self.current_profile_name == "Default Settings":
            QMessageBox.information(
                self,
                "Cannot Modify Default",
                "The Default Settings profile cannot be modified.\n\nCreate a new profile and save there."
            )
            return

        mode = self._current_call_number_mode()
        config = {
            "retry_days": self.spin_retry.value(),
            "call_number_mode": mode,
            "collect_lccn": mode in {"lccn", "both"},
            "collect_nlmcn": mode in {"nlmcn", "both"},
        }
        self.profile_manager.save_profile(self.current_profile_name, config)
        self.has_unsaved_changes = False
        self.btn_save.setEnabled(False)
        self.config_changed.emit(config)
        QMessageBox.information(self, "Saved", f"Profile '{self.current_profile_name}' saved.")

    def _create_new_profile(self):
        name, ok = QInputDialog.getText(self, "New Profile", "Profile Name:")
        if ok and name:
            name = name.strip()
            if not name:
                return
            if name in self.profile_manager.list_profiles():
                QMessageBox.warning(self, "Error", "Profile already exists.")
                return
            
            # Create from current visible settings (matches old tab "Save As" behavior).
            self.profile_manager.save_profile(name, self.get_config())
            self._refresh_profile_list()
            self.profile_combo.setCurrentText(name) # Will trigger load

    def _delete_current_profile(self):
        if self.current_profile_name == "Default Settings":
            QMessageBox.warning(self, "Error", "Cannot delete default profile.")
            return
            
        confirm = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete profile '{self.current_profile_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.profile_manager.delete_profile(self.current_profile_name)
            self.profile_manager.set_active_profile("Default Settings")
            self._refresh_profile_list()
            self._load_profile("Default Settings")
            # It will auto-select default or first available

    def get_config(self):
        """Public accessor for other tabs."""
        mode = self._current_call_number_mode()
        return {
            "retry_days": self.spin_retry.value(),
            "call_number_mode": mode,
            # Keep parity with legacy ConfigTab expected keys.
            "collect_lccn": mode in {"lccn", "both"},
            "collect_nlmcn": mode in {"nlmcn", "both"},
            "output_tsv": True,
            "output_invalid_isbn_file": True,
        }

    def _current_call_number_mode(self):
        mode = self.call_number_combo.currentData()
        return mode if mode in {"lccn", "nlmcn", "both"} else "lccn"

    def _mode_from_settings(self, settings):
        mode = settings.get("call_number_mode")
        if mode in {"lccn", "nlmcn", "both"}:
            return mode
        collect_lccn = bool(settings.get("collect_lccn", True))
        collect_nlmcn = bool(settings.get("collect_nlmcn", False))
        if collect_lccn and collect_nlmcn:
            return "both"
        if collect_nlmcn:
            return "nlmcn"
        return "lccn"
