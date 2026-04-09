"""
call_number_validators.py

Centralised entry point for validating LC and NLM call numbers before they
are stored in the database or returned as harvest results.

This module provides two styles of API:
- ``validate_call_numbers`` — validates an (lccn, nlmcn) pair together and
  returns a cleaned tuple; convenient for callers that hold both at once.
- ``validate_lccn`` / ``validate_nlmcn`` — validate a single call number;
  used by individual API clients after extraction.

All validation logic is delegated to the specialised validator modules:
- :mod:`src.utils.lccn_validator` — LC Classification (MARC 050) rules.
- :mod:`src.utils.nlmcn_validator` — NLM Classification (MARC 060) rules.

The ``source`` parameter accepted by every function is intentionally unused;
it is kept for API compatibility with older call sites that passed a source
label for logging.

Part of the LCCN Harvester Project.
"""

from typing import Optional, Tuple

from src.utils.lccn_validator import is_valid_lccn
from src.utils.nlmcn_validator import is_valid_nlmcn


def validate_call_numbers(
    lccn: Optional[str] = None,
    nlmcn: Optional[str] = None,
    source: Optional[str] = None,
    strict: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Validate and clean LCCN and NLMCN call numbers.

    Parameters
    ----------
    lccn : str | None
        Library of Congress call number candidate.
    nlmcn : str | None
        National Library of Medicine call number candidate.
    source : str | None
        Source API name (unused, kept for compatibility).
    strict : bool
        If True, reject invalid formats. If False, return as-is for logging purposes.

    Returns
    -------
    tuple[str | None, str | None]
        Validated (lccn, nlmcn) pair. Invalid ones become None.
    """
    validated_lccn = None
    validated_nlmcn = None

    if lccn:
        lccn = lccn.strip()
        if is_valid_lccn(lccn):
            validated_lccn = lccn

    if nlmcn:
        nlmcn = nlmcn.strip()
        if is_valid_nlmcn(nlmcn):
            validated_nlmcn = nlmcn

    return validated_lccn, validated_nlmcn


def validate_lccn(call_number: Optional[str], source: Optional[str] = None) -> Optional[str]:
    """
    Validate a single LCCN.

    Parameters
    ----------
    call_number : str | None
        Call number to validate.
    source : str | None
        Source API name (unused, kept for compatibility).

    Returns
    -------
    str | None
        The call number if valid, None otherwise.
    """
    if not call_number:
        return None

    call_number = call_number.strip()
    if is_valid_lccn(call_number):
        return call_number

    return None


def validate_nlmcn(call_number: Optional[str], source: Optional[str] = None) -> Optional[str]:
    """
    Validate a single NLMCN.

    Parameters
    ----------
    call_number : str | None
        Call number to validate.
    source : str | None
        Source API name (unused, kept for compatibility).

    Returns
    -------
    str | None
        The call number if valid, None otherwise.
    """
    if not call_number:
        return None

    call_number = call_number.strip()
    if is_valid_nlmcn(call_number):
        return call_number

    return None
