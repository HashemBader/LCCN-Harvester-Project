"""
Module: mock_targets_tab.py
Purpose: A modern, dark-themed Target Management tab for the Mock GUI.
         Integrates with TargetsManager for persistence.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialog, QFormLayout, QLineEdit, QSpinBox, 
    QDialogButtonBox, QMessageBox, QCheckBox, QComboBox, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from utils.targets_manager import TargetsManager, Target
from z3950.session_manager import validate_connection

class MockTargetDialog(QDialog):
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
        
        form_layout.addRow("Library Name:", self.name_edit)
        form_layout.addRow("Host Address:", self.host_edit)
        form_layout.addRow("Port:", self.port_spin)
        form_layout.addRow("Database Name:", self.database_edit)

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
            "database": self.database_edit.text().strip()
        }


class MockTargetsTab(QWidget):
    """
    The main widget to specific configuration of targets.
    Replaces the static table in the settings tab.
    """
    def __init__(self):
        super().__init__()
        self.manager = TargetsManager()
        self._setup_ui()
        self.refresh_targets()

    def _setup_ui(self):
        layout = QVBoxLayout()
        # layout.setContentsMargins(0, 0, 0, 0) # Seamless integration

        # Title / Header
        group_box = QGroupBox("Z39.50 Search Targets")
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

        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_toggle)
        btn_layout.addWidget(self.btn_remove)
        btn_layout.addStretch()

        group_layout.addLayout(btn_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Enabled", "Rank", "Library Name", "Host / IP", "Port", "Database"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed) # Enabled
        self.table.setColumnWidth(0, 70)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed) # Rank
        self.table.setColumnWidth(1, 80)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents) # Port column small
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
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
            
            self.table.setCellWidget(row, 1, rank_combo)

            # 3. Name
            name_item = QTableWidgetItem(target.name)
            name_item.setData(Qt.ItemDataRole.UserRole, target) # Store data here
            self.table.setItem(row, 2, name_item)

            # 4. Host
            self.table.setItem(row, 3, QTableWidgetItem(target.host))
            
            # 5. Port
            port_str = str(target.port) if target.port else ""
            self.table.setItem(row, 4, QTableWidgetItem(port_str))

            # 6. Database
            self.table.setItem(row, 5, QTableWidgetItem(target.database))
            
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
        dialog = MockTargetDialog(self)
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

        dialog = MockTargetDialog(self, target)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()

            # Update target object
            target.name = data["name"]
            target.host = data["host"]
            target.port = data["port"]
            target.database = data["database"]
            
            self.manager.modify_target(target)
            self.refresh_targets()

    def remove_target(self):
        target = self._get_selected_target()
        if not target: return

        if target.target_type == "API":
             QMessageBox.warning(self, "Restricted", "Cannot remove built-in API targets.")
             return

        confirm = QMessageBox.question(
            self, "Confirm Delete", 
            f"Are you sure you want to remove '{target.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if confirm == QMessageBox.StandardButton.Yes:
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
