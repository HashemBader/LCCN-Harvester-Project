"""
Module: pyz3950_compat.py
Purpose: Compatibility shim that verifies PyZ3950 is importable and ready.
         Returns a (success, reason) tuple so callers can degrade gracefully.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_cached_result: tuple[bool, str] | None = None


def ensure_pyz3950_importable() -> tuple[bool, str]:
    """
    Check that PyZ3950's zoom module can be imported.

    Returns:
        (True, "")           — PyZ3950 is available and importable.
        (False, "<reason>")  — PyZ3950 is missing or broken.

    The result is cached after the first call so repeated invocations are free.
    """
    global _cached_result
    if _cached_result is not None:
        return _cached_result

    try:
        from PyZ3950 import zoom as _zoom  # noqa: F401
        _cached_result = (True, "")
        return _cached_result
    except ImportError as exc:
        msg = f"PyZ3950 is not installed: {exc}"
        logger.warning(msg)
        _cached_result = (False, msg)
        return _cached_result
    except Exception as exc:
        msg = f"PyZ3950 import error: {exc}"
        logger.warning(msg)
        _cached_result = (False, msg)
        return _cached_result
