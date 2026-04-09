"""
Configuration package for the LCCN Harvester.

Exposes:
    ProfileManager  -- Read/write access to named user configuration profiles.
                       Handles profile CRUD, active-profile tracking, targets
                       TSV seeding, and one-time legacy-DB migration.

See also:
    config.app_paths -- File-system path resolution for dev and frozen builds,
                        including platform-specific user-data directories.
"""
from .profile_manager import ProfileManager

__all__ = ['ProfileManager']
