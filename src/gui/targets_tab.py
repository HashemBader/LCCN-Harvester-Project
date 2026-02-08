"""
Module: targets_tab.py
Purpose: A modern, dark-themed Target Management tab.
         Integrates with TargetsManager for persistence.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialog, QFormLayout, QLineEdit, QSpinBox, 
    QDialogButtonBox, QMessageBox, QCheckBox, QComboBox, QWidget,
    QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, QDateTime
from copy import deepcopy
from PyQt6.QtGui import QIcon

from utils.targets_manager import TargetsManager, Target
from z3950.session_manager import validate_connection

class TargetDialog(QDialog):
    """Dialog for adding/editing Z39.50 targets with dark theme support."""

    def __init__(self, parent=None, target: Target = None):
        super().__init__(parent)
        self.setWindowTitle("Add Target" if target is None else "Edit Target")
        self.target = target
        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self):
        layout = QVBoxLayout()
        form_layout = QFormLayout()

        # Target fields
        self.name_edit = QLineEdit(self.target.name if self.target else "")
        self.host_edit = QLineEdit(self.target.host if self.target else "")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.target.port if self.target and self.target.port else 210)
        self.database_edit = QLineEdit(self.target.database if self.target else "")
        self.username_edit = QLineEdit(self.target.username if self.target else "")
        self.password_edit = QLineEdit(self.target.password if self.target else "")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        
        form_layout.addRow("Target Name:", self.name_edit)
        form_layout.addRow("Host Address:", self.host_edit)
        form_layout.addRow("Port:", self.port_spin)
        form_layout.addRow("Database Name:", self.database_edit)
        form_layout.addRow("Username (if needed):", self.username_edit)
        form_layout.addRow("Password (if needed):", self.password_edit)

        layout.addLayout(form_layout)

        # Test Connection Button
        self.btn_test = QPushButton("Test Connection")
        self.btn_test.clicked.connect(self.test_connection)
        layout.addWidget(self.btn_test)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.try_accept) # Intercept OK to validate
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def _apply_styles(self):
        # Basic dark theme for the dialog
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
            QLabel {
                color: #cdd6f4;
                font-weight: bold;
            }
            QLineEdit, QSpinBox {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 6px;
                color: #ffffff;
            }
            /* Explicitly style spinbox buttons to fix hit-testing */
            QSpinBox::up-button, QSpinBox::down-button {
                width: 20px;
                background-color: #313244;
                border: none;
                border-left: 1px solid #45475a;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background-color: #45475a;
            }
            /* Use SVG icons for arrows */
            QSpinBox::up-arrow {
                width: 12px; 
                height: 12px;
                image: url(src/gui/icons/plus.svg);
                border: none;
            }
            QSpinBox::down-arrow {
                width: 12px; 
                height: 12px;
                image: url(src/gui/icons/minus.svg);
                border: none;
            }
            QLineEdit:focus, QSpinBox:focus {
                border: 1px solid #89b4fa;
            }
            QPushButton {
                background-color: #313244;
                color: white;
                border: 1px solid #45475a;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
        """)

    def test_connection(self):
        """Manually test connection and show result."""
        host = self.host_edit.text().strip()
        port = self.port_spin.value()

        if not host:
            QMessageBox.warning(self, "Input Error", "Please enter a host to test.")
            return

        self.setCursor(Qt.CursorShape.WaitCursor)
        success = validate_connection(host, port)
        self.unsetCursor()

        if success:
            QMessageBox.information(self, "Success", f"Successfully connected to {host}:{port}")
        else:
            QMessageBox.critical(self, "Connection Failed", f"Could not connect to {host}:{port}.\nPlease check the details and try again.")

    def try_accept(self):
        """Validate connection before accepting, with user override."""
        host = self.host_edit.text().strip()
        port = self.port_spin.value()
        
        # Basic Input Validation
        if not self.name_edit.text().strip() or not host:
             QMessageBox.warning(self, "Validation Error", "Name and Host are required.")
             return

        # Connectivity Validation
        self.setCursor(Qt.CursorShape.WaitCursor)
        success = validate_connection(host, port)
        self.unsetCursor()

        if success:
            self.accept()
        else:
            reply = QMessageBox.question(
                self, 
                "Connection Failed", 
                f"Could not connect to {host}:{port}.\n\nDo you want to save this target anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.accept()


    def get_data(self):
        """Return a dictionary of the input data."""
        return {
            "name": self.name_edit.text().strip(),
            "host": self.host_edit.text().strip(),
            "port": self.port_spin.value(),
            "database": self.database_edit.text().strip(),
            "username": self.username_edit.text().strip(),
            "password": self.password_edit.text().strip()
        }


class RestoreDialog(QDialog):
    """Dialog to show edit/delete history and restore items."""
    def __init__(self, history, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Restore History")
        self.resize(500, 400)
        self.history = history
        self.selected_action = None
        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self):
        layout = QVBoxLayout()
        
        lbl = QLabel("Select an action to undo:")
        layout.addWidget(lbl)

        self.list_widget = QListWidget()
        for idx, item in enumerate(self.history):
            action = item['type']
            target_name = item['snapshot'].name if item['snapshot'] else "Unknown"
            time_str = item['timestamp'].toString("HH:mm:ss")
            text = f"[{time_str}] {action}: {target_name}"
            
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.ItemDataRole.UserRole, idx)
            self.list_widget.addItem(list_item)
            
        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Restore")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; color: #cdd6f4; }
            QListWidget { background-color: #313244; color: #ffffff; border: 1px solid #45475a; border-radius: 4px; }
            QLabel { color: #cdd6f4; font-weight: bold; }
            QPushButton { background-color: #313244; color: white; border: 1px solid #45475a; padding: 6px 12px; border-radius: 4px; }
            QPushButton:hover { background-color: #45475a; }
        """)

    def get_selected_index(self):
        if len(self.list_widget.selectedItems()) > 0:
            return self.list_widget.selectedItems()[0].data(Qt.ItemDataRole.UserRole)
        return None


class TargetsTab(QWidget):
    """
    The main widget to specific configuration of targets.
    Replaces the static table in the settings tab.
    """
    def __init__(self):
        super().__init__()
        self.manager = TargetsManager()
        self.history = [] # List of {type, snapshot, timestamp}
        self._setup_ui()
        self.refresh_targets()

    def set_advanced_mode(self, enabled):
        """No-op for compatibility with main window calls."""
        pass

    def _setup_ui(self):
        layout = QVBoxLayout()
        # layout.setContentsMargins(0, 0, 0, 0) # Seamless integration

        # Title / Header
        group_box = QGroupBox("Z39.50 Targets")
        group_layout = QVBoxLayout()

        # Toolbar
        btn_layout = QHBoxLayout()
        
        self.btn_add = QPushButton("Add New Target")
        self.btn_add.setObjectName("PrimaryButton")
        self.btn_add.clicked.connect(self.add_target)
        
        self.btn_edit = QPushButton("Edit Selected")
        self.btn_edit.clicked.connect(self.edit_target)

        self.btn_remove = QPushButton("Remove Selected")
        self.btn_remove.setObjectName("DangerButton")
        self.btn_remove.clicked.connect(self.remove_target)
        
        self.btn_toggle = QPushButton("Toggle Active")
        self.btn_toggle.clicked.connect(self.toggle_target)

        # Restore Button
        self.btn_restore = QPushButton("Restore History")
        self.btn_restore.clicked.connect(self.show_restore_dialog)

        # Search Container (Simulates a single input with clear button)
        self.search_container = QWidget()
        self.search_container.setStyleSheet("""
            QWidget {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 4px;
            }
            QLineEdit {
                background-color: transparent;
                border: none;
                color: #cdd6f4;
                padding: 4px 8px;
                min-width: 180px;
            }
            /* Hover effect for the clear button */
            QToolButton {
                background-color: transparent;
                border: none;
                border-radius: 2px;
                color: #cdd6f4; /* Text color for 'X' */
                font-weight: bold;
                font-size: 16px;
            }
            QToolButton:hover {
                background-color: #45475a; 
                color: #ffffff;
            }
        """)
        search_layout = QHBoxLayout(self.search_container)
        search_layout.setContentsMargins(0, 0, 2, 0)
        search_layout.setSpacing(0)
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search targets...")
        self.search_edit.textChanged.connect(self.filter_targets)
        
        # Change QPushButton to QToolButton style in stylesheet for consistency
        # Actually, let's just make it a QToolButton
        from PyQt6.QtWidgets import QToolButton
        self.search_clear_btn = QToolButton()
        self.search_clear_btn.setText("×")
        self.search_clear_btn.setFixedSize(28, 28)
        self.search_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_clear_btn.setToolTip("Clear search")
        self.search_clear_btn.hide()
        self.search_clear_btn.clicked.connect(lambda: self.search_edit.clear())
        self.search_edit.textChanged.connect(lambda t: self.search_clear_btn.setVisible(bool(t)))

        search_layout.addWidget(self.search_edit)
        search_layout.addWidget(self.search_clear_btn)

        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_toggle)
        btn_layout.addWidget(self.btn_restore) # Add restore button
        btn_layout.addStretch() # Pushes everything after this to the right
        btn_layout.addWidget(self.search_container) # Add search container at end

        group_layout.addLayout(btn_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["Enabled", "Rank", "Target Name", "Host / IP", "Port", "Database", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed) # Enabled
        self.table.setColumnWidth(0, 70)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed) # Rank
        self.table.setColumnWidth(1, 80)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents) # Port column small
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed) # Actions
        self.table.setColumnWidth(6, 100)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        
        # Style the header to be bold
        self.table.horizontalHeader().setStyleSheet("font-weight: bold;")

        # Double click to edit
        self.table.itemDoubleClicked.connect(self.edit_target)

        group_layout.addWidget(self.table)
        
        group_box.setLayout(group_layout)
        layout.addWidget(group_box)
        self.setLayout(layout)

    def refresh_targets(self):
        """Reload targets from the manager and display them."""
        self.table.clearContents()
        targets = self.manager.get_all_targets()
        self.table.setRowCount(len(targets))
        
        # Block signals during refresh to avoid recursive loops
        self.table.blockSignals(True)

        for row, target in enumerate(targets):
            # Store target object in a hidden item (e.g. name column) for retrieval
            # We can't store it in column 0 easily if it's a widget, so we use column 2 (Name)
            
            # 1. Enabled (Checkbox)
            # Create a container widget to center the checkbox
            container = QWidget()
            chk_layout = QHBoxLayout(container)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            chk = QCheckBox()
            chk.setChecked(target.selected)
            # Style it to be green when checked if desired, but default is standard check
            chk.setStyleSheet("""
                QCheckBox::indicator { width: 18px; height: 18px; }
                QCheckBox::indicator:checked {
                    background-color: #a6e3a1; /* Green */
                    border: 1px solid #a6e3a1;
                    image: url(none);
                }
                QCheckBox::indicator:unchecked {
                    background-color: #f38ba8; /* Red */
                    border: 1px solid #f38ba8;
                    image: url(none);
                }
            """)
            # Connect
            chk.toggled.connect(lambda checked, t=target: self._on_enabled_toggled(checked, t))
            
            chk_layout.addWidget(chk)
            self.table.setCellWidget(row, 0, container)

            # 2. Rank (ComboBox)
            rank_combo = QComboBox()
            # Populate with 1..N
            for i in range(1, len(targets) + 1):
                rank_combo.addItem(str(i), i)
            
            rank_combo.setCurrentText(str(target.rank if target.rank > 0 else 999))
            rank_combo.currentTextChanged.connect(lambda text, t=target: self._on_rank_changed(text, t))
            
            # Container to center the combobox
            rank_container = QWidget()
            rank_layout = QHBoxLayout(rank_container)
            rank_layout.setContentsMargins(0, 0, 0, 0)
            rank_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rank_layout.addWidget(rank_combo)
            
            self.table.setCellWidget(row, 1, rank_container)

            # 3. Name
            name_item = QTableWidgetItem(target.name)
            name_item.setData(Qt.ItemDataRole.UserRole, target) # Store data here
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, name_item)

            # 4. Host
            host_item = QTableWidgetItem(target.host)
            host_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, host_item)
            
            # 5. Port
            port_str = str(target.port) if target.port else ""
            port_item = QTableWidgetItem(port_str)
            port_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, port_item)

            # 6. Database
            db_item = QTableWidgetItem(target.database)
            db_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 5, db_item)

            # 7. Remove Button
            if target.target_type != "API":
                btn_remove = QPushButton("Remove")
                btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_remove.setStyleSheet("""
                    QPushButton {
                        background-color: #f38ba8;
                        color: #1e1e2e;
                        border: none;
                        border-radius: 4px;
                        padding: 4px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #e78284;
                    }
                """)
                btn_remove.clicked.connect(lambda _, t=target: self._remove_specific_target(t))
                
                # Container to center the button
                btn_container = QWidget()
                btn_layout = QHBoxLayout(btn_container)
                btn_layout.setContentsMargins(4, 2, 4, 2)
                btn_layout.addWidget(btn_remove)
                self.table.setCellWidget(row, 6, btn_container)
            
        self.table.blockSignals(False)
    
    def _on_enabled_toggled(self, checked, target):
        target.selected = checked
        self.manager.modify_target(target)
        
    def _on_rank_changed(self, text, target):
        if not text: return
        try:
            new_rank = int(text)
            if new_rank == target.rank: return
            
            # Find the target currently holding this new rank
            all_targets = self.manager.get_all_targets()
            other_target = next((t for t in all_targets if t.rank == new_rank), None)
            
            # Perform the swap
            if other_target and other_target.target_id != target.target_id:
                other_target.rank = target.rank # Move other target to current target's old rank
                self.manager.modify_target(other_target) # Save other first
            
            target.rank = new_rank
            self.manager.modify_target(target)
            
            self.refresh_targets() # Refresh to re-order rows and update dropdowns
            
        except ValueError:
            pass

    def add_target(self):
        dialog = TargetDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            
            # Calculate next rank
            all_targets = self.manager.get_all_targets()
            next_rank = 1
            if all_targets:
                next_rank = max(t.rank for t in all_targets) + 1

            new_target = Target(
                target_id="", # Auto-assign
                name=data["name"],
                target_type="Z3950",
                host=data["host"],
                port=data["port"],
                database=data["database"],
                username=data.get("username", ""),
                password=data.get("password", ""),
                record_syntax="USMARC", # Default
                rank=next_rank, # Append to end with next available rank
                selected=True
            )
            self.manager.add_target(new_target)
            self.refresh_targets()

    def edit_target(self):
        target = self._get_selected_target()
        if not target: return

        if target.target_type == "API":
             QMessageBox.information(self, "Info", "Built-in API targets cannot be edited.")
             return

        dialog = TargetDialog(self, target)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Track history before modification
            self._track_history("EDIT", target)
            
            data = dialog.get_data()

            # Update target object
            target.name = data["name"]
            target.host = data["host"]
            target.port = data["port"]
            target.port = data["port"]
            target.database = data["database"]
            target.username = data.get("username", "")
            target.password = data.get("password", "")
            
            self.manager.modify_target(target)
            self.refresh_targets()

    def remove_target(self):
        # Legacy toolbar method - keep or redirect?
        # Redirect to currently selected row if any
        target = self._get_selected_target()
        if target:
            self._remove_specific_target(target)

    def _remove_specific_target(self, target):
        """Remove a specific target object."""
        if target.target_type == "API":
             QMessageBox.warning(self, "Restricted", "Cannot remove built-in API targets.")
             return

        confirm = QMessageBox.question(
            self, "Confirm Delete", 
            f"Are you sure you want to remove '{target.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if confirm == QMessageBox.StandardButton.Yes:
            # Track history before delete
            self._track_history("DELETE", target)
            self.manager.delete_target(target.target_id)
            self.refresh_targets()

    def toggle_target(self):
        target = self._get_selected_target()
        if not target: return

        target.selected = not target.selected
        self.manager.modify_target(target)
        self.refresh_targets()

    def _get_selected_target(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        # Data is stored in the "Name" column (Index 2) now
        item = self.table.item(row, 2)
        if item:
             return item.data(Qt.ItemDataRole.UserRole)
        return None

    def filter_targets(self, text):
        """Filter rows based on search text (Target Name only)."""
        text = text.lower()
        for row in range(self.table.rowCount()):
            # Check Name (2) only
            name_item = self.table.item(row, 2)
            name = name_item.text().lower() if name_item else ""
            
            visible = (text in name)
            self.table.setRowHidden(row, not visible)

    def _track_history(self, action_type, target):
        """Save a snapshot of the target state."""
        snapshot = deepcopy(target)
        self.history.append({
            'type': action_type,
            'snapshot': snapshot,
            'timestamp': QDateTime.currentDateTime()
        })
        # Optional: Limit history size
        if len(self.history) > 50:
            self.history.pop(0)

    def show_restore_dialog(self):
        """Show the restore history dialog."""
        if not self.history:
             QMessageBox.information(self, "History", "No actions to restore in this session.")
             return

        dialog = RestoreDialog(self.history, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            idx = dialog.get_selected_index()
            if idx is not None:
                item = self.history.pop(idx) # Remove from history once restored
                self._restore_item(item)

    def _restore_item(self, item):
        """Restore the target based on action type."""
        action = item['type']
        snapshot = item['snapshot']
        
        if action == "DELETE":
            # Re-add the target to the end of the list with a new rank.
            all_targets = self.manager.get_all_targets()
            next_rank = 1
            if all_targets:
                next_rank = max(t.rank for t in all_targets) + 1
            
            snapshot.rank = next_rank
            
            # Note: We might want to clear the ID to let add_target generate a new one 
            # if we truly want it to be 'new', but keeping ID preserves identity if needed.
            # However, if we deleted it, the ID is free. 
            # Let's keep ID to respect 'restore', but rank moves to end as requested.
            
            self.manager.add_target(snapshot)
            self.refresh_targets()
            QMessageBox.information(self, "Restored", f"Restored '{snapshot.name}' to end of list.")
            
        elif action == "EDIT":
            # Revert modifications
            self.manager.modify_target(snapshot)
            self.refresh_targets()
            QMessageBox.information(self, "Restored", f"Reverted changes to '{snapshot.name}'.")
