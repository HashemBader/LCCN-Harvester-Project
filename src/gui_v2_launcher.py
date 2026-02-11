"""
Module: gui_v2_launcher.py
Launcher for the V2 Modern GUI (Sidebar + Catppuccin Theme).
"""
import sys
from pathlib import Path

# Ensure project root is in the path (so 'src.utils' imports work)
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

# Also ensure src is in path for local relative imports if needed
sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication
from src.gui.modern_window import ModernMainWindow

def main():
    """Launch the V2 GUI application."""
    app = QApplication(sys.argv)

    # Set application metadata
    app.setApplicationName("LCCN Harvester Pro V2")
    app.setOrganizationName("UPEI Library")
    app.setApplicationVersion("2.0.0")

    # Create and show main window (Style is applied inside the class now)
    window = ModernMainWindow()
    window.show()

    # Start event loop
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
