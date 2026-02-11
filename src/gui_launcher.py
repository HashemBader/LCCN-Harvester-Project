"""
Module: gui_launcher.py
Launcher script for the LCCN Harvester GUI
"""
import os
import sys
from pathlib import Path

# Resolve stable paths regardless of how PyCharm launches this file.
SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent

# Ensure src is in the import path
sys.path.insert(0, str(SRC_DIR))

from PyQt6.QtWidgets import QApplication
from gui.main_window import MainWindow
#from gui.styles import MODERN_STYLE


def _configure_runtime_environment():
    """Make runtime deterministic across IDE/terminal launches."""
    # Ensure all relative data/config/docs paths resolve from project root.
    os.chdir(PROJECT_ROOT)

    # Prefer certifi bundle for SSL if caller has not configured one.
    if not os.getenv("SSL_CERT_FILE"):
        try:
            import certifi  # type: ignore

            os.environ["SSL_CERT_FILE"] = certifi.where()
        except Exception:
            pass

    if os.getenv("SSL_CERT_FILE") and not os.getenv("REQUESTS_CA_BUNDLE"):
        os.environ["REQUESTS_CA_BUNDLE"] = os.environ["SSL_CERT_FILE"]


def main():
    """Launch the LCCN Harvester GUI application."""
    _configure_runtime_environment()
    app = QApplication(sys.argv)

    # Set application metadata
    app.setApplicationName("LCCN Harvester")
    app.setOrganizationName("UPEI Library")
    app.setApplicationVersion("1.0.0")

    # Apply global stylesheet
    #app.setStyleSheet(MODERN_STYLE)

    # Create and show main window
    window = MainWindow()
    window.show()

    # Start event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
