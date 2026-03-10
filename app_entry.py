"""
app_entry.py
============
Single entry-point for the LCCN Harvester GUI.

Works in two modes:
  * Development  – run directly with ``python app_entry.py``
  * Frozen build – invoked by the PyInstaller-generated executable

PyInstaller sets ``sys.frozen = True`` and ``sys._MEIPASS`` to the extraction
directory when running a frozen build.  This file detects that and routes
paths accordingly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# 1. Bootstrap sys.path so our package imports work in both modes
# ---------------------------------------------------------------------------
def _bootstrap_path() -> None:
    if getattr(sys, "frozen", False):
        # Running inside a PyInstaller bundle.
        # _MEIPASS contains the extracted packages; sub-directory 'src' is
        # NOT present in frozen builds – packages live directly under _MEIPASS.
        meipass = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        for p in (str(meipass),):
            if p not in sys.path:
                sys.path.insert(0, p)
    else:
        # Running from source tree.
        project_root = Path(__file__).resolve().parent
        src_dir = project_root / "src"
        for p in (str(project_root), str(src_dir)):
            if p not in sys.path:
                sys.path.insert(0, p)


_bootstrap_path()


# ---------------------------------------------------------------------------
# 2. First-run setup for frozen builds (seed config, create data dir, chdir)
# ---------------------------------------------------------------------------
def _first_run_setup() -> None:
    from config.app_paths import ensure_user_data_setup, get_user_data_dir

    # Seed config/ and create data/ inside the user-data directory
    ensure_user_data_setup()

    # Change working directory so relative paths (data/, config/) resolve
    # to the writable user-data directory rather than inside the bundle.
    user_dir = get_user_data_dir()
    os.chdir(user_dir)


# ---------------------------------------------------------------------------
# 3. SSL certificate configuration
# ---------------------------------------------------------------------------
def _configure_ssl() -> None:
    if not os.getenv("SSL_CERT_FILE"):
        try:
            import certifi  # type: ignore
            os.environ["SSL_CERT_FILE"] = certifi.where()
        except Exception:
            pass
    if os.getenv("SSL_CERT_FILE") and not os.getenv("REQUESTS_CA_BUNDLE"):
        os.environ["REQUESTS_CA_BUNDLE"] = os.environ["SSL_CERT_FILE"]


# ---------------------------------------------------------------------------
# 4. Main
# ---------------------------------------------------------------------------
def main() -> None:
    _first_run_setup()
    _configure_ssl()

    from PyQt6.QtWidgets import QApplication
    from gui.modern_window import ModernMainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("LCCN Harvester")
    app.setOrganizationName("UPEI Library")
    app.setApplicationVersion("1.0.0")

    window = ModernMainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
