"""
marc_parser.py

MARC record parsing utilities for bibliographic data extraction.

Part of the LCCN Harvester Project.

This module provides format-agnostic functions for extracting target MARC
fields from the three representation formats encountered in the harvester:

MARC-JSON
    The standard JSON serialisation of MARC 21 records (used by the LoC SRU
    JSON endpoint, Z39.50 servers, and modern library systems).  Structure::

        {"fields": [{"050": {"subfields": [{"a": "QA76.73"}, {"b": "P38"}]}}]}

MARCXML
    The W3C XML representation of MARC 21 records (default for LoC SRU and
    OAI-PMH).  The ``marc:`` namespace prefix maps to
    ``http://www.loc.gov/MARC21/slim``.

Binary MARC-21
    Not yet implemented; reserved for future direct Z39.50 byte-stream
    support.

Target MARC fields
------------------
050 ($a, $b)
    LC Classification (Library of Congress call number).
060 ($a, $b)
    NLM Classification (National Library of Medicine call number).
020 ($a)
    ISBN (used to collect all ISBNs linked to a record for deduplication).

Extracted subfield strings are passed to
:mod:`src.utils.call_number_normalizer` for assembly into a single call
number string.

Examples
--------
Extract from MARC-JSON::

    >>> from src.utils.marc_parser import extract_marc_fields_from_json
    >>> marc_json = {"fields": [...]}
    >>> fields = extract_marc_fields_from_json(marc_json)
    >>> lccn = " ".join(fields["050"]["a"] + fields["050"]["b"])

Extract from MARCXML::

    >>> from src.utils.marc_parser import extract_marc_fields_from_xml
    >>> fields = extract_marc_fields_from_xml(root_element)
    >>> lccn = " ".join(fields["050"]["a"] + fields["050"]["b"])
"""

import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple
import logging

from src.utils.call_number_normalizer import normalize_call_number, normalize_isbn_subfield

logger = logging.getLogger(__name__)


def extract_marc_fields_from_json(record: Dict) -> Dict[str, Dict[str, List[str]]]:
    """
    Extract MARC 050 (LC call number) and 060 (NLM call number) subfields from a MARC-JSON record.

    MARC-JSON is the standard JSON representation of MARC records used by:
      - LOC SRU API (when requesting JSON format)
      - Some Z39.50 servers
      - Modern library systems

    Parameters
    ----------
    record : dict
        A MARC-JSON record object with a "fields" list.
        Expected structure:
        {
            "fields": [
                {"050": {"subfields": [{"a": "QA76.73"}, {"b": "P38"}]}},
                ...
            ]
        }

    Returns
    -------
    dict[str, dict[str, list[str]]]
        Extracted subfield values organized by field tag and subfield code:
        {
            "050": {"a": ["QA76.73", "QA76.9"], "b": ["P38", "P98"]},
            "060": {"a": [], "b": []}
        }

    Notes
    -----
    - Handles variable-length field arrays (repeating fields)
    - Returns empty lists if fields not found
    - Strips whitespace from extracted values
    """
    # Pre-populate the result dict so callers can always access ["050"]["a"]
    # etc. without KeyError, even when those fields are absent in the record.
    result = {
        "020": {"a": []},
        "050": {"a": [], "b": []},
        "060": {"a": [], "b": []},
    }

    fields = record.get("fields", [])

    for field in fields:
        for tag in ("020", "050", "060"):
            if tag in field:
                subfields = field[tag].get("subfields", [])
                for sf in subfields:
                    if "a" in sf:
                        text = sf["a"]
                        if isinstance(text, str):
                            result[tag]["a"].append(text.strip())
                    elif tag != "020" and "b" in sf:
                        # MARC 020 does not use $b for ISBNs; skip $b for that tag.
                        text = sf["b"]
                        if isinstance(text, str):
                            result[tag]["b"].append(text.strip())

    return result


def extract_marc_fields_from_xml(
    xml_element: ET.Element,
    namespaces: Optional[Dict[str, str]] = None,
) -> Dict[str, Dict[str, List[str]]]:
    """
    Extract MARC 050 and 060 subfields from a MARCXML record element.

    MARCXML is the XML representation of MARC records used by:
      - LOC SRU API (default format)
      - OAI-PMH harvesting
      - Library of Congress systems
      - Z39.50 via XML encoding

    Parameters
    ----------
    xml_element : ET.Element
        Root element of a MARCXML record or a datafield container.
    namespaces : dict[str, str] | None
        XML namespace mapping. Default includes MARCXML namespace.
        If None, uses standard LOC MARC21 namespace.

    Returns
    -------
    dict[str, dict[str, list[str]]]
        Extracted subfield values organized by field tag and subfield code:
        {
            "050": {"a": ["QA76.73.P38"], "b": []},
            "060": {"a": [], "b": []}
        }

    Examples
    --------
    >>> import xml.etree.ElementTree as ET
    >>> from src.utils.marc_parser import extract_marc_fields_from_xml
    >>> root = ET.parse("record.xml").getroot()
    >>> fields = extract_marc_fields_from_xml(root)
    >>> lccn = " ".join(fields["050"]["a"] + fields["050"]["b"])

    Notes
    -----
    - Handles MARCXML namespace automatically
    - Works with both complete records and extracted datafield elements
    - Returns empty lists if fields not found
    - Strips whitespace from extracted values
    """
    if namespaces is None:
        # Default MARCXML namespace as defined by the Library of Congress.
        namespaces = {"marc": "http://www.loc.gov/MARC21/slim"}

    # Pre-populate so callers always get a consistent structure.
    result = {
        "020": {"a": []},
        "050": {"a": [], "b": []},
        "060": {"a": [], "b": []},
    }

    # ".//marc:datafield" is a descendant search that works whether the caller
    # passes a full <record> element or just a fragment of the XML tree.
    for datafield in xml_element.findall(".//marc:datafield", namespaces):
        tag = datafield.get("tag")
        if tag in result:
            for subfield in datafield.findall("marc:subfield", namespaces):
                code = subfield.get("code")
                # Only collect $a and $b; other subfield codes are not needed.
                if code in ("a", "b") and subfield.text:
                    result[tag][code].append(subfield.text.strip())

    return result


def extract_call_numbers_from_json(record: Dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract LC (050) and NLM (060) call numbers from a MARC-JSON record.

    Extracts MARC fields and normalizes them according to MARC 050/060 standards:
    - Uses FIRST $a subfield if multiple exist
    - Concatenates with $b subfields, space-separated
    - Trims whitespace

    Parameters
    ----------
    record : dict
        A MARC-JSON record object.

    Returns
    -------
    tuple[str | None, str | None]
        (lccn, nlmcn) pair, or (None, None) if not found.
        Each call number is normalized and properly formatted.
    """
    fields = extract_marc_fields_from_json(record)

    # normalize_call_number returns "" when no subfields are present;
    # convert that to None so callers can do a simple truthiness check.
    lccn = normalize_call_number(fields["050"]["a"], fields["050"]["b"]) or None
    nlmcn = normalize_call_number(fields["060"]["a"], fields["060"]["b"]) or None

    return lccn, nlmcn


def extract_call_numbers_from_xml(
    xml_element: ET.Element,
    namespaces: Optional[Dict[str, str]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract LC (050) and NLM (060) call numbers from a MARCXML record.

    Extracts MARC fields and normalizes them according to MARC 050/060 standards:
    - Uses FIRST $a subfield if multiple exist
    - Concatenates with $b subfields, space-separated
    - Trims whitespace

    Parameters
    ----------
    xml_element : ET.Element
        Root element of a MARCXML record.
    namespaces : dict[str, str] | None
        XML namespace mapping. Uses standard MARCXML namespace if None.

    Returns
    -------
    tuple[str | None, str | None]
        (lccn, nlmcn) pair, or (None, None) if not found.
        Each call number is normalized and properly formatted.
    """
    fields = extract_marc_fields_from_xml(xml_element, namespaces)

    # normalize_call_number returns "" when no subfields are present;
    # convert that to None so callers can use a simple truthiness check.
    lccn = normalize_call_number(fields["050"]["a"], fields["050"]["b"]) or None
    nlmcn = normalize_call_number(fields["060"]["a"], fields["060"]["b"]) or None

    return lccn, nlmcn


def extract_isbns_from_json(record: Dict) -> List[str]:
    """
    Extract ISBNs from MARC 020 $a subfields in a MARC-JSON record.

    Extracts all $a subfields from 020 fields and normalizes them:
    - Removes hyphens, spaces, and other non-alphanumeric characters
    - Handles 10/13-digit ISBNs
    - Preserves leading zeros

    Parameters
    ----------
    record : dict
        A MARC-JSON record object.

    Returns
    -------
    list[str]
        List of normalized ISBN strings, or empty list if none found.
    """
    fields = extract_marc_fields_from_json(record)
    isbns = []
    for isbn_raw in fields["020"]["a"]:
        normalized = normalize_isbn_subfield(isbn_raw)
        # Only keep values whose length is exactly 10 or 13 digits — anything
        # else is not a valid ISBN (e.g. qualifying text that slipped through).
        if len(normalized) in (10, 13):
            isbns.append(normalized)
    return isbns


def extract_isbns_from_xml(
    xml_element: ET.Element,
    namespaces: Optional[Dict[str, str]] = None,
) -> List[str]:
    """
    Extract ISBNs from MARC 020 $a subfields in a MARCXML record.

    Extracts all $a subfields from 020 fields and normalizes them:
    - Removes hyphens, spaces, and other non-alphanumeric characters
    - Handles 10/13-digit ISBNs
    - Preserves leading zeros

    Parameters
    ----------
    xml_element : ET.Element
        Root element of a MARCXML record.
    namespaces : dict[str, str] | None
        XML namespace mapping. Uses standard MARCXML namespace if None.

    Returns
    -------
    list[str]
        List of normalized ISBN strings, or empty list if none found.
    """
    fields = extract_marc_fields_from_xml(xml_element, namespaces)
    isbns = []
    for isbn_raw in fields["020"]["a"]:
        normalized = normalize_isbn_subfield(isbn_raw)
        # Only keep values whose length is exactly 10 or 13 digits.
        if len(normalized) in (10, 13):
            isbns.append(normalized)
    return isbns

