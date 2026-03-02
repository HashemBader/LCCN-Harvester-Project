"""
Module: targets_tab_v2.py
Purpose: A modern, dark-themed Target Management tab.
         Integrates with TargetsManager for persistence.
"""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys
import urllib.request

# Add src to path for utils/z3950 imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtCore import Qt, QDateTime, pyqtSignal, QEvent, QSize
from PyQt6.QtGui import QIcon
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
    QScrollArea,
    QFrame,
)

from utils.targets_manager import TargetsManager, Target
from config.profile_manager import ProfileManager
from z3950.session_manager import validate_connection


class TargetDialog(QDialog):
    """Dialog for adding/editing Z39.50 targets with dark theme support."""

    def __init__(self, parent=None, target: Target | None = None, total_targets: int = 1):
        super().__init__(parent)
        self.setWindowTitle("Add Target" if target is None else "Edit Target")
        self.target = target
        self.total_targets = total_targets
        self.connection_status = None  # Store connection test result
        self.remove_requested = False
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

        # Rank selector — range grows to include +1 slot when adding
        self.rank_spin = QSpinBox()
        self.rank_spin.setRange(1, self.total_targets)
        if self.target:
            self.rank_spin.setValue(self.target.rank if self.target.rank else 1)
        else:
            self.rank_spin.setValue(self.total_targets)  # default: last

        form_layout.addRow("Target Name:", self.name_edit)
        form_layout.addRow("Host Address:", self.host_edit)
        form_layout.addRow("Port:", self.port_spin)
        form_layout.addRow("Database Name:", self.database_edit)
        form_layout.addRow("Rank:", self.rank_spin)

        layout.addLayout(form_layout)

        self.btn_test = QPushButton("Test Connection")
        self.btn_test.clicked.connect(self.test_connection)
        layout.addWidget(self.btn_test)

        # Bottom row: Remove (left, edit-only) | Ok / Cancel (right)
        bottom_layout = QHBoxLayout()

        if self.target is not None:
            self.btn_remove_dlg = QPushButton("Remove")
            self.btn_remove_dlg.setObjectName("DangerButton")
            self.btn_remove_dlg.clicked.connect(self._on_remove_clicked)
            bottom_layout.addWidget(self.btn_remove_dlg)

        bottom_layout.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.try_accept)
        buttons.rejected.connect(self.reject)
        bottom_layout.addWidget(buttons)

        layout.addLayout(bottom_layout)

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
            QPushButton#DangerButton {
                background-color: #ed8796;
                color: #1e1e2e;
                border: 1px solid #d97082;
            }
            QPushButton#DangerButton:hover {
                background-color: #d97082;
            }
        """
        )

    def test_connection(self):
        """Manually test connection and show result."""
        host = self.host_edit.text().strip()
        port = self.port_spin.value()
        database = self.database_edit.text().strip()

        if not host:
            QMessageBox.warning(self, "Input Error", "Please enter a host to test.")
            return

        self.setCursor(Qt.CursorShape.WaitCursor)
        success = validate_connection(host, port)
        self.unsetCursor()
        
        self.connection_status = success  # Store the result
        address = f"{host}:{port}/{database}" if database else f"{host}:{port}"

        if success:
            QMessageBox.information(self, "Success", f"Successfully connected to {address}")
        else:
            QMessageBox.critical(
                self,
                "Connection Failed",
                f"Could not connect to {address}.\nPlease check the details and try again.",
            )

    def try_accept(self):
        """Validate connection before accepting, with user override."""
        host = self.host_edit.text().strip()
        port = self.port_spin.value()
        database = self.database_edit.text().strip()

        if not self.name_edit.text().strip() or not host:
            QMessageBox.warning(self, "Validation Error", "Name and Host are required.")
            return

        self.setCursor(Qt.CursorShape.WaitCursor)
        success = validate_connection(host, port)
        self.unsetCursor()
        
        self.connection_status = success  # Store the result
        address = f"{host}:{port}/{database}" if database else f"{host}:{port}"

        if success:
            self.accept()
        else:
            reply = QMessageBox.question(
                self,
                "Connection Failed",
                f"Could not connect to {address}.\n\nDo you want to save this target anyway?",
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
            "rank": self.rank_spin.value(),
        }
    
    def get_connection_status(self):
        """Return the connection test result (True/False/None)."""
        return self.connection_status

    def _on_remove_clicked(self):
        """Flag that remove was requested and close the dialog."""
        self.remove_requested = True
        self.reject()



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
        self._profile_manager = ProfileManager()
        active_profile = self._profile_manager.get_active_profile()
        targets_file = self._profile_manager.get_targets_file(active_profile)
        self.manager = TargetsManager(targets_file=targets_file)
        self.history = []
        self.server_status = {}  # Cache for server status checks
        self._setup_ui()
        self._check_on_startup()  # Check APIs + active Z3950 on launch

    def _check_on_startup(self):
        """Check APIs and active Z3950 targets on launch."""
        targets = self.manager.get_all_targets()
        api_targets = [
            t for t in targets
            if t.target_type and "api" in t.target_type.lower()
        ]
        z3950_active = [
            t for t in targets
            if not (t.target_type and "api" in t.target_type.lower()) and t.selected
        ]
        check_targets = api_targets + z3950_active
        if check_targets:
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {}
                for t in api_targets:
                    futures[executor.submit(self._check_api_online, t.name)] = t
                for t in z3950_active:
                    futures[executor.submit(validate_connection, t.host, t.port, 2, True)] = t
                for future in as_completed(futures):
                    t = futures[future]
                    try:
                        self.server_status[t.target_id] = future.result()
                    except Exception:
                        self.server_status[t.target_id] = False
        self.refresh_targets()

    def set_advanced_mode(self, enabled):
        """No-op for compatibility with main window calls."""
        _ = enabled

    def load_profile_targets(self, profile_name: str):
        """Switch to the targets file associated with *profile_name*.

        Called automatically when the active profile changes so that
        each profile maintains its own independent set of targets.
        """
        targets_file = self._profile_manager.get_targets_file(profile_name)
        self.manager = TargetsManager(targets_file=targets_file)
        self.server_status.clear()
        self.history.clear()
        self._check_on_startup()

    def eventFilter(self, obj, event):
        """Filter out wheel events on comboboxes to prevent accidental value changes."""
        if isinstance(obj, QComboBox) and event.type() == QEvent.Type.Wheel:
            return True  # Block the event
        return super().eventFilter(obj, event)

    def _setup_ui(self):
        # Wrap content in a scroll area so widgets never get compressed on resize
        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _outer.setSpacing(0)
        _scroll = QScrollArea()
        _scroll.setWidgetResizable(True)
        _scroll.setFrameShape(QFrame.Shape.NoFrame)
        _scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        _scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        _scr_content = QWidget()
        _scroll.setWidget(_scr_content)
        _outer.addWidget(_scroll)
        layout = QVBoxLayout(_scr_content)
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
        self.btn_add.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_add.clicked.connect(self.add_target)

        self.btn_restore = QPushButton("Restore History")
        self.btn_restore.setObjectName("SecondaryButton")
        self.btn_restore.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_restore.clicked.connect(self.show_restore_dialog)

        self.btn_check_servers = QPushButton("Check Servers")
        self.btn_check_servers.setObjectName("SecondaryButton")
        self.btn_check_servers.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
        btn_layout.addWidget(self.btn_restore)
        btn_layout.addWidget(self.btn_check_servers)
        btn_layout.addStretch()
        btn_layout.addWidget(self.search_container)

        layout.addLayout(btn_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["Rank", "Active", "Target Name", "Host / IP", "Port", "Database", "Edit", "Server"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 120)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 90)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(6, 60)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(7, 100)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
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

        # Ensure the table always shows a reasonable minimum height
        self.table.setMinimumHeight(200)
        layout.addWidget(self.table)

    def mousePressEvent(self, event):
        """Clear table selection when clicking outside the table."""
        if not self.table.geometry().contains(event.pos()):
            self.table.clearSelection()
        super().mousePressEvent(event)

    def _emit_targets_changed(self):
        self.targets_changed.emit(self.get_targets())

    @staticmethod
    def _check_api_online(target_name: str) -> bool:
        """Check if a built-in API target is reachable via HTTP."""
        name = target_name.strip().lower()
        if "library of congress" in name or name == "loc":
            url = "http://lx2.loc.gov:210/LCDB?operation=explain&version=1.1"
        elif "harvard" in name:
            url = "https://api.lib.harvard.edu/v2/items.json?limit=1"
        elif "openlibrary" in name or "open library" in name:
            url = "https://openlibrary.org/"
        else:
            return False
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "LCCNHarvester/0.1")
            with urllib.request.urlopen(req, timeout=4) as resp:
                return resp.status < 500
        except Exception:
            pass
        try:
            req2 = urllib.request.Request(url)
            req2.add_header("User-Agent", "LCCNHarvester/0.1")
            with urllib.request.urlopen(req2, timeout=4) as resp:
                return resp.status < 500
        except Exception:
            return False

    def check_all_servers(self):
        """Check active Z3950 targets and all API targets in parallel."""
        self.setCursor(Qt.CursorShape.WaitCursor)
        self.server_status.clear()
        targets = self.manager.get_all_targets()

        z3950_active = [
            t for t in targets
            if not (t.target_type and "api" in t.target_type.lower()) and t.selected
        ]
        api_targets = [
            t for t in targets
            if t.target_type and "api" in t.target_type.lower()
        ]

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {}
            for t in z3950_active:
                futures[executor.submit(validate_connection, t.host, t.port, 2, True)] = t
            for t in api_targets:
                futures[executor.submit(self._check_api_online, t.name)] = t

            for future in as_completed(futures):
                t = futures[future]
                try:
                    self.server_status[t.target_id] = future.result()
                except Exception:
                    self.server_status[t.target_id] = False

        self.refresh_targets(check_servers=False)
        self.unsetCursor()

    def refresh_targets(self, check_servers=False):
        """Reload targets from the manager and display them."""
        self.table.clearContents()
        targets = self.manager.get_all_targets()
        self.table.setRowCount(len(targets))
        self.table.blockSignals(True)

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

            # Edit button (pencil icon)
            edit_btn = QPushButton()
            edit_btn.setFixedHeight(36)
            edit_btn.setFixedWidth(40)
            edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            edit_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            edit_btn.setToolTip("Edit target")
            _pencil_icon_path = str(Path(__file__).parent / "icons" / "pencil.svg")
            edit_btn.setIcon(QIcon(_pencil_icon_path))
            edit_btn.setIconSize(QSize(18, 18))
            edit_btn.setStyleSheet("""
                QPushButton {
                    background-color: #313244;
                    border: 2px solid #45475a;
                    border-radius: 8px;
                    font-size: 16px;
                    color: #cdd6f4;
                    text-align: center;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #89b4fa;
                    border-color: #74c7ec;
                    color: #1e1e2e;
                }
                QPushButton:pressed {
                    background-color: #74c7ec;
                }
            """)
            edit_btn.clicked.connect(lambda checked, t=target: self._edit_specific_target(t))
            self.table.setCellWidget(row, 6, edit_btn)

            # Server status indicator
            server_btn = QPushButton()
            server_btn.setFixedHeight(36)
            server_btn.setMinimumWidth(60)
            server_btn.setMaximumWidth(100)
            server_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            server_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            server_btn.setEnabled(False)  # Not clickable, just status display

            is_online = self.server_status.get(target.target_id, None)
            if is_online is None:
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
            
            self.table.setCellWidget(row, 7, server_btn)

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
        all_targets = self.manager.get_all_targets()
        total = len(all_targets) + 1  # +1 to include the new slot
        dialog = TargetDialog(self, total_targets=total)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            chosen_rank = data["rank"]

            new_target = Target(
                target_id="",
                name=data["name"],
                target_type="Z3950",
                host=data["host"],
                port=data["port"],
                database=data["database"],
                record_syntax="USMARC",
                rank=total,  # temporary; reordering below
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

                # Apply chosen rank via reorder
                self._on_rank_changed(chosen_rank, added_target)
            else:
                self.refresh_targets()

    def edit_target(self):
        target = self._get_selected_target()
        if target:
            self._edit_specific_target(target)

    def _edit_specific_target(self, target):
        """Open edit dialog for a given target object."""
        if target.target_type == "API":
            QMessageBox.information(self, "Info", "Built-in API targets cannot be edited.")
            return

        all_targets_now = self.manager.get_all_targets()
        total = len(all_targets_now)
        dialog = TargetDialog(self, target, total_targets=total)
        result = dialog.exec()

        # Remove was clicked inside the dialog
        if dialog.remove_requested:
            self._remove_specific_target(target)
            return

        if result == QDialog.DialogCode.Accepted:
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

            # Apply rank change if it differs
            chosen_rank = data["rank"]
            if chosen_rank != target.rank:
                self._on_rank_changed(chosen_rank, target)
            else:
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
            self._track_history("DELETE", target)
            self.manager.delete_target(target.target_id)
            self.refresh_targets()

    def _toggle_target_active(self, target):
        """Toggle target active status from the table button."""
        target.selected = not target.selected
        self.manager.modify_target(target)

        # Check server when activating
        if target.selected:
            try:
                if target.target_type and "api" in target.target_type.lower():
                    is_online = self._check_api_online(target.name)
                else:
                    is_online = validate_connection(target.host, target.port, 2, True)
                self.server_status[target.target_id] = is_online
            except Exception:
                is_online = False
                self.server_status[target.target_id] = False

            if not is_online:
                if target.target_type and "api" in target.target_type.lower():
                    address = target.name
                else:
                    address = f"{target.host}:{target.port}/{target.database}" if target.database else f"{target.host}:{target.port}"
                QMessageBox.warning(
                    self,
                    "Connection Failed",
                    f"Could not connect to {address}.\nThe target has been activated but may not respond during harvest.",
                )

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


