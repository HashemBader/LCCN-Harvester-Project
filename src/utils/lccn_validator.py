"""
Module: lccn_validator.py
Part of the LCCN Harvester Project.
"""


def is_valid_lccn(call_number: str) -> bool:
    """
    Validate an LCCN call number
    """
    if not call_number:
        return False

    parts = call_number.strip().split()

    if len(parts) < 1:
        return False

    # Part 1: Class letters + number
    class_part = parts[0]

    # Split letters and numbers
    letters = ""
    numbers = ""

    for ch in class_part:
        if ch.isalpha():
            letters += ch
        elif ch.isdigit() or ch == ".":
            numbers += ch
        else:
            return False

    # Validate class letters
    if not (1 <= len(letters) <= 3):
        return False

    for ch in letters:
        if ch not in "ABCDEFGHJKLMNPQRSTUVWXYZ":
            return False  # Excludes I and O

    # Validate class number
    if not numbers or numbers.count(".") > 1:
        return False

    try:
        float(numbers)
    except ValueError:
        return False

    # Optional parts
    for part in parts[1:]:
        # Cutter: .A12
        if part.startswith(".") and len(part) >= 3:
            if not (part[1].isalpha() and part[2:].isdigit()):
                return False
        # Year: YYYY
        elif part.isdigit() and len(part) == 4:
            pass
        else:
            return False

    return True
