"""Lightweight persistence layer for GUI user preferences (theme and last profile).

``ThemeManager`` reads and writes a small JSON file (``data/gui_settings.json``)
that survives across application sessions.  It is designed to be instantiated
cheaply on demand — any module can call ``ThemeManager().get_theme()`` without
maintaining a long-lived reference.

Theme-switching flow in the application:
    1. The user clicks the theme toggle in ``ModernMainWindow``.
    2. ``ModernMainWindow._apply_theme`` calls ``ThemeManager().set_theme(mode)``
       which persists the new value to disk.
    3. ``_apply_theme`` then calls ``app.setStyleSheet(generate_stylesheet(palette))``
       to replace the global QSS, and calls ``HelpTab.refresh_theme(colors)`` to
       update inline styles that live outside the QSS cascade.
    4. On the next cold start, ``ThemeManager().get_theme()`` returns the saved
       value so the correct palette is applied before the window is shown.

Stored keys:
    ``theme`` — ``"dark"`` or ``"light"`` (default ``"light"``).
    ``last_profile`` — Display name of the most recently active profile.
"""
import json
from pathlib import Path
from typing import Literal


class ThemeManager:
    """Reads and writes GUI preferences to ``data/gui_settings.json``.

    The class is intentionally stateless between instantiations: each call to
    ``__init__`` reloads the settings file so two instances always agree on the
    current values.
    """

    def __init__(self):
        from config.app_paths import get_app_root
        self.app_root = get_app_root()
        # Store settings under data/ so they survive source-tree updates and
        # are not accidentally committed alongside code changes.
        self.settings_file = self.app_root / "data" / "gui_settings.json"
        # Ensure the parent directory exists; required on first run or after a
        # clean checkout where data/ is not present.
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_settings()

    def _load_settings(self):
        """Load settings from the JSON file, or create and persist defaults.

        Any I/O or JSON parse error is silently swallowed and replaced with
        default settings so a corrupted file never prevents the app from
        starting.
        """
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    self.settings = json.load(f)
            else:
                # First run: initialise and persist the defaults immediately.
                self.settings = self._create_default_settings()
                self._save_settings()
        except Exception:
            # Corrupted or unreadable file — fall back to defaults in memory.
            self.settings = self._create_default_settings()

    def _create_default_settings(self) -> dict:
        """Return the factory-default settings dict used on first run.

        Returns:
            A dict containing ``theme`` (``"light"``) and
            ``last_profile`` (``"Default Settings"``).
        """
        return {
            "theme": "light",  # "dark" or "light"
            "last_profile": "Default Settings"
        }

    def _save_settings(self):
        """Persist the current in-memory settings dict to the JSON file.

        Any I/O error is silently swallowed so a read-only filesystem (e.g. a
        packaged app running from a protected directory) never crashes the GUI.
        """
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2)
        except Exception:
            pass  # Silently fail if we can't write settings

    def get_theme(self) -> Literal["dark", "light"]:
        """Return the current theme mode, defaulting to ``"light"`` if invalid.

        Returns:
            ``"dark"`` or ``"light"``.
        """
        theme = self.settings.get("theme", "light")
        # Guard against corrupt stored values that are not valid theme names.
        return theme if theme in ("dark", "light") else "light"

    def set_theme(self, theme: str):
        """Set and persist the theme mode.

        Silently ignores values that are not ``"dark"`` or ``"light"`` so
        callers do not need to validate before calling.

        Args:
            theme: ``"dark"`` or ``"light"``.
        """
        if isinstance(theme, str) and theme in ("dark", "light"):
            self.settings["theme"] = theme
            self._save_settings()

    def get_last_profile(self) -> str:
        """Return the name of the most recently active profile.

        Returns:
            Profile display name, defaulting to ``"Default Settings"`` when no
            value has been stored yet.
        """
        return self.settings.get("last_profile", "Default Settings")

    def set_last_profile(self, profile_name: str):
        """Persist the most recently active profile name.

        Args:
            profile_name: Display name of the active profile.
        """
        self.settings["last_profile"] = profile_name
        self._save_settings()

