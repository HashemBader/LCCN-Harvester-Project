"""
Module: theme_manager.py
Manages application theme preferences (light/dark mode).
"""
import json
from pathlib import Path
from typing import Literal


class ThemeManager:
    """Manages theme persistence and application state."""

    def __init__(self):
        self.app_root = Path(__file__).parent.parent.parent
        # store settings in project data folder
        self.settings_file = self.app_root / "data" / "gui_settings.json"
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_settings()

    def _load_settings(self):
        """Load settings from file or create defaults."""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    self.settings = json.load(f)
            else:
                self.settings = self._create_default_settings()
                self._save_settings()
        except Exception:
            self.settings = self._create_default_settings()

    def _create_default_settings(self) -> dict:
        """Create default settings."""
        return {
            "theme": "dark",  # "dark" or "light"
            "last_profile": "Default Settings"
        }

    def _save_settings(self):
        """Save settings to file."""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2)
        except Exception:
            pass  # Silently fail if we can't write settings

    def get_theme(self) -> Literal["dark", "light"]:
        """Get current theme mode."""
        theme = self.settings.get("theme", "dark")
        return theme if theme in ("dark", "light") else "dark"

    def set_theme(self, theme: str):
        """Set and persist theme mode."""
        if isinstance(theme, str) and theme in ("dark", "light"):
            self.settings["theme"] = theme
            self._save_settings()

    def get_last_profile(self) -> str:
        """Get last active profile name."""
        return self.settings.get("last_profile", "Default Settings")

    def set_last_profile(self, profile_name: str):
        """Set and persist last active profile."""
        self.settings["last_profile"] = profile_name
        self._save_settings()

