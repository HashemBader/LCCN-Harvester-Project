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

    # Extract MARC fields 050 (LCCN) and 060 (NLMCN).
    # When multiple occurrences exist, prefer the LC-assigned one (ind2='0')
    # over institution copies (ind2='4' or blank) to avoid mixing $b values
    # from different field occurrences during normalization.
    for field_tag in ("050", "060"):
        try:
            field_objs = record.get_fields(field_tag)
            if not field_objs:
                continue

            # Prefer ind2='0' (assigned by LC) but only among occurrences
            # that actually yield usable subfields. Fall back to other
            # occurrences in order until one with data is found.
            preferred = None
            subfields_list = None

            lc_assigned = [fo for fo in field_objs if getattr(fo, "indicator2", None) == "0"]
            others = [fo for fo in field_objs if getattr(fo, "indicator2", None) != "0"]
            preferred_candidates = lc_assigned + others

            for fo in preferred_candidates:
                subfields = _extract_subfields_from_pymarc_field(fo)
                if subfields:
                    preferred = fo
                    subfields_list = subfields
                    break

            if preferred is not None and subfields_list:
                fields.append({
                    field_tag: {
                        "subfields": subfields_list,
                        "ind1": getattr(preferred, "indicator1", None),
                        "ind2": getattr(preferred, "indicator2", None),
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

    Notes
    -----
    pymarc >= 5.0 stores subfields as a list of Subfield(code, value) namedtuples.
    The old flat alternating-list format [code, val, code, val, ...] was removed in
    pymarc 5.1 — Field.__init__ now raises ValueError when strings are passed.
    All real pymarc Field objects (including those produced by Record(data=...)
    via the Z39.50 client) therefore always use the namedtuple format.
    """
    subfields_list = []

    try:
        if hasattr(field, 'subfields'):
            for sf in field.subfields:
                code = sf.code
                value = sf.value
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
