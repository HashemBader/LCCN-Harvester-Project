"""
Module: targets_tab_v2.py
V2 target manager UI matching modern shell while preserving target backend.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QComboBox,
    QCheckBox,
    QMessageBox,
    QDialog,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QDialogButtonBox,
)

from utils.targets_manager import TargetsManager, Target
from z3950.session_manager import validate_connection


class AddTargetDialog(QDialog):
    """Dialog for adding custom Z39.50 targets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Z39.50 Target")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_input = QLineEdit()
        self.host_input = QLineEdit()
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(210)
        self.database_input = QLineEdit()
        self.rank_input = QSpinBox()
        self.rank_input.setRange(1, 999)
        self.rank_input.setValue(10)

        form.addRow("Name", self.name_input)
        form.addRow("Host", self.host_input)
        form.addRow("Port", self.port_input)
        form.addRow("Database", self.database_input)
        form.addRow("Rank", self.rank_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_target_data(self) -> dict:
        return {
            "name": self.name_input.text().strip(),
            "host": self.host_input.text().strip(),
            "port": self.port_input.value(),
            "database": self.database_input.text().strip(),
            "rank": self.rank_input.value(),
        }


class TargetsTabV2(QWidget):
    targets_changed = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.manager = TargetsManager()
        self._setup_ui()
        self.refresh_targets()

    def set_advanced_mode(self, enabled):
        _ = enabled

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        title = QLabel("TARGET MANAGEMENT")
        title.setProperty("class", "CardTitle")
        title.setStyleSheet("font-size: 24px; letter-spacing: 1px;")
        layout.addWidget(title)

        top_row = QHBoxLayout()
        self.builtin_info = QLabel(
            "Built-in API Targets\nCommon targets like LoC, Harvard, and OpenLibrary are managed automatically."
        )
        self.builtin_info.setWordWrap(True)
        self.builtin_info.setStyleSheet(
            "color: #a5adcb; background: #2b3250; border-left: 3px solid #8aadf4; "
            "padding: 8px 10px; border-radius: 6px;"
        )

        self.btn_add = QPushButton("Add Target")
        self.btn_add.setProperty("class", "SecondaryButton")
        self.btn_add.clicked.connect(self._add_target)

        top_row.addWidget(self.builtin_info, stretch=1)
        top_row.addWidget(self.btn_add)
        layout.addLayout(top_row)

        table_frame = QFrame()
        table_frame.setProperty("class", "Card")
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(8, 8, 8, 8)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["RANK", "ENABLED", "TARGET NAME", "TYPE", "STATUS"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        table_layout.addWidget(self.table)

        layout.addWidget(table_frame)

    def _emit_targets_changed(self):
        self.targets_changed.emit(self.get_targets())

    def refresh_targets(self):
        targets = self.manager.get_all_targets()
        self.table.setRowCount(len(targets))

        for row, target in enumerate(targets):
            rank_combo = QComboBox()
            for i in range(1, len(targets) + 1):
                rank_combo.addItem(str(i), i)
            rank_combo.setCurrentText(str(target.rank if target.rank > 0 else 1))
            rank_combo.currentTextChanged.connect(
                lambda text, target_id=target.target_id: self._on_rank_changed(target_id, text)
            )
            self.table.setCellWidget(row, 0, rank_combo)

            selected_check = QCheckBox()
            selected_check.setChecked(target.selected)
            selected_check.stateChanged.connect(
                lambda _state, target_id=target.target_id: self._on_selected_changed(target_id)
            )
            selected_check.setStyleSheet("margin-left: 12px; margin-right: 12px;")
            self.table.setCellWidget(row, 1, selected_check)

            name_item = QTableWidgetItem(target.name)
            name_item.setData(Qt.ItemDataRole.UserRole, target.target_id)
            self.table.setItem(row, 2, name_item)

            target_type = "API" if target.target_type.upper() == "API" else "Z39.50"
            type_item = QTableWidgetItem(target_type)
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, type_item)

            status_text, status_color = self._status_for_target(target)
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setForeground(status_color)
            self.table.setItem(row, 4, status_item)

        self._emit_targets_changed()

    def _status_for_target(self, target: Target):
        if not target.selected:
            return "Inactive", Qt.GlobalColor.red
        if target.target_type.upper() == "API":
            return "Active", Qt.GlobalColor.green
        if target.host and target.port:
            try:
                if validate_connection(target.host, int(target.port), timeout=2):
                    return "Active", Qt.GlobalColor.green
            except Exception:
                pass
        return "Inactive", Qt.GlobalColor.red

    def _find_target(self, target_id: str) -> Target | None:
        for target in self.manager.get_all_targets():
            if target.target_id == target_id:
                return target
        return None

    def _on_rank_changed(self, target_id: str, text: str):
        if not text:
            return
        target = self._find_target(target_id)
        if not target:
            return
        new_rank = int(text)
        if new_rank == target.rank:
            return

        targets = self.manager.get_all_targets()
        swap_target = next((item for item in targets if item.rank == new_rank), None)
        if swap_target and swap_target.target_id != target.target_id:
            swap_target.rank = target.rank
            self.manager.modify_target(swap_target)

        target.rank = new_rank
        self.manager.modify_target(target)
        self.refresh_targets()

    def _on_selected_changed(self, target_id: str):
        target = self._find_target(target_id)
        if not target:
            return
        row = next(
            (idx for idx in range(self.table.rowCount())
             if self.table.item(idx, 2) and self.table.item(idx, 2).data(Qt.ItemDataRole.UserRole) == target_id),
            -1,
        )
        if row < 0:
            return
        checkbox = self.table.cellWidget(row, 1)
        if isinstance(checkbox, QCheckBox):
            target.selected = checkbox.isChecked()
            self.manager.modify_target(target)
            self.refresh_targets()

    def _add_target(self):
        dialog = AddTargetDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        data = dialog.get_target_data()
        if not data["name"] or not data["host"] or not data["database"]:
            QMessageBox.warning(self, "Missing Fields", "Name, host, and database are required.")
            return
        new_target = Target(
            target_id="",
            name=data["name"],
            target_type="Z3950",
            host=data["host"],
            port=data["port"],
            database=data["database"],
            record_syntax="USMARC",
            rank=data["rank"],
            selected=True,
        )
        self.manager.add_target(new_target)
        self.refresh_targets()

    def get_targets(self):
        mapped_targets = []
        for target in self.manager.get_all_targets():
            target_type = "z3950" if target.target_type.upper().startswith("Z") else "api"
            mapped_targets.append(
                {
                    "target_id": target.target_id,
                    "name": target.name,
                    "type": target_type,
                    "host": target.host,
                    "port": target.port,
                    "database": target.database,
                    "record_syntax": target.record_syntax,
                    "rank": target.rank,
                    "selected": target.selected,
                    "username": target.username,
                    "password": target.password,
                }
            )
        return mapped_targets

    def get_selected_targets(self):
        return [target for target in self.get_targets() if target.get("selected", True)]

