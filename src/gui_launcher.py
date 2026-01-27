"""
Module: gui_launcher.py
Launcher script for the LCCN Harvester GUI
"""
import sys
from pathlib import Path

# Ensure src is in the path
sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication
from gui.main_window import MainWindow


def main():
    """Launch the LCCN Harvester GUI application."""
    app = QApplication(sys.argv)

    # Set application metadata
    app.setApplicationName("LCCN Harvester")
    app.setOrganizationName("UPEI Library")
    app.setApplicationVersion("1.0.0")

    # Create and show main window
    window = MainWindow()
    window.show()

    # Start event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()