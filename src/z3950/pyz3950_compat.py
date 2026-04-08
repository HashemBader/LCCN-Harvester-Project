"""
Module: pyz3950_compat.py
Purpose: Compatibility shim that verifies PyZ3950 is importable and ready.
         Returns a (success, reason) tuple so callers can degrade gracefully.
"""

from __future__ import annotations

import logging
import re
import sys

logger = logging.getLogger(__name__)

_cached_result: tuple[bool, str] | None = None
_hotfix_applied = False


def _apply_python_311_regex_hotfix() -> None:
    """
    Monkey-patch re.compile to handle legacy regexes with global flags (?, etc.) in the middle.
    Python 3.11+ throws an error if these are not at the very start of the string.
    Since PLY (used by PyZ3950) combines tokens into a single large regex, it
    breaks these legacy patterns by pushing the flags into the middle.
    """
    global _hotfix_applied
    if _hotfix_applied or sys.version_info < (3, 11):
        return

    orig_compile = re.compile

    def patched_compile(pattern, flags=0):
        if isinstance(pattern, (str, bytes)):
            # Convert to string for checking
            is_bytes = isinstance(pattern, bytes)
            p_str = pattern.decode("utf-8", "ignore") if is_bytes else pattern

            # Only touch patterns that HAVE a global flag hidden in the middle
            # (i.e., not at the very beginning)
            modified = False
            for flag_str, re_flag in [("(?i)", re.IGNORECASE),
                                    ("(?m)", re.MULTILINE),
                                    ("(?s)", re.DOTALL)]:
                if flag_str in p_str and not p_str.startswith(flag_str):
                    p_str = p_str.replace(flag_str, "")
                    flags |= re_flag
                    modified = True

            if modified:
                pattern = p_str.encode("utf-8") if is_bytes else p_str

        return orig_compile(pattern, flags)

    re.compile = patched_compile
    _hotfix_applied = True
    logger.debug("Applied production-safe Python 3.11+ regex hotfix for PyZ3950/PLY compatibility.")


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

    # Apply the hotfix before attempting any PyZ3950 imports
    _apply_python_311_regex_hotfix()

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
