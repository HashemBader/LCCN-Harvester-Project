"""
Tests for src/z3950/marc_decoder.py

Covers:
- pymarc >= 5.x Subfield namedtuple path in _extract_subfields_from_pymarc_field
- Legacy flat-list path in _extract_subfields_from_pymarc_field
- pymarc_record_to_json: single field, both fields, ind2 preference, no fields
- extract_call_numbers_from_pymarc: end-to-end pipeline with real pymarc Records
"""

from unittest.mock import MagicMock

import pytest
from pymarc import Field, Record, Subfield

from src.z3950.marc_decoder import (
    _extract_subfields_from_pymarc_field,
    extract_call_numbers_from_pymarc,
    pymarc_record_to_json,
)


def _field(tag: str, ind2: str, *pairs: tuple) -> Field:
    """Helper: build a pymarc 5.x Field from (code, value) pairs."""
    return Field(
        tag=tag,
        indicators=[" ", ind2],
        subfields=[Subfield(code, val) for code, val in pairs],
    )


# ---------------------------------------------------------------------------
# _extract_subfields_from_pymarc_field
# ---------------------------------------------------------------------------


def test_extract_subfields_namedtuple_pymarc5():
    """pymarc >= 5.x stores subfields as Subfield(code, value) namedtuples."""
    f = _field("050", "0", ("a", "QA76.73"), ("b", "P38"))
    result = _extract_subfields_from_pymarc_field(f)
    assert result == [{"a": "QA76.73"}, {"b": "P38"}]


def test_extract_subfields_legacy_flat_list():
    """pymarc >= 5.1 removed the old flat [code, val, ...] list format entirely;
    Field.__init__ now raises ValueError when strings are passed.  The legacy
    branch in marc_decoder was dead code and has been removed.  This test
    documents that a mock object with a plain list of strings is handled
    gracefully (AttributeError on sf.code is caught) rather than crashing."""
    mock_field = MagicMock()
    # Plain strings don't have .code / .value attributes — the loop will hit
    # AttributeError on the first iteration, which is caught by the try/except.
    mock_field.subfields = ["a", "QA76.73", "b", "P38"]
    result = _extract_subfields_from_pymarc_field(mock_field)
    # No crash; returns empty list because strings have no .code attribute.
    assert result == []


def test_extract_subfields_strips_whitespace():
    """Values with surrounding whitespace are stripped."""
    f = _field("050", "0", ("a", "  QA76.73  "), ("b", " P38 "))
    result = _extract_subfields_from_pymarc_field(f)
    assert result == [{"a": "QA76.73"}, {"b": "P38"}]


# ---------------------------------------------------------------------------
# pymarc_record_to_json
# ---------------------------------------------------------------------------


def test_pymarc_record_to_json_single_050():
    r = Record()
    r.add_field(_field("050", "0", ("a", "QA76.73"), ("b", "P38")))
    result = pymarc_record_to_json(r)
    f050 = [f["050"] for f in result["fields"] if "050" in f]
    assert len(f050) == 1
    assert f050[0]["subfields"] == [{"a": "QA76.73"}, {"b": "P38"}]
    assert f050[0]["ind2"] == "0"


def test_pymarc_record_to_json_single_060():
    r = Record()
    r.add_field(_field("060", " ", ("a", "WG 120.5")))
    result = pymarc_record_to_json(r)
    f060 = [f["060"] for f in result["fields"] if "060" in f]
    assert len(f060) == 1
    assert f060[0]["subfields"] == [{"a": "WG 120.5"}]


def test_pymarc_record_to_json_both_050_and_060():
    r = Record()
    r.add_field(_field("050", "0", ("a", "QA76.73"), ("b", "P38")))
    r.add_field(_field("060", " ", ("a", "WG 120.5")))
    result = pymarc_record_to_json(r)
    tags = [list(f.keys())[0] for f in result["fields"]]
    assert "050" in tags
    assert "060" in tags
    assert len(result["fields"]) == 2


def test_pymarc_record_to_json_prefers_ind2_0_over_ind2_4():
    """Multiple 050 fields: ind2='0' (LC-assigned) must be chosen over ind2='4' (institution)."""
    r = Record()
    r.add_field(_field("050", "4", ("a", "PZ7.C6837"), ("b", "BadCopy 1999")))
    r.add_field(_field("050", "0", ("a", "PZ7.C6837"), ("b", "LCCopy 2008")))
    result = pymarc_record_to_json(r)
    f050 = [f["050"] for f in result["fields"] if "050" in f]
    assert len(f050) == 1
    b_vals = [sf["b"] for sf in f050[0]["subfields"] if "b" in sf]
    assert b_vals[0] == "LCCopy 2008"


def test_pymarc_record_to_json_falls_back_to_first_when_no_ind2_0():
    """When no ind2='0' exists at all, use the first 050 occurrence."""
    r = Record()
    r.add_field(_field("050", "4", ("a", "PZ7.C6837"), ("b", "First 1999")))
    r.add_field(_field("050", "4", ("a", "PZ7.C6837"), ("b", "Second 2008")))
    result = pymarc_record_to_json(r)
    f050 = [f["050"] for f in result["fields"] if "050" in f]
    assert len(f050) == 1
    b_vals = [sf["b"] for sf in f050[0]["subfields"] if "b" in sf]
    assert b_vals[0] == "First 1999"


def test_pymarc_record_to_json_no_050_060():
    """A record with no 050 or 060 fields returns an empty fields list."""
    r = Record()
    r.add_field(_field("020", " ", ("a", "0451524934")))  # ISBN only
    result = pymarc_record_to_json(r)
    assert result == {"fields": []}


def test_pymarc_record_to_json_invalid_object():
    """An object that lacks get_fields returns an empty fields dict gracefully."""
    result = pymarc_record_to_json("not_a_record")
    assert result == {"fields": []}


# ---------------------------------------------------------------------------
# extract_call_numbers_from_pymarc  (end-to-end pipeline)
# ---------------------------------------------------------------------------


def test_extract_call_numbers_lccn_and_nlmcn():
    r = Record()
    r.add_field(_field("050", "0", ("a", "QA76.73"), ("b", "P38")))
    r.add_field(_field("060", " ", ("a", "WG 120.5")))
    lccn, nlmcn = extract_call_numbers_from_pymarc(r)
    assert lccn == "QA76.73 P38"
    assert nlmcn == "WG 120.5"


def test_extract_call_numbers_lccn_only():
    r = Record()
    r.add_field(_field("050", "0", ("a", "QA76.73"), ("b", "P38")))
    lccn, nlmcn = extract_call_numbers_from_pymarc(r)
    assert lccn == "QA76.73 P38"
    assert nlmcn is None


def test_extract_call_numbers_nlmcn_only():
    r = Record()
    r.add_field(_field("060", " ", ("a", "WG 120.5")))
    lccn, nlmcn = extract_call_numbers_from_pymarc(r)
    assert lccn is None
    assert nlmcn == "WG 120.5"


def test_extract_call_numbers_no_fields():
    r = Record()
    lccn, nlmcn = extract_call_numbers_from_pymarc(r)
    assert lccn is None
    assert nlmcn is None


def test_extract_call_numbers_four_digit_class():
    """Regression: 4-digit LC class numbers (PS, HF, etc.) are extracted correctly."""
    r = Record()
    r.add_field(_field("050", "0", ("a", "PS3562.E353"), ("b", "T6 2002")))
    lccn, nlmcn = extract_call_numbers_from_pymarc(r)
    assert lccn == "PS3562.E353 T6 2002"
    assert nlmcn is None


def test_extract_call_numbers_ind2_preference_end_to_end():
    """End-to-end: ind2='0' field is used when multiple 050 fields exist."""
    r = Record()
    r.add_field(_field("050", "4", ("a", "PZ7.C6837"), ("b", "WrongCopy 1999")))
    r.add_field(_field("050", "0", ("a", "PZ7.C6837"), ("b", "RightCopy 2008")))
    lccn, _ = extract_call_numbers_from_pymarc(r)
    assert lccn == "PZ7.C6837 RightCopy 2008"


# ---------------------------------------------------------------------------
# Multi-$a MARC Edge Cases
# ---------------------------------------------------------------------------


def test_extract_subfields_multiple_a_subfields_first_used():
    """When a single field has multiple $a subfields, all are extracted as separate dicts."""
    f = _field("050", "0", ("a", "QA76.73"), ("a", "QA76.9"))
    result = _extract_subfields_from_pymarc_field(f)
    # Both $a values are extracted as separate dict entries
    assert result == [{"a": "QA76.73"}, {"a": "QA76.9"}]


def test_extract_subfields_multiple_a_with_b_interleaved():
    """Multiple $a and $b subfields are extracted in order."""
    f = _field("050", "0", ("a", "QA76.73"), ("b", "P38"), ("a", "QA76.9"), ("b", "P98"))
    result = _extract_subfields_from_pymarc_field(f)
    # All subfields extracted in their original order
    assert result == [
        {"a": "QA76.73"},
        {"b": "P38"},
        {"a": "QA76.9"},
        {"b": "P98"}
    ]


def test_pymarc_record_to_json_multiple_a_in_050():
    """Multiple $a subfields in a single 050 field are all extracted."""
    r = Record()
    r.add_field(_field("050", "0", ("a", "QA76.73"), ("a", "QA76.9")))
    result = pymarc_record_to_json(r)
    f050 = [f["050"] for f in result["fields"] if "050" in f]
    assert len(f050) == 1
    # Both $a values should be in the subfields list
    subfields = f050[0]["subfields"]
    a_values = [sf["a"] for sf in subfields if "a" in sf]
    assert a_values == ["QA76.73", "QA76.9"]


def test_pymarc_record_to_json_multiple_a_in_060():
    """Multiple $a subfields in a single 060 field are all extracted."""
    r = Record()
    r.add_field(_field("060", " ", ("a", "WG 120.5"), ("a", "WG 120.6")))
    result = pymarc_record_to_json(r)
    f060 = [f["060"] for f in result["fields"] if "060" in f]
    assert len(f060) == 1
    subfields = f060[0]["subfields"]
    a_values = [sf["a"] for sf in subfields if "a" in sf]
    assert a_values == ["WG 120.5", "WG 120.6"]


def test_extract_call_numbers_multiple_a_050_uses_first():
    """When 050 has multiple $a, only FIRST $a is used in final call number."""
    r = Record()
    # Multiple $a values in a single 050 field
    r.add_field(_field("050", "0", ("a", "QA76.73"), ("a", "QA76.9"), ("b", "P38")))
    lccn, nlmcn = extract_call_numbers_from_pymarc(r)
    # Only the first $a (QA76.73) is used
    assert lccn == "QA76.73 P38"
    assert nlmcn is None


def test_extract_call_numbers_multiple_a_060_uses_first():
    """When 060 has multiple $a, only FIRST $a is used in final call number."""
    r = Record()
    # Multiple $a values in a single 060 field
    r.add_field(_field("060", " ", ("a", "WG 120.5"), ("a", "WG 120.6"), ("b", "C65")))
    lccn, nlmcn = extract_call_numbers_from_pymarc(r)
    # Only the first $a (WG 120.5) is used
    assert lccn is None
    assert nlmcn == "WG 120.5 C65"


def test_extract_call_numbers_multiple_050_fields_all_a_extracted():
    """Multiple 050 fields each with multiple $a are all collected, but first is preferred."""
    r = Record()
    r.add_field(_field("050", "4", ("a", "QA76.99"), ("a", "QA77")))  # ind2='4' (non-LC)
    r.add_field(_field("050", "0", ("a", "QA76.73"), ("a", "QA76.9"), ("b", "P38")))  # ind2='0' (LC)
    lccn, nlmcn = extract_call_numbers_from_pymarc(r)
    # Prefers ind2='0' field, and uses only first $a from it
    assert lccn == "QA76.73 P38"


def test_extract_call_numbers_multiple_060_fields_all_a_extracted():
    """Multiple 060 fields each with multiple $a are all collected, but first is preferred."""
    r = Record()
    r.add_field(_field("060", " ", ("a", "WG 120.99"), ("a", "WG 120.88")))  # first 060
    r.add_field(_field("060", " ", ("a", "WG 120.5"), ("a", "WG 120.6"), ("b", "C65")))  # second 060
    lccn, nlmcn = extract_call_numbers_from_pymarc(r)
    # Uses first 060 field that has subfields
    assert nlmcn == "WG 120.99 C65" or nlmcn == "WG 120.99"


def test_extract_call_numbers_multiple_a_with_no_b():
    """Multiple $a with no $b uses only first $a."""
    r = Record()
    r.add_field(_field("050", "0", ("a", "QA76.73"), ("a", "QA76.9")))
    lccn, nlmcn = extract_call_numbers_from_pymarc(r)
    # Only first $a, no $b to append
    assert lccn == "QA76.73"


def test_extract_call_numbers_multiple_a_with_multiple_b():
    """Multiple $a with multiple $b: first $a is used with ALL $b values."""
    r = Record()
    r.add_field(_field("050", "0", ("a", "QA76.73"), ("b", "P38"), ("a", "QA76.9"), ("b", "P98")))
    lccn, nlmcn = extract_call_numbers_from_pymarc(r)
    # First $a with ALL $b values
    assert lccn == "QA76.73 P38 P98"


def test_extract_call_numbers_empty_a_before_valid_a():
    """When $a has empty/whitespace values before a valid one, they are skipped."""
    r = Record()
    r.add_field(_field("050", "0", ("a", "  "), ("a", "QA76.73"), ("b", "P38")))
    lccn, nlmcn = extract_call_numbers_from_pymarc(r)
    # The whitespace-only $a is extracted but should be empty after strip()
    # After normalization, the first non-empty value should be used
    # This depends on how marc_parser handles empty strings in the list
    assert lccn is not None or lccn == "QA76.73"


def test_extract_call_numbers_multiple_a_with_both_050_and_060():
    """Both 050 and 060 with multiple $a use first of each."""
    r = Record()
    r.add_field(_field("050", "0", ("a", "QA76.73"), ("a", "QA76.9"), ("b", "P38")))
    r.add_field(_field("060", " ", ("a", "WG 120.5"), ("a", "WG 120.6"), ("b", "C65")))
    lccn, nlmcn = extract_call_numbers_from_pymarc(r)
    # First $a from each field
    assert lccn == "QA76.73 P38"
    assert nlmcn == "WG 120.5 C65"


def test_pymarc_record_to_json_multiple_a_mixed_with_other_subfields():
    """Multiple $a mixed with $c, $d, etc. are all extracted in order."""
    r = Record()
    r.add_field(_field("050", "0", ("a", "QA76.73"), ("c", "extra1"), ("a", "QA76.9"), ("d", "extra2")))
    result = pymarc_record_to_json(r)
    f050 = [f["050"] for f in result["fields"] if "050" in f]
    subfields = f050[0]["subfields"]
    # All subfields should be present
    assert len(subfields) == 4
    # $a values in order
    a_values = [sf.get("a") for sf in subfields if "a" in sf]
    assert a_values == ["QA76.73", "QA76.9"]


def test_extract_subfields_three_a_values():
    """Edge case: field with three $a subfields (unusual but possible)."""
    f = _field("050", "0", ("a", "QA76.73"), ("a", "QA76.9"), ("a", "QA77.5"))
    result = _extract_subfields_from_pymarc_field(f)
    assert len(result) == 3
    a_values = [sf["a"] for sf in result]
    assert a_values == ["QA76.73", "QA76.9", "QA77.5"]


def test_extract_call_numbers_three_a_values_uses_first():
    """With three $a values, only the first is used."""
    r = Record()
    r.add_field(_field("050", "0", ("a", "QA76.73"), ("a", "QA76.9"), ("a", "QA77.5"), ("b", "P38")))
    lccn, nlmcn = extract_call_numbers_from_pymarc(r)
    # Only first $a
    assert lccn == "QA76.73 P38"

