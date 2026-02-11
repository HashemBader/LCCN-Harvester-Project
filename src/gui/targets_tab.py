"""
Module: targets_tab.py
Target management tab for APIs and Z39.50 servers.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QListWidget, QListWidgetItem,
    QDialog, QFormLayout, QLineEdit, QSpinBox, QDialogButtonBox,
    QMessageBox, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from pathlib import Path
import json


class TargetDialog(QDialog):
    """Dialog for adding/editing Z39.50 targets."""

    def __init__(self, parent=None, target_data=None):
        super().__init__(parent)
        self.setWindowTitle("Add Z39.50 Target" if target_data is None else "Edit Z39.50 Target")
        self.target_data = target_data or {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        form_layout = QFormLayout()

        # Target fields
        self.name_edit = QLineEdit(self.target_data.get("name", ""))
        self.host_edit = QLineEdit(self.target_data.get("host", ""))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.target_data.get("port", 210))
        self.database_edit = QLineEdit(self.target_data.get("database", ""))

        form_layout.addRow("Name:", self.name_edit)
        form_layout.addRow("Host:", self.host_edit)
        form_layout.addRow("Port:", self.port_spin)
        form_layout.addRow("Database:", self.database_edit)

        layout.addLayout(form_layout)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def get_target_data(self):
        """Return the target data from the dialog."""
        return {
            "name": self.name_edit.text().strip(),
            "host": self.host_edit.text().strip(),
            "port": self.port_spin.value(),
            "database": self.database_edit.text().strip(),
            "type": "z3950",
            "selected": True,
            "rank": 0
        }


class TargetsTab(QWidget):
    targets_changed = pyqtSignal(list)  # Emits list of targets when changed

    def __init__(self):
        super().__init__()
        self.targets_file = Path("data/targets.json")
        self.targets = []
        self._setup_ui()
        self._load_targets()

    def _setup_ui(self):
        layout = QVBoxLayout()

        # Title
        title_label = QLabel("Target Management")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title_label)

        # Instructions
        instructions = QLabel(
            "Manage source order and selection. Targets are checked from top to bottom until a match is found."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # API Targets (read-only)
        api_group = QGroupBox("Built-in API Targets (Non-Z39.50)")
        api_layout = QVBoxLayout()

        api_note = QLabel("Enable/disable APIs here, then use priority controls below to set lookup order.")
        api_note.setWordWrap(False)
        api_note.setMinimumHeight(22)
        api_note.setStyleSheet("color: #a7a59b; font-size: 12px;")
        api_layout.addWidget(api_note)

        self.api_checkboxes: dict[str, QCheckBox] = {}
        self._api_name_map = {
            "Library of Congress": {"Library of Congress"},
            "Harvard": {"Harvard", "Harvard LibraryCloud"},
            "OpenLibrary": {"OpenLibrary"},
        }

        for api_name in self._api_name_map:
            checkbox = QCheckBox(api_name)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(
                lambda state, name=api_name: self._toggle_api_checkbox(name, state)
            )
            self.api_checkboxes[api_name] = checkbox
            api_layout.addWidget(checkbox)

        self.api_status_label = QLabel("Enabled APIs: 3/3")
        self.api_status_label.setStyleSheet(
            "font-size: 11px; color: #a7a59b; "
            "padding: 6px 10px; border: 1px solid #2d2e2b; border-radius: 6px; background: #1f201d;"
        )
        api_layout.addWidget(self.api_status_label)

        api_group.setLayout(api_layout)
        layout.addWidget(api_group)

        # Z39.50 Targets
        z3950_group = QGroupBox("Z39.50 Targets")
        z3950_layout = QVBoxLayout()

        # Target list
        self.target_list = QListWidget()
        self.target_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.target_list.itemDoubleClicked.connect(self._edit_target)
        z3950_layout.addWidget(self.target_list)

        # Target management buttons
        button_layout = QHBoxLayout()

        self.add_button = QPushButton("Add Target")
        self.add_button.clicked.connect(self._add_target)

        self.edit_button = QPushButton("Edit")
        self.edit_button.clicked.connect(self._edit_target)

        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(self._remove_target)

        self.toggle_button = QPushButton("Toggle Selected")
        self.toggle_button.clicked.connect(self._toggle_target)

        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.edit_button)
        button_layout.addWidget(self.remove_button)
        button_layout.addWidget(self.toggle_button)
        button_layout.addStretch()

        z3950_layout.addLayout(button_layout)
        z3950_group.setLayout(z3950_layout)
        layout.addWidget(z3950_group)

        # Ranking controls
        rank_group = QGroupBox("Target Priority")
        rank_layout = QHBoxLayout()

        self.move_up_button = QPushButton("Move Up")
        self.move_up_button.clicked.connect(self._move_target_up)

        self.move_down_button = QPushButton("Move Down")
        self.move_down_button.clicked.connect(self._move_target_down)

        rank_note = QLabel("Higher targets are checked first")
        rank_note.setStyleSheet("font-style: italic; color: gray;")

        rank_layout.addWidget(self.move_up_button)
        rank_layout.addWidget(self.move_down_button)
        rank_layout.addWidget(rank_note)
        rank_layout.addStretch()

        rank_group.setLayout(rank_layout)
        layout.addWidget(rank_group)

        # Info label
        info_layout = QHBoxLayout()
        info_label = QLabel("💡 Changes are automatically saved")
        info_label.setStyleSheet("font-style: italic; color: #666666; font-size: 11px;")
        info_layout.addWidget(info_label)
        info_layout.addStretch()
        layout.addLayout(info_layout)

        layout.addStretch()
        self.setLayout(layout)
        self.advanced_mode = False

    def set_advanced_mode(self, enabled):
        """Enable/disable advanced mode features."""
        self.advanced_mode = enabled
        # Targets tab features are always visible for now

    def _load_default_targets(self):
        """Load default API targets."""
        return [
            {"name": "Library of Congress", "type": "api", "selected": True, "rank": 1},
            {"name": "Harvard", "type": "api", "selected": True, "rank": 2},
            {"name": "OpenLibrary", "type": "api", "selected": True, "rank": 3}
        ]

    def _load_targets(self):
        """Load targets from file or create defaults."""
        try:
            if self.targets_file.exists():
                with open(self.targets_file, 'r') as f:
                    self.targets = json.load(f)
            else:
                self.targets = self._load_default_targets()
                self._save_targets()
        except Exception as e:
            QMessageBox.warning(
                self,
                "Warning",
                f"Failed to load targets: {str(e)}\nUsing defaults."
            )
            self.targets = self._load_default_targets()

        self._sync_api_checkboxes()
        self._refresh_target_list()

    def _refresh_target_list(self):
        """Refresh the target list display."""
        self._sync_api_checkboxes()
        self.target_list.clear()

        # Sort by rank
        sorted_targets = sorted(self.targets, key=lambda x: x.get("rank", 999))

        for target in sorted_targets:
            name = target.get("name", "Unknown")
            target_type = target.get("type", "unknown")
            selected = target.get("selected", True)

            # Format display text
            status = "✓" if selected else "✗"
            if target_type == "z3950":
                host = target.get("host", "")
                display_text = f"{status} {name} ({host}) [Z39.50]"
            else:
                display_text = f"{status} {name} [API]"

            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, target)

            # Gray out if not selected
            if not selected:
                item.setForeground(Qt.GlobalColor.gray)

            self.target_list.addItem(item)

        self._update_api_status_label()

    def _add_target(self):
        """Add a new Z39.50 target."""
        dialog = TargetDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            target_data = dialog.get_target_data()

            if not target_data["name"] or not target_data["host"]:
                QMessageBox.warning(
                    self,
                    "Invalid Input",
                    "Name and Host are required fields."
                )
                return

            # Set rank to be after existing targets
            target_data["rank"] = len(self.targets) + 1
            self.targets.append(target_data)
            self._refresh_target_list()

            # Auto-save the changes
            self._auto_save_targets()

    def _edit_target(self):
        """Edit selected target."""
        current_item = self.target_list.currentItem()
        if not current_item:
            return

        target = current_item.data(Qt.ItemDataRole.UserRole)

        if target.get("type") == "api":
            QMessageBox.information(
                self,
                "Cannot Edit",
                "Built-in API targets cannot be edited. You can only change their rank and selection status."
            )
            return

        dialog = TargetDialog(self, target)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated_data = dialog.get_target_data()
            updated_data["rank"] = target["rank"]  # Preserve rank
            updated_data["selected"] = target["selected"]  # Preserve selection

            # Update in list
            idx = self.targets.index(target)
            self.targets[idx] = updated_data
            self._refresh_target_list()

            # Auto-save the changes
            self._auto_save_targets()

    def _remove_target(self):
        """Remove selected target."""
        current_item = self.target_list.currentItem()
        if not current_item:
            return

        target = current_item.data(Qt.ItemDataRole.UserRole)

        if target.get("type") == "api":
            QMessageBox.warning(
                self,
                "Cannot Remove",
                "Built-in API targets cannot be removed."
            )
            return

        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Remove target '{target.get('name')}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.targets.remove(target)
            self._refresh_target_list()

            # Auto-save the changes
            self._auto_save_targets()

    def _toggle_target(self):
        """Toggle selection status of target."""
        current_item = self.target_list.currentItem()
        if not current_item:
            return

        target = current_item.data(Qt.ItemDataRole.UserRole)
        target["selected"] = not target.get("selected", True)
        self._refresh_target_list()

        # Auto-save the changes
        self._auto_save_targets()

    def _toggle_api_checkbox(self, api_name: str, state: int):
        """Toggle selected state for a built-in API from checkbox."""
        enabled = state == Qt.CheckState.Checked.value
        valid_names = self._api_name_map.get(api_name, {api_name})

        for target in self.targets:
            if target.get("name") in valid_names and target.get("type", "api") == "api":
                target["selected"] = enabled
                break

        self._refresh_target_list()
        self._auto_save_targets()

    def _move_target_up(self):
        """Move target up in priority."""
        current_row = self.target_list.currentRow()
        if current_row <= 0:
            return

        # Get sorted targets (same as displayed)
        sorted_targets = sorted(self.targets, key=lambda x: x.get("rank", 999))

        # Swap the two targets in the sorted list
        sorted_targets[current_row], sorted_targets[current_row - 1] = \
            sorted_targets[current_row - 1], sorted_targets[current_row]

        # Reassign ranks based on new order
        for idx, target in enumerate(sorted_targets):
            target["rank"] = idx + 1

        self._refresh_target_list()
        self.target_list.setCurrentRow(current_row - 1)

        # Auto-save the changes
        self._auto_save_targets()

    def _move_target_down(self):
        """Move target down in priority."""
        current_row = self.target_list.currentRow()
        if current_row < 0 or current_row >= self.target_list.count() - 1:
            return

        # Get sorted targets (same as displayed)
        sorted_targets = sorted(self.targets, key=lambda x: x.get("rank", 999))

        # Swap the two targets in the sorted list
        sorted_targets[current_row], sorted_targets[current_row + 1] = \
            sorted_targets[current_row + 1], sorted_targets[current_row]

        # Reassign ranks based on new order
        for idx, target in enumerate(sorted_targets):
            target["rank"] = idx + 1

        self._refresh_target_list()
        self.target_list.setCurrentRow(current_row + 1)

        # Auto-save the changes
        self._auto_save_targets()

    def _auto_save_targets(self):
        """Auto-save targets to file (without showing success message)."""
        try:
            self.targets_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.targets_file, 'w') as f:
                json.dump(self.targets, f, indent=2)

            self.targets_changed.emit(self.targets)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to auto-save targets: {str(e)}"
            )

    def _save_targets(self):
        """Save targets to file with confirmation message."""
        try:
            self.targets_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.targets_file, 'w') as f:
                json.dump(self.targets, f, indent=2)

            self.targets_changed.emit(self.targets)
            QMessageBox.information(
                self,
                "Success",
                "Target configuration saved successfully."
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save targets: {str(e)}"
            )

    def get_targets(self):
        """Return list of targets."""
        return self.targets

    def _sync_api_checkboxes(self):
        """Sync checkbox states from current target config."""
        enabled_count = 0
        for label, valid_names in self._api_name_map.items():
            selected = True
            for target in self.targets:
                if target.get("name") in valid_names and target.get("type", "api") == "api":
                    selected = target.get("selected", True)
                    break
            checkbox = self.api_checkboxes.get(label)
            if checkbox is not None:
                checkbox.blockSignals(True)
                checkbox.setChecked(selected)
                checkbox.blockSignals(False)
            if selected:
                enabled_count += 1
        self.api_status_label.setText(f"Enabled APIs: {enabled_count}/{len(self.api_checkboxes)}")

    def _update_api_status_label(self):
        enabled_count = 0
        for checkbox in self.api_checkboxes.values():
            if checkbox.isChecked():
                enabled_count += 1
        self.api_status_label.setText(f"Enabled APIs: {enabled_count}/{len(self.api_checkboxes)}")
