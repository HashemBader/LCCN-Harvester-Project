"""
Module: marc_decoder.py
Convert pymarc Record objects to standardized formats for call number extraction.

Part of the LCCN Harvester Project.

This module provides utilities for converting binary MARC records (from Z39.50 servers)
to formats compatible with the marc_parser module.

The workflow is:
  Z39.50 Client → pymarc.Record → marc_decoder → call number extraction
"""

from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


def pymarc_record_to_json(record: Any) -> Dict[str, List[Dict[str, Any]]]:
    """
    Convert a pymarc Record to MARC-JSON format compatible with marc_parser.

    Parameters
    ----------
    record : pymarc.Record
        A parsed MARC record from pymarc library.

    Returns
    -------
    dict[str, list[dict[str, Any]]]
        A dictionary with a "fields" list containing MARC field objects in JSON format.
        Structure:
        {
            "fields": [
                {"050": {"subfields": [{"a": "QA76.73"}, {"b": "P38"}]}},
                {"060": {"subfields": [{"a": "WG 120"}]}},
                ...
            ]
        }

    Notes
    -----
    - Only extracts MARC fields 050 (LCCN) and 060 (NLMCN)
    - Handles repeating fields and subfields
    - Preserves subfield order and values
    """
    if not hasattr(record, 'get_fields'):
        logger.warning("Invalid pymarc Record: missing get_fields method")
        return {"fields": []}

    fields = []

    # Extract MARC fields 050 (LCCN) and 060 (NLMCN)
    for field_tag in ("050", "060"):
        try:
            field_objs = record.get_fields(field_tag)
            if field_objs:
                for field_obj in field_objs:
                    subfields_list = _extract_subfields_from_pymarc_field(field_obj)
                    if subfields_list:
                        fields.append({
                            field_tag: {
                                "subfields": subfields_list,
                                "ind1": getattr(field_obj, "indicator1", None),
                                "ind2": getattr(field_obj, "indicator2", None),
                            }
                        })
        except Exception as e:
            logger.debug(f"Error extracting field {field_tag}: {e}")

    return {"fields": fields}


def _extract_subfields_from_pymarc_field(field: Any) -> List[Dict[str, str]]:
    """
    Extract subfields from a pymarc Field object.

    Parameters
    ----------
    field : pymarc.field.Field
        A MARC field object.

    Returns
    -------
    list[dict[str, str]]
        List of subfield dictionaries like [{"a": "value"}, {"b": "value"}]
    """
    subfields_list = []

    try:
        # pymarc Field objects have a subfields property that contains alternating
        # subfield codes and values: [code1, value1, code2, value2, ...]
        if hasattr(field, 'subfields'):
            subfields_pairs = field.subfields
            # Process pairs of (code, value)
            for i in range(0, len(subfields_pairs), 2):
                if i + 1 < len(subfields_pairs):
                    code = subfields_pairs[i]
                    value = subfields_pairs[i + 1]
                    if code and value:
                        subfields_list.append({code: value.strip() if isinstance(value, str) else str(value)})
    except Exception as e:
        logger.debug(f"Error extracting subfields: {e}")

    return subfields_list


def extract_call_numbers_from_pymarc(record: Any) -> tuple[Optional[str], Optional[str]]:
    """
    Extract LCCN and NLMCN call numbers from a pymarc Record.

    This is a convenience function for Z39.50 workflows that:
    1. Converts pymarc Record to MARC-JSON format
    2. Extracts and normalizes call numbers
    3. Returns (lccn, nlmcn) pair

    Parameters
    ----------
    record : pymarc.Record
        A parsed MARC record from pymarc library.

    Returns
    -------
    tuple[str | None, str | None]
        (lccn, nlmcn) pair with normalized call numbers, or (None, None) if not found.
    """
    # Import here to avoid circular dependencies and allow lazy loading
    from src.utils.marc_parser import extract_call_numbers_from_json

    marc_json = pymarc_record_to_json(record)
    return extract_call_numbers_from_json(marc_json)
