"""
Module: config_tab.py
Configuration settings tab with profile management.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QSpinBox, QGroupBox, QPushButton,
    QMessageBox, QComboBox, QInputDialog, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).parent.parent))
from config.profile_manager import ProfileManager


class ConfigTab(QWidget):
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
        layout = QVBoxLayout()
        layout.setSpacing(15)

        # Profile Selector Section - Clean and minimal
        profile_section = self._create_profile_section()
        layout.addWidget(profile_section)

        # Settings Section
        settings_section = self._create_settings_section()
        layout.addWidget(settings_section)

        layout.addStretch()
        self.setLayout(layout)
        self.advanced_mode = False

    def _create_profile_section(self):
        """Create clean profile selector section."""
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet("""
            QFrame {
                background-color: #1b1f24;
                border: 1px solid #2c3440;
                border-radius: 6px;
                padding: 12px;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(10)

        # Title row
        title_row = QHBoxLayout()
        title = QLabel("Configuration Profile")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #e6e1d5;")
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        # Profile selector row
        selector_row = QHBoxLayout()

        # Dropdown
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(250)
        self.profile_combo.setStyleSheet("""
            QComboBox {
                padding: 6px 10px;
                border: 1px solid #2c3440;
                border-radius: 4px;
                background: #232a32;
                color: #e6e1d5;
                font-size: 13px;
            }
            QComboBox:hover {
                border-color: #f4b860;
            }
            QComboBox QAbstractItemView {
                background: #1b1f24;
                color: #e6e1d5;
                selection-background-color: #2e3943;
                selection-color: #f4b860;
            }
        """)
        self._refresh_profile_list()
        self.profile_combo.currentTextChanged.connect(self._on_profile_selected)

        active_label = QLabel("Active:")
        active_label.setStyleSheet("color: #e6e1d5; font-weight: 500;")
        selector_row.addWidget(active_label)
        selector_row.addWidget(self.profile_combo)
        selector_row.addStretch()

        # Unsaved changes indicator
        self.unsaved_label = QLabel("● Unsaved changes")
        self.unsaved_label.setStyleSheet("color: #ff6b6b; font-size: 11px; font-weight: bold;")
        self.unsaved_label.setVisible(False)
        selector_row.addWidget(self.unsaved_label)

        layout.addLayout(selector_row)

        # Action buttons row - Simple and clean
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(8)

        # Save button
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save_to_current_profile)
        self.save_btn.setStyleSheet(self._get_button_style("#28a745"))

        # Save As button
        save_as_btn = QPushButton("Save As...")
        save_as_btn.clicked.connect(self._save_as_new_profile)
        save_as_btn.setStyleSheet(self._get_button_style("#007bff"))

        # Session Only button
        session_btn = QPushButton("Use Session Only")
        session_btn.clicked.connect(self._use_session_only)
        session_btn.setStyleSheet(self._get_button_style("#6c757d"))

        # Manage button (dropdown for rename/delete)
        manage_btn = QPushButton("⚙️ Manage")
        manage_btn.clicked.connect(self._show_manage_menu)
        manage_btn.setStyleSheet(self._get_button_style("#17a2b8"))

        buttons_row.addWidget(self.save_btn)
        buttons_row.addWidget(save_as_btn)
        buttons_row.addWidget(session_btn)
        buttons_row.addWidget(manage_btn)
        buttons_row.addStretch()

        layout.addLayout(buttons_row)

        frame.setLayout(layout)
        return frame

    def _create_settings_section(self):
        """Create settings section."""
        frame = QFrame()
        layout = QVBoxLayout()

        # Title
        title = QLabel("Settings")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #e6e1d5; margin-top: 5px;")
        layout.addWidget(title)

        # Call Number Collection
        collection_group = self._create_group("Call Number Collection")
        collection_layout = QVBoxLayout()

        self.lccn_checkbox = QCheckBox("Collect Library of Congress Call Numbers (LCCN)")
        self.lccn_checkbox.setChecked(True)
        self.lccn_checkbox.stateChanged.connect(self._mark_unsaved)
        self.lccn_checkbox.setStyleSheet("color: #e6e1d5;")
        collection_layout.addWidget(self.lccn_checkbox)

        self.nlmcn_checkbox = QCheckBox("Collect NLM Call Numbers (NLMCN)")
        self.nlmcn_checkbox.stateChanged.connect(self._mark_unsaved)
        self.nlmcn_checkbox.setStyleSheet("color: #e6e1d5;")
        collection_layout.addWidget(self.nlmcn_checkbox)

        collection_group.setLayout(collection_layout)
        layout.addWidget(collection_group)

        # Retry Settings
        retry_group = self._create_group("Retry Settings")
        retry_layout = QHBoxLayout()

        retry_label = QLabel("Days before retrying failed ISBNs:")
        retry_label.setStyleSheet("color: #e6e1d5;")
        self.retry_spinbox = QSpinBox()
        self.retry_spinbox.setMinimum(0)
        self.retry_spinbox.setMaximum(365)
        self.retry_spinbox.setValue(7)
        self.retry_spinbox.setSuffix(" days")
        self.retry_spinbox.valueChanged.connect(self._mark_unsaved)
        self.retry_spinbox.setStyleSheet("padding: 4px; color: #e6e1d5; background: #232a32; border: 1px solid #2c3440;")

        retry_layout.addWidget(retry_label)
        retry_layout.addWidget(self.retry_spinbox)
        retry_layout.addStretch()

        retry_group.setLayout(retry_layout)
        layout.addWidget(retry_group)

        # Output Settings
        output_group = self._create_group("Output Settings")
        output_layout = QVBoxLayout()

        self.tsv_checkbox = QCheckBox("Generate TSV output file")
        self.tsv_checkbox.setChecked(True)
        self.tsv_checkbox.stateChanged.connect(self._mark_unsaved)
        self.tsv_checkbox.setStyleSheet("color: #e6e1d5;")
        output_layout.addWidget(self.tsv_checkbox)

        self.invalid_isbn_checkbox = QCheckBox("Generate invalid ISBN file")
        self.invalid_isbn_checkbox.setChecked(True)
        self.invalid_isbn_checkbox.stateChanged.connect(self._mark_unsaved)
        self.invalid_isbn_checkbox.setStyleSheet("color: #e6e1d5;")
        output_layout.addWidget(self.invalid_isbn_checkbox)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        frame.setLayout(layout)
        return frame

    def _create_group(self, title):
        """Create a clean group box."""
        group = QGroupBox(title)
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                color: #f0c989;
                border: 1px solid #2c3440;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #f0c989;
            }
        """)
        return group

    def _get_button_style(self, color):
        """Get consistent button styling."""
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                padding: 6px 14px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {self._darken_color(color)};
            }}
            QPushButton:pressed {{
                background-color: {self._darken_color(color, 0.2)};
            }}
            QPushButton:disabled {{
                background-color: #cccccc;
                color: #666666;
            }}
        """

    def _darken_color(self, hex_color, factor=0.1):
        """Darken a hex color."""
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        rgb = tuple(max(0, int(c * (1 - factor))) for c in rgb)
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    def _refresh_profile_list(self):
        """Refresh the profile dropdown."""
        current = self.profile_combo.currentText()
        self.profile_combo.clear()

        profiles = self.profile_manager.list_profiles()
        self.profile_combo.addItems(profiles)

        # Restore selection
        if current in profiles:
            self.profile_combo.setCurrentText(current)

    def _on_profile_selected(self, profile_name):
        """Handle profile selection."""
        if not profile_name or profile_name == self.current_profile_name:
            return

        # Check for unsaved changes
        if self.has_unsaved_changes:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"You have unsaved changes to '{self.current_profile_name}'.\n\nDiscard changes and switch to '{profile_name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                self.profile_combo.setCurrentText(self.current_profile_name)
                return

        self._load_profile(profile_name)

    def _load_profile(self, profile_name):
        """Load a profile."""
        profile_data = self.profile_manager.load_profile(profile_name)
        if not profile_data:
            QMessageBox.warning(self, "Error", f"Failed to load profile: {profile_name}")
            return

        settings = profile_data.get("settings", {})

        # Update UI - check if widgets exist first
        if hasattr(self, 'lccn_checkbox'):
            self.lccn_checkbox.setChecked(settings.get("collect_lccn", True))
            self.nlmcn_checkbox.setChecked(settings.get("collect_nlmcn", False))
            self.retry_spinbox.setValue(settings.get("retry_days", 7))
            self.tsv_checkbox.setChecked(settings.get("output_tsv", True))
            self.invalid_isbn_checkbox.setChecked(settings.get("output_invalid_isbn_file", True))

        self.current_profile_name = profile_name
        if hasattr(self, 'profile_combo'):
            self.profile_combo.setCurrentText(profile_name)
        self.profile_manager.set_active_profile(profile_name)

        self._clear_unsaved()
        self.profile_changed.emit(profile_name)

    def _mark_unsaved(self):
        """Mark that there are unsaved changes."""
        self.has_unsaved_changes = True
        self.unsaved_label.setVisible(True)
        self.save_btn.setEnabled(True)

    def _clear_unsaved(self):
        """Clear unsaved changes flag."""
        self.has_unsaved_changes = False
        if hasattr(self, 'unsaved_label'):
            self.unsaved_label.setVisible(False)
        if hasattr(self, 'save_btn'):
            self.save_btn.setEnabled(False)

    def _get_current_settings(self):
        """Get current settings from UI."""
        return {
            "collect_lccn": self.lccn_checkbox.isChecked(),
            "collect_nlmcn": self.nlmcn_checkbox.isChecked(),
            "retry_days": self.retry_spinbox.value(),
            "output_tsv": self.tsv_checkbox.isChecked(),
            "output_invalid_isbn_file": self.invalid_isbn_checkbox.isChecked()
        }

    def _normalize_settings(self, settings):
        """Create a stable comparable representation for settings."""
        import json
        return json.dumps(settings, sort_keys=True, separators=(",", ":"))

    def _find_duplicate_profiles(self, settings, *, exclude_name=None):
        """Return profile names that have identical settings."""
        target = self._normalize_settings(settings)
        duplicates = []
        for profile_name in self.profile_manager.list_profiles():
            if exclude_name and profile_name == exclude_name:
                continue
            profile = self.profile_manager.load_profile(profile_name)
            if not profile:
                continue
            existing_settings = profile.get("settings", {})
            if self._normalize_settings(existing_settings) == target:
                duplicates.append(profile_name)
        return duplicates

    def _save_to_current_profile(self):
        """Save changes to current profile."""
        if self.current_profile_name == "Default Settings":
            QMessageBox.information(
                self,
                "Cannot Modify Default",
                "The Default Settings profile cannot be modified.\n\nPlease use 'Save As...' to create a new profile."
            )
            return

        settings = self._get_current_settings()
        self.profile_manager.save_profile(self.current_profile_name, settings)

        self._clear_unsaved()
        self.config_changed.emit(settings)

        QMessageBox.information(self, "Saved", f"Profile '{self.current_profile_name}' saved successfully.")

    def _save_as_new_profile(self):
        """Save current settings as a new profile."""
        name, ok = QInputDialog.getText(
            self,
            "Save New Profile",
            "Enter a name for this profile:",
            text=""
        )

        if ok and name:
            name = name.strip()
            if not name:
                return

            # Check if name already exists
            if name in self.profile_manager.list_profiles():
                reply = QMessageBox.question(
                    self,
                    "Profile Exists",
                    f"Profile '{name}' already exists. Overwrite it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return

            settings = self._get_current_settings()

            # Warn if settings duplicate an existing profile.
            duplicates = self._find_duplicate_profiles(settings, exclude_name=name)
            if duplicates:
                dup_list = "\n".join([f"• {n}" for n in duplicates])
                reply = QMessageBox.question(
                    self,
                    "Duplicate Profile Settings",
                    "These settings already exist in another profile:\n\n"
                    f"{dup_list}\n\n"
                    "Create this profile anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return

            self.profile_manager.save_profile(name, settings)

            self._refresh_profile_list()
            self._load_profile(name)

            QMessageBox.information(self, "Success", f"Profile '{name}' created successfully.")

    def _use_session_only(self):
        """Use current settings for this session only."""
        self._clear_unsaved()
        QMessageBox.information(
            self,
            "Session Only",
            "These settings will be used for this session only.\n\nChanges will not be saved to the profile."
        )

    def _show_manage_menu(self):
        """Show profile management options."""
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QCursor

        menu = QMenu(self)

        rename_action = menu.addAction("✏️ Rename Profile")
        delete_action = menu.addAction("🗑️ Delete Profile")
        menu.addSeparator()
        reset_action = menu.addAction("🔄 Reset to Default Settings")

        action = menu.exec(QCursor.pos())

        if action == rename_action:
            self._rename_profile()
        elif action == delete_action:
            self._delete_profile()
        elif action == reset_action:
            self._reset_to_default()

    def _rename_profile(self):
        """Rename current profile."""
        if self.current_profile_name == "Default Settings":
            QMessageBox.information(self, "Cannot Rename", "The Default Settings profile cannot be renamed.")
            return

        new_name, ok = QInputDialog.getText(
            self,
            "Rename Profile",
            "Enter new name:",
            text=self.current_profile_name
        )

        if ok and new_name:
            new_name = new_name.strip()
            if new_name and new_name != self.current_profile_name:
                if self.profile_manager.rename_profile(self.current_profile_name, new_name):
                    self._refresh_profile_list()
                    self._load_profile(new_name)
                    QMessageBox.information(self, "Success", f"Profile renamed to '{new_name}'.")
                else:
                    QMessageBox.warning(self, "Error", "Failed to rename profile.")

    def _delete_profile(self):
        """Delete current profile."""
        if self.current_profile_name == "Default Settings":
            QMessageBox.information(self, "Cannot Delete", "The Default Settings profile cannot be deleted.")
            return

        reply = QMessageBox.question(
            self,
            "Delete Profile",
            f"Are you sure you want to delete profile '{self.current_profile_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self.profile_manager.delete_profile(self.current_profile_name):
                self._refresh_profile_list()
                self._load_profile("Default Settings")
                QMessageBox.information(self, "Deleted", "Profile deleted successfully.")
            else:
                QMessageBox.warning(self, "Error", "Failed to delete profile.")

    def _reset_to_default(self):
        """Reset to default settings."""
        reply = QMessageBox.question(
            self,
            "Reset to Default",
            "Reset current settings to Default Settings values?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._load_profile("Default Settings")

    def set_advanced_mode(self, enabled):
        """Enable/disable advanced mode features."""
        self.advanced_mode = enabled

    def get_config(self):
        """Return current configuration."""
        return self._get_current_settings()
