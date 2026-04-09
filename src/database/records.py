"""
Typed record structures shared across the database and harvester layers.

This module defines the data-transfer objects (DTOs) that flow between the
harvester, the database manager, and the GUI.  Keeping them in a dedicated
module avoids circular imports because both ``db_manager`` and the harvester
orchestrator depend on these types.

Classes:
    MainRecord      -- A successful harvest result (ISBN + call number(s)).
    AttemptedRecord -- A failed/pending lookup with retry metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MainRecord:
    """Combined call-number record exposed to the UI and harvester layers.

    Represents a successful harvest for a single ISBN.  One record can carry
    both an LC call number (``lccn``) and an NLM call number (``nlmcn``) when
    multiple sources were queried.

    Note: The database stores one row per ``(isbn, call_number_type, source)``
    triple; ``DatabaseManager._aggregate_main_rows`` collapses those rows into
    this combined view.

    Attributes:
        isbn:            The 10- or 13-digit ISBN (stored as a string).
        lccn:            Library of Congress call number, if found.
        lccn_source:     Which harvesting target provided the LCCN.
        nlmcn:           National Library of Medicine call number, if found.
        nlmcn_source:    Which harvesting target provided the NLM CN.
        classification:  Leading LoC subject letters derived from ``lccn``.
        source:          Comma/plus-separated string of all contributing sources.
        date_added:      Harvest date as an ISO date string or ``YYYYMMDD`` int.
    """

    isbn: str
    lccn: Optional[str] = None
    lccn_source: Optional[str] = None
    nlmcn: Optional[str] = None
    nlmcn_source: Optional[str] = None
    classification: Optional[str] = None
    source: Optional[str] = None
    date_added: Optional[int | str] = None


@dataclass(frozen=True)
class AttemptedRecord:
    """Retry-tracking row for a single ISBN/target/call-number-type key.

    Mirrors the ``attempted`` database table and is used throughout the
    harvester to decide whether to skip or retry a lookup.

    Attributes:
        isbn:           The ISBN that was attempted.
        last_target:    Identifier of the last lookup target tried.
        attempt_type:   ``'lccn'``, ``'nlmcn'``, or ``'both'`` (default).
        last_attempted: Date of most recent attempt as ``YYYYMMDD`` int or
                        ISO string.
        fail_count:     Running total of consecutive failures for this key.
        last_error:     Human-readable message from the most recent failure.
    """

    isbn: str
    last_target: Optional[str] = None
    attempt_type: str = "both"
    last_attempted: Optional[int | str] = None
    fail_count: int = 1
    last_error: Optional[str] = None
