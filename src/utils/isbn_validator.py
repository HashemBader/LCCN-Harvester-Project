"""
Module: isbn_validator.py
Part of the LCCN Harvester Project.
"""

from datetime import datetime
from pathlib import Path
import re

try:
    from stdnum import isbn as stdnum_isbn
    STDNUM_AVAILABLE = True
except ImportError:
    STDNUM_AVAILABLE = False

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
