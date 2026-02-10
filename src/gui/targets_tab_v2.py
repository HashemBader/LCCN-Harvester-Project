"""
Module: targets_tab_v2.py
V2 Targets Tab: "Control Center" layout with Callouts and Clean Table.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

class CalloutBox(QFrame):
    """Blue 'Info' callout using V2 palette."""
    def __init__(self, title, text):
        super().__init__()
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(138, 173, 244, 0.1); 
                border-left: 4px solid #8aadf4;
                border-radius: 4px;
            }
            QLabel { background: transparent; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #8aadf4; font-weight: bold; font-size: 13px;")
        
        lbl_text = QLabel(text)
        lbl_text.setStyleSheet("color: #cad3f5; font-size: 12px;")
        lbl_text.setWordWrap(True)
        
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_text)

class TargetsTabV2(QWidget):
    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30,30,30,30)
        layout.setSpacing(20)

        # 1. Header with Actions
        header_layout = QHBoxLayout()
        
        title = QLabel("Target Management")
        title.setProperty("class", "CardTitle")
        title.setStyleSheet("font-size: 18px;")
        
        # Tools
        btn_add = QPushButton("Add Target")
        btn_add.setProperty("class", "SecondaryButton")
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(btn_add)
        
        layout.addLayout(header_layout)

        # 2. Callout Info
        callout = CalloutBox(
            "Built-in API Targets", 
            "Common targets like LoC, Harvard, and OpenLibrary are managed automatically. "
            "Use this list to add custom Z39.50 servers."
        )
        layout.addWidget(callout)

        # 3. Targets Table (Card)
        table_frame = QFrame()
        table_frame.setProperty("class", "Card")
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(0,0,0,0)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Enabled", "Target Name", "Type", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setStyleSheet("background: transparent; border: none;")
        
        table_layout.addWidget(self.table)
        layout.addWidget(table_frame)
        
        # Mock Data load
        self._load_mock_data()

    targets_changed = pyqtSignal(list)

    def _load_mock_data(self):
        targets = [
            ("Library of Congress", "API", "Ready"),
            ("Harvard Library", "API", "Ready"),
            ("OpenLibrary", "API", "Ready"),
            ("Yale Z39.50", "Z39.50", "Unknown")
        ]
        
        self.table.setRowCount(len(targets))
        for i, (name, t_type, status) in enumerate(targets):
            # Checkbox
            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.setContentsMargins(10,0,0,0)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk = QCheckBox()
            chk.setChecked(True)
            chk.toggled.connect(self._on_target_toggled) # Connect to slot
            chk_layout.addWidget(chk)

            # Store full config in the checkbox item for easy retrieval
            target_config = {
                "name": name, 
                "type": "z3950" if t_type == "Z3950" else "api",
                # Add dummy host/port for Z39.50 mock
                "host": "z3950.loc.gov", "port": 7090, "database": "VOYAGER" 
            }
            if name == "Library of Congress": target_config["name"] = "loc"
            elif name == "Harvard Library": target_config["name"] = "harvard"
            elif name == "OpenLibrary": target_config["name"] = "openlibrary"
            # Add some unique ID if needed or rely on name

            chk.setProperty("target_config", target_config)
            
            self.table.setCellWidget(i, 0, chk_widget)
            
            # Name
            self.table.setItem(i, 1, QTableWidgetItem(name))
            
            # Type
            self.table.setItem(i, 2, QTableWidgetItem(t_type))
            
            # Status
            item_status = QTableWidgetItem(status)
            item_status.setForeground(QColor("#a6da95") if status=="Ready" else QColor("#a5adcb"))
            self.table.setItem(i, 3, item_status)

    def _on_target_toggled(self, checked):
        """Emit signal when any target is toggled."""
        self.targets_changed.emit(self.get_selected_targets())

    def get_selected_targets(self):
        """Return list of selected target configurations."""
        selected = []
        for i in range(self.table.rowCount()):
            widget = self.table.cellWidget(i, 0)
            if widget:
                # Find the checkbox inside the centered widget layout
                # We need to iterate children because findChild might grab any checkbox
                for child in widget.children():
                    if isinstance(child, QCheckBox):
                         if child.isChecked():
                             config = child.property("target_config")
                             if config: selected.append(config)
                         break
        return selected


    def set_advanced_mode(self, val):
        pass
