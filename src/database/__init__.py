"""
Public surface of the ``database`` package.

Exports are resolved lazily via ``__getattr__`` so that importing this
package does not trigger heavy imports (e.g. SQLite connections) unless
the caller actually uses one of the exported names.

Exported names:
    DatabaseManager  -- The main SQLite access class.
    MainRecord       -- DTO for a successful harvest result.
    AttemptedRecord  -- DTO for a failed/pending lookup with retry state.
    now_datetime_str -- Current local datetime as ``"YYYY-MM-DD HH:MM:SS"``.
    today_yyyymmdd   -- Today's date as an integer ``YYYYMMDD``.
"""

from typing import TYPE_CHECKING, Any

__all__ = ["DatabaseManager", "MainRecord", "AttemptedRecord", "now_datetime_str", "today_yyyymmdd"]

if TYPE_CHECKING:
    from .db_manager import DatabaseManager, MainRecord, AttemptedRecord, now_datetime_str, today_yyyymmdd


def __getattr__(name: str) -> Any:
    """Resolve exported names on first access (PEP 562 lazy module attributes)."""
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
    if name == "today_yyyymmdd":  # Alias kept for compatibility during migration.
        from .db_manager import today_yyyymmdd
        return today_yyyymmdd
    if name == "utc_now_iso":  # Alias kept for compatibility.
        from .db_manager import now_datetime_str
        return now_datetime_str
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
