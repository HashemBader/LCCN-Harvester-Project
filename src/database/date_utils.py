"""
Date and formatting helpers shared by the database layer.

The database stores all date values as ``YYYYMMDD`` integers (e.g. 20240315)
for easy sorting and range queries without relying on SQLite's text-based
date functions.  This module provides the conversion utilities needed to move
between that integer format, ISO-8601 strings, and Python ``datetime`` objects.

Public API:
    now_datetime_str()           -- current local time as ``"YYYY-MM-DD HH:MM:SS"``
    today_yyyymmdd()             -- today as an integer ``YYYYMMDD``
    normalize_to_datetime_str()  -- any supported date value → ISO datetime string
    normalize_to_yyyymmdd_int()  -- any supported date value → ``YYYYMMDD`` integer
    yyyymmdd_to_iso_date()       -- any supported date value → ``"YYYY-MM-DD"``
    classification_from_lccn()   -- extract LoC class letters from a call number
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional


def now_datetime_str() -> str:
    """Return current local datetime as an ISO-8601 string."""
    return datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def today_yyyymmdd() -> int:
    """Return today's local date as an integer in ``YYYYMMDD`` format."""
    return int(datetime.now().strftime("%Y%m%d"))


def normalize_to_datetime_str(value: Optional[int | str]) -> Optional[str]:
    """Convert supported date values to an ISO-8601 datetime string.

    Accepted input formats:
      - ``None`` or ``""`` → returns ``None``
      - ``"YYYY-MM-DD HH:MM:SS"`` (already normalised) → returned as-is
      - ``"YYYYMMDD"`` digit string → ``"YYYY-MM-DD 00:00:00"``
      - Any ISO-8601 string (with optional ``Z`` suffix) → converted to local time
      - Integer ``YYYYMMDD`` (8 digits) → ``"YYYY-MM-DD 00:00:00"``
      - Anything else → coerced via ``str()``

    Returns:
        An ISO datetime string ``"YYYY-MM-DD HH:MM:SS"`` or ``None``.
    """
    if value in (None, ""):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # Fast-path: already in the canonical storage format
        if len(text) == 19 and text[4] == "-" and text[10] == " " and text[13] == ":":
            return text
        # Compact date-only format used in the DB (e.g. "20240315")
        if len(text) == 8 and text.isdigit():
            return f"{text[:4]}-{text[4:6]}-{text[6:8]} 00:00:00"

        try:
            # Handle ISO-8601 variants including UTC "Z" suffix
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return text

    if isinstance(value, int):
        digits = str(value)
        if len(digits) == 8:
            return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]} 00:00:00"

    return str(value)


def yyyymmdd_to_iso_date(value: Optional[int | str]) -> Optional[str]:
    """Convert supported date values into a ``YYYY-MM-DD`` date-only string.

    Delegates to ``normalize_to_datetime_str`` and strips the time component.

    Returns:
        A ``"YYYY-MM-DD"`` string, or ``None`` if *value* is empty/None.
    """
    normalized = normalize_to_datetime_str(value)
    if not normalized:
        return normalized
    return normalized[:10]


def normalize_to_yyyymmdd_int(value: Optional[int | str]) -> int:
    """Convert supported date values into a ``YYYYMMDD`` integer.

    Falls back to today's date when *value* cannot be parsed, so every row in
    the database always has a valid date.

    Args:
        value: A date value in any format accepted by
               ``normalize_to_datetime_str``, or an integer already in
               ``YYYYMMDD`` form.

    Returns:
        An 8-digit integer like ``20240315``.
    """
    if isinstance(value, int):
        digits = str(value)
        if len(digits) == 8:
            return value  # Already in YYYYMMDD form; skip further parsing

    normalized = normalize_to_datetime_str(value)
    if normalized:
        digits = normalized[:10].replace("-", "")
        if len(digits) == 8 and digits.isdigit():
            return int(digits)

    # Unrecognised format — use today so we don't store a NULL-equivalent zero
    return today_yyyymmdd()


def classification_from_lccn(lccn: Optional[str]) -> Optional[str]:
    """Best-effort derivation of LoC classification letters from a call number.

    Reads the leading alphabetic prefix of a Library of Congress call number
    (up to 3 letters) which represents the LoC subject classification (e.g.
    ``"QA"`` for mathematics, ``"PS"`` for American literature).

    Args:
        lccn: A raw LC call number string such as ``"QA76.73.P98"``.

    Returns:
        The uppercase leading letter(s) like ``"QA"``, or ``None`` if *lccn*
        is empty or starts with a non-alphabetic character.
    """
    if not lccn:
        return None
    letters: list[str] = []
    for char in lccn.strip():
        if char.isalpha():
            letters.append(char.upper())
            if len(letters) == 3:  # LoC classes are at most 3 letters (e.g. "KFX")
                break
        else:
            break  # First non-letter marks the end of the classification prefix
    return "".join(letters) if letters else None
