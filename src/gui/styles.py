"""
Premium UI Themes for LCCN Harvester
Professional dark and light themes that surpass the mock design
"""

# DARK THEME - Graphite Ember (distinct from mock)
DARK_THEME = """
QWidget {
    background-color: #171716;
    color: #e8e6df;
    font-size: 13px;
}

QLabel {
    color: #e8e6df;
    background: transparent;
    padding: 0px;
}

QMainWindow {
    background-color: #151514;
}

/* Tabs - Left Nav Rail */
QTabWidget::pane {
    border: 1px solid #2d2e2b;
    background: #171716;
    border-radius: 12px;
    margin-left: 8px;
}

QTabBar::tab {
    background: #1b1c1a;
    color: #a7a59b;
    min-width: 186px;
    min-height: 48px;
    text-align: left;
    padding: 10px 14px;
    margin: 2px 0;
    border-radius: 10px;
    border: 1px solid transparent;
    font-weight: 600;
    font-size: 14px;
}

QTabBar::tab:selected {
    background: #20211e;
    color: #c2d07f;
    border: 1px solid #35372f;
}

QTabBar::tab:hover:!selected {
    background: #262723;
    color: #c2d07f;
    border: 1px solid #31322d;
}

/* Buttons - Colored Variants */
QPushButton {
    background-color: #2b2c28;
    color: white;
    border: none;
    padding: 12px 24px;
    border-radius: 8px;
    font-weight: 600;
    font-size: 14px;
}

QPushButton:hover {
    background-color: #363733;
}

QPushButton:pressed {
    background-color: #242521;
}

QPushButton:disabled {
    background-color: #1f201d;
    color: #8a887f;
}

QPushButton#PrimaryButton {
    background-color: #c2d07f;
    color: #1a1a18;
}

QPushButton#PrimaryButton:hover {
    background-color: #d2df8e;
    border: 1px solid #d2df8e;
}

QPushButton#SuccessButton {
    background-color: #a9d48f;
    color: #1a1a18;
}

QPushButton#SuccessButton:hover {
    background-color: #b9e19f;
}

QPushButton#DangerButton {
    background-color: #d9a59c;
    color: #1a1a18;
}

QPushButton#DangerButton:hover {
    background-color: #e4b4ab;
}

QPushButton#SecondaryButton {
    background-color: transparent;
    color: #c2d07f;
    border: 2px solid #c2d07f;
}

QPushButton#SecondaryButton:hover {
    background-color: #242521;
}

/* Group Boxes - Premium Cards */
QGroupBox {
    background-color: #1f201d;
    border: 1px solid #2d2e2b;
    border-radius: 12px;
    margin-top: 16px;
    padding: 12px 14px 14px 14px;
    font-weight: 700;
    font-size: 14px;
    color: #c2d07f;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
}

QCheckBox {
    spacing: 8px;
    padding: 2px 0;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
}

/* Input Fields */
QLineEdit, QSpinBox, QComboBox {
    background-color: #232320;
    border: 2px solid #2d2e2b;
    border-radius: 8px;
    padding: 10px 14px;
    color: #e8e6df;
    selection-background-color: #3a3b35;
}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #c2d07f;
}

QLineEdit:hover, QSpinBox:hover, QComboBox:hover {
    border-color: #3a3b35;
}

QTextEdit {
    background-color: #171716;
    border: 1px solid #2d2e2b;
    border-radius: 8px;
    color: #cfe3c0;
    font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
    padding: 8px;
}

/* Tables - Premium */
QTableWidget {
    background-color: #1f201d;
    border: 1px solid #2d2e2b;
    border-radius: 10px;
    gridline-color: #2d2e2b;
}

QTableWidget::item {
    padding: 10px;
    color: #e8e6df;
    border-bottom: 1px solid #242521;
}

QTableWidget::item:alternate {
    background-color: #20211e;
}

QTableWidget::item:hover {
    background-color: #242521;
}

QTableWidget::item:selected {
    background-color: #2f302a;
    color: #c2d07f;
}

QHeaderView::section {
    background-color: #242521;
    padding: 12px;
    border: none;
    border-bottom: 2px solid #2d2e2b;
    font-weight: 700;
    color: #c2d07f;
}

/* Progress Bar */
QProgressBar {
    border: none;
    border-radius: 8px;
    background-color: #242521;
    text-align: center;
    height: 28px;
    color: white;
    font-weight: 600;
}

QProgressBar::chunk {
    background-color: #c2d07f;
    border-radius: 8px;
}

/* Subtle card depth */
QGroupBox {
    margin-top: 16px;
}

/* Drop Zone Fix */
QFrame#DropZone {
    border: 3px dashed #c2d07f;
    border-radius: 12px;
    background-color: #1f201d;
}

QFrame#DropZone QLabel {
    border: none;
    background: transparent;
}

/* Status Bar */
QStatusBar {
    background-color: #1f201d;
    border-top: 1px solid #2d2e2b;
    color: #a7a59b;
}

/* Scroll Bars */
QScrollBar:vertical {
    background-color: #171716;
    width: 14px;
    border-radius: 7px;
}

QScrollBar::handle:vertical {
    background-color: #2b2c28;
    border-radius: 7px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #363733;
}

/* Menu Bar */
QMenuBar {
    background-color: #1f201d;
    border-bottom: 1px solid #2d2e2b;
    padding: 6px;
}

QMenuBar::item {
    padding: 10px 16px;
    color: #e8e6df;
    border-radius: 6px;
}

QMenuBar::item:selected {
    background-color: #242521;
    color: #c2d07f;
}

QMenu {
    background-color: #1f201d;
    border: 1px solid #2d2e2b;
    border-radius: 10px;
    padding: 6px;
}

QMenu::item {
    padding: 10px 28px;
    color: #e8e6df;
    border-radius: 6px;
}

QMenu::item:selected {
    background-color: #242521;
    color: #c2d07f;
}

/* Subtle section divider */
QFrame#SectionDivider {
    background-color: #2d2e2b;
    margin: 6px 0 8px 0;
}

QToolTip {
    background-color: #1f201d;
    color: #e8e6df;
    border: 1px solid #3a3b35;
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 12px;
}
"""

# Keep light theme as fallback
LIGHT_THEME = """
QMainWindow {
    background-color: #f5f7fa;
}

QTabWidget::pane {
    border: 1px solid #e1e8ed;
    background-color: white;
    border-radius: 8px;
    margin-left: 8px;
}

QTabBar::tab {
    background-color: #f4f6f8;
    color: #657786;
    min-width: 186px;
    min-height: 48px;
    text-align: left;
    padding: 10px 14px;
    margin: 2px 0;
    border-radius: 8px;
    border: 1px solid transparent;
    font-weight: 500;
    font-size: 13px;
}

QTabBar::tab:selected {
    background-color: #ffffff;
    color: #1da1f2;
    border: 1px solid #d7e0e8;
}

QTabBar::tab:hover:!selected {
    background-color: #edf2f7;
    color: #1a91da;
    border: 1px solid #dfe7ef;
}

QPushButton {
    background-color: #1da1f2;
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 6px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #1a91da;
}

QPushButton#SuccessButton {
    background-color: #17bf63;
}

QPushButton#DangerButton {
    background-color: #e0245e;
}

QPushButton#SecondaryButton {
    background-color: white;
    color: #1da1f2;
    border: 2px solid #1da1f2;
}

QGroupBox {
    background-color: white;
    border: 1px solid #e1e8ed;
    border-radius: 8px;
    margin-top: 12px;
    padding: 16px;
    font-weight: 600;
}

QLineEdit, QTextEdit, QSpinBox, QComboBox {
    background-color: white;
    border: 2px solid #e1e8ed;
    border-radius: 6px;
    padding: 8px 12px;
}

QLineEdit:focus {
    border-color: #1da1f2;
}

QTableWidget {
    background-color: white;
    border: 1px solid #e1e8ed;
    border-radius: 6px;
}

QProgressBar {
    border: none;
    border-radius: 6px;
    background-color: #e1e8ed;
    height: 24px;
}

QProgressBar::chunk {
    background-color: #1da1f2;
    border-radius: 6px;
}

QFrame#DropZone QLabel {
    border: none;
    background: transparent;
}
"""

# Default to dark theme
MODERN_STYLE = DARK_THEME
