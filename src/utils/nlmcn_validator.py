"""
Module: nlmcn_validator.py
Part of the LCCN Harvester Project.
"""

def is_valid_nlmcn(call_number: str) -> bool:
    """
    Validate an NLMCN call number.

    NLMCN Format (per MARC 060):
    - Class: 1-3 letters from valid NLM classes (W, WA, WB, ..., QS, QT, etc.)
    - Class Number: 1-3 digits, optionally followed by decimal notation (.digits, .letters+digits, etc.)
    - Optional Components: Additional cutters or years (space-separated)

    Examples:
    - WG 120 (class + number)
    - WG 120.5 (class + number with decimal)
    - WG 120.5 .A1 (class + number + cutter)
    - WG 120.5 1980 (class + number + year)
    """
    if not call_number:
        return False

    parts = call_number.strip().split()

    if len(parts) < 2:
        return False  # NLM always has class + number

    # Part 1: Class letters
    class_letters = parts[0]

    if not class_letters.replace(".", "").isalpha():
        return False

    # Valid NLM classes
    valid_nlm_classes = {
        "QS", "QT", "QU", "QV", "QW",
        "W", "WA", "WB", "WC", "WD", "WE", "WF", "WG", "WH", "WI",
        "WJ", "WK", "WL", "WM", "WN", "WO", "WP", "WQ", "WR", "WS",
        "WT", "WU", "WV", "WW", "WX", "WY", "WZ"
    }

    if class_letters not in valid_nlm_classes:
        return False

    # Part 2: Class number (may include decimal notation like 120.5)
    class_number_part = parts[1]

    # Must start with digits
    if not class_number_part or not class_number_part[0].isdigit():
        return False

    # Extract initial digits (1-3)
    i = 0
    digit_count = 0
    while i < len(class_number_part) and class_number_part[i].isdigit() and digit_count < 3:
        digit_count += 1
        i += 1

    if digit_count == 0:
        return False

    # Validate remainder after initial digits (decimal notation like .5, .A1, etc.)
    remainder = class_number_part[i:]
    if remainder:
        if not _is_valid_nlmcn_remainder(remainder):
            return False

    # Optional parts
    for part in parts[2:]:
        # Cutter: .A12, .GA1
        if part.startswith(".") and len(part) >= 3:
            if not (part[1].isalpha() and part[2:].isalnum()):
                return False
        # Year: YYYY
        elif part.isdigit() and len(part) == 4:
            pass
        else:
            return False

    return True


def _is_valid_nlmcn_remainder(remainder: str) -> bool:
    """
    Validate the remainder after the initial class digits in NLMCN.

    This includes patterns like: .5, .A1, .123, etc.
    """
    if not remainder:
        return True

    # Must start with a period
    if not remainder.startswith("."):
        return False

    # Split by periods to validate each segment
    segments = remainder.split(".")

    # First segment is empty (from leading period)
    for segment in segments[1:]:
        if not segment:
            # Double period or trailing period - generally invalid
            continue

        # Each segment should be alphanumeric
        for ch in segment:
            if not ch.isalnum():
                return False

    return True

