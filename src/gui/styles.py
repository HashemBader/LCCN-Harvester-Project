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


# V2 THEME - Catppuccin Macchiato inspired (design-only upgrade)
CATPPUCCIN_THEME = {
    "base": "#24273a",
    "surface0": "#363a4f",
    "surface1": "#494d64",
    "surface2": "#5b6078",
    "text": "#ffffff",
    "subtext0": "#a5adcb",
    "subtext1": "#b8c0e0",
    "overlay1": "#8087a2",
    "blue": "#8aadf4",
    "sapphire": "#7dc4e4",
    "red": "#ed8796",
    "green": "#a6da95",
    "yellow": "#eed49f",
    "mauve": "#c6a0f6",
    "lavender": "#b7bdf8",
}

V2_STYLESHEET = """
QWidget {
    background-color: #24273a;
    color: #ffffff;
    font-family: 'Segoe UI', 'Roboto', sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #24273a;
}

QWidget#TopHeader {
    background-color: #1e2030;
    border-bottom: 1px solid #363a4f;
}

QLabel#MainTitle {
    color: #8aadf4;
    font-size: 24px;
    font-weight: 800;
    background: transparent;
}

QTabWidget::pane {
    border: 1px solid #363a4f;
    background: #24273a;
    border-radius: 12px;
    margin-left: 8px;
}

QTabBar::tab {
    background: #1e2030;
    color: #a5adcb;
    min-width: 186px;
    min-height: 48px;
    text-align: left;
    padding: 10px 14px;
    margin: 2px 0;
    border-radius: 10px;
    border: 1px solid transparent;
    font-weight: 700;
}

QTabBar::tab:selected {
    background: #2a2d3e;
    color: #8aadf4;
    border: 1px solid #494d64;
}

QTabBar::tab:hover:!selected {
    background: #303349;
    color: #ffffff;
    border: 1px solid #494d64;
}

QPushButton {
    border-radius: 8px;
    padding: 10px 18px;
    font-weight: 700;
    font-size: 13px;
    border: 1px solid transparent;
    background-color: #363a4f;
    color: #ffffff;
}

QPushButton:hover {
    background-color: #494d64;
}

QPushButton:disabled {
    background-color: #2b2f42;
    color: #5b6078;
}

QPushButton.PrimaryButton, QPushButton#PrimaryButton {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8aadf4, stop:1 #6d96e8);
    color: #1e2030;
    border-top: 1px solid rgba(255,255,255,0.20);
}

QPushButton.PrimaryButton:hover, QPushButton#PrimaryButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #b7bdf8, stop:1 #8aadf4);
}

QPushButton.SecondaryButton, QPushButton#SecondaryButton {
    background-color: #363a4f;
    color: #ffffff;
    border: 1px solid #494d64;
}

QPushButton.SecondaryButton:hover, QPushButton#SecondaryButton:hover {
    background-color: #494d64;
}

QPushButton.DangerButton, QPushButton#DangerButton {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ed8796, stop:1 #d25e6d);
    color: #1e2030;
    border-top: 1px solid rgba(255,255,255,0.20);
}

QPushButton.DangerButton:hover, QPushButton#DangerButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f5bde6, stop:1 #ed8796);
}

QGroupBox {
    background-color: #1e2030;
    border: 1px solid #363a4f;
    border-top: 1px solid #5b6078;
    border-radius: 12px;
    margin-top: 16px;
    padding: 12px;
    font-weight: 700;
    color: #b8c0e0;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 8px;
}

QLineEdit, QTextEdit, QSpinBox, QComboBox {
    background-color: #181926;
    border: 1px solid #494d64;
    border-radius: 8px;
    padding: 10px 12px;
    color: #ffffff;
}

QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #8aadf4;
    background-color: #1e2030;
}

QTableWidget {
    background-color: #1e2030;
    border: 1px solid #363a4f;
    border-radius: 8px;
    gridline-color: #363a4f;
}

QTableWidget::item {
    color: #ffffff;
    border-bottom: 1px solid #2a2d3e;
    padding: 8px;
}

QTableWidget::item:selected {
    background-color: rgba(138, 173, 244, 0.20);
}

QHeaderView::section {
    background-color: #181926;
    padding: 10px;
    border: none;
    border-bottom: 2px solid #8aadf4;
    font-weight: 800;
    color: #ffffff;
}

QProgressBar {
    border: none;
    border-radius: 8px;
    background-color: #181926;
    text-align: center;
    min-height: 20px;
}

QProgressBar::chunk {
    background-color: #8aadf4;
    border-radius: 8px;
}

QStatusBar {
    background-color: #1e2030;
    border-top: 1px solid #363a4f;
    color: #a5adcb;
}

QFrame#DropZone, QFrame#DragZone {
    border: 2px dashed #8aadf4;
    background-color: rgba(138, 173, 244, 0.08);
    border-radius: 14px;
}

QFrame#DropZone:hover, QFrame#DragZone:hover {
    background-color: rgba(138, 173, 244, 0.15);
    border-color: #b7bdf8;
}

QScrollBar:vertical {
    background-color: #1e2030;
    width: 12px;
    border-radius: 6px;
}

QScrollBar::handle:vertical {
    background-color: #494d64;
    border-radius: 6px;
    border: 2px solid #1e2030;
}

QScrollBar::handle:vertical:hover {
    background-color: #5b6078;
}

QMenuBar {
    background-color: #1e2030;
    border-bottom: 1px solid #363a4f;
}

QMenuBar::item:selected {
    background-color: #2a2d3e;
    color: #8aadf4;
    border-radius: 6px;
}

QMenu {
    background-color: #1e2030;
    border: 1px solid #363a4f;
    border-radius: 8px;
}

QMenu::item:selected {
    background-color: #2a2d3e;
    color: #8aadf4;
    border-radius: 4px;
}

QToolTip {
    background-color: #181926;
    color: #cad3f5;
    border: 1px solid #8aadf4;
    padding: 6px 8px;
    border-radius: 6px;
}
"""

# Use V2 styling as the default visual theme.
MODERN_STYLE = V2_STYLESHEET
