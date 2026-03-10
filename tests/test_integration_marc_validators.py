#!/usr/bin/env python3
"""
Test: Integration test for marc_parser + validators + API workflow
"""

import xml.etree.ElementTree as ET
from src.utils.marc_parser import (
    extract_call_numbers_from_xml,
    extract_call_numbers_from_json,
    extract_marc_fields_from_xml,
    extract_marc_fields_from_json,
)
from src.utils.call_number_validators import validate_call_numbers, validate_lccn, validate_nlmcn


def test_marcxml_extraction():
    """Test MARC parser with MARCXML format"""
    print("Testing MARCXML extraction...")

    # Mock MARCXML response (as would come from LOC SRU)
    marcxml_str = '''
    <record xmlns="http://www.loc.gov/MARC21/slim">
        <datafield tag="050">
            <subfield code="a">QA76.73</subfield>
            <subfield code="b">P38</subfield>
        </datafield>
        <datafield tag="060">
            <subfield code="a">WG 120</subfield>
            <subfield code="b">5</subfield>
        </datafield>
    </record>
    '''

    root = ET.fromstring(marcxml_str)

    # Test field extraction
    fields = extract_marc_fields_from_xml(root)
    assert fields["050"]["a"] == ["QA76.73"]
    assert fields["050"]["b"] == ["P38"]
    assert fields["060"]["a"] == ["WG 120"]
    assert fields["060"]["b"] == ["5"]
    print("  ✓ Field extraction works")

    # Test call number extraction
    lccn, nlmcn = extract_call_numbers_from_xml(root)
    assert lccn == "QA76.73 P38"
    assert nlmcn == "WG 120 5"
    print("  ✓ Call number extraction works")


def test_marc_json_extraction():
    """Test MARC parser with MARC-JSON format"""
    print("Testing MARC-JSON extraction...")

    # Mock MARC-JSON record (as would come from Z39.50 or LOC JSON API)
    marc_json = {
        "fields": [
            {
                "050": {
                    "subfields": [
                        {"a": "QA76.73"},
                        {"b": "P38"}
                    ]
                }
            },
            {
                "060": {
                    "subfields": [
                        {"a": "WG 120"},
                        {"b": "5"}
                    ]
                }
            }
        ]
    }

    # Test field extraction
    fields = extract_marc_fields_from_json(marc_json)
    assert fields["050"]["a"] == ["QA76.73"]
    assert fields["050"]["b"] == ["P38"]
    assert fields["060"]["a"] == ["WG 120"]
    assert fields["060"]["b"] == ["5"]
    print("  ✓ JSON field extraction works")

    # Test call number extraction
    lccn, nlmcn = extract_call_numbers_from_json(marc_json)
    assert lccn == "QA76.73 P38"
    assert nlmcn == "WG 120 5"
    print("  ✓ JSON call number extraction works")


def test_validation():
    """Test validators"""
    print("Testing validators...")

    # Test valid call numbers
    lccn = validate_lccn("QA76.73.P38", source="test")
    assert lccn == "QA76.73.P38"
    print("  ✓ Valid LCCN passes")

    nlmcn = validate_nlmcn("WG 120.5", source="test")
    assert nlmcn == "WG 120.5"
    print("  ✓ Valid NLMCN passes")

    # Test invalid call numbers
    lccn = validate_lccn("INVALID_FORMAT", source="test")
    assert lccn is None
    print("  ✓ Invalid LCCN rejected")

    nlmcn = validate_nlmcn("INVALID_FORMAT", source="test")
    assert nlmcn is None
    print("  ✓ Invalid NLMCN rejected")

    # Test both at once
    lccn, nlmcn = validate_call_numbers(
        lccn="QA76.73.P38",
        nlmcn="WG 120.5",
        source="test"
    )
    assert lccn == "QA76.73.P38"
    assert nlmcn == "WG 120.5"
    print("  ✓ Multiple validation works")


def test_end_to_end():
    """Test complete workflow: extract MARCXML → validate → store"""
    print("Testing end-to-end workflow...")

    # Simulate LOC API response
    marcxml_str = '''
    <record xmlns="http://www.loc.gov/MARC21/slim">
        <datafield tag="050">
            <subfield code="a">QA76.73</subfield>
            <subfield code="b">P38</subfield>
        </datafield>
    </record>
    '''

    root = ET.fromstring(marcxml_str)

    # Step 1: Extract from MARC
    lccn, nlmcn = extract_call_numbers_from_xml(root)
    print(f"  Extracted: lccn={lccn}, nlmcn={nlmcn}")

    # Step 2: Validate
    lccn, nlmcn = validate_call_numbers(
        lccn=lccn,
        nlmcn=nlmcn,
        source="Library of Congress"
    )
    print(f"  Validated: lccn={lccn}, nlmcn={nlmcn}")

    # Step 3: Would be saved to database
    assert lccn == "QA76.73 P38"
    assert nlmcn is None
    print("  ✓ Complete workflow successful")


if __name__ == "__main__":
    print("\n=== Integration Tests ===\n")
    test_marcxml_extraction()
    print()
    test_marc_json_extraction()
    print()
    test_validation()
    print()
    test_end_to_end()
    print("\n=== All Tests Passed ✓ ===\n")

