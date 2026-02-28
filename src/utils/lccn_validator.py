"""
Module: lccn_validator.py
Part of the LCCN Harvester Project.
"""


def is_valid_lccn(call_number: str) -> bool:
    """
    Validate an LCCN call number.

    LCCN Format (per MARC 050):
    - Class: 1-3 letters (A-Z, excluding I and O) followed by 1-3 digits
    - Optional Cutter: . + letter + digits (e.g., .P38, .B27)
    - Optional Additional Parts: Further cutters, decimal points with digits/letters, years, etc.

    Examples:
    - QA76 (class only)
    - QA76.73 (class + decimal)
    - QA76.73.P38 (class + decimal + cutter)
    - HF5726.B27 1980 (class + cutter + year)
    """
    if not call_number:
        return False

    call_number = call_number.strip()

    if not call_number:
        return False

    # Split into space-separated components
    parts = call_number.split()

    if len(parts) < 1:
        return False

    # Part 1: Class (letters + numbers, possibly with decimal)
    class_part = parts[0]

    if not class_part:
        return False

    # Extract initial letters and numbers (before any decimal)
    letters = ""
    numbers = ""
    i = 0

    # Get leading letters
    while i < len(class_part) and class_part[i].isalpha():
        if class_part[i] not in "ABCDEFGHJKLMNPQRSTUVWXYZ":
            return False  # Excludes I and O
        letters += class_part[i]
        i += 1

    # Validate we have 1-3 letters
    if not (1 <= len(letters) <= 3):
        return False

    # Get digits (and decimal parts)
    remainder = class_part[i:]

    # The remainder should be valid LCCN continuation:
    # digits, then optionally: .digits, .letters+digits, etc.
    if not remainder:
        return False

    # First character after letters must be a digit
    if not remainder[0].isdigit():
        return False

    # Collect leading digits (1-3)
    j = 0
    digit_count = 0
    while j < len(remainder) and remainder[j].isdigit() and digit_count < 3:
        digit_count += 1
        j += 1

    if digit_count == 0:
        return False

    # After the required digits, we can have:
    # - Nothing (valid)
    # - Space-separated parts (handled below)
    # - .digits, .letters+digits, etc. (part of class_part)

    # Validate remainder after initial digits (decimal notation)
    rest = remainder[j:]
    if rest:
        # Must follow decimal notation pattern: .X.X.X etc
        # where X can be letters, digits, or combinations
        if not _is_valid_lccn_remainder(rest):
            return False

    # Validate remaining space-separated parts
    for part in parts[1:]:
        if not part:
            continue

        # Can be:
        # 1. Cutter: .X## (e.g., .P38, .B27)
        # 2. Year: YYYY
        # 3. Other variations

        if part.startswith("."):
            # Cutter format: .X## or similar
            if len(part) < 2:
                return False
            # After the dot, should start with a letter
            if not part[1].isalpha():
                return False
            # Rest should be alphanumeric
            for ch in part[2:]:
                if not ch.isalnum():
                    return False
        elif part.isdigit():
            # Could be year or class number
            if len(part) == 4:
                # Likely a year
                pass
            elif 1 <= len(part) <= 3:
                # Could be a number component
                pass
            else:
                return False
        else:
            # Other formats - be permissive but check structure
            # Allow letters and digits mixed, with periods
            for ch in part:
                if not (ch.isalnum() or ch == "."):
                    return False

    return True


def _is_valid_lccn_remainder(remainder: str) -> bool:
    """
    Validate the remainder after the initial class letters and digits.

    This includes patterns like: .73.P38, .A1, etc.
    """
    if not remainder:
        return True

    # Must start with a period
    if not remainder.startswith("."):
        return False

    # Split by periods to validate each segment
    segments = remainder.split(".")

    # First segment is empty (from leading period)
    for i, segment in enumerate(segments[1:], 1):
        if not segment:
            # Double period or trailing period - could be valid in some cases
            continue

        # Each segment should be alphanumeric
        for ch in segment:
            if not ch.isalnum():
                return False

    return True
