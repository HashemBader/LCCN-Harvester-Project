"""
nlmcn_validator.py

Validates National Library of Medicine (NLM) Classification call numbers
against the MARC 060 field format.

Background
----------
The NLM Classification system assigns call numbers to health-sciences
literature catalogued by the National Library of Medicine.  Call numbers are
stored in MARC field 060 and follow this structure:

    <Class letters> <Class digits>[.<Decimal>] [<Cutter>] [<Year>]

The NLM schedule uses a closed set of two-character (or single ``W``) class
prefixes — all starting with ``W`` or with the preclinical science codes
``QS``, ``QT``, ``QU``, ``QV``, ``QW``.

Examples of valid NLM call numbers:
    WG 120           — class + number
    WG 120.5         — class + number with decimal subdivision
    WG 120.5 .A1     — class + number + Cutter
    WG 120.5 1980    — class + number + publication year
    QV 55 .B45 2001  — pre-clinical sciences class + number + Cutter + year

Part of the LCCN Harvester Project.
"""

def is_valid_nlmcn(call_number: str) -> bool:
    """
    Return ``True`` if ``call_number`` is a structurally valid NLM call number.

    Validation rules (per MARC 060 / NLM Classification schedule)
    -------------------------------------------------------------
    1. The first space-separated token must be a recognised NLM **class prefix**
       (one of the entries in ``valid_nlm_classes``).
    2. The second token must begin with 1–3 digits (the class number), optionally
       followed by a decimal subdivision validated by
       :func:`_is_valid_nlmcn_remainder`.
    3. Any additional tokens must each be either:
       - A **Cutter number**: starts with ``.``, then a letter, then alphanumeric
         chars (e.g., ``.A12``, ``.GA1``).
       - A **year**: exactly 4 digits.
       Anything else is rejected, making NLM validation stricter than the LC
       validator in its treatment of supplementary tokens.

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

    # NLM call numbers always have at least two space-separated tokens:
    # the class prefix (e.g., "WG") and the class number (e.g., "120").
    parts = call_number.strip().split()

    if len(parts) < 2:
        return False

    # --- Step 1: Validate class prefix ---
    class_letters = parts[0]

    # The class prefix must be purely alphabetic (no digits or punctuation).
    if not class_letters.replace(".", "").isalpha():
        return False

    # Complete set of valid NLM schedule prefixes.
    # "QS"–"QW" cover the pre-clinical basic sciences; all "W*" codes cover
    # clinical and health-services topics.
    valid_nlm_classes = {
        "QS", "QT", "QU", "QV", "QW",
        "W", "WA", "WB", "WC", "WD", "WE", "WF", "WG", "WH", "WI",
        "WJ", "WK", "WL", "WM", "WN", "WO", "WP", "WQ", "WR", "WS",
        "WT", "WU", "WV", "WW", "WX", "WY", "WZ"
    }

    if class_letters not in valid_nlm_classes:
        return False

    # --- Step 2: Validate class number token ---
    # The class number may include an inline decimal subdivision, e.g. "120.5".
    class_number_part = parts[1]

    if not class_number_part or not class_number_part[0].isdigit():
        return False

    # NLM class numbers are 1–3 digits (1–999 in the current schedule).
    i = 0
    digit_count = 0
    while i < len(class_number_part) and class_number_part[i].isdigit() and digit_count < 3:
        digit_count += 1
        i += 1

    if digit_count == 0:
        return False

    # Anything after the initial digits must be a valid decimal continuation.
    remainder = class_number_part[i:]
    if remainder:
        if not _is_valid_nlmcn_remainder(remainder):
            return False

    # --- Step 3: Validate optional supplementary tokens ---
    for part in parts[2:]:
        # Cutter number: at least 3 chars — ".", a letter, then alphanumeric chars.
        if part.startswith(".") and len(part) >= 3:
            if not (part[1].isalpha() and part[2:].isalnum()):
                return False
        # Publication year: exactly 4 digits.
        elif part.isdigit() and len(part) == 4:
            pass
        else:
            # NLM validation is strict — any other token format is rejected.
            return False

    return True


def _is_valid_nlmcn_remainder(remainder: str) -> bool:
    """
    Validate the inline decimal extension of an NLM class number token.

    Handles patterns like ``.5``, ``.A1``, ``.123`` appended directly to the
    class digits within the second space-token (e.g., the ``.5`` in ``120.5``).

    Parameters
    ----------
    remainder : str
        Substring of the class number token that follows the leading digits.

    Returns
    -------
    bool
    """
    if not remainder:
        return True

    # The decimal extension must begin with a period.
    if not remainder.startswith("."):
        return False

    # Validate each dot-separated segment (skip the empty first segment from
    # the leading ".").
    segments = remainder.split(".")

    for segment in segments[1:]:
        if not segment:
            # Empty segment (double period / trailing period) — tolerated.
            continue

        for ch in segment:
            if not ch.isalnum():
                return False

    return True

