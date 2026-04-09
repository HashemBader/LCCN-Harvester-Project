"""
Module: pyz3950_compat.py
Part of the LCCN Harvester Project — Z39.50 subsystem.

Compatibility shim that verifies PyZ3950 is importable and ready.

PyZ3950 is an optional, third-party package with a complex C-extension
dependency chain (asn1, MARC, etc.).  Installation failures, version
mismatches, or platform incompatibilities are common.  Rather than letting
an ``ImportError`` propagate unpredictably through the call stack, this module
provides a single probe function that every Z39.50 consumer can call before
attempting real imports.  It returns a ``(bool, str)`` tuple so callers can
degrade gracefully (e.g. skip Z39.50 targets) instead of crashing the whole
harvest run.

The probe result is cached after the first call so that repeated invocations
(one per search, for instance) have effectively zero overhead.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Module-level cache for the import probe result.  ``None`` means the check has
# not been run yet; afterwards it holds ``(True, "")`` or ``(False, reason)``.
_cached_result: tuple[bool, str] | None = None


def ensure_pyz3950_importable() -> tuple[bool, str]:
    """
    Check that PyZ3950's ``zoom`` module can be imported successfully.

    Performs a trial import of ``PyZ3950.zoom`` and caches the outcome so that
    subsequent calls return immediately without repeating the import attempt.

    Returns:
        tuple[bool, str]:
            ``(True, "")``          — PyZ3950 is available and importable.
            ``(False, "<reason>")`` — PyZ3950 is missing or broken; the second
                                      element contains a human-readable explanation
                                      suitable for log messages or error dialogs.

    Notes:
        The ``ImportError`` branch covers the normal "package not installed" case.
        The broad ``Exception`` branch handles rarer but real-world scenarios such
        as a partially-installed package whose C extension fails to load (e.g.
        ``OSError: .so: cannot open shared object file``).
    """
    global _cached_result
    # Short-circuit: return the cached result from a previous call.
    if _cached_result is not None:
        return _cached_result

    try:
        # noqa: F401 — imported solely to verify availability; result not used.
        from PyZ3950 import zoom as _zoom  # noqa: F401
        _cached_result = (True, "")
        return _cached_result
    except ImportError as exc:
        msg = f"PyZ3950 is not installed: {exc}"
        logger.warning(msg)
        _cached_result = (False, msg)
        return _cached_result
    except Exception as exc:
        # Catches C-extension load failures, broken eggs, etc.
        msg = f"PyZ3950 import error: {exc}"
        logger.warning(msg)
        _cached_result = (False, msg)
        return _cached_result
