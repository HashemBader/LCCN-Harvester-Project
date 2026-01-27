"""
Package: src.database
Part of the LCCN Harvester Project.

This file uses lazy imports to avoid the RuntimeWarning that can happen when running:
  python -m src.database.db_manager
"""

from typing import TYPE_CHECKING, Any

__all__ = ["DatabaseManager", "MainRecord", "AttemptedRecord"]

if TYPE_CHECKING:
    from .db_manager import DatabaseManager, MainRecord, AttemptedRecord


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
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
