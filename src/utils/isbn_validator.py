"""
Module: isbn_validator.py
Part of the LCCN Harvester Project.
"""

from stdnum import isbn
from datetime import datetime
from pathlib import Path
import messages

INVALID_ISBN_LOG = Path("invalid_isbns.log")


def log_invalid_isbn(isbn_value: str, reason: str = messages.GuiMessages.warn_title_invalid) -> None:
    """
    Append an invalid ISBN entry to the invalid ISBN log file.
    """
    timestamp = datetime.now().isoformat()
    with INVALID_ISBN_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{timestamp}\t{isbn_value}\t{reason}\n")
    return False

def normalize_isbn(isbn_str: str) -> str:
    """
    Normalize an ISBN string to a valid ISBN string.
    """
    try:
        normalized_isbn_str = isbn.validate(isbn_str)
        return normalized_isbn_str
    except Exception:
        log_invalid_isbn(isbn_str, messages.GuiMessages.warn_title_invalid)
        return ""


def validate_isbn(isbn_str: str) -> bool:
    """
    Validate either ISBN-10 or ISBN-13.
    Normalizes hyphens automatically.
    """
    try:
        isbn.validate(isbn_str)
        return True
    except Exception:
        log_invalid_isbn(isbn_str, messages.GuiMessages.warn_title_invalid)
        return False
