"""
styles_v2.py
Professional V2 Theme (Catppuccin).
Dynamically generated light and dark modes.
"""

CATPPUCCIN_DARK = {
    # Base Abstractions (High Contrast Dark)
    "bg": "#111827",               # Tailwind Gray-900 (Deep background)
    "surface": "#1f2937",          # Tailwind Gray-800 (Cards and panels)
    "surface2": "#374151",         # Tailwind Gray-700 (Raised panels / headers)
    "border": "#4b5563",           # Tailwind Gray-600 (Clear structural lines)
    "border_strong": "#6b7280",    # Tailwind Gray-500 (Strong dividers/focus)
    
    # Text
    "text": "#f9fafb",             # Tailwind Gray-50 (Crisp white)
    "text_muted": "#9ca3af",       # Tailwind Gray-400 (Readable secondary text)
    
    # Semantic States
    "primary": "#3b82f6",          # Blue
    "success": "#22c55e",          # Green
    "warning": "#f59e0b",          # Amber
    "danger": "#ef4444",           # Red
    
    # Interactive States
    "hover": "#374151",            # Gray-700 (Hover bg)
    "focus": "#60a5fa",            # Blue-400
    "shadow": "#030712",           # Deep dark for bottom-borders
}

CATPPUCCIN_LIGHT = {
    # Base Abstractions (High Contrast Light)
    "bg": "#f3f4f6",               # Tailwind Gray-100 (Subtle application background)
    "surface": "#ffffff",          # Pure white cards
    "surface2": "#f8fafc",         # Slate-50 for headers
    "border": "#cbd5e1",           # Slate-300 (Very sharp visible borders)
    "border_strong": "#94a3b8",    # Slate-400 (Strong dividers)
    
    # Text
    "text": "#0f172a",             # Slate-900 (Near black)
    "text_muted": "#64748b",       # Slate-500 (Clear secondary text)
    
    # Semantic States
    "primary": "#2563eb",          # Blue
    "success": "#16a34a",          # Green
    "warning": "#d97706",          # Amber
    "danger": "#dc2626",           # Red
    
    # Interactive States
    "hover": "#f1f5f9",            # Slate-100
    "focus": "#3b82f6",            # Blue-500
    "shadow": "#e2e8f0",           # Slate-200 (Drop shadow simulation)
}

CATPPUCCIN_THEME = CATPPUCCIN_DARK

def generate_stylesheet(theme: dict) -> str:
    """Returns fully dynamic stylesheet string."""
    t = theme

    def hex_to_rgba(hex_str, alpha):
        """Safely convert #RRGGBB to rgba(r,g,b,a) for PyQt styling."""
        hex_str = hex_str.lstrip('#')
        # Handle 6-digit hexes safely
        if len(hex_str) == 6:
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
    import tempfile
    import os
    def get_svg_file(svg_string, color_hex, name):
        colored = svg_string.replace('CURRENT_COLOR', color_hex)
        temp_dir = tempfile.gettempdir()
        filename = f"{name}_{color_hex.replace('#', '')}.svg"
        path = os.path.join(temp_dir, filename).replace('\\', '/')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(colored)
        return path
        
    chevron_down = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='CURRENT_COLOR' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><polyline points='6 9 12 15 18 9'></polyline></svg>"
    chevron_up = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='CURRENT_COLOR' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><polyline points='18 15 12 9 6 15'></polyline></svg>"

    return f"""/* --- Global Base --- */
QWidget {{
    background-color: {t['bg']}; /* App Background */
    color: {t['text']};            /* Text Primary */
    font-family: 'Segoe UI', 'Roboto', sans-serif;
    font-size: 14px;
}}

/* Prevent blocky background rectangles behind text labels */
QLabel {{
    background: transparent;
    color: {t['text_muted']};
}}

/* --- Sidebar: Gradient Depth --- */
QFrame#Sidebar {{
    background-color: {t['bg']};
    border-right: 1px solid {t['border']};
}}

QLabel#SidebarTitle {{
    color: {t['primary']}; 
    font-size: 18px;
    font-weight: 800;
    padding: 20px 0;
    margin-bottom: 20px;
    qproperty-alignment: AlignCenter;
}}

/* Sidebar Navigation Buttons */
QPushButton[class="NavButton"], QPushButton.NavButton, QPushButton#NavButton {{
    background-color: transparent;
    color: {t['text_muted']};
    text-align: left;
    padding: 12px 20px; 
    border: none;
    border-left: 3px solid transparent; 
    font-weight: 600;
    font-size: 14px;
    margin-bottom: 2px;
    outline: none;
}}

QPushButton[class="NavButton"]:hover, QPushButton.NavButton:hover, QPushButton#NavButton:hover {{
    background-color: {t['hover']}; 
    color: {t['text']};
    border-left: 3px solid transparent;
}}

QPushButton[class="NavButton"]:checked, QPushButton.NavButton:checked, QPushButton#NavButton:checked {{
    background-color: {hex_to_rgba(t['primary'], 0.1)};
    color: {t['primary']}; 
    border-left: 3px solid {t['primary']};
}}

QPushButton[class="NavButton"]:pressed, QPushButton.NavButton:pressed, QPushButton#NavButton:pressed {{
    background-color: {hex_to_rgba(t['primary'], 0.15)};
    color: {t['primary']};
    border-left: 3px solid {t['primary']};
}}

QPushButton[class="NavButton"]:focus, QPushButton.NavButton:focus, QPushButton#NavButton:focus {{
    border-left: 3px solid {t['primary']};
    background-color: {hex_to_rgba(t['primary'], 0.1)};
    color: {t['text']};
}}

/* Tooltips */
QToolTip {{
    background-color: {t['surface']};
    color: {t['text_muted']};
    border: 1px solid {t['primary']};
    padding: 4px 8px;
    border-radius: 4px;
}}

/* --- Header / Content --- */
QWidget#ContentArea {{
    background-color: {t['bg']};
}}

QLabel#PageTitle {{
    font-size: 26px;
    font-weight: 800;
    color: {t['text']};
    margin-bottom: 20px;
    letter-spacing: 0.2px;
}}

/* --- Cards / Panels: The Space Context --- */
QFrame[class="Card"], QFrame.Card {{
    background-color: {t['surface']}; 
    border: 1px solid {t['border']}; 
    border-bottom: 2px solid {t['shadow']}; /* Simulated Box Shadow Drop */
    border-radius: 12px;
}}

QFrame[class="Card"]:hover, QFrame.Card:hover {{
    border: 1px solid {t['primary']};
    border-bottom: 2px solid {t['primary']};
}}

/* Special Styling for Live Panel to make it a focal point */
QFrame#LivePanel {{
    background-color: {t['surface']};
    border: 1px solid {t['primary']}; 
    border-top: 2px solid {t['primary']}; 
}}

QLabel[class="CardTitle"], QLabel.CardTitle {{
    color: {t['text_muted']}; 
    font-size: 14px; 
    font-weight: 700;
    letter-spacing: 0.2px;
}}

QLabel[class="CardValue"], QLabel.CardValue {{
    color: {t['text']};
    font-size: 32px; 
    font-weight: 800;
}}

QLabel[class="CardHelper"], QLabel.CardHelper {{
    color: {t['text_muted']};
    font-size: 11px;
}}

QLabel[class="ActivityLabel"], QLabel.ActivityLabel {{
    color: {t['text_muted']};
    font-weight: 600;
    font-size: 13px;
}}

QLabel[class="ActivityValue"], QLabel.ActivityValue {{
    color: {t['text']};
    font-family: Menlo, Monaco, 'Courier New', monospace;
    font-size: 13px;
}}

QLabel[class="SectionTitle"], QLabel.SectionTitle {{
    color: {t['text_muted']};
    font-size: 18px;
    font-weight: bold;
}}

QLabel[class="DropIcon"], QLabel.DropIcon {{
    font-size: 48px;
    border: none;
    background: transparent;
}}

QLabel[class="DropText"], QLabel.DropText {{
    font-size: 14px;
    font-weight: bold;
    color: {t['warning']};
    border: none;
    background: transparent;
}}

QLabel[class="DropHint"], QLabel.DropHint {{
    font-size: 11px;
    color: {t['text_muted']};
    border: none;
    background: transparent;
}}

QLabel[class="HelperText"], QLabel.HelperText {{
    font-size: 12px;
    color: {t['text_muted']};
    background: transparent;
    border: none;
}}

/* --- Status Pills --- */
QLabel[class="StatusPill"], QLabel.StatusPill {{
    background-color: transparent;
    color: {t['text_muted']};
    border-radius: 0;
    padding: 0;
    min-height: 0;
    max-height: 16777215;
    font-weight: bold;
    font-size: 11px;
    text-transform: uppercase;
    border: none;
}}

QLabel[class="StatusPill"][state="running"], QLabel.StatusPill[state="running"] {{
    color: {t['primary']};
}}

QLabel[class="StatusPill"][state="paused"], QLabel.StatusPill[state="paused"] {{
    color: {t['warning']};
}}

QLabel[class="StatusPill"][state="error"], QLabel.StatusPill[state="error"] {{
    color: {t['danger']};
}}

QLabel[class="StatusPill"][state="success"], QLabel.StatusPill[state="success"] {{
    color: {t['success']};
}}

QLabel[class="StatusPill"][state="idle"], QLabel.StatusPill[state="idle"] {{
    color: {t['text_muted']};
}}

/* --- Controls: Inputs --- */
QLineEdit, QSpinBox, QTextEdit, QPlainTextEdit {{
    background-color: {t['bg']}; 
    border: 1px solid {t['border']}; 
    border-radius: 8px;
    padding: 12px;
    color: {t['text']};
    font-size: 14px;
}}

QLineEdit:focus, QSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 2px solid {t['focus']};
    background-color: {t['surface']};
}}

/* Stronger Affordance for Dropdowns */
QComboBox {{
    background-color: {t['bg']}; 
    border: 1px solid {t['border_strong']}; 
    border-radius: 8px;
    padding: 12px;
    color: {t['text']};
    font-size: 14px;
}}

QComboBox:hover {{
    background-color: {t['hover']};
}}

QComboBox:focus {{
    border: 2px solid {t['focus']};
    background-color: {t['surface']};
}}

/* Ensure dropdown menus don't inherit OS native green selections */
QComboBox QAbstractItemView {{
    background-color: {t['bg']};
    border: 1px solid {t['border']};
    selection-background-color: {t['hover']};
    selection-color: {t['focus']};
    border-radius: 4px;
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 32px;
    border-left: 1px solid {t['border_strong']};
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    background: transparent;
}}
QComboBox::down-arrow {{
    image: url("{get_svg_file(chevron_down, t['text_muted'], 'chevron_down')}");
    width: 16px;
    height: 16px;
}}
QComboBox::down-arrow:on, QComboBox::down-arrow:hover, QComboBox::down-arrow:focus {{
    image: url("{get_svg_file(chevron_down, t['focus'], 'chevron_down')}");
}}

/* Rank column combo — tighter vertical padding so the number isn't clipped */
QComboBox#RankCombo {{
    padding: 4px 32px 4px 8px;
}}

/* Clean up QSpinBox arrows to avoid dark system patches */
QSpinBox::up-button, QSpinBox::down-button {{
    background: transparent;
    border: none;
    width: 20px;
}}
QSpinBox::up-arrow {{
    image: url("{get_svg_file(chevron_up, t['text_muted'], 'chevron_up')}");
    width: 14px;
    height: 14px;
}}
QSpinBox::down-arrow {{
    image: url("{get_svg_file(chevron_down, t['text_muted'], 'chevron_down')}");
    width: 14px;
    height: 14px;
}}
QSpinBox::up-arrow:hover, QSpinBox::down-arrow:hover {{
    image: url("{get_svg_file(chevron_up, t['focus'], 'chevron_up')}");
}}


/* Scroll Areas */
QScrollArea[class="ScrollArea"], QScrollArea.ScrollArea {{
    background: transparent;
    border: none;
}}

/* Drag Zone (Input) */
QFrame#DragZone, QFrame[class="DragZone"] {{
    border: 2px dashed {t['border_strong']}; 
    background-color: {t['surface']}14; 
    border-radius: 16px;
}}
QFrame#DragZone:hover, QFrame[class="DragZone"]:hover {{
    background-color: {t['hover']}26;
    border-color: {t['focus']};
}}

QFrame[class="DragZone"][state="ready"] {{
    border: 3px dashed {t['warning']};
    background-color: {t['surface']};
}}
QFrame[class="DragZone"][state="ready"]:hover {{
    background-color: {t['hover']}26;
    border-color: {t['warning']};
}}

QFrame[class="DragZone"][state="active"] {{
    border: 3px dashed {t['primary']};
    background-color: {t['surface2']};
}}

QFrame[class="DragZone"][state="success"] {{
    border: 3px solid {t['primary']};
    background-color: {t['surface2']};
}}

/* Tables */
QTableWidget {{
    background-color: {t['surface']}; 
    alternate-background-color: {t['bg']};
    border: 1px solid {t['border']}; 
    border-radius: 8px;
    gridline-color: {t['border']}; 
    outline: none; /* Strip native focus brackets */
    selection-background-color: transparent;
    selection-color: {t['text']};
}}

QTableWidget::item {{
    border-bottom: 1px solid {t['border']};
    padding: 9px 10px;
    color: {t['text']};
    background: transparent;
}}

QTableWidget::item:selected {{
    background-color: transparent;
    color: {t['text']};
}}

QTableWidget::item:hover {{
    background-color: {t['hover']};
}}

QHeaderView::section {{
    background-color: {t['surface2']}; 
    padding: 10px 12px;
    border: none;
    border-bottom: 2px solid {t['border_strong']}; /* Subtle structural underline */
    font-weight: 700;
    color: {t['text']};
    font-size: 13px;
}}

/* Scrollbars */
QScrollBar:vertical {{
    background-color: {t['bg']};
    width: 12px;
    border-radius: 6px;
}}
QScrollBar::handle:vertical {{
    background-color: {t['border']};
    border-radius: 6px;
    border: 2px solid {t['bg']}; /* Pseudo padding */
}}
QScrollBar::handle:vertical:hover {{
    background-color: {t['border_strong']};
}}
QScrollBar:horizontal {{
    background-color: {t['bg']};
    height: 12px;
    border-radius: 6px;
}}
QScrollBar::handle:horizontal {{
    background-color: {t['border']};
    border-radius: 6px;
    border: 2px solid {t['bg']};
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {t['border_strong']};
}}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* --- BUTTON SYSTEM (VIBRANT) --- */

QPushButton {{
    border-radius: 8px;
    padding: 10px 20px;
    font-weight: 700;
    font-size: 14px;
    border: 1px solid transparent;
    outline: none;
}}

QPushButton:focus {{
    border: 2px solid {t['surface2']};
    outline: none;
}}

/* 1. Primary: Blue Fill */
QPushButton[class="PrimaryButton"], QPushButton.PrimaryButton, QPushButton#PrimaryButton {{
    background-color: {t['primary']};
    color: #ffffff; 
    border: 1px solid transparent;
}}
QPushButton[class="PrimaryButton"]:hover, QPushButton.PrimaryButton:hover, QPushButton#PrimaryButton:hover {{
    background-color: {t['focus']};
}}
QPushButton[class="PrimaryButton"]:pressed, QPushButton.PrimaryButton:pressed, QPushButton#PrimaryButton:pressed {{
    background-color: {t['primary']};
    margin-top: 1px;
}}
QPushButton[class="PrimaryButton"]:disabled, QPushButton.PrimaryButton:disabled, QPushButton#PrimaryButton:disabled {{
    background-color: {t['hover']};
    color: {t['text_muted']};
    border: none;
}}

/* 2. Secondary: Neutral / Surface */
QPushButton[class="SecondaryButton"], QPushButton.SecondaryButton, QPushButton#SecondaryButton {{
    background-color: {t['surface']}; 
    color: {t['text']};
    border: 1px solid {t['border']};
}}
QPushButton[class="SecondaryButton"]:hover, QPushButton.SecondaryButton:hover, QPushButton#SecondaryButton:hover {{
    background-color: {t['hover']};
    border-color: {t['border_strong']};
}}
QPushButton[class="SecondaryButton"]:disabled, QPushButton.SecondaryButton:disabled, QPushButton#SecondaryButton:disabled {{
    background-color: {t['surface']};
    color: {t['text_muted']};
    border: 1px solid {t['border']};
}}

/* 3. Danger: Red Fill */
QPushButton[class="DangerButton"], QPushButton.DangerButton, QPushButton#DangerButton {{
    background-color: {t['danger']};
    color: #ffffff; 
    border: 1px solid transparent;
}}
QPushButton[class="DangerButton"]:hover, QPushButton.DangerButton:hover, QPushButton#DangerButton:hover {{
    background-color: {t['focus']};
}}
QPushButton[class="DangerButton"]:disabled, QPushButton.DangerButton:disabled, QPushButton#DangerButton:disabled {{
    background-color: {t['hover']};
    color: {t['text_muted']};
    border: none;
}}

/* Dashboard Profile Dock (right-side utility component) */
QFrame#DashboardProfilePanel {{
    background-color: {t['surface']};
    border: 1px solid {t['border']};
    border-top: 2px solid {t['border_strong']};
    border-radius: 14px;
}}

QFrame#DashboardProfilePanel:hover {{
    border-color: {t['border_strong']};
}}

QLabel#DashboardProfileIcon {{
    background: transparent;
    border: none;
    border-radius: 9px;
    padding: 0;
}}

QLabel#DashboardProfileEyebrow {{
    color: {t['text_muted']};
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.9px;
}}

QLabel#DashboardProfileMeta {{
    color: {t['text_muted']};
    font-size: 12px;
    font-weight: 600;
}}

QComboBox#DashboardProfileCombo {{
    min-height: 40px;
    padding: 6px 42px 6px 12px;
    border-radius: 12px;
    background-color: {t['bg']};
    border: 1px solid {t['border']};
    color: {t['text']};
    font-weight: 600;
    selection-background-color: {t['primary']};
    selection-color: #ffffff;
}}

QComboBox#DashboardProfileCombo:hover {{
    border-color: {t['primary']};
    background-color: {t['surface']};
}}

QComboBox#DashboardProfileCombo:focus {{
    border: 1px solid {t['primary']};
    background-color: {t['surface']};
}}

QComboBox#DashboardProfileCombo::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 40px;
    background-color: {t['surface']};
    border-left: 1px solid {t['border']};
    border-top-right-radius: 11px;
    border-bottom-right-radius: 11px;
}}

QComboBox#DashboardProfileCombo::down-arrow {{
    image: none;
    width: 0;
    height: 0;
}}

QComboBox#DashboardProfileCombo:on {{
    border-color: {t['primary']};
}}

QComboBox#DashboardProfileCombo:on::drop-down {{
    border-left-color: {t['primary']};
    background-color: {t['hover']};
}}

QPushButton#DashboardProfileAction {{
    min-height: 40px;
    padding: 8px 16px;
    border-radius: 10px;
    background-color: {t['surface']};
    color: {t['text_muted']};
    border: 1px solid {t['border']};
    border-top: 1px solid {t['border_strong']};
    font-weight: 700;
}}

QPushButton#DashboardProfileAction:hover {{
    background-color: {t['hover']};
    border-color: {t['primary']};
    color: {t['text']};
}}

QPushButton#DashboardProfileAction:pressed {{
    background-color: {t['surface2']};
}}

/* Harvester Banner Success State */
QFrame#HarvestBanner[state="completed"] {{
    background-color: {t['success']};
    border: 1px solid {t['success']};
}}

QFrame#HarvestBanner[state="completed"] QLabel {{
    color: {t['text']};
}}

/* --- Links & Utilities --- */
QPushButton[class="LinkButton"], QPushButton.LinkButton {{
    color: {t['primary']};
    text-decoration: underline;
    background: transparent;
    border: none;
}}
QPushButton[class="LinkButton"]:hover, QPushButton.LinkButton:hover {{
    color: {t['focus']};
}}

QFrame[class="Divider"], QFrame.Divider {{
    color: {t['border']};
    background-color: {t['border']};
    min-height: 1px;
    max-height: 1px;
}}

/* --- Progress Bars --- */
QProgressBar[class="TerminalProgressBar"], QProgressBar.TerminalProgressBar {{
    background-color: {t['surface']}; 
    height: 8px; 
    border-radius: 4px; 
    border: none;
}}
QProgressBar[class="TerminalProgressBar"]::chunk, QProgressBar.TerminalProgressBar::chunk {{
    background-color: {t['primary']}; 
    border-radius: 4px; 
}}
QProgressBar[class="TerminalProgressBar"][state="success"]::chunk, QProgressBar.TerminalProgressBar[state="success"]::chunk {{
    background-color: {t['success']}; 
}}
QProgressBar[class="TerminalProgressBar"][state="error"]::chunk, QProgressBar.TerminalProgressBar[state="error"]::chunk, QProgressBar[class="TerminalProgressBar"][state="cancelled"]::chunk, QProgressBar.TerminalProgressBar[state="cancelled"]::chunk {{
    background-color: {t['danger']}; 
}}
QProgressBar[class="TerminalProgressBar"][state="paused"]::chunk, QProgressBar.TerminalProgressBar[state="paused"]::chunk {{
    background-color: {t['warning']}; 
}}

/* --- Targets Tab Classes --- */
QLabel[class="Banner"], QLabel.Banner {{
    color: {t['text_muted']};
    background-color: {t['surface']};
    border-left: 3px solid {t['primary']};
    padding: 10px;
    border-radius: 6px;
    font-size: 11px;
}}

QWidget[class="SearchContainer"], QWidget.SearchContainer {{
    background-color: {t['bg']};
    border: 1px solid {t['border']};
    border-radius: 4px;
}}
QWidget[class="SearchContainer"] QLineEdit, QWidget.SearchContainer QLineEdit {{
    background-color: transparent;
    border: none;
    color: {t['text']};
    padding: 4px 8px;
    min-width: 180px;
}}
QWidget[class="SearchContainer"] QToolButton, QWidget.SearchContainer QToolButton {{
    background-color: transparent;
    border: none;
    border-radius: 2px;
    color: {t['text']};
    font-weight: bold;
    font-size: 16px;
}}
QWidget[class="SearchContainer"] QToolButton:hover, QWidget.SearchContainer QToolButton:hover {{
    background-color: {t['border']};
    color: {t['text']};
}}

QPushButton[class="IconButton"], QPushButton.IconButton {{
    background-color: {t['bg']};
    border: 2px solid {t['border']};
    border-radius: 8px;
}}
QPushButton[class="IconButton"]:hover, QPushButton.IconButton:hover {{
    background-color: {t['hover']};
    border-color: {t['primary']};
}}

/* --- Group Boxes --- */
QGroupBox {{
    background-color: transparent;
    border: 1px solid {t['border']};
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 14px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: {t['text_muted']};
    font-weight: bold;
    font-size: 13px;
}}

/* --- Harvest Tab Status Box --- */
QFrame[class="HarvestStatus"], QFrame.HarvestStatus {{
    background-color: {t['surface']};
    border-radius: 8px;
    border: 1px solid {t['border_strong']};
    border-left: 4px solid {t['border']};
}}
QFrame[class="HarvestStatus"][state="ready"], QFrame.HarvestStatus[state="ready"] {{
    border-left-color: {t['primary']};
}}
QFrame[class="HarvestStatus"][state="running"], QFrame.HarvestStatus[state="running"] {{
    border-left-color: {t['primary']};
}}
QFrame[class="HarvestStatus"][state="paused"], QFrame.HarvestStatus[state="paused"] {{
    border-left-color: {t['warning']};
}}
QFrame[class="HarvestStatus"][state="error"], QFrame.HarvestStatus[state="error"], QFrame.HarvestStatus[state="cancelled"] {{
    border-left-color: {t['danger']};
}}
QFrame[class="HarvestStatus"][state="completed"], QFrame.HarvestStatus[state="completed"] {{
    border-left-color: {t['success']};
}}

QLabel[class="StatusTitle"], QLabel.StatusTitle {{
    font-size: 16px; 
    font-weight: bold; 
    letter-spacing: 1px; 
    border: none;
    color: {t['text_muted']};
}}
QLabel[class="StatusTitle"][state="ready"], QLabel.StatusTitle[state="ready"] {{
    color: {t['primary']};
}}
QLabel[class="StatusTitle"][state="running"], QLabel.StatusTitle[state="running"] {{
    color: {t['primary']};
}}
QLabel[class="StatusTitle"][state="paused"], QLabel.StatusTitle[state="paused"] {{
    color: {t['warning']};
}}
QLabel[class="StatusTitle"][state="error"], QLabel.StatusTitle[state="error"], QLabel.StatusTitle[state="cancelled"] {{
    color: {t['danger']};
}}
QLabel[class="StatusTitle"][state="completed"], QLabel.StatusTitle[state="completed"] {{
    color: {t['success']};
}}

QLabel[class="StatusText"], QLabel.StatusText {{
    font-size: 14px; 
    font-weight: bold;
    color: {t['text_muted']};
}}
QLabel[class="StatusText"][state="ready"], QLabel.StatusText[state="ready"] {{
    color: {t['primary']};
}}
QLabel[class="StatusText"][state="running"], QLabel.StatusText[state="running"] {{
    color: {t['primary']};
}}
QLabel[class="StatusText"][state="paused"], QLabel.StatusText[state="paused"] {{
    color: {t['warning']};
}}
QLabel[class="StatusText"][state="error"], QLabel.StatusText[state="error"], QLabel.StatusText[state="cancelled"] {{
    color: {t['danger']};
}}
QLabel[class="StatusText"][state="completed"], QLabel.StatusText[state="completed"] {{
    color: {t['success']};
}}

QPushButton#ActiveToggle[state="active"] {{
    background-color: {t['success']};
    border: none;
    border-radius: 6px;
}}
QPushButton#ActiveToggle[state="active"]:hover {{
    background-color: {t['focus']};
}}
QPushButton#ActiveToggle[state="inactive"] {{
    background-color: {t['danger']};
    border: none;
    border-radius: 6px;
}}
QPushButton#ActiveToggle[state="inactive"]:hover {{
    background-color: {t['focus']};
}}

QPushButton[class="StatusIndicator"][state="online"] {{
    background-color: {t['success']};
    border: none;
    border-radius: 6px;
    font-weight: bold;
    font-size: 11px;
    color: white;
}}
QPushButton[class="StatusIndicator"][state="offline"] {{
    background-color: {t['danger']};
    border: none;
    border-radius: 6px;
    font-weight: bold;
    font-size: 11px;
    color: white;
}}
QPushButton[class="StatusIndicator"][state="unknown"] {{
    background-color: {t['surface2']};
    border: none;
    border-radius: 6px;
    font-weight: bold;
    font-size: 11px;
    color: {t['text_muted']};
}}
/* --- Shortcuts Dialog --- */
QFrame[class="ShortcutItem"] {{
    background: {t['surface']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 8px;
    margin: 4px;
}}
QFrame[class="ShortcutItem"]:hover {{
    background: {t['hover']};
    border: 1px solid {t['primary']};
}}
QLabel#ShortcutKeys {{
    background: {t['bg']};
    color: {t['primary']};
    font-size: 12px;
    font-weight: bold;
    padding: 6px 12px;
    border-radius: 4px;
    min-width: 120px;
}}
QLabel#ShortcutDesc {{
    color: {t['text']};
    font-size: 13px;
    padding-left: 10px;
}}
QLabel#DialogHeader {{
    color: {t['text']};
    font-size: 24px;
    font-weight: bold;
    padding: 10px;
}}
QLabel#DialogSubtitle {{
    color: {t['text_muted']};
    font-size: 12px;
    padding-bottom: 10px;
}}
QScrollArea[class="TransparentScroll"] {{
    background: transparent;
    border: none;
}}
QLabel#CategoryHeader {{
    color: {t['text']};
    font-size: 16px;
    font-weight: bold;
    padding: 8px;
    border-bottom: 2px solid {t['border_strong']};
    margin-top: 10px;
}}
"""

V2_STYLESHEET = generate_stylesheet(CATPPUCCIN_DARK)
