
"""
Module: pyz3950_compat.py
Purpose: Compatibility shim that verifies PyZ3950 is importable and ready.
         Includes a robust regex hotfix for Python 3.11+.
"""

from __future__ import annotations

import logging
import re
import sys

logger = logging.getLogger(__name__)

# Module-level cache for the import probe result.
_cached_result: tuple[bool, str] | None = None
_hotfix_applied = False


def _apply_python_311_regex_hotfix() -> None:
    """
    Monkey-patch re.compile to handle legacy regexes with global flags (?, etc.) in the middle.
    Introduced to fix PyZ3950/PLY incompatibilities on Python 3.11+.
    """
    global _hotfix_applied
    if _hotfix_applied or sys.version_info < (3, 11):
        return

    orig_compile = re.compile

    def patched_compile(pattern, flags=0):
        if isinstance(pattern, (str, bytes)):
            is_bytes = isinstance(pattern, bytes)
            p_str = pattern.decode("utf-8", "ignore") if is_bytes else pattern

            # Robust detection of any inline global flags (?imsux)
            flag_ptrn = orig_compile(r'\(\?[imsux]+\)')
            all_flags = flag_ptrn.findall(p_str)
            
            if all_flags:
                # Remove from middle, move to start
                p_clean = flag_ptrn.sub('', p_str)
                unique_flags = "".join(sorted(set(all_flags)))
                p_final = unique_flags + p_clean
                pattern = p_final.encode("utf-8") if is_bytes else p_final

        return orig_compile(pattern, flags)

    re.compile = patched_compile
    _hotfix_applied = True
    logger.debug("Applied robust Python 3.11+ regex hotfix for PyZ3950 compatibility.")


def ensure_pyz3950_importable() -> tuple[bool, str]:
    """
    Check that PyZ3950's zoom module can be imported.
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