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
        # Use relative paths - portable for USB stick
        self.app_root = Path(__file__).parent.parent.parent
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

    def get_targets_file(self, name: str) -> Path:
        """Return the Path to the targets TSV file for the given profile.

        "Default Settings" uses the shared ``data/targets.tsv``.
        All other profiles use ``config/profiles/<slug>_targets.tsv``.
        """
        if name == "Default Settings":
            return self.default_targets_path
        filename = name.lower().replace(" ", "_").replace("/", "_")
        return self.profiles_dir / f"{filename}_targets.tsv"

    def _normalize_profile_name(self, name: str) -> str:
        """Normalize names for case-insensitive duplicate checks."""
        return " ".join((name or "").split()).strip().casefold()

    def list_profiles(self) -> List[str]:
        """Return list of available profile names."""
        profiles = ["Default Settings"]  # Built-in always first
        seen = {self._normalize_profile_name("Default Settings")}

        # Add user-created profiles
        for file in sorted(self.profiles_dir.glob("*.json")):
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

        # Search user profiles
        normalized_target = self._normalize_profile_name(name)
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
        # Sanitize filename
        filename = name.lower().replace(" ", "_").replace("/", "_")
        file_path = self.profiles_dir / f"{filename}.json"

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

        return True

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

        # Find and delete the profile file
        for file in self.profiles_dir.glob("*.json"):
            try:
                data = self._load_json(file)
                if data.get("profile_name") == name:
                    file.unlink()
                    # Remove the associated targets TSV if present
                    targets_file = self.get_targets_file(name)
                    if targets_file.exists():
                        targets_file.unlink()
                    return True
            except Exception:
                continue

        return False

    def rename_profile(self, old_name: str, new_name: str) -> bool:
        """Rename a profile."""
        if old_name == "Default Settings":
            return False  # Cannot rename default

        # Load old profile
        profile_data = self.load_profile(old_name)
        if not profile_data:
            return False

        # Rename the targets TSV before deleting the old profile record
        old_targets = self.get_targets_file(old_name)
        new_targets = self.get_targets_file(new_name)
        if old_targets.exists() and not new_targets.exists():
            old_targets.rename(new_targets)

        # Delete old profile (targets file already renamed, so skip implicit delete)
        for file in self.profiles_dir.glob("*.json"):
            try:
                data = self._load_json(file)
                if data.get("profile_name") == old_name:
                    file.unlink()
                    break
            except Exception:
                continue

        # Save with new name (save_profile won't overwrite new_targets because it now exists)
        profile_data["profile_name"] = new_name
        filename = new_name.lower().replace(" ", "_").replace("/", "_")
        file_path = self.profiles_dir / f"{filename}.json"
        profile_data["last_modified"] = datetime.now().isoformat()
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
