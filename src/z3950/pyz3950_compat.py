"""
Module: pyz3950_compat.py
Purpose: Compatibility shim that verifies PyZ3950 is importable and ready.
         Includes a robust regex hotfix for Python 3.11+.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import logging
import sys
import types
from pathlib import Path

logger = logging.getLogger(__name__)

# Module-level cache for the import probe result.
_cached_result: tuple[bool, str] | None = None


def _quiet_import(module_name: str):
    """Import *module_name* while suppressing noisy third-party stdout/stderr."""
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        module = importlib.import_module(module_name)
    return module, sink.getvalue()


def _looks_like_legacy_ccl_regex_issue(exc: Exception, captured_output: str) -> bool:
    """Return ``True`` for the legacy PyZ3950 lexer regex bug on newer Python versions."""
    details = f"{exc}\n{captured_output}".lower()
    return (
        "can't build lexer" in details
        or "global flags not at the start of the expression" in details
        or "invalid regular expression for rule 't_attrset'" in details
        or "invalid regular expression for rule 't_qual'" in details
        or "invalid regular expression for rule 't_logop'" in details
    )


def _patch_legacy_ccl_source(source: str) -> str:
    """Patch old inline-regex flag syntax in ``PyZ3950.ccl`` for Python 3.11+."""
    patched = source
    replacements = {
        "r'(?i)ATTRSET'": "r'(?i:ATTRSET)'",
        'r"(?i)ATTRSET"': 'r"(?i:ATTRSET)"',
        "r'(?i)(AND)|(OR)|(NOT)'": "r'(?i:(AND)|(OR)|(NOT))'",
        'r"(?i)(AND)|(OR)|(NOT)"': 'r"(?i:(AND)|(OR)|(NOT))"',
        r't_QUAL.__doc__ = r"(?i)" + quals + r"|(\([0-9]+,[0-9]+\))"':
            r't_QUAL.__doc__ = r"(?i:" + quals + r"|(\([0-9]+,[0-9]+\)))"',
        "t_QUAL.__doc__ = r'(?i)' + quals + r'|(\\([0-9]+,[0-9]+\\))'":
            "t_QUAL.__doc__ = r'(?i:' + quals + r'|(\\([0-9]+,[0-9]+\\)))'",
    }
    for old, new in replacements.items():
        patched = patched.replace(old, new)
    return patched


def _install_patched_ccl_module() -> None:
    """Load a patched ``PyZ3950.ccl`` module into ``sys.modules`` before importing zoom."""
    package = importlib.import_module("PyZ3950")
    package_dir = Path(package.__file__).resolve().parent
    ccl_path = package_dir / "ccl.py"
    source = ccl_path.read_text(encoding="utf-8")
    patched = _patch_legacy_ccl_source(source)
    if patched == source:
        raise RuntimeError("PyZ3950 lexer build failed and no known compatibility patch matched ccl.py")

    sys.modules.pop("PyZ3950.ccl", None)
    sys.modules.pop("PyZ3950.zoom", None)

    module = types.ModuleType("PyZ3950.ccl")
    module.__file__ = str(ccl_path)
    module.__package__ = "PyZ3950"
    sys.modules["PyZ3950.ccl"] = module
    exec(compile(patched, str(ccl_path), "exec"), module.__dict__)


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
        _quiet_import("PyZ3950.zoom")
        _cached_result = (True, "")
        return _cached_result
    except ImportError as exc:
        msg = f"PyZ3950 is not installed: {exc}"
        logger.warning(msg)
        _cached_result = (False, msg)
        return _cached_result
    except Exception as exc:
        # Catches C-extension load failures, broken eggs, and legacy lexer regex
        # issues without letting third-party import noise flood the console.
        captured_output = ""
        try:
            _, captured_output = _quiet_import("PyZ3950.zoom")
        except Exception:
            pass

        if _looks_like_legacy_ccl_regex_issue(exc, captured_output):
            try:
                _install_patched_ccl_module()
                _quiet_import("PyZ3950.zoom")
                logger.info("Applied compatibility patch for legacy PyZ3950 lexer regexes.")
                _cached_result = (True, "")
                return _cached_result
            except Exception as patch_exc:
                exc = patch_exc

        msg = f"PyZ3950 import error: {exc}"
        logger.warning(msg)
        _cached_result = (False, msg)
        return _cached_result
