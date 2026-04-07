"""
Package: src.database
Part of the LCCN Harvester Project.

This file uses lazy imports to avoid the RuntimeWarning that can happen when running:
  python -m src.database.db_manager
"""

"""
src.database package exports.
"""

"""
Package: src.database

Lazy exports to avoid RuntimeWarning when running:
  python -m src.database.db_manager
"""

from typing import TYPE_CHECKING, Any

__all__ = ["DatabaseManager", "MainRecord", "AttemptedRecord", "now_datetime_str"]

if TYPE_CHECKING:
    from .db_manager import DatabaseManager, MainRecord, AttemptedRecord, now_datetime_str


def __getattr__(name: str) -> Any:
    if name == "DatabaseManager":
        from .db_manager import DatabaseManager
        return DatabaseManager
    if name == "MainRecord":
        from .db_manager import MainRecord
        return MainRecord
    if name == "AttemptedRecord":
        from .db_manager import AttemptedRecord
        return AttemptedRecord
    if name == "now_datetime_str":
        from .db_manager import now_datetime_str
        return now_datetime_str
    if name == "today_yyyymmdd": # Alias for compatibility during migration
        from .db_manager import now_datetime_str
        return now_datetime_str
    if name == "utc_now_iso": # Alias for compatibility
        from .db_manager import now_datetime_str
        return now_datetime_str
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

