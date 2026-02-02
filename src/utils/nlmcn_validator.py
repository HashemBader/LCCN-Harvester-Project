"""
Module: nlmcn_validator.py
Part of the LCCN Harvester Project.
"""

def is_valid_nlmcn(call_number: str) -> bool:
    """
    Validate an NLMCN
    """
    if not call_number:
        return False

    parts = call_number.strip().split()

    if len(parts) < 2:
        return False  # NLM always has class + number

    # Part 1: Class letters
    class_letters = parts[0]

    if not class_letters.isalpha():
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

    # Part 2: Class number
    class_number = parts[1]

    if not class_number.isdigit():
        return False

    if not (1 <= len(class_number) <= 3):
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
