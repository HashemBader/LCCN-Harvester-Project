"""
Module: isbn_validator.py
Part of the LCCN Harvester Project.
"""

from datetime import datetime
from pathlib import Path
from typing import Iterable
import re

try:
    from stdnum import isbn as _stdnum_isbn
except ImportError:
    STDNUM_AVAILABLE = False
    stdnum_isbn = None
else:
    STDNUM_AVAILABLE = True
    stdnum_isbn = _stdnum_isbn

try:
    from . import messages
except ImportError:
    class messages:
        class GuiMessages:
            warn_title_invalid = "Invalid ISBN"

INVALID_ISBN_LOG = Path("invalid_isbns.log")


def log_invalid_isbn(isbn_value: str, reason: str = messages.GuiMessages.warn_title_invalid) -> None:
    """
    Append an invalid ISBN entry to the invalid ISBN log file.
    """
    timestamp = datetime.now().isoformat()
    with INVALID_ISBN_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{timestamp}\t{isbn_value}\n")

def _simple_normalize_isbn(isbn_str: str) -> str:
    """Simple ISBN normalization when stdnum is not available."""
    # Remove hyphens, spaces, and other non-alphanumeric characters
    cleaned = re.sub(r'[^0-9Xx]', '', isbn_str)

    # Basic length check (ISBN-10 or ISBN-13)
    if len(cleaned) in (10, 13):
        return cleaned.upper()
    return ""


def _simple_validate_isbn(isbn_str: str) -> bool:
    """Simple ISBN validation when stdnum is not available."""
    cleaned = _simple_normalize_isbn(isbn_str)
    return len(cleaned) in (10, 13)


def _isbn_sort_key(isbn_str: str) -> str:
    """Return a sort key for ISBNs where the numerically smallest ISBN sorts first."""
    normalized = _simple_normalize_isbn(isbn_str).upper()
    if normalized.endswith("X"):
        normalized = normalized[:-1] + "9"
    return normalized or isbn_str.strip().upper()


def pick_lowest_isbn(isbns: Iterable[str]) -> str:
    """Return the numerically lowest ISBN from a sequence of ISBN strings."""
    candidates = [isbn for isbn in isbns if isbn and str(isbn).strip()]
    if not candidates:
        raise ValueError("At least one ISBN is required")
    return min(candidates, key=_isbn_sort_key)


def normalize_isbn(isbn_str: str) -> str:
    """
    Normalize an ISBN string to a valid ISBN string.
    """
    if STDNUM_AVAILABLE:
        try:
            normalized_isbn_str = stdnum_isbn.validate(isbn_str)
            return normalized_isbn_str
        except Exception:
            log_invalid_isbn(isbn_str, messages.GuiMessages.warn_title_invalid)
            return ""
    else:
        # Fallback to simple normalization
        result = _simple_normalize_isbn(isbn_str)
        if not result:
            log_invalid_isbn(isbn_str, messages.GuiMessages.warn_title_invalid)
        return result


def _simple_isbn13_checksum(first_twelve: str) -> str:
    """Compute the ISBN-13 checksum digit for a 12-digit prefix."""
    total = 0
    for index, char in enumerate(first_twelve):
        digit = int(char)
        total += digit if index % 2 == 0 else digit * 3
    return str((10 - (total % 10)) % 10)


def _canonical_linked_isbn(isbn_str: str) -> str:
    """Return a canonical ISBN-13 form suitable for linked/equality comparison."""
    if STDNUM_AVAILABLE:
        try:
            validated = stdnum_isbn.validate(isbn_str)
            return stdnum_isbn.to_isbn13(validated)
        except Exception:
            return ""

    cleaned = _simple_normalize_isbn(isbn_str)
    if not cleaned:
        return ""
    if len(cleaned) == 13:
        return cleaned
    if len(cleaned) == 10:
        prefix = "978" + cleaned[:-1]
        return prefix + _simple_isbn13_checksum(prefix)
    return ""


def linked_isbns_match(left: str, right: str) -> bool:
    """Return True when two ISBN values refer to the same linked book identifier."""
    left_canonical = _canonical_linked_isbn(left)
    right_canonical = _canonical_linked_isbn(right)
    return bool(left_canonical) and left_canonical == right_canonical


compare_linked_isbns = linked_isbns_match


def validate_isbn(isbn_str: str) -> bool:
    """
    Validate either ISBN-10 or ISBN-13.
    Normalizes hyphens automatically.
    """
    if STDNUM_AVAILABLE:
        try:
            stdnum_isbn.validate(isbn_str)
            return True
        except Exception:
            log_invalid_isbn(isbn_str, messages.GuiMessages.warn_title_invalid)
            return False
    else:
        # Fallback to simple validation
        result = _simple_validate_isbn(isbn_str)
        if not result:
            log_invalid_isbn(isbn_str, messages.GuiMessages.warn_title_invalid)
        return result
