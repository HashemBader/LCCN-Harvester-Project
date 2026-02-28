"""
styles_v2.py
Professional V2 Theme (Catppuccin Macchiato).
Polish: Borderless Cards, Soft Shadows, Unified Button System.
"""

# Palette Dictionary (for Python access)
CATPPUCCIN_DARK = {
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
    "rosewater": "#f4dbd6",
    "lavender": "#b7bdf8",
}

CATPPUCCIN_LIGHT = {
    "base": "#f7f7fb",
    "surface0": "#ffffff",
    "surface1": "#f0f2f8",
    "surface2": "#e1e6ef",
    "text": "#2e3440",
    "subtext0": "#4b5063",
    "subtext1": "#5b6176",
    "overlay1": "#8a8fa6",
    "blue": "#1e66f5",
    "sapphire": "#209fb5",
    "red": "#d20f39",
    "green": "#40a02b",
    "yellow": "#df8e1d",
    "mauve": "#8839ef",
    "rosewater": "#f2d5cf",
    "lavender": "#7287fd",
}

# Backwards compat alias
CATPPUCCIN_THEME = CATPPUCCIN_DARK


def generate_stylesheet(theme: dict) -> str:
    """Generate a minimal stylesheet string from a palette dict.

    This covers primary selectors used by the app. Keep it compact so it
    doesn't override every rule in the static V2_STYLESHEET.
    """
    t = theme
    return f"""
/* Global */
QWidget {{ background-color: {t['base']}; color: {t['text']}; font-family: 'Segoe UI', 'Roboto', sans-serif; }}
QLabel {{ background: transparent; color: {t['text']}; font-size: 14px; }}

/* Sidebar */
QFrame#Sidebar {{ background-color: {t['surface0']}; border-right: 1px solid {t['surface1']}; }}
QLabel#SidebarTitle {{ color: {t['blue']}; font-size: 18px; font-weight: 800; padding: 20px 0; margin-bottom: 20px; qproperty-alignment: AlignCenter; }}

/* Dashboard Card Elements */
QLabel[class="CardTitle"], QLabel.CardTitle {{ color: {t['subtext1']}; font-size: 14px; font-weight: 700; }}
QLabel[class="CardValue"], QLabel.CardValue {{ color: {t['text']}; font-size: 32px; font-weight: 800; }}
QLabel[class="CardHelper"], QLabel.CardHelper {{ color: {t['subtext0']}; font-size: 11px; }}
QLabel[class="ActivityLabel"], QLabel.ActivityLabel {{ color: {t['subtext0']}; font-size: 13px; font-weight: 600; }}
QLabel[class="ActivityValue"], QLabel.ActivityValue {{ color: {t['text']}; font-size: 13px; font-family: Menlo, Monaco, 'Courier New', monospace; }}
QLabel[class="SectionTitle"], QLabel.SectionTitle {{ color: {t['text']}; font-size: 18px; font-weight: bold; }}
QLabel[class="DropIcon"], QLabel.DropIcon {{ font-size: 48px; border: none; background: transparent; }}
QLabel[class="DropText"], QLabel.DropText {{ font-size: 14px; font-weight: bold; color: {t['yellow']}; border: none; background: transparent; }}
QLabel[class="DropHint"], QLabel.DropHint {{ font-size: 11px; color: {t['subtext0']}; border: none; background: transparent; }}
QLabel[class="HelperText"], QLabel.HelperText {{ font-size: 12px; color: {t['subtext0']}; background: transparent; border: none; }}

/* Nav Buttons */
QPushButton.NavButton {{ background-color: transparent; color: {t['subtext0']}; text-align: left; padding: 12px 20px; border: none; border-left: 3px solid transparent; font-weight: 600; font-size: 14px; margin-bottom: 2px; }}
QPushButton.NavButton:hover {{ background-color: rgba(138, 173, 244, 0.1); color: {t['text']}; }}
QPushButton.NavButton:checked {{ color: {t['blue']}; border-left: 3px solid {t['blue']}; }}

/* Inputs */
QLineEdit, QSpinBox, QComboBox {{ background-color: {t['surface1']}; border: 1px solid {t['surface2']}; border-radius: 8px; padding: 8px; color: {t['text']}; font-size: 14px; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 2px solid {t['blue']}; background-color: {t['surface2']}; }}

/* Buttons */
QPushButton {{ border-radius: 8px; padding: 8px 14px; font-weight: 700; font-size: 14px; }}
QPushButton.PrimaryButton {{ background-color: {t['blue']}; color: {t['base']}; border: none; }}
QPushButton.SecondaryButton {{ background-color: {t['surface1']}; color: {t['text']}; border: 1px solid {t['surface2']}; }}
QPushButton.DangerButton {{ background-color: {t['red']}; color: {t['base']}; border: none; }}

/* Tooltips */
QToolTip {{ background-color: {t['surface1']}; color: {t['text']}; border: 1px solid {t['blue']}; padding: 4px 8px; border-radius: 4px; font-size: 12px; }}
"""

V2_STYLESHEET = """
/* --- Global Base --- */
QWidget {
    background-color: #24273a; /* App Background */
    color: #ffffff;            /* Text Primary */
    font-family: 'Segoe UI', 'Roboto', sans-serif;
    font-size: 14px;
}

/* Prevent blocky background rectangles behind text labels */
QLabel {
    background: transparent;
    color: #e6eaf6;
}

/* --- Sidebar: Gradient Depth --- */
QFrame#Sidebar {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #24273a, stop:1 #1e2030);
    border-right: 1px solid #363a4f;
}

QLabel#SidebarTitle {
    color: #8aadf4; 
    font-size: 18px;
    font-weight: 800;
    padding: 20px 0;
    margin-bottom: 20px;
    /* Text Glow Effect */
    qproperty-alignment: AlignCenter;
}

/* Sidebar Navigation Buttons */
QPushButton[class="NavButton"], QPushButton.NavButton {
    background-color: transparent;
    color: #a5adcb;
    text-align: left;
    padding: 12px 20px; 
    border: none;
    border-left: 3px solid transparent; 
    font-weight: 600;
    font-size: 14px;
    margin-bottom: 2px;
}

QPushButton[class="NavButton"]:hover, QPushButton.NavButton:hover {
    background-color: rgba(138, 173, 244, 0.1); /* Subtle Blue Tint */
    color: #ffffff;
}

QPushButton[class="NavButton"]:checked, QPushButton.NavButton:checked {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(138, 173, 244, 0.2), stop:1 transparent);
    color: #8aadf4; 
    border-left: 3px solid #8aadf4;
}

QPushButton[class="NavButton"]:focus, QPushButton.NavButton:focus {
    border-left: 3px solid #f4dbd6;
    background-color: rgba(138, 173, 244, 0.16);
    color: #ffffff;
}

/* Tooltips */
QToolTip {
    background-color: #181926;
    color: #cad3f5;
    border: 1px solid #8aadf4;
    padding: 4px 8px;
    border-radius: 4px;
}

/* --- Header / Content --- */
QWidget#ContentArea {
    background-color: #24273a;
}

QLabel#PageTitle {
    font-size: 26px;
    font-weight: 800;
    color: #ffffff;
    margin-bottom: 20px;
    letter-spacing: 0.2px;
}

/* --- Cards / Panels: The "Pop" --- */
QFrame[class="Card"], QFrame.Card {
    background-color: #1e1e2e; 
    border: 1px solid #363a4f; /* Subtle border returned for definition */
    border-top: 1px solid #5b6078; /* Top Highlight for "Lighting" effect */
    border-radius: 12px;
}

QFrame[class="Card"]:hover, QFrame.Card:hover {
    border: 1px solid #494d64;
    border-top: 1px solid #6e738d;
    background-color: #262938; /* Slight lift */
}

/* Special Styling for Live Panel to make it a focal point */
QFrame#LivePanel {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1e1e2e, stop:1 #24273a);
    border: 1px solid #8aadf4; /* Blue border to signify activity center */
    border-top: 2px solid #8aadf4; /* Stronger top highlight */
}

QLabel[class="CardTitle"], QLabel.CardTitle {
    color: #cad3f5; 
    font-size: 14px; 
    font-weight: 700;
    letter-spacing: 0.2px;
}

QLabel[class="CardValue"], QLabel.CardValue {
    color: #ffffff;
    font-size: 32px; 
    font-weight: 800;
}

QLabel[class="CardHelper"], QLabel.CardHelper {
    color: #a5adcb;
    font-size: 11px;
}

QLabel[class="ActivityLabel"], QLabel.ActivityLabel {
    color: #a5adcb;
    font-weight: 600;
    font-size: 13px;
}

QLabel[class="ActivityValue"], QLabel.ActivityValue {
    color: #ffffff;
    font-family: Menlo, Monaco, 'Courier New', monospace;
    font-size: 13px;
}

QLabel[class="SectionTitle"], QLabel.SectionTitle {
    color: #cad3f5;
    font-size: 18px;
    font-weight: bold;
}

QLabel[class="DropIcon"], QLabel.DropIcon {
    font-size: 48px;
    border: none;
    background: transparent;
}

QLabel[class="DropText"], QLabel.DropText {
    font-size: 14px;
    font-weight: bold;
    color: #f4b860;
    border: none;
    background: transparent;
}

QLabel[class="DropHint"], QLabel.DropHint {
    font-size: 11px;
    color: #a7a199;
    border: none;
    background: transparent;
}

QLabel[class="HelperText"], QLabel.HelperText {
    font-size: 12px;
    color: #a7a59b;
    background: transparent;
    border: none;
}

/* --- Status Pills --- */
QLabel[class="StatusPill"], QLabel.StatusPill {
    background-color: #363a4f;
    color: #cba6f7;
    border-radius: 12px;
    padding: 6px 14px;
    font-weight: bold;
    font-size: 11px;
    text-transform: uppercase;
    border: 1px solid transparent;
}

/* --- Controls: Inputs --- */
QLineEdit, QSpinBox, QComboBox {
    background-color: #181926; 
    border: 1px solid #494d64; 
    border-radius: 8px;
    padding: 12px;
    color: #ffffff;
    font-size: 14px;
}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 2px solid #f4dbd6;
    background-color: #1e2030;
}

/* Drag Zone (Input) */
QFrame#DragZone {
    border: 2px dashed #8aadf4; 
    background-color: rgba(138, 173, 244, 0.08); 
    border-radius: 16px;
}
QFrame#DragZone:hover {
    background-color: rgba(138, 173, 244, 0.15);
    border-color: #b7bdf8;
}

/* Tables */
QTableWidget {
    background-color: #1e1e2e; 
    border: none; 
    border-radius: 8px;
    gridline-color: #363a4f; 
}

QTableWidget::item {
    border-bottom: 1px solid #2a2d3e; 
    padding: 9px 10px;
    color: #e8ebf7;
    background: transparent;
}

QTableWidget::item:selected {
    background-color: rgba(138, 173, 244, 0.2);
    color: #ffffff;
}

QTableWidget::item:hover {
    background-color: #2a2d3e; 
}

QHeaderView::section {
    background-color: #181926; 
    padding: 10px 12px;
    border: none;
    border-bottom: 2px solid #8aadf4; /* Accent underline for header */
    font-weight: 700;
    color: #eaf0ff;
    font-size: 13px;
}

/* Scrollbars */
QScrollBar:vertical {
    background-color: #1e2030;
    width: 12px;
    border-radius: 6px;
}
QScrollBar::handle:vertical {
    background-color: #494d64;
    border-radius: 6px;
    border: 2px solid #1e2030; /* Pseudo padding */
}
QScrollBar::handle:vertical:hover {
    background-color: #5b6078;
}

/* --- BUTTON SYSTEM (VIBRANT) --- */

QPushButton {
    border-radius: 8px;
    padding: 10px 20px;
    font-weight: 700;
    font-size: 14px;
    border: 1px solid transparent;
}

QPushButton:focus {
    border: 2px solid #f4dbd6;
}

/* 1. Primary: Blue Gradient */
QPushButton[class="PrimaryButton"], QPushButton.PrimaryButton, QPushButton#PrimaryButton {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8aadf4, stop:1 #6d96e8);
    color: #1e2030; 
    border-top: 1px solid rgba(255,255,255,0.2); /* Highlight */
}
QPushButton[class="PrimaryButton"]:hover, QPushButton.PrimaryButton:hover, QPushButton#PrimaryButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #b7bdf8, stop:1 #8aadf4);
}
QPushButton[class="PrimaryButton"]:pressed, QPushButton.PrimaryButton:pressed, QPushButton#PrimaryButton:pressed {
    background-color: #6d96e8;
    margin-top: 1px;
}
QPushButton[class="PrimaryButton"]:disabled, QPushButton.PrimaryButton:disabled, QPushButton#PrimaryButton:disabled {
    background-color: #363a4f;
    color: #c2c8df;
    border: none;
}

/* 2. Secondary: Neutral / Surface */
QPushButton[class="SecondaryButton"], QPushButton.SecondaryButton, QPushButton#SecondaryButton {
    background-color: #363a4f; 
    color: #ffffff;
    border: 1px solid #494d64;
}
QPushButton[class="SecondaryButton"]:hover, QPushButton.SecondaryButton:hover, QPushButton#SecondaryButton:hover {
    background-color: #494d64;
    border-color: #5b6078;
}
QPushButton[class="SecondaryButton"]:disabled, QPushButton.SecondaryButton:disabled, QPushButton#SecondaryButton:disabled {
    background-color: #363a4f;
    color: #6e738d;
    border: 1px solid #363a4f;
}

/* 3. Danger: Red Gradient */
QPushButton[class="DangerButton"], QPushButton.DangerButton, QPushButton#DangerButton {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ed8796, stop:1 #d25e6d);
    color: #1e2030; 
    border-top: 1px solid rgba(255,255,255,0.2);
}
QPushButton[class="DangerButton"]:hover, QPushButton.DangerButton:hover, QPushButton#DangerButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f5bde6, stop:1 #ed8796);
}
QPushButton[class="DangerButton"]:disabled, QPushButton.DangerButton:disabled, QPushButton#DangerButton:disabled {
    background-color: #363a4f;
    color: #6e738d;
    border: 1px solid #363a4f;
}

/* Dashboard Profile Dock (right-side utility component) */
QFrame#DashboardProfilePanel {
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(30, 30, 46, 0.96),
        stop:1 rgba(36, 39, 58, 0.96)
    );
    border: 1px solid #3a3f59;
    border-top: 1px solid #667091;
    border-radius: 14px;
}

QFrame#DashboardProfilePanel:hover {
    border-color: #5b6078;
    border-top-color: #7ea7ff;
}

QLabel#DashboardProfileIcon {
    background-color: rgba(138, 173, 244, 0.10);
    border: 1px solid rgba(138, 173, 244, 0.22);
    border-radius: 9px;
    padding: 0;
}

QLabel#DashboardProfileEyebrow {
    color: #cad3f5;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.9px;
}

QLabel#DashboardProfileMeta {
    color: #a5adcb;
    font-size: 12px;
    font-weight: 600;
}

QComboBox#DashboardProfileCombo {
    min-height: 40px;
    padding: 6px 42px 6px 12px;
    border-radius: 12px;
    background-color: #171927;
    border: 1px solid #4d5675;
    color: #ffffff;
    font-weight: 600;
    selection-background-color: #8aadf4;
    selection-color: #1e2030;
}

QComboBox#DashboardProfileCombo:hover {
    border-color: #677297;
    background-color: #1b1e30;
}

QComboBox#DashboardProfileCombo:focus {
    border: 1px solid #8aadf4;
    background-color: #1b1e30;
}

QComboBox#DashboardProfileCombo::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 40px;
    background-color: #101321;
    border-left: 1px solid #4d5675;
    border-top-right-radius: 11px;
    border-bottom-right-radius: 11px;
}

QComboBox#DashboardProfileCombo::down-arrow {
    image: none;
    width: 0;
    height: 0;
}

QComboBox#DashboardProfileCombo:on {
    border-color: #8aadf4;
}

QComboBox#DashboardProfileCombo:on::drop-down {
    border-left-color: #8aadf4;
    background-color: #151a2c;
}

QPushButton#DashboardProfileAction {
    min-height: 40px;
    padding: 8px 16px;
    border-radius: 10px;
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #323a56, stop:1 #2a3148);
    color: #e6eaf6;
    border: 1px solid #505d81;
    border-top: 1px solid #7b89b6;
    font-weight: 700;
}

QPushButton#DashboardProfileAction:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3c4670, stop:1 #303a58);
    border-color: #8aadf4;
    color: #ffffff;
}

QPushButton#DashboardProfileAction:pressed {
    background-color: #2b3044;
}
"""
