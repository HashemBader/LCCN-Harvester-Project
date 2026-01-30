"""
Module: mock_gui_launcher.py
Purpose: A modern, professional GUI container for the LCCN Harvester using PyQt6.
         Implements a tabbed interface (Harvest, Results, Settings) with a custom dark theme.
"""

import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QLabel, QLineEdit, QTextEdit,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QGroupBox, QFileDialog, QStatusBar, QFrame,
    QSizePolicy, QSpacerItem
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QFont, QColor, QPalette

# --- Modern Dark Theme Stylesheet ---
STYLESHEET = """
/* Global Reset */
QWidget {
    background-color: #1e1e2e; /* Deep dark blue-grey */
    color: #cdd6f4;            /* Off-white text */
    font-family: 'Segoe UI', 'Roboto', sans-serif;
    font-size: 14px;
}

/* Tab Widget */
QTabWidget::pane {
    border: 1px solid #313244;
    background: #1e1e2e;
    border-radius: 8px;
    margin-top: -1px; 
}

QTabBar::tab {
    background: #181825;
    color: #a6adc8;
    padding: 10px 20px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 4px;
    font-weight: bold;
}

QTabBar::tab:selected {
    background: #313244;
    color: #ffffff;
    border-bottom: 2px solid #89b4fa; /* Accent blue */
}

QTabBar::tab:hover {
    background: #313244;
    color: #ffffff;
}

/* Groups and Frames (Cards) */
QGroupBox {
    border: 1px solid #313244;
    border-radius: 8px;
    margin-top: 24px;
    background-color: #181825; /* Slightly darker card background */
    font-weight: bold;
    color: #cba6f7; /* Accent purple */
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 10px;
    left: 10px;
}

/* Inputs */
QLineEdit {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px;
    color: #ffffff;
    selection-background-color: #585b70;
}

QLineEdit:focus {
    border: 1px solid #89b4fa;
}

QTextEdit {
    background-color: #11111b; /* Very dark for console/logs */
    border: 1px solid #313244;
    border-radius: 6px;
    color: #a6e3a1; /* Terminal green text */
    font-family: 'Consolas', 'Courier New', monospace;
    padding: 5px;
}

/* Buttons */
QPushButton {
    background-color: #313244;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    color: #ffffff;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #45475a;
}

QPushButton:pressed {
    background-color: #585b70;
}

QPushButton#PrimaryButton {
    background-color: #89b4fa; /* Accent Blue */
    color: #1e1e2e;
}

QPushButton#PrimaryButton:hover {
    background-color: #b4befe;
}

QPushButton#SuccessButton {
    background-color: #a6e3a1; /* Green */
    color: #1e1e2e;
}

QPushButton#SuccessButton:hover {
    background-color: #94e2d5;
}

QPushButton#DangerButton {
    background-color: #f38ba8; /* Red */
    color: #1e1e2e;
}

QPushButton#DangerButton:hover {
    background-color: #eba0ac;
}

/* Tables */
QTableWidget {
    background-color: #181825;
    border: 1px solid #313244;
    gridline-color: #313244;
    border-radius: 8px;
}

QTableWidget::item {
    padding: 5px;
    border-bottom: 1px solid #313244;
}

QTableWidget::item:selected {
    background-color: #45475a;
    color: white;
}

QHeaderView::section {
    background-color: #11111b;
    color: #cdd6f4;
    padding: 8px;
    border: none;
    border-bottom: 2px solid #313244;
    font-weight: bold;
}

/* Progress Bar */
QProgressBar {
    border: 1px solid #313244;
    border-radius: 6px;
    text-align: center;
    background-color: #181825;
    color: white;
}

QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 5px;
}

/* Status Bar */
QStatusBar {
    background-color: #11111b;
    color: #9399b2;
    border-top: 1px solid #313244;
}
"""

class ModernMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # 1. Window Setup
        self.setWindowTitle("LCCN Harvester Pro")
        self.resize(1000, 750)
        
        # 2. Main Container
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # 3. Layouts & Tabs
        self.layout = QVBoxLayout(main_widget)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        # Header Title
        header_layout = QHBoxLayout()
        title_label = QLabel("LCCN Harvester")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #89b4fa; margin-bottom: 10px;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        self.layout.addLayout(header_layout)

        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)

        # 4. Create Tabs
        self.create_harvest_tab()
        self.create_results_tab()
        self.create_settings_tab()

        # 5. Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("System Ready")

    def create_harvest_tab(self):
        """Tab 1: File Selection, Controls, and Modern Dashboard"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Section A: Input Card
        input_group = QGroupBox("Input Configuration")
        input_layout = QVBoxLayout()
        
        file_row = QHBoxLayout()
        self.lbl_file = QLabel("Source File:")
        self.lbl_file.setStyleSheet("color: #a6adc8;")
        self.txt_file_path = QLineEdit()
        self.txt_file_path.setPlaceholderText("Select a .txt or .csv file containing ISBNs...")
        self.txt_file_path.setReadOnly(True)
        self.btn_browse = QPushButton("Browse Files")
        self.btn_browse.setObjectName("PrimaryButton")
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.clicked.connect(self.browse_file)
        
        file_row.addWidget(self.lbl_file)
        file_row.addWidget(self.txt_file_path, 1)
        file_row.addWidget(self.btn_browse)
        
        input_layout.addLayout(file_row)
        input_group.setLayout(input_layout)
        
        # Section B: Actions Card
        action_group = QGroupBox("Control Center")
        action_layout = QHBoxLayout()
        
        self.btn_start = QPushButton("Start Harvesting")
        self.btn_start.setObjectName("SuccessButton")
        self.btn_start.setMinimumHeight(40)
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setIcon(QIcon.fromTheme("media-playback-start"))
        
        self.btn_stop = QPushButton("Stop Process")
        self.btn_stop.setObjectName("DangerButton")
        self.btn_stop.setMinimumHeight(40)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        
        action_layout.addWidget(self.btn_start)
        action_layout.addWidget(self.btn_stop)
        action_group.setLayout(action_layout)
        
        # Section C: Progress & Logs
        monitor_group = QGroupBox("Live Monitor")
        monitor_layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Idle")
        self.progress_bar.setMinimumHeight(25)
        
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setPlaceholderText("Waiting for activity...")

        monitor_layout.addWidget(QLabel("Progress:"))
        monitor_layout.addWidget(self.progress_bar)
        monitor_layout.addWidget(QLabel("Activity Log:"))
        monitor_layout.addWidget(self.log_area)
        monitor_group.setLayout(monitor_layout)
        
        # Add all to Tab Layout
        layout.addWidget(input_group)
        layout.addWidget(action_group)
        layout.addWidget(monitor_group)
        
        tab.setLayout(layout)
        self.tabs.addTab(tab, "Harvest Dashboard")

    def create_results_tab(self):
        """Tab 2: Professional Table View"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Toolbar
        toolbar_layout = QHBoxLayout()
        self.btn_export = QPushButton("Export to CSV")
        self.btn_export.setObjectName("PrimaryButton")
        self.btn_clear = QPushButton("Clear Results")
        self.btn_clear.setObjectName("DangerButton")
        
        toolbar_layout.addWidget(self.btn_export)
        toolbar_layout.addWidget(self.btn_clear)
        toolbar_layout.addStretch()
        
        # Table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels(["ISBN", "Title", "LCCN", "Source", "Status"])
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setShowGrid(False)
        
        layout.addLayout(toolbar_layout)
        layout.addWidget(self.results_table)
        
        tab.setLayout(layout)
        self.tabs.addTab(tab, "Data Results")

    def create_settings_tab(self):
        """Tab 3: Settings Grid"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Group 1: Preferences
        pref_group = QGroupBox("Harvesting Preferences")
        pref_layout = QVBoxLayout()
        
        self.chk_lccn = QCheckBox("Retrieve LCCN (050 tag)")
        self.chk_lccn.setChecked(True)
        self.chk_lccn.setStyleSheet("spacing: 10px; font-size: 15px;")
        
        self.chk_nlm = QCheckBox("Retrieve NLM Call Number (060 tag)")
        self.chk_nlm.setStyleSheet("spacing: 10px; font-size: 15px;")
        
        pref_layout.addWidget(self.chk_lccn)
        pref_layout.addWidget(self.chk_nlm)
        pref_group.setLayout(pref_layout)
        
        # Group 2: Targets
        target_group = QGroupBox("Z39.50 Search Targets")
        target_layout = QVBoxLayout()
        
        btn_layout = QHBoxLayout()
        self.btn_add_target = QPushButton("Add New Target")
        self.btn_add_target.setObjectName("PrimaryButton")
        self.btn_remove_target = QPushButton("Remove Selected")
        
        btn_layout.addWidget(self.btn_add_target)
        btn_layout.addWidget(self.btn_remove_target)
        btn_layout.addStretch()
        
        self.target_list = QTableWidget()
        self.target_list.setColumnCount(4)
        self.target_list.setHorizontalHeaderLabels(["Enabled", "Library Name", "Host / IP", "Port"])
        self.target_list.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.target_list.verticalHeader().setVisible(False)
        self.target_list.setShowGrid(False)
        self.target_list.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        target_layout.addLayout(btn_layout)
        target_layout.addWidget(self.target_list)
        target_group.setLayout(target_layout)
        
        layout.addWidget(pref_group)
        layout.addWidget(target_group)
        
        tab.setLayout(layout)
        self.tabs.addTab(tab, "Configuration")

    # --- Helper Functions ---
    def browse_file(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select ISBN Source File", "", "Text Files (*.txt);;CSV Files (*.csv)")
        if fname:
            self.txt_file_path.setText(fname)
            self.log_area.append(f"<span style='color: #89b4fa;'>[INFO]</span> Selected file: {fname}")
            self.progress_bar.setFormat("Ready to Harvest")

def run():
    app = QApplication(sys.argv)
    
    # improved styling
    app.setStyle("Fusion") 
    app.setStyleSheet(STYLESHEET)
    
    window = ModernMainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    run()
