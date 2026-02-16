"""
Module: targets_tab_v2.py
Purpose: A modern, dark-themed Target Management tab.
         Integrates with TargetsManager for persistence.
"""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtCore import Qt, QDateTime, pyqtSignal, QEvent
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialog,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QDialogButtonBox,
    QMessageBox,
    QCheckBox,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QToolButton,
    QInputDialog,
    QSizePolicy,
)

from utils.targets_manager import TargetsManager, Target
from z3950.session_manager import validate_connection


class TargetDialog(QDialog):
    """Dialog for adding/editing Z39.50 targets with dark theme support."""

    def __init__(self, parent=None, target: Target | None = None):
        super().__init__(parent)
        self.setWindowTitle("Add Target" if target is None else "Edit Target")
        self.target = target
        self.connection_status = None  # Store connection test result
        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self):
        layout = QVBoxLayout()
        form_layout = QFormLayout()

        self.name_edit = QLineEdit(self.target.name if self.target else "")
        self.host_edit = QLineEdit(self.target.host if self.target else "")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.target.port if self.target and self.target.port else 210)
        self.database_edit = QLineEdit(self.target.database if self.target else "")

        form_layout.addRow("Target Name:", self.name_edit)
        form_layout.addRow("Host Address:", self.host_edit)
        form_layout.addRow("Port:", self.port_spin)
        form_layout.addRow("Database Name:", self.database_edit)

        layout.addLayout(form_layout)

        self.btn_test = QPushButton("Test Connection")
        self.btn_test.clicked.connect(self.test_connection)
        layout.addWidget(self.btn_test)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.try_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def _apply_styles(self):
        self.setStyleSheet(
            """
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
            QSpinBox::up-button, QSpinBox::down-button {
                width: 20px;
                background-color: #313244;
                border: none;
                border-left: 1px solid #45475a;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background-color: #45475a;
            }
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
        """
        )

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
        
        self.connection_status = success  # Store the result

        if success:
            QMessageBox.information(self, "Success", f"Successfully connected to {host}:{port}")
        else:
            QMessageBox.critical(
                self,
                "Connection Failed",
                f"Could not connect to {host}:{port}.\nPlease check the details and try again.",
            )

    def try_accept(self):
        """Validate connection before accepting, with user override."""
        host = self.host_edit.text().strip()
        port = self.port_spin.value()

        if not self.name_edit.text().strip() or not host:
            QMessageBox.warning(self, "Validation Error", "Name and Host are required.")
            return

        self.setCursor(Qt.CursorShape.WaitCursor)
        success = validate_connection(host, port)
        self.unsetCursor()
        
        self.connection_status = success  # Store the result

        if success:
            self.accept()
        else:
            reply = QMessageBox.question(
                self,
                "Connection Failed",
                f"Could not connect to {host}:{port}.\n\nDo you want to save this target anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
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
        }
    
    def get_connection_status(self):
        """Return the connection test result (True/False/None)."""
        return self.connection_status



class RestoreDialog(QDialog):
    """Dialog to show edit/delete history and restore items."""

    def __init__(self, history, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Restore History")
        self.resize(500, 400)
        self.history = history
        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self):
        layout = QVBoxLayout()

        lbl = QLabel("Select an action to undo:")
        layout.addWidget(lbl)

        self.list_widget = QListWidget()
        for idx, item in enumerate(self.history):
            action = item["type"]
            target_name = item["snapshot"].name if item["snapshot"] else "Unknown"
            time_str = item["timestamp"].toString("HH:mm:ss")
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
        self.setStyleSheet(
            """
            QDialog { background-color: #1e1e2e; color: #cdd6f4; }
            QListWidget { background-color: #313244; color: #ffffff; border: 1px solid #45475a; border-radius: 4px; }
            QLabel { color: #cdd6f4; font-weight: bold; }
            QPushButton { background-color: #313244; color: white; border: 1px solid #45475a; padding: 6px 12px; border-radius: 4px; }
            QPushButton:hover { background-color: #45475a; }
        """
        )

    def get_selected_index(self):
        if len(self.list_widget.selectedItems()) > 0:
            return self.list_widget.selectedItems()[0].data(Qt.ItemDataRole.UserRole)
        return None


class TargetsTabV2(QWidget):
    """
    The main widget for configuring targets.
    """

    targets_changed = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.manager = TargetsManager()
        self.history = []
        self.server_status = {}  # Cache for server status checks
        self._setup_ui()
        self.refresh_targets(check_servers=True)  # Check servers only on initial load

    def set_advanced_mode(self, enabled):
        """No-op for compatibility with main window calls."""
        _ = enabled

    def eventFilter(self, obj, event):
        """Filter out wheel events on comboboxes to prevent accidental value changes."""
        if isinstance(obj, QComboBox) and event.type() == QEvent.Type.Wheel:
            return True  # Block the event
        return super().eventFilter(obj, event)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Target Management")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Info banner
        built_in_label = QLabel(
            "Built-in APIs: Library of Congress API, Harvard Library API, OpenLibrary API"
        )
        built_in_label.setWordWrap(True)
        built_in_label.setStyleSheet(
            "color: #a6adc8; background-color: #1e1e2e; border-left: 3px solid #89b4fa; "
            "padding: 10px; border-radius: 6px; font-size: 11px;"
        )
        layout.addWidget(built_in_label)

        # Action buttons row
        btn_layout = QHBoxLayout()

        self.btn_add = QPushButton("Add New Target")
        self.btn_add.setObjectName("PrimaryButton")
        self.btn_add.clicked.connect(self.add_target)

        self.btn_edit = QPushButton("Edit Selected")
        self.btn_edit.setObjectName("SecondaryButton")
        self.btn_edit.clicked.connect(self.edit_target)

        self.btn_remove = QPushButton("Remove Selected")
        self.btn_remove.setObjectName("DangerButton")
        self.btn_remove.clicked.connect(self.remove_target)

        self.btn_restore = QPushButton("Restore History")
        self.btn_restore.setObjectName("SecondaryButton")
        self.btn_restore.clicked.connect(self.show_restore_dialog)

        self.btn_check_servers = QPushButton("Check Servers")
        self.btn_check_servers.setObjectName("SecondaryButton")
        self.btn_check_servers.clicked.connect(self.check_all_servers)

        self.search_container = QWidget()
        self.search_container.setStyleSheet(
            """
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
            QToolButton {
                background-color: transparent;
                border: none;
                border-radius: 2px;
                color: #cdd6f4;
                font-weight: bold;
                font-size: 16px;
            }
            QToolButton:hover {
                background-color: #45475a;
                color: #ffffff;
            }
        """
        )
        search_layout = QHBoxLayout(self.search_container)
        search_layout.setContentsMargins(0, 0, 2, 0)
        search_layout.setSpacing(0)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search targets...")
        self.search_edit.textChanged.connect(self.filter_targets)

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
        btn_layout.addWidget(self.btn_remove)
        btn_layout.addWidget(self.btn_restore)
        btn_layout.addWidget(self.btn_check_servers)
        btn_layout.addStretch()
        btn_layout.addWidget(self.search_container)

        layout.addLayout(btn_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["Rank", "Active", "Target Name", "Host / IP", "Port", "Database", "Server"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 120)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 90)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(6, 100)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setAlternatingRowColors(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setStyleSheet(
            """
            QTableWidget {
                background-color: #1e1e2e;
                border: 2px solid #313244;
                border-radius: 8px;
                color: #cdd6f4;
                outline: none;
                selection-background-color: #89b4fa;
                selection-color: #11111b;
            }
            QTableWidget::item {
                padding: 12px 8px;
                border-bottom: 1px solid #313244;
                outline: none;
                border: none;
            }
            QTableWidget::item:hover {
                background-color: #313244;
            }
            QTableWidget::item:selected {
                background-color: #89b4fa;
                color: #11111b;
            }
            QTableWidget::item:selected:hover {
                background-color: #74c7ec;
                color: #11111b;
            }
            QHeaderView::section {
                background-color: #181825;
                color: #b4befe;
                padding: 12px;
                border: none;
                border-bottom: 2px solid #313244;
                font-weight: bold;
                text-transform: uppercase;
                font-size: 11px;
                letter-spacing: 0.5px;
            }
        """
        )

        self.table.itemDoubleClicked.connect(lambda _item: self.edit_target())

        layout.addWidget(self.table)

    def mousePressEvent(self, event):
        """Clear table selection when clicking outside the table."""
        if not self.table.geometry().contains(event.pos()):
            self.table.clearSelection()
        super().mousePressEvent(event)

    def _emit_targets_changed(self):
        self.targets_changed.emit(self.get_targets())

    def check_all_servers(self):
        """Manually check all server connections in parallel and update the display."""
        self.setCursor(Qt.CursorShape.WaitCursor)
        self.server_status.clear()
        targets = self.manager.get_all_targets()
        
        # Filter Z3950 targets only
        z3950_targets = [
            target for target in targets
            if not (target.target_type and "api" in target.target_type.lower())
        ]
        
        # Check all servers in parallel
        if z3950_targets:
            with ThreadPoolExecutor(max_workers=10) as executor:
                # Submit all checks
                future_to_target = {
                    executor.submit(validate_connection, target.host, target.port, 2, True): target
                    for target in z3950_targets
                }
                
                # Collect results as they complete
                for future in as_completed(future_to_target):
                    target = future_to_target[future]
                    try:
                        is_online = future.result()
                        self.server_status[target.target_id] = is_online
                    except Exception:
                        # If check fails, mark as offline
                        self.server_status[target.target_id] = False
        
        self.refresh_targets(check_servers=False)
        self.unsetCursor()

    def refresh_targets(self, check_servers=False):
        """Reload targets from the manager and display them.
        
        Args:
            check_servers (bool): If True, check server connection status.
        """
        self.table.clearContents()
        targets = self.manager.get_all_targets()
        self.table.setRowCount(len(targets))
        self.table.blockSignals(True)
        
        # Check servers if requested (parallel)
        if check_servers:
            z3950_targets = [
                target for target in targets
                if not (target.target_type and "api" in target.target_type.lower())
            ]
            
            if z3950_targets:
                with ThreadPoolExecutor(max_workers=10) as executor:
                    future_to_target = {
                        executor.submit(validate_connection, target.host, target.port, 2, True): target
                        for target in z3950_targets
                    }
                    
                    for future in as_completed(future_to_target):
                        target = future_to_target[future]
                        try:
                            is_online = future.result()
                            self.server_status[target.target_id] = is_online
                        except Exception:
                            self.server_status[target.target_id] = False

        for row, target in enumerate(targets):
            rank_combo = QComboBox()
            rank_combo.setFixedHeight(36)
            rank_combo.setStyleSheet("""
                QComboBox {
                    background-color: #313244;
                    border: 2px solid #45475a;
                    border-radius: 8px;
                    padding: 6px 30px 6px 16px;
                    color: #cdd6f4;
                    font-size: 14px;
                    font-weight: 600;
                }
                QComboBox:hover {
                    background-color: #3a3d4f;
                    border-color: #89b4fa;
                }
                QComboBox:focus {
                    border-color: #89b4fa;
                    background-color: #3a3d4f;
                }
                QComboBox::drop-down {
                    subcontrol-origin: padding;
                    subcontrol-position: right center;
                    width: 24px;
                    border: none;
                    border-top-right-radius: 8px;
                    border-bottom-right-radius: 8px;
                }
                QComboBox::drop-down:hover {
                    background-color: #45475a;
                }
                QComboBox::down-arrow {
                    width: 0;
                    height: 0;
                    border-left: 5px solid transparent;
                    border-right: 5px solid transparent;
                    border-top: 6px solid #cdd6f4;
                    margin-right: 6px;
                }
                QComboBox QAbstractItemView {
                    background-color: #313244;
                    color: #cdd6f4;
                    border: 2px solid #45475a;
                    border-radius: 8px;
                    padding: 4px;
                    selection-background-color: #89b4fa;
                    selection-color: #11111b;
                    outline: none;
                }
                QComboBox QAbstractItemView::item {
                    padding: 8px 12px;
                    border-radius: 4px;
                }
                QComboBox QAbstractItemView::item:hover {
                    background-color: #89b4fa;
                    color: #11111b;
                }
            """)
            for i in range(1, len(targets) + 1):
                rank_combo.addItem(str(i), i)
            # Set current rank using userData (robust)
            index = rank_combo.findData(target.rank)
            if index != -1:
                rank_combo.setCurrentIndex(index)
            else:
                # fallback: put it at the end
                rank_combo.setCurrentIndex(rank_combo.count() - 1)
            rank_combo.currentIndexChanged.connect(
                lambda _, t=target, c=rank_combo: self._on_rank_changed(c.currentData(), t)
            )
            rank_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            rank_combo.installEventFilter(self)

            self.table.setCellWidget(row, 0, rank_combo)

            # Active status indicator
            active_btn = QPushButton()
            active_btn.setFixedHeight(36)
            active_btn.setMinimumWidth(50)
            active_btn.setMaximumWidth(90)
            active_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            active_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            active_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if target.selected:
                active_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #a6da95;
                        border: 2px solid #8bd57e;
                        border-radius: 8px;
                        font-weight: bold;
                        font-size: 18px;
                        color: #1e1e2e;
                        text-align: center;
                        padding: 0px;
                    }
                    QPushButton:hover {
                        background-color: #8bd57e;
                        border-color: #6fb76a;
                    }
                    QPushButton:pressed {
                        background-color: #6fb76a;
                    }
                """)
                active_btn.setText("✓")
            else:
                active_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #ed8796;
                        border: 2px solid #d97082;
                        border-radius: 8px;
                        font-weight: bold;
                        font-size: 18px;
                        color: #1e1e2e;
                        text-align: center;
                        padding: 0px;
                    }
                    QPushButton:hover {
                        background-color: #d97082;
                        border-color: #c55d6e;
                    }
                    QPushButton:pressed {
                        background-color: #c55d6e;
                    }
                """)
                active_btn.setText("✕")
            active_btn.clicked.connect(lambda checked, t=target: self._toggle_target_active(t))
            
            self.table.setCellWidget(row, 1, active_btn)

            name_item = QTableWidgetItem(target.name)
            name_item.setData(Qt.ItemDataRole.UserRole, target)
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, name_item)

            host_item = QTableWidgetItem(target.host)
            host_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, host_item)

            port_str = str(target.port) if target.port else ""
            port_item = QTableWidgetItem(port_str)
            port_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, port_item)

            db_item = QTableWidgetItem(target.database)
            db_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 5, db_item)

            # Server status indicator
            server_btn = QPushButton()
            server_btn.setFixedHeight(36)
            server_btn.setMinimumWidth(60)
            server_btn.setMaximumWidth(100)
            server_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            server_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            server_btn.setEnabled(False)  # Not clickable, just status display
            
            # Check server status for Z3950 targets only
            if target.target_type and "api" in target.target_type.lower():
                # API targets don't need server check
                server_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #6c7086;
                        border: 2px solid #585b70;
                        border-radius: 8px;
                        font-weight: bold;
                        font-size: 11px;
                        color: #cdd6f4;
                        text-align: center;
                        padding: 0px;
                    }
                """)
                server_btn.setText("API")
            else:
                # Use cached server status
                is_online = self.server_status.get(target.target_id, None)
                if is_online is None:
                    # No cached status, show offline
                    server_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #ed8796;
                            border: 2px solid #d97082;
                            border-radius: 8px;
                            font-weight: bold;
                            font-size: 11px;
                            color: #1e1e2e;
                            text-align: center;
                            padding: 0px;
                        }
                    """)
                    server_btn.setText("OFFLINE")
                elif is_online:
                    server_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #a6da95;
                            border: 2px solid #8bd57e;
                            border-radius: 8px;
                            font-weight: bold;
                            font-size: 11px;
                            color: #1e1e2e;
                            text-align: center;
                            padding: 0px;
                        }
                    """)
                    server_btn.setText("ONLINE")
                else:
                    server_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #ed8796;
                            border: 2px solid #d97082;
                            border-radius: 8px;
                            font-weight: bold;
                            font-size: 11px;
                            color: #1e1e2e;
                            text-align: center;
                            padding: 0px;
                        }
                    """)
                    server_btn.setText("OFFLINE")
            
            self.table.setCellWidget(row, 6, server_btn)

        self.table.blockSignals(False)
        self._emit_targets_changed()

    def get_targets(self):
        """Return targets formatted for harvest target factory."""
        mapped_targets = []
        for t in self.manager.get_all_targets():
            target_type = (t.target_type or "").strip().lower()
            normalized = "z3950" if "z" in target_type else "api"
            mapped_targets.append(
                {
                    "target_id": t.target_id,
                    "name": t.name,
                    "type": normalized,
                    "host": t.host,
                    "port": t.port,
                    "database": t.database,
                    "record_syntax": t.record_syntax,
                    "rank": t.rank,
                    "selected": t.selected
                }
            )
        return mapped_targets

    def _on_rank_changed(self, new_rank, target):
        if not new_rank or new_rank == target.rank:
            return

        all_targets = sorted(
            self.manager.get_all_targets(),
            key=lambda t: t.rank
        )

        # remove target from list
        all_targets = [t for t in all_targets if t.target_id != target.target_id]

        # insert at new position
        new_index = max(0, min(new_rank - 1, len(all_targets)))
        all_targets.insert(new_index, target)

        # reassign clean ranks
        for i, t in enumerate(all_targets, start=1):
            t.rank = i
            self.manager.modify_target(t)

        self.refresh_targets()

    def add_target(self):
        dialog = TargetDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()

            all_targets = self.manager.get_all_targets()
            next_rank = len(all_targets) + 1

            new_target = Target(
                target_id="",
                name=data["name"],
                target_type="Z3950",
                host=data["host"],
                port=data["port"],
                database=data["database"],
                record_syntax="USMARC",
                rank=next_rank,
                selected=True,
            )
            self.manager.add_target(new_target)
            
            # Get the newly added target and store its connection status
            added_targets = self.manager.get_all_targets()
            added_target = next((t for t in added_targets if t.name == data["name"] and t.host == data["host"]), None)
            if added_target:
                connection_status = dialog.get_connection_status()
                if connection_status is not None:
                    self.server_status[added_target.target_id] = connection_status
            
            self.refresh_targets()

    def edit_target(self):
        target = self._get_selected_target()
        if not target:
            return

        if target.target_type == "API":
            QMessageBox.information(self, "Info", "Built-in API targets cannot be edited.")
            return

        dialog = TargetDialog(self, target)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._track_history("EDIT", target)
            data = dialog.get_data()

            target.name = data["name"]
            target.host = data["host"]
            target.port = data["port"]
            target.database = data["database"]

            self.manager.modify_target(target)
            
            # Update server status with the connection test result from dialog
            connection_status = dialog.get_connection_status()
            if connection_status is not None:
                self.server_status[target.target_id] = connection_status
            
            self.refresh_targets()

    def remove_target(self):
        target = self._get_selected_target()
        if target:
            self._remove_specific_target(target)

    def _remove_specific_target(self, target):
        """Remove a specific target object."""
        if target.target_type == "API":
            QMessageBox.warning(self, "Restricted", "Cannot remove built-in API targets.")
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to remove '{target.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if confirm == QMessageBox.StandardButton.Yes:
            typed, ok = QInputDialog.getText(
                self,
                "Type to Confirm",
                f"Type 'delete' to permanently remove '{target.name}':",
            )
            if not ok or typed.strip().lower() != "delete":
                QMessageBox.information(self, "Cancelled", "Deletion cancelled.")
                return

            self._track_history("DELETE", target)
            self.manager.delete_target(target.target_id)
            self.refresh_targets()

    def _toggle_target_active(self, target):
        """Toggle target active status from the table button."""
        target.selected = not target.selected
        self.manager.modify_target(target)
        self.refresh_targets()

    def _get_selected_target(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 2)  # Name column is now at index 2
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def filter_targets(self, text):
        """Filter rows based on search text (Target Name only)."""
        text = text.lower()
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 2)  # Name column is now at index 2
            name = name_item.text().lower() if name_item else ""
            visible = text in name
            self.table.setRowHidden(row, not visible)

    def _track_history(self, action_type, target):
        """Save a snapshot of the target state."""
        snapshot = deepcopy(target)
        self.history.append(
            {
                "type": action_type,
                "snapshot": snapshot,
                "timestamp": QDateTime.currentDateTime(),
            }
        )
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
                item = self.history.pop(idx)
                self._restore_item(item)

    def _restore_item(self, item):
        """Restore the target based on action type."""
        action = item["type"]
        snapshot = item["snapshot"]

        if action == "DELETE":
            all_targets = self.manager.get_all_targets()
            next_rank = max((t.rank for t in all_targets), default=0) + 1

            snapshot.rank = next_rank
            self.manager.add_target(snapshot)
            self.refresh_targets()
            QMessageBox.information(self, "Restored", f"Restored '{snapshot.name}' to end of list.")

        elif action == "EDIT":
            self.manager.modify_target(snapshot)
            self.refresh_targets()
            QMessageBox.information(self, "Restored", f"Reverted changes to '{snapshot.name}'.")


