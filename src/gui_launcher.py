"""
Module: gui_launcher.py
Part of the LCCN Harvester Project.

Entry point for the LCCN Harvester graphical user interface.

Responsibilities
----------------
1. Resolves the project root and ``src`` directory so that both
   ``from src.xxx`` (absolute) and ``from gui.xxx`` (legacy relative-style)
   package imports work correctly regardless of how the process is started
   (IDE run-config, ``python -m``, direct script invocation, etc.).
2. Sets the working directory to the project root so that all relative
   file paths used by the application (config files, SQLite database, docs)
   resolve consistently.
3. Bootstraps SSL certificate configuration using the ``certifi`` bundle when
   the caller has not already set ``SSL_CERT_FILE`` or ``REQUESTS_CA_BUNDLE``.
4. Creates the ``QApplication`` instance, sets application metadata, creates
   the main window, and enters the Qt event loop.

This module is intended to be run directly (``python src/gui_launcher.py``) or
imported as a package entry point.  The ``main()`` function is the canonical
callable for ``pyproject.toml`` / ``setup.cfg`` console-script hooks.
"""
import os
import sys
from pathlib import Path

# Resolve stable absolute paths at import time so they are available to both
# _configure_runtime_environment() and the sys.path manipulation below.
SRC_DIR = Path(__file__).resolve().parent  # …/src
PROJECT_ROOT = SRC_DIR.parent              # repository root

# Ensure both project root and src are importable regardless of launch mode.
# - PROJECT_ROOT supports absolute package imports like `from src...`
# - SRC_DIR supports legacy imports like `from gui...` / `from utils...`
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from PyQt6.QtWidgets import QApplication
from gui.modern_window import ModernMainWindow


def _configure_runtime_environment():
    """
    Prepare the runtime environment for a consistent GUI session.

    Performs three setup steps before the QApplication is created:

    1. **Working directory**: Changes ``cwd`` to the project root so that all
       relative file paths (SQLite DB, config files, log files) resolve to the
       same location regardless of where the process was launched from.

    2. **SSL certificate bundle**: If ``SSL_CERT_FILE`` is not already set,
       attempts to locate the ``certifi`` CA bundle and export its path.  This
       ensures that HTTPS requests made via ``urllib`` / ``requests`` succeed on
       platforms where the system CA store is incomplete or inaccessible (e.g.
       some macOS / Windows Python distributions).

    3. **requests CA bundle sync**: Propagates ``SSL_CERT_FILE`` into
       ``REQUESTS_CA_BUNDLE`` so the ``requests`` library (used by the API
       harvest modules) picks up the same certificate bundle automatically.
    """
    # Ensure all relative data/config/docs paths resolve from project root.
    os.chdir(PROJECT_ROOT)

    # Prefer certifi bundle for SSL if caller has not configured one.
    if not os.getenv("SSL_CERT_FILE"):
        try:
            import certifi  # type: ignore
            # certifi.where() returns the absolute path to its cacert.pem file.
            os.environ["SSL_CERT_FILE"] = certifi.where()
        except Exception:
            # certifi may not be installed; silently continue with the system store.
            pass

    # Keep requests' CA bundle in sync with the SSL_CERT_FILE we just set.
    if os.getenv("SSL_CERT_FILE") and not os.getenv("REQUESTS_CA_BUNDLE"):
        os.environ["REQUESTS_CA_BUNDLE"] = os.environ["SSL_CERT_FILE"]


def main():
    """
    Launch the LCCN Harvester GUI application.

    Configures the runtime environment, constructs the ``QApplication`` and
    ``ModernMainWindow`` instances, then hands control to the Qt event loop.
    Does not return until the user closes the application window.
    """
    _configure_runtime_environment()
    app = QApplication(sys.argv)

    # Application metadata is used by Qt for OS-level window/taskbar labels,
    # QSettings storage paths, and About dialogs.
    app.setApplicationName("LCCN Harvester")
    app.setOrganizationName("UPEI Library")
    app.setApplicationVersion("1.0.0")

    # Create and show the main application window.
    window = ModernMainWindow()
    window.show()

    # Enter the Qt event loop; sys.exit ensures the process exit code reflects
    # whether the event loop ended cleanly (0) or with an error (non-zero).
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
