"""
styles_v2.py
Professional V2 Theme (Catppuccin Macchiato).
Polish: Borderless Cards, Soft Shadows, Unified Button System.
"""

CATPPUCCIN_THEME = """
/* --- Global Base --- */
QWidget {
    background-color: #24273a; /* App Background */
    color: #ffffff;            /* Text Primary */
    font-family: 'Segoe UI', 'Roboto', sans-serif;
    font-size: 14px;
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
QPushButton.NavButton {
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

QPushButton.NavButton:hover {
    background-color: rgba(138, 173, 244, 0.1); /* Subtle Blue Tint */
    color: #ffffff;
}

QPushButton.NavButton:checked {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(138, 173, 244, 0.2), stop:1 transparent);
    color: #8aadf4; 
    border-left: 3px solid #8aadf4;
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
}

/* --- Cards / Panels: The "Pop" --- */
QFrame.Card {
    background-color: #1e1e2e; 
    border: 1px solid #363a4f; /* Subtle border returned for definition */
    border-top: 1px solid #5b6078; /* Top Highlight for "Lighting" effect */
    border-radius: 12px;
}

QFrame.Card:hover {
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

QLabel.CardTitle {
    color: #cad3f5; 
    font-size: 13px; 
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.2px;
}

QLabel.CardValue {
    color: #ffffff;
    font-size: 32px; 
    font-weight: 800;
}

/* --- Status Pills --- */
QLabel.StatusPill {
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
    border: 1px solid #8aadf4; 
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
    padding: 10px;
    color: #ffffff;
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
    padding: 12px;
    border: none;
    border-bottom: 2px solid #8aadf4; /* Accent underline for header */
    font-weight: 800;
    color: #ffffff;
    text-transform: uppercase;
    font-size: 12px;
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
    font-size: 13px;
    border: 1px solid transparent;
}

/* 1. Primary: Blue Gradient */
QPushButton.PrimaryButton, QPushButton#PrimaryButton {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8aadf4, stop:1 #6d96e8);
    color: #1e2030; 
    border-top: 1px solid rgba(255,255,255,0.2); /* Highlight */
}
QPushButton.PrimaryButton:hover, QPushButton#PrimaryButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #b7bdf8, stop:1 #8aadf4);
}
QPushButton.PrimaryButton:pressed, QPushButton#PrimaryButton:pressed {
    background-color: #6d96e8;
    margin-top: 1px;
}
QPushButton.PrimaryButton:disabled, QPushButton#PrimaryButton:disabled {
    background-color: #363a4f;
    color: #5b6078;
    border: none;
}

/* 2. Secondary: Neutral / Surface */
QPushButton.SecondaryButton, QPushButton#SecondaryButton {
    background-color: #363a4f; 
    color: #ffffff;
    border: 1px solid #494d64;
}
QPushButton.SecondaryButton:hover, QPushButton#SecondaryButton:hover {
    background-color: #494d64;
    border-color: #5b6078;
}

/* 3. Danger: Red Gradient */
QPushButton.DangerButton, QPushButton#DangerButton {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ed8796, stop:1 #d25e6d);
    color: #1e2030; 
    border-top: 1px solid rgba(255,255,255,0.2);
}
QPushButton.DangerButton:hover, QPushButton#DangerButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f5bde6, stop:1 #ed8796);
}
"""
