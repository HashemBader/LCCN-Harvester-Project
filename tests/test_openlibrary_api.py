"""
Tests for src/api/openlibrary_api.py

Covers:
- lc_classifications[] primary path → success
- classifications.lc_classifications alternate JSON shape → success
- None payload → not_found
- Empty payload (no lc_classifications) → not_found
- Invalid call number value → rejected by validator → not_found
- lccn / identifiers.lccn fields are LC control numbers and must NOT be used
  (those fallback paths were removed; this test documents and guards that behaviour)
"""

import pytest

from src.api.openlibrary_api import OpenLibraryApiClient


@pytest.fixture
def client():
    return OpenLibraryApiClient()


# ---------------------------------------------------------------------------
# Successful extraction
# ---------------------------------------------------------------------------


def test_lc_classifications_primary_path(client):
    """The standard lc_classifications list is the correct source for the LCCN call number."""
    payload = {"lc_classifications": ["QA76.73.P38"]}
    result = client.extract_call_numbers("0131103628", payload)
    assert result.status == "success"
    assert result.lccn == "QA76.73.P38"
    assert result.nlmcn is None


def test_lc_classifications_alternate_shape(client):
    """Some OL payloads nest lc_classifications inside a 'classifications' dict."""
    payload = {"classifications": {"lc_classifications": ["QA76.73.P38"]}}
    result = client.extract_call_numbers("0131103628", payload)
    assert result.status == "success"
    assert result.lccn == "QA76.73.P38"


def test_lc_classifications_four_digit_class(client):
    """4-digit LC class numbers (PS, HF, …) are valid and pass the validator."""
    payload = {"lc_classifications": ["PS3562.E353 T6 2002"]}
    result = client.extract_call_numbers("0060935464", payload)
    assert result.status == "success"
    assert result.lccn == "PS3562.E353 T6 2002"


# ---------------------------------------------------------------------------
# not_found cases
# ---------------------------------------------------------------------------


def test_none_payload_returns_not_found(client):
    result = client.extract_call_numbers("0131103628", None)
    assert result.status == "not_found"
    assert result.lccn is None
    assert result.nlmcn is None


def test_empty_payload_returns_not_found(client):
    result = client.extract_call_numbers("0131103628", {})
    assert result.status == "not_found"
    assert result.lccn is None


def test_invalid_call_number_rejected_by_validator(client):
    """A value in lc_classifications that is not a valid LC call number is rejected."""
    payload = {"lc_classifications": ["not_a_real_call_number"]}
    result = client.extract_call_numbers("0131103628", payload)
    assert result.status == "not_found"
    assert result.lccn is None


# ---------------------------------------------------------------------------
# lccn / identifiers.lccn are LC CONTROL numbers — must not be returned
# ---------------------------------------------------------------------------


def test_lccn_identifier_field_is_not_used(client):
    """
    OpenLibrary's top-level 'lccn' field is an LC control number (MARC 010,
    e.g. '2001016794'), not an LC classification call number (MARC 050).
    The client must not return it as a call number.
    """
    payload = {"lccn": ["2001016794"]}
    result = client.extract_call_numbers("0131103628", payload)
    assert result.status == "not_found"
    assert result.lccn is None


def test_identifiers_lccn_field_is_not_used(client):
    """
    identifiers.lccn is also an LC control number — must not be used as a
    call number even when no lc_classifications value is present.
    """
    payload = {"identifiers": {"lccn": ["2001016794"]}}
    result = client.extract_call_numbers("0131103628", payload)
    assert result.status == "not_found"
    assert result.lccn is None


def test_lccn_identifier_with_valid_lc_classifications(client):
    """
    When both lc_classifications and lccn identifier are present, only
    lc_classifications should contribute to the result.
    """
    payload = {
        "lc_classifications": ["QA76.73.P38"],
        "lccn": ["2001016794"],
    }
    result = client.extract_call_numbers("0131103628", payload)
    assert result.status == "success"
    assert result.lccn == "QA76.73.P38"
