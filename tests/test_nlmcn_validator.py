"""
Tests for src/utils/nlmcn_validator.py

Covers:
- Standard NLM call number formats (class + number, with/without decimal, cutter, year)
- All major valid NLM class prefixes (Q*, W*)
- Rejection of invalid class letters, missing class number, wrong trailing parts
- Rejection of bare LC control numbers
"""

import pytest

from src.utils.nlmcn_validator import is_valid_nlmcn


@pytest.mark.parametrize(
    "call_number",
    [
        "WG 120",             # class + integer number
        "WG 120.5",           # class + decimal number
        "WA 100",             # WA class
        "WZ 112",             # WZ class
        "QS 4",               # QS class, single-digit number
        "QT 34",              # QT class
        "WG 120.5 .A1",       # with cutter
        "WG 120.5 1980",      # with 4-digit year
        "WB 310",             # WB class
        "WN 200.5 .R3",       # radiology class with cutter
    ],
)
def test_is_valid_nlmcn_valid(call_number):
    assert is_valid_nlmcn(call_number) is True, f"Expected {call_number!r} to be valid"


@pytest.mark.parametrize(
    "call_number",
    [
        "",                   # empty string
        "WG",                 # class only, no number
        "XYZ 123",            # not a valid NLM class
        "ABC 123",            # not a valid NLM class
        "LC 100",             # LC, not NLM
        "WG abc",             # non-digit class number
        "2007039987",         # LC control number (no class letters)
        "WG 120 5",           # extra single digit — not a valid year (len != 4)
        "WG 120 abc",         # extra alphabetic part — not allowed
    ],
)
def test_is_valid_nlmcn_invalid(call_number):
    assert is_valid_nlmcn(call_number) is False, f"Expected {call_number!r} to be invalid"


def test_all_q_subclasses_valid():
    """QS, QT, QU, QV, QW are all valid NLM classes."""
    for cls in ("QS", "QT", "QU", "QV", "QW"):
        assert is_valid_nlmcn(f"{cls} 10") is True


def test_all_w_subclasses_valid():
    """WA through WZ (excluding invalid combos) are valid NLM classes."""
    for cls in ("WA", "WB", "WC", "WD", "WE", "WF", "WG", "WH", "WI",
                "WJ", "WK", "WL", "WM", "WN", "WO", "WP", "WQ", "WR",
                "WS", "WT", "WU", "WV", "WW", "WX", "WY", "WZ"):
        assert is_valid_nlmcn(f"{cls} 10") is True


def test_bare_w_class_valid():
    """'W' on its own (without a suffix letter) is a valid NLM class."""
    assert is_valid_nlmcn("W 26.5") is True
