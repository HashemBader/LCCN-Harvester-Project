"""
Module: app_paths.py
Resolves file-system paths for both development and frozen (PyInstaller) builds.

Usage
-----
    from config.app_paths import get_app_root, get_bundle_root, ensure_user_data_setup

In development
    get_bundle_root()  -> project root   (read-only resources live here)
    get_app_root()     -> project root   (writable data also lives here)

When frozen (PyInstaller)
    get_bundle_root()  -> sys._MEIPASS   (read-only bundled resources)
    get_app_root()     -> platform user-data dir  (writable)
                          macOS:   ~/Library/Application Support/LCCN Harvester/
                          Windows: %APPDATA%/LCCN Harvester/
                          Linux:   ~/.lccn_harvester/
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path

_IS_FROZEN: bool = getattr(sys, "frozen", False)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_bundle_root() -> Path:
    """Return the root directory that contains *read-only* bundled resources.

    * Frozen : ``sys._MEIPASS`` (the extraction temp-dir)
    * Dev    : project root (two levels above this file's ``src/config/``)
    """
    if _IS_FROZEN:
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # src/config/app_paths.py  → parent = config, parent.parent = src, .parent = project root
    return Path(__file__).resolve().parent.parent.parent


def get_user_data_dir() -> Path:
    """Return a *writable* directory for user data (config, output, settings).

    The directory is created if it does not exist.
    """
    if _IS_FROZEN:
        system = platform.system()
        if system == "Darwin":
            base = Path.home() / "Library" / "Application Support" / "LCCN Harvester"
        elif system == "Windows":
            appdata = os.environ.get("APPDATA") or str(Path.home())
            base = Path(appdata) / "LCCN Harvester"
        else:
            base = Path.home() / ".lccn_harvester"
        base.mkdir(parents=True, exist_ok=True)
        return base
    # In development the project root *is* the user-data dir
    return get_bundle_root()


def get_app_root() -> Path:
    """Convenience alias: the writable root expected by ProfileManager, ThemeManager, etc."""
    return get_user_data_dir()


def ensure_user_data_setup() -> None:
    """Seed the writable user-data directory on the **first run** of a frozen build.

    Copies ``config/`` and creates ``data/`` if they do not yet exist in the
    user-data directory.  Does nothing when running from source.
    """
    if not _IS_FROZEN:
        return

    bundle_root = get_bundle_root()
    user_dir = get_user_data_dir()

    # --- Seed config directory ---
    bundle_config = bundle_root / "config"
    user_config = user_dir / "config"
    if bundle_config.exists() and not user_config.exists():
        shutil.copytree(str(bundle_config), str(user_config))

    # --- Ensure data output directory exists ---
    (user_dir / "data").mkdir(parents=True, exist_ok=True)
