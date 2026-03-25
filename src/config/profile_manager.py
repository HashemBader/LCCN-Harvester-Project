"""
Module: profile_manager.py
Manages configuration profiles for the LCCN Harvester.
"""
import shutil
from pathlib import Path
from typing import List, Dict, Optional
import json
from datetime import datetime


class ProfileManager:
    """Manage configuration profiles."""

    def __init__(self):
        from config.app_paths import get_app_root
        self.app_root = get_app_root()
        self.profiles_dir = self.app_root / "config" / "profiles"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

        self.default_profile_path = self.app_root / "config" / "default_profile.json"
        self.active_profile_path = self.app_root / "config" / "active_profile.txt"
        self.default_targets_path = self.app_root / "data" / "targets.tsv"

        # Ensure default profile exists
        if not self.default_profile_path.exists():
            self._create_default_profile()

    def _create_default_profile(self):
        """Create the built-in default profile."""
        default_settings = {
            "profile_name": "Default Settings",
            "created_at": datetime.now().isoformat(),
            "description": "Factory default configuration",
            "settings": {
                "targets": [
                    {"name": "Library of Congress", "enabled": True, "priority": 1},
                    {"name": "Harvard LibraryCloud", "enabled": True, "priority": 2},
                    {"name": "OpenLibrary", "enabled": True, "priority": 3}
                ],
                "harvest_options": {
                    "stop_on_first_result": True,
                    "use_cache": True,
                    "retry_failed": True,
                    "max_retries": 3,
                    "retry_delay": 5
                },
                "advanced_options": {
                    "timeout": 30,
                    "concurrent_requests": 5,
                    "rate_limit": 10
                }
            }
        }

        with open(self.default_profile_path, 'w') as f:
            json.dump(default_settings, f, indent=2)

    def _profile_slug(self, name: str) -> str:
        """Return the sanitized folder/filename slug for a profile name."""
        return name.lower().replace(" ", "_").replace("/", "_")

    def get_profile_dir(self, name: str) -> Path:
        """Return the Path to the profile's dedicated config folder.

        ``config/profiles/<slug>/``
        """
        return self.profiles_dir / self._profile_slug(name)

    def get_profile_data_dir(self, name: str) -> Path:
        """Return the Path to the profile's dedicated data/exports folder.

        ``data/<slug>/``
        """
        return self.app_root / "data" / self._profile_slug(name)

    def get_db_path(self, name: str) -> Path:
        """Return the profile-specific SQLite database path.

        Default Settings keeps the legacy root path for backward compatibility.
        All other profiles use ``data/<slug>/lccn_harvester.sqlite3`` so their
        results are fully isolated from every other profile.
        """
        if name == "Default Settings":
            return self.app_root / "data" / "lccn_harvester.sqlite3"
        data_dir = self.get_profile_data_dir(name)
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "lccn_harvester.sqlite3"

    def get_targets_file(self, name: str) -> Path:
        """Return the Path to the targets TSV file for the given profile.

        "Default Settings" uses the shared ``data/targets.tsv``.
        User profiles use ``config/profiles/<slug>/targets.tsv``.
        Falls back to the legacy flat location if the new one doesn't exist yet.
        """
        if name == "Default Settings":
            return self.default_targets_path
        slug = self._profile_slug(name)
        new_path = self.profiles_dir / slug / f"{slug}_targets.tsv"
        if new_path.exists():
            return new_path
        # Legacy flat location (backward compat)
        legacy_path = self.profiles_dir / f"{slug}_targets.tsv"
        if legacy_path.exists():
            return legacy_path
        # Default to new location even if it doesn't exist yet
        return new_path

    def _normalize_profile_name(self, name: str) -> str:
        """Normalize names for case-insensitive duplicate checks."""
        return " ".join((name or "").split()).strip().casefold()

    def list_profiles(self) -> List[str]:
        """Return list of available profile names."""
        profiles = ["Default Settings"]  # Built-in always first
        seen = {self._normalize_profile_name("Default Settings")}

        # Collect all candidate JSON files: new-style (subdir) first, then legacy flat
        candidate_files = sorted(self.profiles_dir.glob("*/*.json")) + sorted(self.profiles_dir.glob("*.json"))

        for file in candidate_files:
            try:
                with open(file) as f:
                    data = json.load(f)
                    profile_name = data.get("profile_name", file.stem)
                    norm = self._normalize_profile_name(profile_name)
                    if not norm or norm in seen:
                        continue
                    seen.add(norm)
                    profiles.append(profile_name)
            except Exception:
                # Skip corrupted profiles
                continue

        return profiles

    def load_profile(self, name: str) -> Optional[Dict]:
        """Load a profile by name."""
        if name == "Default Settings":
            return self._load_json(self.default_profile_path)

        normalized_target = self._normalize_profile_name(name)

        # Check new subdir location first
        slug = self._profile_slug(name)
        new_path = self.profiles_dir / slug / f"{slug}.json"
        if new_path.exists():
            try:
                data = self._load_json(new_path)
                if self._normalize_profile_name(data.get("profile_name", "")) == normalized_target:
                    return data
            except Exception:
                pass

        # Fall back to flat legacy files
        for file in self.profiles_dir.glob("*.json"):
            try:
                data = self._load_json(file)
                if self._normalize_profile_name(data.get("profile_name", "")) == normalized_target:
                    return data
            except Exception:
                continue

        return None

    def profile_name_exists(self, name: str, exclude_name: Optional[str] = None) -> bool:
        """Return True if a profile name already exists (case-insensitive)."""
        normalized_name = self._normalize_profile_name(name)
        normalized_exclude = self._normalize_profile_name(exclude_name or "")
        if not normalized_name:
            return False
        for profile_name in self.list_profiles():
            norm = self._normalize_profile_name(profile_name)
            if norm == normalized_exclude:
                continue
            if norm == normalized_name:
                return True
        return False

    def save_profile(self, name: str, settings: Dict, description: str = ""):
        """Save settings as a named profile."""
        slug = self._profile_slug(name)

        # Ensure the profile's own config subdirectory exists
        profile_dir = self.get_profile_dir(name)
        profile_dir.mkdir(parents=True, exist_ok=True)

        file_path = profile_dir / f"{slug}.json"

        # Load existing or create new
        if file_path.exists():
            try:
                profile_data = self._load_json(file_path)
                profile_data["last_modified"] = datetime.now().isoformat()
                profile_data["settings"] = settings
                if description:
                    profile_data["description"] = description
            except Exception:
                profile_data = self._create_profile_data(name, settings, description)
        else:
            profile_data = self._create_profile_data(name, settings, description)

        with open(file_path, 'w') as f:
            json.dump(profile_data, f, indent=2)

        # On first creation, seed a profile-specific targets file from the default.
        targets_file = self.get_targets_file(name)
        if not targets_file.exists() and self.default_targets_path.exists():
            shutil.copy2(self.default_targets_path, targets_file)

        # Ensure the profile's data/exports directory exists
        data_dir = self.get_profile_data_dir(name)
        data_dir.mkdir(parents=True, exist_ok=True)

        return True

    def update_profile_settings(self, name: str, updates: Dict) -> bool:
        """Merge setting updates into an existing profile, creating it if needed."""
        if not isinstance(updates, dict):
            raise TypeError("updates must be a dictionary")

        if name == "Default Settings":
            file_path = self.default_profile_path
            profile_data = self._load_json(file_path) if file_path.exists() else self._create_profile_data(name, {}, "")
        else:
            slug = self._profile_slug(name)
            profile_dir = self.get_profile_dir(name)
            profile_dir.mkdir(parents=True, exist_ok=True)
            file_path = profile_dir / f"{slug}.json"
            if file_path.exists():
                profile_data = self._load_json(file_path)
            else:
                loaded = self.load_profile(name)
                profile_data = loaded if loaded else self._create_profile_data(name, {}, "")

        settings = profile_data.get("settings")
        if not isinstance(settings, dict):
            settings = {}
        settings.update(updates)
        profile_data["settings"] = settings
        profile_data["profile_name"] = name
        profile_data["last_modified"] = datetime.now().isoformat()

        with open(file_path, 'w') as f:
            json.dump(profile_data, f, indent=2)

        return True

    def get_profile_setting(self, name: str, key: str, default=None):
        """Return a single profile setting value."""
        profile = self.load_profile(name)
        if not profile:
            return default
        settings = profile.get("settings", {})
        if not isinstance(settings, dict):
            return default
        return settings.get(key, default)

    def set_active_profile_setting(self, key: str, value) -> bool:
        """Persist a single setting into the currently active profile."""
        return self.update_profile_settings(self.get_active_profile(), {key: value})

    def get_active_profile_setting(self, key: str, default=None):
        """Read a single setting from the currently active profile."""
        return self.get_profile_setting(self.get_active_profile(), key, default)

    def _create_profile_data(self, name: str, settings: Dict, description: str) -> Dict:
        """Create new profile data structure."""
        return {
            "profile_name": name,
            "created_at": datetime.now().isoformat(),
            "description": description,
            "settings": settings
        }

    def delete_profile(self, name: str) -> bool:
        """Delete a profile."""
        if name == "Default Settings":
            return False  # Cannot delete default

        deleted = False

        # Remove new-style profile subdirectory if it exists
        profile_dir = self.get_profile_dir(name)
        if profile_dir.exists():
            shutil.rmtree(profile_dir)
            deleted = True

        # Also clean up any legacy flat files for this profile
        for file in list(self.profiles_dir.glob("*.json")):
            try:
                data = self._load_json(file)
                if data.get("profile_name") == name:
                    file.unlink()
                    deleted = True
                    break
            except Exception:
                continue

        # Remove legacy flat targets TSV if present
        slug = self._profile_slug(name)
        legacy_targets = self.profiles_dir / f"{slug}_targets.tsv"
        if legacy_targets.exists():
            legacy_targets.unlink()

        # Note: the data/exports directory (get_profile_data_dir) is intentionally
        # preserved so previously exported files are not lost.

        return deleted

    def rename_profile(self, old_name: str, new_name: str) -> bool:
        """Rename a profile."""
        if old_name == "Default Settings":
            return False  # Cannot rename default

        # Load old profile
        profile_data = self.load_profile(old_name)
        if not profile_data:
            return False

        old_slug = self._profile_slug(old_name)
        new_slug = self._profile_slug(new_name)

        # --- Config folder (new-style) ---
        old_profile_dir = self.get_profile_dir(old_name)
        new_profile_dir = self.get_profile_dir(new_name)

        if old_profile_dir.exists():
            if not new_profile_dir.exists():
                old_profile_dir.rename(new_profile_dir)
            else:
                # Target dir already exists; copy contents and remove old
                for item in old_profile_dir.iterdir():
                    dest = new_profile_dir / item.name
                    if not dest.exists():
                        item.rename(dest)
                shutil.rmtree(old_profile_dir)

            # Rename the JSON file inside the new dir to match new slug
            old_json = new_profile_dir / f"{old_slug}.json"
            new_json = new_profile_dir / f"{new_slug}.json"
            if old_json.exists() and not new_json.exists():
                old_json.rename(new_json)
        else:
            # Legacy flat targets file: move to new location
            old_targets = self.profiles_dir / f"{old_slug}_targets.tsv"
            new_targets_dir = new_profile_dir
            new_targets_dir.mkdir(parents=True, exist_ok=True)
            new_targets_path = new_targets_dir / f"{new_slug}_targets.tsv"
            if old_targets.exists() and not new_targets_path.exists():
                old_targets.rename(new_targets_path)

        # Remove old legacy flat JSON if present
        for file in list(self.profiles_dir.glob("*.json")):
            try:
                data = self._load_json(file)
                if data.get("profile_name") == old_name:
                    file.unlink()
                    break
            except Exception:
                continue

        # --- Data/exports folder ---
        old_data_dir = self.get_profile_data_dir(old_name)
        new_data_dir = self.get_profile_data_dir(new_name)
        if old_data_dir.exists() and not new_data_dir.exists():
            old_data_dir.rename(new_data_dir)

        # Save updated profile JSON with new name
        new_profile_dir.mkdir(parents=True, exist_ok=True)
        profile_data["profile_name"] = new_name
        profile_data["last_modified"] = datetime.now().isoformat()
        file_path = new_profile_dir / f"{new_slug}.json"
        with open(file_path, 'w') as f:
            json.dump(profile_data, f, indent=2)

        return True

    def get_active_profile(self) -> str:
        """Get the currently active profile name."""
        if self.active_profile_path.exists():
            try:
                return self.active_profile_path.read_text().strip()
            except Exception:
                pass
        return "Default Settings"

    def set_active_profile(self, name: str):
        """Set the active profile."""
        with open(self.active_profile_path, 'w') as f:
            f.write(name)

    def _load_json(self, file_path: Path) -> Dict:
        """Load and parse JSON file."""
        with open(file_path) as f:
            return json.load(f)

    def get_profile_info(self, name: str) -> Optional[Dict]:
        """Get metadata about a profile."""
        profile = self.load_profile(name)
        if not profile:
            return None

        return {
            "name": profile.get("profile_name"),
            "description": profile.get("description", ""),
            "created_at": profile.get("created_at"),
            "last_modified": profile.get("last_modified"),
            "num_targets": len(profile.get("settings", {}).get("targets", [])),
        }
