"""
Tests for src/utils/call_number_normalizer.py

Tests verify the exact MARC 050 and 060 $a/$b normalization rules:
- 050 LCCN: Uses first $a only, appends $b with space
- 060 NLMCN: Uses first $a only, appends $b with space
- Both handle multiple $a (first only), multiple $b (all concatenated), whitespace, etc.
"""

import pytest

from src.utils.call_number_normalizer import normalize_call_number


# ---------------------------------------------------------------------------
# 050 LCCN Normalization - Basic Cases
# ---------------------------------------------------------------------------


def test_normalize_050_single_a_only():
    """050 with single $a and no $b."""
    result = normalize_call_number(["QA76.73"])
    assert result == "QA76.73"


def test_normalize_050_single_a_single_b():
    """050 with single $a and single $b, space-separated."""
    result = normalize_call_number(["QA76.73"], ["P38"])
    assert result == "QA76.73 P38"


def test_normalize_050_single_a_multiple_b():
    """050 with single $a and multiple $b, all concatenated with spaces."""
    result = normalize_call_number(["QA76.73"], ["P38", "2005"])
    assert result == "QA76.73 P38 2005"


def test_normalize_050_first_a_used_when_multiple():
    """050 with multiple $a: only FIRST $a is used."""
    result = normalize_call_number(["QA76.73", "QA76.9"])
    assert result == "QA76.73"


def test_normalize_050_first_a_with_multiple_b():
    """050 with multiple $a and multiple $b: first $a with all $b."""
    result = normalize_call_number(["QA76.73", "QA76.9"], ["P38", "2005"])
    assert result == "QA76.73 P38 2005"


def test_normalize_050_empty_a_list():
    """050 with empty $a list returns empty string."""
    result = normalize_call_number([])
    assert result == ""


def test_normalize_050_empty_b_list():
    """050 with empty $b list is ignored."""
    result = normalize_call_number(["QA76.73"], [])
    assert result == "QA76.73"


def test_normalize_050_none_b():
    """050 with None $b (no $b field) is ignored."""
    result = normalize_call_number(["QA76.73"], None)
    assert result == "QA76.73"


# ---------------------------------------------------------------------------
# 050 LCCN Normalization - Whitespace Handling
# ---------------------------------------------------------------------------


def test_normalize_050_strips_whitespace_a():
    """$a values are stripped of leading/trailing whitespace."""
    result = normalize_call_number(["  QA76.73  "])
    assert result == "QA76.73"


def test_normalize_050_strips_whitespace_b():
    """$b values are stripped of leading/trailing whitespace."""
    result = normalize_call_number(["QA76.73"], ["  P38  "])
    assert result == "QA76.73 P38"


def test_normalize_050_strips_whitespace_both():
    """Both $a and $b are stripped."""
    result = normalize_call_number(["  QA76.73  "], ["  P38  ", "  2005  "])
    assert result == "QA76.73 P38 2005"


def test_normalize_050_empty_string_a():
    """Empty string $a returns empty string."""
    result = normalize_call_number([""])
    assert result == ""


def test_normalize_050_whitespace_only_a():
    """Whitespace-only $a becomes empty after strip."""
    result = normalize_call_number(["   "])
    assert result == ""


def test_normalize_050_whitespace_only_b():
    """Whitespace-only $b is skipped."""
    result = normalize_call_number(["QA76.73"], ["   "])
    assert result == "QA76.73"


def test_normalize_050_mixed_empty_b_values():
    """Multiple $b with some empty/whitespace are skipped."""
    result = normalize_call_number(["QA76.73"], ["P38", "   ", "2005"])
    assert result == "QA76.73 P38 2005"


# ---------------------------------------------------------------------------
# 050 LCCN Normalization - Edge Cases
# ---------------------------------------------------------------------------


def test_normalize_050_preserves_internal_spacing():
    """Internal spacing within $a/$b values is preserved."""
    result = normalize_call_number(["QA 76.73 X"], ["P 38 Y"])
    assert result == "QA 76.73 X P 38 Y"


def test_normalize_050_preserves_punctuation():
    """Punctuation and special characters in $a/$b are preserved."""
    result = normalize_call_number(["QA76.73.P38"], [".2005"])
    assert result == "QA76.73.P38 .2005"


def test_normalize_050_three_b_values():
    """Three $b values are all included."""
    result = normalize_call_number(["QA76.73"], ["P38", "2005", "v.1"])
    assert result == "QA76.73 P38 2005 v.1"


def test_normalize_050_three_a_uses_first():
    """Three $a values, only first is used."""
    result = normalize_call_number(["QA76.73", "QA76.9", "QA77.5"], ["P38"])
    assert result == "QA76.73 P38"


def test_normalize_050_real_world_example_1():
    """Real-world LC call number: PS3562.E353 with cutter T6 and year 2002."""
    result = normalize_call_number(["PS3562.E353"], ["T6", "2002"])
    assert result == "PS3562.E353 T6 2002"


def test_normalize_050_real_world_example_2():
    """Real-world LC call number: HF5726 with cutter B27 and year 1980."""
    result = normalize_call_number(["HF5726"], ["B27", "1980"])
    assert result == "HF5726 B27 1980"


# ---------------------------------------------------------------------------
# 060 NLMCN Normalization - Basic Cases
# ---------------------------------------------------------------------------


def test_normalize_060_single_a_only():
    """060 with single $a and no $b."""
    result = normalize_call_number(["WG 120.5"])
    assert result == "WG 120.5"


def test_normalize_060_single_a_single_b():
    """060 with single $a and single $b, space-separated."""
    result = normalize_call_number(["WG 120.5"], ["C65"])
    assert result == "WG 120.5 C65"


def test_normalize_060_single_a_multiple_b():
    """060 with single $a and multiple $b, all concatenated with spaces."""
    result = normalize_call_number(["WG 120.5"], ["C65", "2010"])
    assert result == "WG 120.5 C65 2010"


def test_normalize_060_first_a_used_when_multiple():
    """060 with multiple $a: only FIRST $a is used."""
    result = normalize_call_number(["WG 120.5", "WG 120.6"])
    assert result == "WG 120.5"


def test_normalize_060_first_a_with_multiple_b():
    """060 with multiple $a and multiple $b: first $a with all $b."""
    result = normalize_call_number(["WG 120.5", "WG 120.6"], ["C65", "2010"])
    assert result == "WG 120.5 C65 2010"


# ---------------------------------------------------------------------------
# 060 NLMCN Normalization - Whitespace Handling
# ---------------------------------------------------------------------------


def test_normalize_060_strips_whitespace_a():
    """$a values are stripped of leading/trailing whitespace."""
    result = normalize_call_number(["  WG 120.5  "])
    assert result == "WG 120.5"


def test_normalize_060_strips_whitespace_b():
    """$b values are stripped of leading/trailing whitespace."""
    result = normalize_call_number(["WG 120.5"], ["  C65  "])
    assert result == "WG 120.5 C65"


def test_normalize_060_empty_string_a():
    """Empty string $a returns empty string."""
    result = normalize_call_number([""])
    assert result == ""


def test_normalize_060_whitespace_only_a():
    """Whitespace-only $a becomes empty after strip."""
    result = normalize_call_number(["   "])
    assert result == ""


def test_normalize_060_whitespace_only_b():
    """Whitespace-only $b is skipped."""
    result = normalize_call_number(["WG 120.5"], ["   "])
    assert result == "WG 120.5"


# ---------------------------------------------------------------------------
# 060 NLMCN Normalization - Edge Cases
# ---------------------------------------------------------------------------


def test_normalize_060_preserves_internal_spacing():
    """Internal spacing within $a/$b values is preserved."""
    result = normalize_call_number(["WG 120.5 X"], ["C 65 Y"])
    assert result == "WG 120.5 X C 65 Y"


def test_normalize_060_preserves_punctuation():
    """Punctuation and special characters in $a/$b are preserved."""
    result = normalize_call_number(["WG120.5.6"], [".C65"])
    assert result == "WG120.5.6 .C65"


def test_normalize_060_three_b_values():
    """Three $b values are all included."""
    result = normalize_call_number(["WG 120.5"], ["C65", "2010", "v.2"])
    assert result == "WG 120.5 C65 2010 v.2"


def test_normalize_060_three_a_uses_first():
    """Three $a values, only first is used."""
    result = normalize_call_number(["WG 120.5", "WG 120.6", "WG 120.7"], ["C65"])
    assert result == "WG 120.5 C65"


def test_normalize_060_real_world_example_1():
    """Real-world NLM call number: WG 120.5 with subdivision C65."""
    result = normalize_call_number(["WG 120.5"], ["C65"])
    assert result == "WG 120.5 C65"


def test_normalize_060_real_world_example_2():
    """Real-world NLM call number: RA 644.5 with cutter and year."""
    result = normalize_call_number(["RA 644.5"], ["F6", "2015"])
    assert result == "RA 644.5 F6 2015"


# ---------------------------------------------------------------------------
# Consistency Tests - 050 and 060 Use Same Rule
# ---------------------------------------------------------------------------


def test_normalize_050_060_same_structure_a_only():
    """050 and 060 treat $a-only the same."""
    a_lccn = normalize_call_number(["QA76.73"])
    a_nlmcn = normalize_call_number(["WG 120.5"])
    assert a_lccn == "QA76.73"
    assert a_nlmcn == "WG 120.5"


def test_normalize_050_060_same_structure_a_b():
    """050 and 060 treat $a + $b the same."""
    ab_lccn = normalize_call_number(["QA76.73"], ["P38"])
    ab_nlmcn = normalize_call_number(["WG 120.5"], ["C65"])
    assert ab_lccn == "QA76.73 P38"
    assert ab_nlmcn == "WG 120.5 C65"


def test_normalize_050_060_same_structure_multiple_b():
    """050 and 060 treat multiple $b the same."""
    mult_b_lccn = normalize_call_number(["QA76.73"], ["P38", "2005"])
    mult_b_nlmcn = normalize_call_number(["WG 120.5"], ["C65", "2010"])
    assert mult_b_lccn == "QA76.73 P38 2005"
    assert mult_b_nlmcn == "WG 120.5 C65 2010"


def test_normalize_050_060_same_structure_multiple_a_ignored():
    """050 and 060 both ignore extra $a values."""
    mult_a_lccn = normalize_call_number(["QA76.73", "QA76.9"], ["P38"])
    mult_a_nlmcn = normalize_call_number(["WG 120.5", "WG 120.6"], ["C65"])
    assert mult_a_lccn == "QA76.73 P38"
    assert mult_a_nlmcn == "WG 120.5 C65"


def test_normalize_050_060_same_whitespace_handling():
    """050 and 060 handle whitespace the same."""
    ws_lccn = normalize_call_number(["  QA76.73  "], ["  P38  "])
    ws_nlmcn = normalize_call_number(["  WG 120.5  "], ["  C65  "])
    assert ws_lccn == "QA76.73 P38"
    assert ws_nlmcn == "WG 120.5 C65"


# ---------------------------------------------------------------------------
# Integration with Marc Parser - Normalization Rule Enforcement
# ---------------------------------------------------------------------------


def test_normalize_ensures_first_a_rule_050():
    """Ensures the 'first $a' rule for 050 fields per MARC standard."""
    # Simulating marc_parser extracting multiple $a from 050
    a_values = ["QA76.73", "QA76.9"]  # Both extracted but only first used
    b_values = ["P38"]
    result = normalize_call_number(a_values, b_values)
    assert result == "QA76.73 P38"
    assert "QA76.9" not in result


def test_normalize_ensures_first_a_rule_060():
    """Ensures the 'first $a' rule for 060 fields per MARC standard."""
    # Simulating marc_parser extracting multiple $a from 060
    a_values = ["WG 120.5", "WG 120.6"]  # Both extracted but only first used
    b_values = ["C65"]
    result = normalize_call_number(a_values, b_values)
    assert result == "WG 120.5 C65"
    assert "WG 120.6" not in result


def test_normalize_ensures_all_b_rule_050():
    """Ensures the 'all $b' rule for 050 fields per MARC standard."""
    # Simulating marc_parser extracting multiple $b from 050
    a_values = ["QA76.73"]
    b_values = ["P38", "2005"]  # All $b included
    result = normalize_call_number(a_values, b_values)
    assert result == "QA76.73 P38 2005"
    assert "P38" in result
    assert "2005" in result


def test_normalize_ensures_all_b_rule_060():
    """Ensures the 'all $b' rule for 060 fields per MARC standard."""
    # Simulating marc_parser extracting multiple $b from 060
    a_values = ["WG 120.5"]
    b_values = ["C65", "2010"]  # All $b included
    result = normalize_call_number(a_values, b_values)
    assert result == "WG 120.5 C65 2010"
    assert "C65" in result
    assert "2010" in result


def test_normalize_exact_spacing_050():
    """Exact spacing rule: first $a + space + (all $b joined with spaces)."""
    a_values = ["QA76.73", "EXTRA"]
    b_values = ["P38", "2005"]
    result = normalize_call_number(a_values, b_values)
    # Should be exactly: first $a, space, first $b, space, second $b
    assert result == "QA76.73 P38 2005"
    # Verify spacing is exactly one space between components
    assert "  " not in result  # No double spaces


def test_normalize_exact_spacing_060():
    """Exact spacing rule: first $a + space + (all $b joined with spaces)."""
    a_values = ["WG 120.5", "EXTRA"]
    b_values = ["C65", "2010"]
    result = normalize_call_number(a_values, b_values)
    # Should be exactly: first $a, space, first $b, space, second $b
    assert result == "WG 120.5 C65 2010"
    # Verify spacing is exactly one space between components
    assert "  " not in result  # No double spaces

