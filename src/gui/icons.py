"""
SVG icon assets shared across the GUI.

This module contains two kinds of exports:

1. **SVG string constants** (``SVG_*``) — each is a self-contained SVG element
   drawn in a Material / Lucide outline style.  The stroke color is set to the
   placeholder string ``"currentColor"`` so that :func:`get_icon` / :func:`get_pixmap`
   can recolor icons at render time via a simple string substitution.

2. **Helper functions** — :func:`get_icon` and :func:`get_pixmap` rasterize an
   SVG string into a ``QIcon`` / ``QPixmap`` at the requested size and tint.

Usage example::

    from src.gui.icons import SVG_DASHBOARD, get_icon
    btn.setIcon(get_icon(SVG_DASHBOARD, color="#cdd6f4"))
"""

from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtSvg import QSvgRenderer

# --- SVG STRINGS (Material / Lucide Style) ---
#
# Every constant below is a self-contained SVG element drawn at a 24×24
# viewBox with stroke="currentColor".  The literal string "currentColor" is
# replaced at render time by get_icon / get_pixmap with the caller's hex tint,
# so none of these strings contain a hard-coded colour.
#
# Naming convention:
#   SVG_<CONCEPT> — e.g. SVG_DASHBOARD, SVG_HARVEST
# Usage sites: sidebar nav buttons, help-tab badges, harvest-tab controls.

# Four-rectangle dashboard / layout grid — used as the Dashboard nav icon.
SVG_DASHBOARD = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9"></rect><rect x="14" y="3" width="7" height="5"></rect><rect x="14" y="12" width="7" height="9"></rect><rect x="3" y="16" width="7" height="5"></rect></svg>"""

# Document with a folded corner and a plus-in-circle — used as the Input nav icon.
SVG_INPUT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="12" y1="18" x2="12" y2="12"></line><line x1="9" y1="15" x2="15" y2="15"></line></svg>"""

# Globe / crosshair — used as the Targets / Configure nav icon.
SVG_TARGETS = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>"""

# Gear / cog with a centre circle — used as the Settings / Help nav icon.
SVG_SETTINGS = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>"""

# Right-pointing filled triangle (play button) — used as the Harvest nav icon.
SVG_HARVEST = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>"""  # Play-button (filled triangle) shape

# Document with horizontal rule lines — used as the Results / Help header icon.
SVG_RESULTS = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>"""

# Open folder with a raised lid — used for file-picker affordances.
SVG_FOLDER_OPEN = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v1"></path><path d="M3 10h18l-2 8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path></svg>"""

# Abstract chip / circuit node — used as an AI / assistant indicator icon.
SVG_AI = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2 2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"></path><path d="M12 16a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-2a2 2 0 0 1 2-2z"></path><path d="M5 9c0-1.1.9-2 2-2h10a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V9z"></path><line x1="9" y1="12" x2="10" y2="12"></line><line x1="14" y1="12" x2="15" y2="12"></line></svg>"""

# Single left-pointing chevron — used in sidebar collapse controls.
SVG_CHEVRON_LEFT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>"""

# Single right-pointing chevron — used in sidebar expand controls.
SVG_CHEVRON_RIGHT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>"""

# Toggle icons use fill="currentColor" on the track or thumb so the accent
# color fills the shape rather than just stroking it.  The inner circle of
# SVG_TOGGLE_ON is hard-coded to dark (#111827) so it contrasts with the
# tinted track regardless of theme.
#
# SVG_TOGGLE_ON — thumb positioned right, track filled with currentColor (accent).
SVG_TOGGLE_ON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="5" width="22" height="14" rx="7" ry="7" fill="currentColor"></rect><circle cx="16" cy="12" r="3" fill="#111827" stroke="#111827"></circle></svg>"""

# SVG_TOGGLE_OFF — thumb positioned left, track unfilled, thumb filled with currentColor.
SVG_TOGGLE_OFF = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="5" width="22" height="14" rx="7" ry="7"></rect><circle cx="8" cy="12" r="3" fill="currentColor"></circle></svg>"""

# Heartbeat / activity waveform — used in the About section of the Help tab.
SVG_ACTIVITY = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>"""

# Circle with a check mark inside — used for accessibility / success indicators.
SVG_CHECK_CIRCLE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>"""

# Circle with an exclamation mark — used for warning / informational states.
SVG_ALERT_CIRCLE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>"""

# Circle with an × inside — used for error / failure states.
SVG_X_CIRCLE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>"""

# --- Helpers ---

def get_icon(svg_data: str, color: str = "#a5adcb") -> QIcon:
    """Rasterize an SVG string into a 24×24 ``QIcon`` with the given tint color.

    The tint is applied by replacing every occurrence of ``"currentColor"``
    in the SVG text with *color* before rendering.  All ``SVG_*`` constants in
    this module use ``stroke="currentColor"`` precisely so they can be recolored
    at runtime.

    Args:
        svg_data: SVG markup string (typically one of the ``SVG_*`` constants).
        color: CSS hex color string used as the stroke/fill tint.

    Returns:
        A ``QIcon`` backed by a 24×24 transparent ``QPixmap``.
    """
    # Replace the "currentColor" placeholder with the requested tint color.
    colored_svg = svg_data.replace("currentColor", color)

    # Feed the modified SVG bytes into QSvgRenderer for off-screen rasterization.
    renderer = QSvgRenderer(QByteArray(colored_svg.encode('utf-8')))
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)  # ensure transparent background

    # QPainter renders the SVG onto the pixmap; painter must be explicitly ended.
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    return QIcon(pixmap)

def get_pixmap(svg_data: str, color: str = "#a5adcb", size: int = 24) -> QPixmap:
    """Rasterize an SVG string into a square ``QPixmap`` with the given tint color.

    Identical rendering pipeline to :func:`get_icon` but returns a ``QPixmap``
    directly and accepts a configurable *size* so callers can produce icons at
    sizes other than 24 px (e.g. 15 px badge icons in the Help tab).

    Args:
        svg_data: SVG markup string.
        color: CSS hex color string used as the stroke/fill tint.
        size: Width and height in pixels for the output pixmap.

    Returns:
        A ``size × size`` transparent ``QPixmap`` with the SVG rendered into it.
    """
    # Replace "currentColor" placeholder with the requested tint.
    colored_svg = svg_data.replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(colored_svg.encode('utf-8')))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap
