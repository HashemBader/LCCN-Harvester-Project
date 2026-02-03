"""
Module: isbn_validator.py
Part of the LCCN Harvester Project.
"""

from stdnum import isbn
from datetime import datetime
from pathlib import Path
from src.utils import messages

INVALID_ISBN_LOG = Path("invalid_isbns.log")


def normalize_isbn(raw: str) -> str:
    """
    Normalize ISBN input into a clean string.

    Rules:
    - Strip leading/trailing whitespace
    - Remove hyphens and spaces
    - Keep as text (never convert to int)
    """
    return raw.strip().replace("-", "").replace(" ", "")


def log_invalid_isbn(isbn_value: str, reason: str = messages.GuiMessages.warn_title_invalid) -> None:
    """
    Append an invalid ISBN entry to the invalid ISBN log file.
    """
    timestamp = datetime.now().isoformat()
    with INVALID_ISBN_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{timestamp}\t{isbn_value}\n")


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
