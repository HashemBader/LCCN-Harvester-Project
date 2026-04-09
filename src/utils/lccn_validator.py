"""
lccn_validator.py

Validates Library of Congress Classification (LCC) call numbers against the
MARC 050 field format.

Background
----------
The LC Classification system assigns a call number to every item catalogued
by the Library of Congress.  Call numbers are stored in MARC field 050 and
follow a hierarchical structure:

    <Class letters><Class digits>[.<Decimal>] [<Cutter>] [<Year>] ...

Examples of valid LC call numbers:
    QA76              — class letters + class digits only
    QA76.73           — class with decimal subdivision
    QA76.73.P38       — class + decimal + Cutter number
    HF5726.B27 1980   — class + Cutter + publication year

The validator here uses a character-by-character approach rather than a
single large regex so that each rule is explicit and easy to adjust.

Important note on terminology
------------------------------
The abbreviation "LCCN" in this project refers to LC **Classification** call
numbers (MARC 050), NOT to LC **Control** Numbers (MARC 010, e.g. "2007039987").
These are two completely different things that share a similar acronym.

Part of the LCCN Harvester Project.
"""


def is_valid_lccn(call_number: str) -> bool:
    """
    Return ``True`` if ``call_number`` is a structurally valid LC Classification call number.

    Validation rules (per MARC 050 / LC Classification schedule)
    -------------------------------------------------------------
    1. The **class letters** must be 1–3 uppercase letters from the LC
       alphabet (A–Z excluding ``I`` and ``O``, which are not assigned in the
       LC schedule).
    2. Immediately after the letters, there must be 1–4 digits (the class
       number, up to 9999 in the current schedule).
    3. After the class digits, an optional **decimal subdivision** may follow,
       beginning with ``.`` and containing alphanumeric segments.
    4. Remaining space-separated tokens are validated as one of:
       - A **Cutter number**: starts with ``.``, followed by a letter, then
         alphanumeric characters (e.g., ``.P38``, ``.B27``).
       - A **year**: exactly 4 digits.
       - A **supplementary number**: 1–3 digits.
       - Any alphanumeric/period token (permissive to handle edge cases in
         real cataloguing data).

    Parameters
    ----------
    call_number : str
        Candidate call number string (may contain leading/trailing whitespace).

    Returns
    -------
    bool
        ``True`` if the call number passes all structural checks.
    """
    if not call_number:
        return False

    call_number = call_number.strip()

    if not call_number:
        return False

    # Split on whitespace; each token is validated separately below.
    parts = call_number.split()

    if len(parts) < 1:
        return False

    # The first token holds the class letters and class number (possibly with
    # a decimal subdivision), e.g. "QA76", "QA76.73", "QA76.73.P38".
    class_part = parts[0]

    if not class_part:
        return False

    # --- Step 1: Parse class letters ---
    letters = ""
    i = 0

    while i < len(class_part) and class_part[i].isalpha():
        if class_part[i] not in "ABCDEFGHJKLMNPQRSTUVWXYZ":
            # The LC schedule never assigns classes starting with I or O.
            return False
        letters += class_part[i]
        i += 1

    # LC classes are 1, 2, or 3 letters (e.g., Q, QA, QAB).
    if not (1 <= len(letters) <= 3):
        return False

    # --- Step 2: Parse class digits ---
    remainder = class_part[i:]

    # A class letter block must be followed by at least one digit.
    if not remainder:
        return False

    if not remainder[0].isdigit():
        return False

    # Consume up to 4 digits (LC class numbers range from 1 to ~9999).
    j = 0
    digit_count = 0
    while j < len(remainder) and remainder[j].isdigit() and digit_count < 4:
        digit_count += 1
        j += 1

    if digit_count == 0:
        return False

    # --- Step 3: Validate optional decimal subdivision within the first token ---
    # e.g., ".73" in "QA76.73" or ".73.P38" in "QA76.73.P38"
    rest = remainder[j:]
    if rest:
        if not _is_valid_lccn_remainder(rest):
            return False

    # --- Step 4: Validate subsequent space-separated tokens ---
    for part in parts[1:]:
        if not part:
            continue

        if part.startswith("."):
            # Cutter number format: .X## where X is a letter and ## are digits/letters.
            # Minimum valid cutter: ".A1" (3 chars).
            if len(part) < 2:
                return False
            if not part[1].isalpha():
                return False
            for ch in part[2:]:
                if not ch.isalnum():
                    return False
        elif part.isdigit():
            # A 4-digit token is almost certainly a publication year.
            # 1–3 digit tokens can be supplementary numeric parts.
            if len(part) == 4:
                pass  # Year — always valid here
            elif 1 <= len(part) <= 3:
                pass  # Short numeric component — valid
            else:
                return False
        else:
            # Permissive catch-all for mixed alphanumeric tokens (e.g., "vol.2").
            for ch in part:
                if not (ch.isalnum() or ch == "."):
                    return False

    return True


def _is_valid_lccn_remainder(remainder: str) -> bool:
    """
    Validate the portion of a MARC 050 class token that follows the initial digits.

    This covers the decimal subdivision and inline Cutter, e.g. ``".73"``,
    ``".73.P38"``, ``".A1"`` appended directly to the class number without a
    space.

    The rule is simple: the remainder must start with a period, and every
    dot-separated segment must be entirely alphanumeric (empty segments from
    double periods are tolerated to handle edge cases in real records).

    Parameters
    ----------
    remainder : str
        The substring after the mandatory leading digits in the first
        space-token of the call number.

    Returns
    -------
    bool
    """
    if not remainder:
        return True

    # Remainder must begin with a decimal point.
    if not remainder.startswith("."):
        return False

    # Split on "." and validate each non-empty segment.
    segments = remainder.split(".")

    # segments[0] is always "" because of the leading "."; skip it.
    for i, segment in enumerate(segments[1:], 1):
        if not segment:
            # Empty segment from a double period or trailing period — tolerated.
            continue

        for ch in segment:
            if not ch.isalnum():
                return False

    return True
