"""
Module: marc_decoder.py
Convert pymarc Record objects to standardized formats for call number extraction.

Part of the LCCN Harvester Project.

This module bridges the Z39.50 subsystem and the rest of the harvester pipeline.
PyZ3950 returns MARC records as raw binary data that is parsed into ``pymarc.Record``
objects by ``Z3950Client``.  The functions here convert those objects into the
MARC-JSON dictionary format that ``src.utils.marc_parser`` understands, so the same
call-number extraction and normalisation logic can be used regardless of whether a
record was fetched via Z39.50 or from a REST API (e.g. OpenLibrary, Harvard).

The workflow is::

  Z39.50 Client → pymarc.Record → marc_decoder → marc_parser → call number extraction

Only the fields relevant to this project are extracted:
  - 020  ISBN
  - 050  Library of Congress Classification (LCCN call number)
  - 060  National Library of Medicine Classification (NLMCN call number)
"""

from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


def pymarc_record_to_json(record: Any) -> Dict[str, List[Dict[str, Any]]]:
    """
    Convert a pymarc Record to MARC-JSON format compatible with marc_parser.

    Iterates over the MARC fields that are relevant to call-number harvesting
    (020, 050, 060), selects the most authoritative occurrence of each field,
    and serialises the result as a dictionary that matches the MARC-JSON
    structure produced by the REST API paths (OpenLibrary, Harvard).

    Parameters
    ----------
    record : pymarc.Record
        A parsed MARC record from pymarc library.

    Returns
    -------
    dict[str, list[dict[str, Any]]]
        A dictionary with a "fields" list containing MARC field objects in JSON format.
        Structure::

            {
                "fields": [
                    {"050": {"subfields": [{"a": "QA76.73"}, {"b": "P38"}],
                             "ind1": "0", "ind2": "0"}},
                    {"060": {"subfields": [{"a": "WG 120"}],
                             "ind1": " ", "ind2": "4"}},
                    ...
                ]
            }

    Notes
    -----
    - Only fields 020 (ISBN), 050 (LCC call number), and 060 (NLM call number)
      are extracted; all other MARC fields are ignored.
    - When a field appears more than once in the record, the occurrence with
      ``indicator2 == '0'`` (assigned by the Library of Congress) is preferred
      over institution-assigned copies (``ind2 == '4'`` or blank) to avoid
      mixing $a / $b subfield values from different occurrences during
      downstream normalisation.
    - Returns ``{"fields": []}`` for invalid or empty input to allow callers
      to proceed without special-casing ``None``.
    """
    if not hasattr(record, 'get_fields'):
        logger.warning("Invalid pymarc Record: missing get_fields method")
        return {"fields": []}

    fields = []

    # Extract MARC fields 020 (ISBN), 050 (LCCN) and 060 (NLMCN).
    # When multiple occurrences exist, prefer the LC-assigned one (ind2='0')
    # over institution copies (ind2='4' or blank) to avoid mixing $b values
    # from different field occurrences during normalization.
    for field_tag in ("020", "050", "060"):
        try:
            field_objs = record.get_fields(field_tag)
            if not field_objs:
                continue

            # Prefer ind2='0' (assigned by LC) but only among occurrences
            # that actually yield usable subfields. Fall back to other
            # occurrences in order until one with data is found.
            preferred = None
            subfields_list = None

            # Partition field occurrences: LC-assigned first, then all others.
            # lc_assigned covers ind2='0'; others covers ind2='4', ' ', etc.
            lc_assigned = [fo for fo in field_objs if getattr(fo, "indicator2", None) == "0"]
            others = [fo for fo in field_objs if getattr(fo, "indicator2", None) != "0"]
            preferred_candidates = lc_assigned + others

            # Walk candidates in priority order; stop at the first that has
            # at least one non-empty subfield to avoid recording an empty entry.
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
    Extract subfields from a pymarc Field object into a list of single-key dicts.

    Each dict in the returned list has exactly one key (the subfield code) mapped
    to the stripped string value, matching the MARC-JSON subfield convention used
    throughout the harvester (e.g. ``[{"a": "QA76.73"}, {"b": "P38"}]``).

    Parameters
    ----------
    field : pymarc.field.Field
        A MARC field object that exposes a ``subfields`` attribute.

    Returns
    -------
    list[dict[str, str]]
        Ordered list of subfield dicts.  Empty list if the field has no usable
        subfields or if an unexpected attribute layout is encountered.

    Notes
    -----
    pymarc >= 5.0 stores subfields as a list of ``Subfield(code, value)``
    namedtuples.  The old flat alternating-list format
    ``[code, val, code, val, ...]`` was removed in pymarc 5.1 — ``Field.__init__``
    now raises ``ValueError`` when strings are passed.  All real pymarc Field
    objects (including those produced by ``Record(data=...)`` via the Z39.50
    client) therefore always use the namedtuple format, so only that format is
    handled here.
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

    Convenience function for Z39.50 workflows that chains the conversion and
    extraction steps into a single call:

    1. Converts the pymarc Record to MARC-JSON via :func:`pymarc_record_to_json`.
    2. Passes the result to ``marc_parser.extract_call_numbers_from_json`` for
       normalisation.
    3. Returns the ``(lccn, nlmcn)`` tuple.

    Parameters
    ----------
    record : pymarc.Record
        A parsed MARC record from pymarc library.

    Returns
    -------
    tuple[str | None, str | None]
        ``(lccn, nlmcn)`` pair with normalised call numbers, or
        ``(None, None)`` if neither is present in the record.
    """
    # Import here to avoid circular dependencies and allow lazy loading.
    # marc_parser lives in src.utils and must not be imported at module level
    # to prevent import cycles with other parts of the pipeline.
    from src.utils.marc_parser import extract_call_numbers_from_json

    marc_json = pymarc_record_to_json(record)
    return extract_call_numbers_from_json(marc_json)


def extract_isbns_from_pymarc(record: Any) -> list[str]:
    """
    Extract normalised ISBNs from a pymarc Record.

    Convenience function for Z39.50 workflows that need all ISBNs embedded in a
    MARC record (MARC field 020 $a), not just the ISBN that was originally
    queried.  Useful for cross-referencing ISBN-10 / ISBN-13 variants stored in
    the same bibliographic record.

    Duplicate ISBNs are removed while preserving the original order using a
    ``dict.fromkeys`` idiom (which is insertion-order-stable in Python 3.7+).

    Parameters
    ----------
    record : pymarc.Record
        A parsed MARC record from pymarc library.

    Returns
    -------
    list[str]
        Deduplicated list of normalised ISBN strings found in the record.
        Empty list if none are present.
    """
    from src.utils.marc_parser import extract_isbns_from_json

    marc_json = pymarc_record_to_json(record)
    # dict.fromkeys preserves insertion order while eliminating duplicates —
    # the dict values are unused; only the keys (ISBNs) matter here.
    return list(dict.fromkeys(extract_isbns_from_json(marc_json)))
