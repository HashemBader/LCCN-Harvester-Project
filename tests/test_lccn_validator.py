"""
Tests for src/utils/lccn_validator.py

Covers:
- Standard 2- and 3-letter LC classes (QA, PS, HF, etc.)
- 4-digit class numbers (regression: previously capped at 3 digits)
- Cutter numbers (.P38, .C65, etc.)
- Years as optional trailing components
- Rejection of LC control numbers (MARC 010, digits-only)
- Rejection of invalid formats (excluded letters I/O, too many letters, no digits)
"""

import pytest

from src.utils.lccn_validator import is_valid_lccn


@pytest.mark.parametrize(
    "call_number",
    [
        "QA76",                    # 2-letter, digits only
        "QA76.73",                 # 2-letter, decimal
        "QA76.73.P38",             # 2-letter, decimal, inline cutter
        "QA76.73 P38",             # 2-letter, decimal, space-separated cutter
        "F123.A5",                 # 1-letter class
        "ABC76.C65",               # 3-letter class
        "PS3562.E353 T6 2002",     # 2-letter, 4-digit class (regression: was rejected)
        "HF5726.B27 1980",         # 2-letter, 4-digit class with year
        "PZ7.C6837 Hun 2008",      # 1-digit class + word cutter + year
        "QA76.76.C65",             # double decimal
        "QA76.76 .C65 2008",       # space before cutter + year
        "RA418.5.P6",              # 1-letter, 3-digit, decimal cutter
    ],
)
def test_is_valid_lccn_valid(call_number):
    assert is_valid_lccn(call_number) is True, f"Expected {call_number!r} to be valid"


@pytest.mark.parametrize(
    "call_number",
    [
        "2007039987",              # LC control number (MARC 010) — digits only
        "2001016794",              # another LC control number
        "n  81067739",             # normalised LC control number format
        "INVALID",                 # starts with excluded letter I
        "ABCDE76",                 # 5 letters — exceeds 3-letter maximum
        "AB",                      # letters only, no digits after
        "I100.A5",                 # I is excluded from LC classes
        "O100.A5",                 # O is excluded from LC classes
        "",                        # empty string
        "   ",                     # whitespace only
    ],
)
def test_is_valid_lccn_invalid(call_number):
    assert is_valid_lccn(call_number) is False, f"Expected {call_number!r} to be invalid"


def test_four_digit_class_regression():
    """
    Regression test: the validator previously capped class digits at 3, rejecting
    real LC call numbers like PS3562 (4 digits).  The fix raised the cap to 4.
    """
    assert is_valid_lccn("PS3562.E353 T6 2002") is True
    assert is_valid_lccn("HF5726.B27 1980") is True
    # 5-digit class numbers do not exist in the LC schedule — still rejected
    assert is_valid_lccn("QA76543") is False


def test_excluded_letters():
    """I and O are excluded from the LC classification schedule."""
    assert is_valid_lccn("I001.A5") is False
    assert is_valid_lccn("O001.A5") is False
    # Nearby valid letters work
    assert is_valid_lccn("H001.A5") is True
    assert is_valid_lccn("N001.A5") is True
