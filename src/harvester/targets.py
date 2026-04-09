"""
Concrete HarvestTarget implementations for the LCCN Harvester.

Each class in this module wraps a specific lookup source (Z39.50 server or
HTTP API) and exposes a uniform ``lookup(isbn) -> TargetResult`` interface so
the orchestrator can treat all sources identically.

Classes:
    Z3950Target              -- Generic Z39.50 lookup using the Z3950Client.
    LibraryOfCongressTarget  -- Library of Congress JSON API.
    HarvardLibraryCloudTarget -- Harvard LibraryCloud metadata API.
    OpenLibraryTarget        -- Internet Archive OpenLibrary API.
    APITarget                -- Placeholder for unconfigured generic API targets.

The module-level ``create_target_from_config`` factory constructs the
appropriate target instance from a GUI-supplied configuration dict, so the
orchestrator does not need to know which concrete class to instantiate.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.harvester.orchestrator import TargetResult
from src.utils import messages
from src.utils.call_number_validators import validate_lccn, validate_nlmcn

logger = logging.getLogger(__name__)

# Z3950 availability - will be checked lazily when needed
# Don't import at module level to avoid crash if PyZ3950 has compatibility issues
Z3950_AVAILABLE = None
Z3950Client = None


class Z3950Target:
    """Z39.50 lookup target.

    Connects to a Z39.50 server, searches by ISBN, and extracts LC/NLM call
    numbers from the returned MARC records.  The Z3950Client is imported
    lazily to prevent app startup failures on systems where PyZ3950 is not
    installed.
    """

    def __init__(self, name: str, host: str, port: int, database: str):
        self.name = name
        self.host = host
        self.port = port
        self.database = database

    def lookup(self, isbn: str) -> TargetResult:
        """Look up *isbn* against this Z39.50 target and return call number data.

        Returns:
            A ``TargetResult`` with ``success=True`` and ``lccn``/``nlmcn``
            fields populated if MARC 050/060 fields were found; otherwise
            ``success=False`` with an error message.
        """
        # Lazy import Z3950Client to avoid crash if PyZ3950 has issues
        global Z3950_AVAILABLE, Z3950Client
        if Z3950_AVAILABLE is None:
            try:
                from src.z3950.client import Z3950Client as Z3950ClientClass
                Z3950Client = Z3950ClientClass
                Z3950_AVAILABLE = True
            except Exception as e:
                Z3950_AVAILABLE = False
                logger.warning(messages.NetworkMessages.z3950_not_available_detail.format(error=str(e)))

        if not Z3950_AVAILABLE:
            return TargetResult(
                success=False,
                source=self.name,
                error=messages.NetworkMessages.z3950_unavailable
            )

        try:
            with Z3950Client(self.host, self.port, self.database) as client:
                records = client.search_by_isbn(isbn)

                if not records:
                    return TargetResult(
                        success=False,
                        source=self.name,
                        error=messages.NetworkMessages.no_match.format(target=self.name)
                    )

                # Extract LCCN (MARC 050 $a+$b), NLMCN (MARC 060 $a+$b), and all ISBNs.
                # Use the shared marc_decoder utility which normalises $a+$b and
                # iterates all returned records until a call number is found.
                from src.z3950.marc_decoder import (
                    extract_call_numbers_from_pymarc,
                    extract_isbns_from_pymarc,
                )

                lccn = None
                nlmcn = None
                all_isbns: list[str] = []
                for rec in records:
                    raw_lccn, raw_nlmcn = extract_call_numbers_from_pymarc(rec)
                    all_isbns.extend(extract_isbns_from_pymarc(rec))
                    lccn = validate_lccn(raw_lccn)
                    nlmcn = validate_nlmcn(raw_nlmcn)
                    if lccn or nlmcn:
                        break

                unique_isbns = tuple(dict.fromkeys(all_isbns))
                if lccn or nlmcn:
                    return TargetResult(
                        success=True,
                        lccn=lccn,
                        nlmcn=nlmcn,
                        source=self.name,
                        isbns=unique_isbns,
                    )
                else:
                    return TargetResult(
                        success=False,
                        source=self.name,
                        error=messages.NetworkMessages.record_no_lccn,
                        isbns=unique_isbns,
                    )

        except Exception as e:
            logger.error(messages.NetworkMessages.z3950_lookup_failed.format(
                isbn=isbn, target=self.name, error=str(e)
            ))
            return TargetResult(
                success=False,
                source=self.name,
                error=str(e)
            )


class LibraryOfCongressTarget:
    """Library of Congress catalog JSON API target.

    Uses the ``LocApiClient`` to query ``loc.gov`` and returns LC/NLM call
    numbers from the response.
    """

    name = "Library of Congress"

    def __init__(self, timeout: int = 8, retries: int = 0):
        from api.loc_api import LocApiClient
        self.client = LocApiClient(timeout_seconds=timeout, max_retries=retries)

    def lookup(self, isbn: str) -> TargetResult:
        """Lookup ISBN using Library of Congress API."""
        try:
            result = self.client.search(isbn)

            if result.status == "success" and (result.lccn or result.nlmcn):
                return TargetResult(
                    success=True,
                    lccn=result.lccn,
                    nlmcn=result.nlmcn,
                    source=self.name,
                    isbns=tuple(result.isbns),
                )
            elif result.status == "not_found":
                return TargetResult(
                    success=False,
                    source=self.name,
                    error=f"No records found in {self.name}.",
                    isbns=tuple(result.isbns),
                )
            else:
                return TargetResult(
                    success=False,
                    source=self.name,
                    error=result.error_message or f"API status: {result.status}",
                    isbns=tuple(result.isbns),
                )
        except Exception as e:
            logger.error(f"Library of Congress lookup failed for {isbn}: {e}")
            return TargetResult(
                success=False,
                source=self.name,
                error=str(e)
            )


class HarvardLibraryCloudTarget:
    """Harvard LibraryCloud metadata API target.

    Uses the ``HarvardApiClient`` to query Harvard's bibliographic metadata
    service and returns LC/NLM call numbers.
    """

    name = "Harvard LibraryCloud"

    def __init__(self, timeout: int = 8, retries: int = 0):
        from api.harvard_api import HarvardApiClient
        self.client = HarvardApiClient(timeout_seconds=timeout, max_retries=retries)

    def lookup(self, isbn: str) -> TargetResult:
        """Lookup ISBN using Harvard LibraryCloud API."""
        try:
            result = self.client.search(isbn)

            if result.status == "success" and (result.lccn or result.nlmcn):
                return TargetResult(
                    success=True,
                    lccn=result.lccn,
                    nlmcn=result.nlmcn,
                    source=self.name,
                    isbns=tuple(result.isbns),
                )
            elif result.status == "not_found":
                return TargetResult(
                    success=False,
                    source=self.name,
                    error=f"No records found in {self.name}.",
                    isbns=tuple(result.isbns),
                )
            else:
                return TargetResult(
                    success=False,
                    source=self.name,
                    error=result.error_message or f"API status: {result.status}",
                    isbns=tuple(result.isbns),
                )
        except Exception as e:
            logger.error(f"Harvard LibraryCloud lookup failed for {isbn}: {e}")
            return TargetResult(
                success=False,
                source=self.name,
                error=str(e)
            )


class OpenLibraryTarget:
    """Internet Archive OpenLibrary bibliographic API target.

    Uses ``OpenLibraryApiClient`` to retrieve call number data from
    openlibrary.org.
    """

    name = "OpenLibrary"

    def __init__(self, timeout: int = 8, retries: int = 0):
        from api.openlibrary_api import OpenLibraryApiClient
        self.client = OpenLibraryApiClient(timeout_seconds=timeout, max_retries=retries)

    def lookup(self, isbn: str) -> TargetResult:
        """Lookup ISBN using OpenLibrary API."""
        try:
            result = self.client.search(isbn)

            if result.status == "success" and (result.lccn or result.nlmcn):
                return TargetResult(
                    success=True,
                    lccn=result.lccn,
                    nlmcn=result.nlmcn,
                    source=self.name,
                    isbns=tuple(result.isbns),
                )
            elif result.status == "not_found":
                return TargetResult(
                    success=False,
                    source=self.name,
                    error=f"No records found in {self.name}.",
                    isbns=tuple(result.isbns),
                )
            else:
                return TargetResult(
                    success=False,
                    source=self.name,
                    error=result.error_message or f"API status: {result.status}",
                    isbns=tuple(result.isbns),
                )
        except Exception as e:
            logger.error(f"OpenLibrary lookup failed for {isbn}: {e}")
            return TargetResult(
                success=False,
                source=self.name,
                error=str(e)
            )


class APITarget:
    """
    Placeholder API target.
    Will be replaced with real API implementations.
    """

    def __init__(self, name: str):
        self.name = name

    def lookup(self, isbn: str) -> TargetResult:
        """Placeholder lookup — always returns failure until a concrete API is wired in."""
        return TargetResult(
            success=False,
            source=self.name,
            error=messages.NetworkMessages.api_not_implemented
        )


def create_target_from_config(target_config: dict):
    """
    Create a target instance from GUI configuration.

    Args:
        target_config: Dictionary with target configuration
            Example: {"name": "Library of Congress", "type": "api", "selected": true, "rank": 1}
            Or: {"name": "Yale", "type": "z3950", "host": "...", "port": 210, "database": "..."}

    Returns:
        Target instance that implements HarvestTarget protocol
    """
    name = str(target_config.get("name", "Unknown")).strip()
    target_type = str(target_config.get("type", "api")).strip().lower()
    try:
        timeout = int(target_config.get("timeout", 8))
    except Exception:
        timeout = 8
    try:
        retries = int(target_config.get("max_retries", 0))
    except Exception:
        retries = 0
    normalized_name = name.lower()

    # Handle specific known API targets (name-first, tolerant aliases)
    # This keeps API targets connected even when UI labels include suffixes
    # such as "Library of Congress API" or "Harvard Library API".
    if "library of congress" in normalized_name or normalized_name == "loc":
        return LibraryOfCongressTarget(timeout=timeout, retries=retries)
    elif "harvard" in normalized_name:
        return HarvardLibraryCloudTarget(timeout=timeout, retries=retries)
    elif "openlibrary" in normalized_name or "open library" in normalized_name:
        return OpenLibraryTarget(timeout=timeout, retries=retries)
    # Handle Z39.50 targets
    elif target_type == "z3950":
        return Z3950Target(
            name=name,
            host=target_config.get("host", ""),
            port=target_config.get("port", 210),
            database=target_config.get("database", "")
        )
    # Fallback to generic API target
    elif target_type == "api":
        return APITarget(name=name)
    else:
        raise ValueError(f"Unknown target type: {target_type}")
