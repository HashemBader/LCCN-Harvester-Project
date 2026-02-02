"""
Module: isbn_validator.py
Part of the LCCN Harvester Project.
"""

from stdnum import isbn
from datetime import datetime
from pathlib import Path
from . import messages

INVALID_ISBN_LOG = Path("invalid_isbns.log")


def log_invalid_isbn(isbn_value: str, reason: str = messages.GuiMessages.warn_title_invalid) -> None:
    """
    Append an invalid ISBN entry to the invalid ISBN log file.
    """
    timestamp = datetime.now().isoformat()
    with INVALID_ISBN_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{timestamp}\t{isbn_value}\t{reason}\n")



""" Working on trying to find a way to output the reason for ISBN reading invalid"""




# def log_invalid_isbn(
#     isbn_value: str,
#     reason: str = "Invalid ISBN",
#     source: str = "Unknown"
# ) -> None:
#     """
#     Append an invalid ISBN entry to the invalid ISBN log file.
#
#     Format (tab-separated):
#     timestamp    raw_isbn    reason    source
#     """
#     timestamp = datetime.now().isoformat()
#
#     with INVALID_ISBN_LOG.open("a", encoding="utf-8") as f:
#         f.write(
#             f"{timestamp}\t"
#             f"{isbn_value}\t"
#             f"{reason}\t"
#             f"{source}\n"
#         )



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
