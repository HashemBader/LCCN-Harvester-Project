"""
Module: marc_parser.py
MARC record parsing utilities for bibliographic data extraction.

Part of the LCCN Harvester Project.

This module provides utilities for extracting MARC fields from different formats:
  - MARC-JSON: For Z39.50, SRU JSON responses, and other JSON-based MARC sources
  - MARCXML: For LOC SRU, Harvard, and other XML-based MARC sources
  - Binary MARC-21: Reserved for future implementation

Examples
--------
Extract from MARC-JSON:

    >>> from src.utils.marc_parser import extract_marc_fields_from_json
    >>> marc_json = {"fields": [...]}
    >>> fields = extract_marc_fields_from_json(marc_json)
    >>> lccn = " ".join(fields["050"]["a"] + fields["050"]["b"])

Extract from MARCXML:

    >>> from src.utils.marc_parser import extract_marc_fields_from_xml
    >>> fields = extract_marc_fields_from_xml("path/to/record.xml")
    >>> lccn = " ".join(fields["050"]["a"] + fields["050"]["b"])
"""

import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple
import logging

from src.utils.call_number_normalizer import normalize_call_number

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
    result = {
        "050": {"a": [], "b": []},
        "060": {"a": [], "b": []},
    }

    fields = record.get("fields", [])

    for field in fields:
        for tag in ("050", "060"):
            if tag in field:
                subfields = field[tag].get("subfields", [])
                for sf in subfields:
                    if "a" in sf:
                        text = sf["a"]
                        if isinstance(text, str):
                            result[tag]["a"].append(text.strip())
                    elif "b" in sf:
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
        namespaces = {"marc": "http://www.loc.gov/MARC21/slim"}

    result = {
        "050": {"a": [], "b": []},
        "060": {"a": [], "b": []},
    }

    # Find all datafield elements (works with or without namespace prefix)
    for datafield in xml_element.findall(".//marc:datafield", namespaces):
        tag = datafield.get("tag")
        if tag in result:
            for subfield in datafield.findall("marc:subfield", namespaces):
                code = subfield.get("code")
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

    # Normalize using FIRST $a with all $b values
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

    # Normalize using FIRST $a with all $b values
    lccn = normalize_call_number(fields["050"]["a"], fields["050"]["b"]) or None
    nlmcn = normalize_call_number(fields["060"]["a"], fields["060"]["b"]) or None

    return lccn, nlmcn

