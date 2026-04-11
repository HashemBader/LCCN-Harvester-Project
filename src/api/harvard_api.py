"""
harvard_api.py

Harvard LibraryCloud Item API client.

Performs ISBN-based lookups using Harvard's LibraryCloud Item API and
extracts call-number-like values (best-effort) from the JSON or embedded
MODS XML response.

API endpoints used
------------------
Primary (identifier search):
    https://api.lib.harvard.edu/v2/items.json?identifier=<ISBN>&limit=1

Fallback (keyword search):
    https://api.lib.harvard.edu/v2/items.json?q=<ISBN>&limit=1

The ``identifier`` parameter searches the item's identifier fields (ISBN,
LCCN, etc.) directly.  If that returns no records, a keyword (``q``) search
is tried as a best-effort fallback.

Response shapes
---------------
The LibraryCloud JSON wraps MODS records.  The common shape is::

    {
        "pagination": {"numFound": 1, ...},
        "items": {
            "mods": [
                {
                    "classification": [{"@authority": "lcc", "#text": "QA76.73"}],
                    "location": [{"shelfLocator": "..."}],
                    ...
                }
            ]
        }
    }

Extraction strategy (applied in order):
1. MODS-like JSON fields (``classification``, ``location.shelfLocator``,
   ``identifier`` with non-lccn type).
2. Generic JSON keys whose names suggest shelf/call data
   (``shelfLocator``, ``callNumber``, ``classification``).
3. Embedded MODS XML blob, if any field contains an XML string.

Notes
-----
- Response schemas can vary across record types; extraction is best-effort.
- This module does NOT validate ISBN checksums (handled by isbn_validator).
- Call number validation is performed by call_number_validators.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as et
from typing import Any, Dict, List, Optional, Tuple

from src.api.base_api import ApiResult, BaseApiClient
from src.api.http_utils import urlopen_with_ca
from src.utils.call_number_validators import validate_lccn, validate_nlmcn
from src.utils.isbn_validator import normalize_isbn


class HarvardApiClient(BaseApiClient):
    """
    Harvard LibraryCloud Item API client.

    Performs identifier=ISBN searches and extracts call-number candidates from:
    - JSON fields (e.g., shelfLocator / classification-like keys)
    - MODS XML if present (e.g., <shelfLocator>, <classification>)
    """

    # Harvard-specific API configuration
    source_name = "Harvard"
    # LibraryCloud API endpoint for item searches
    base_url = "https://api.lib.harvard.edu/v2/items.json"

    @property
    def source(self) -> str:
        # Return the source identifier for this API client
        return self.source_name

    def fetch(self, isbn: str) -> Any:
        """
        Fetch LibraryCloud item data for an ISBN, with a keyword-search fallback.

        Attempts the ``identifier=`` query first (most precise).  If that
        returns no records (or raises a network exception), falls back to a
        full-text ``q=`` keyword search.  The payload that contains records
        is returned preferentially; otherwise the fallback payload is returned
        so downstream code can at least see the raw response for debugging.

        Parameters
        ----------
        isbn : str
            Normalized ISBN string (no hyphens).

        Returns
        -------
        dict | None
            Parsed JSON payload from LibraryCloud, or ``None`` on total failure.

        Raises
        ------
        Exception
            Re-raises exceptions from the fallback request if both queries fail.
        """
        # Attempt precise identifier search first
        primary = None
        try:
            primary = self._request_json(self.build_url(isbn))
            # Return immediately if primary search yields results
            if self._has_records(primary):
                return primary
        except Exception:
            # Primary query path failed; try fallback shape before bubbling up.
            pass

        # Fall back to full-text keyword search if identifier search failed or returned no results
        fallback = self._request_json(self.build_fallback_url(isbn))
        if self._has_records(fallback):
            return fallback

        # Return whichever response we have (fallback preferred, then primary) for debugging
        return fallback if fallback is not None else primary

    def build_url(self, isbn: str) -> str:
        """
        Build the Harvard LibraryCloud query URL for an ISBN.

        Uses the identifier field which searches by ISBN (no hyphens/spaces).
        Per Harvard docs: "an item by its ISBN"
        """
        # Create query parameters for the identifier search
        params = {
            "identifier": isbn,  # Search by ISBN identifier
            "limit": "1",  # Only return the first matching record
        }
        # Construct and return the full URL with query string
        return f"{self.base_url}?{urllib.parse.urlencode(params)}"

    def build_fallback_url(self, isbn: str) -> str:
        """
        Fallback: keyword search across all fields.

        If identifier= returns nothing for a specific ISBN,
        this searches the ISBN as text across all fields.
        """
        # Create query parameters for the keyword search
        params = {
            "q": isbn,  # Full-text keyword search (not identifier-specific)
            "limit": "1",  # Only return the first matching record
        }
        # Construct and return the full URL with query string
        return f"{self.base_url}?{urllib.parse.urlencode(params)}"

    def _request_json(self, url: str) -> Any:
        """
        Perform a GET request and return the parsed JSON body.

        Parameters
        ----------
        url : str
            Fully-formed request URL (built by build_url or build_fallback_url).

        Returns
        -------
        Any
            Python object parsed from the JSON response body.

        Raises
        ------
        Exception
            On non-200 HTTP status or JSON decode failure.
        """
        # Create a request object with the given URL
        req = urllib.request.Request(url)
        # Add HTTP headers for proper identification and content negotiation
        req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X)")
        req.add_header("Accept", "application/json,text/plain,*/*")

        # Use the custom urlopen wrapper to handle certificate validation
        with urlopen_with_ca(req, timeout=self.timeout_seconds) as resp:
            # Check for successful HTTP response code
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")
            # Return the parsed JSON from the response body
            return self.parse_response(resp.read())

    def _has_records(self, payload: Any) -> bool:
        # Payload must be a dictionary to be valid
        if not isinstance(payload, dict):
            return False

        # First check: Look at pagination metadata (Harvard's primary indicator)
        pagination = payload.get("pagination", {})
        if isinstance(pagination, dict):
            try:
                # numFound is the count of matching records in the search results
                num_found = int(pagination.get("numFound", 0))
            except (TypeError, ValueError):
                num_found = 0
            if num_found > 0:
                return True

        # Fallback checks: Look for actual data structures if pagination isn't present
        items = payload.get("items")
        records = payload.get("records")

        # Harvard typically returns items as a dictionary with 'mods' key containing metadata
        if isinstance(items, dict) and "mods" in items:
            mods = items.get("mods")
            # mods can be either a list of records or a single record dict
            return (isinstance(mods, list) and len(mods) > 0) or isinstance(mods, dict)

        # Alternative response formats may return items/records as lists directly
        return (isinstance(items, list) and len(items) > 0) or (
            isinstance(records, list) and len(records) > 0
        )

    def parse_response(self, body: bytes) -> Any:
        """
        Parse HTTP response body into a Python object (expected JSON).
        """
        # Harvard returns JSON at /items.json endpoints, decode and parse it
        return json.loads(body.decode("utf-8", errors="replace"))

    def _extract_candidates(self, parsed: Any) -> Dict[str, List[str]]:
        """
        Best-effort extraction of call-number-like values.

        Returns
        -------
        dict[str, list[str]]
            Keys:
              - "lc": candidate Library of Congress call numbers
              - "nlm": candidate National Library of Medicine call numbers
              - "other": other shelf/classification candidates
        """
        # Initialize the three buckets for different call number types
        lc: List[str] = []
        nlm: List[str] = []
        other: List[str] = []

        # Extract the item records from the parsed JSON response
        items = self._extract_item_objects(parsed)

        # Return empty results if no items were found
        if not items:
            return {"lc": [], "nlm": [], "other": []}

        # Use the first item record for call number extraction
        item0 = items[0] if isinstance(items[0], dict) else {}

        # Phase 1: Extract from structured MODS-style JSON fields (most reliable)
        structured = self._extract_from_mods_like_json(item0)
        lc.extend(structured[0])
        nlm.extend(structured[1])
        other.extend(structured[2])

        # Phase 2: Extract from generic JSON keys that often contain call numbers
        json_candidates = self._find_json_call_number_candidates(item0)
        lc.extend(json_candidates[0])
        nlm.extend(json_candidates[1])
        other.extend(json_candidates[2])

        # Phase 3: Extract from embedded MODS XML if it exists in the response
        mods_xml = self._get_mods_xml_if_present(item0)
        if mods_xml:
            mods_candidates = self._extract_from_mods_xml(mods_xml)
            lc.extend(mods_candidates[0])
            nlm.extend(mods_candidates[1])
            other.extend(mods_candidates[2])

        # Return deduplicated results while maintaining order of discovery
        return {
            "lc": self._dedupe_keep_order(lc),
            "nlm": self._dedupe_keep_order(nlm),
            "other": self._dedupe_keep_order(other),
        }

    def _extract_item_objects(self, parsed: Any) -> List[Dict[str, Any]]:
        # Return empty list if input is not a dictionary
        if not isinstance(parsed, dict):
            return []

        # Extract items from the common LibraryCloud JSON shape: {"items": {"mods": [ ... ]}}
        items = parsed.get("items")
        if isinstance(items, dict):
            # Harvard's standard format: items is a dict with 'mods' key
            mods = items.get("mods")
            if isinstance(mods, list):
                # mods is a list of record dictionaries
                return [m for m in mods if isinstance(m, dict)]
            if isinstance(mods, dict):
                # Sometimes mods is just a single record dict
                return [mods]

        # Try alternate response shapes
        if isinstance(items, list):
            # Items might be a direct list of records
            return [m for m in items if isinstance(m, dict)]

        # Try "records" field (used by some API variants)
        records = parsed.get("records")
        if isinstance(records, list):
            return [m for m in records if isinstance(m, dict)]

        # No items found
        return []

    def _extract_isbns(self, payload: Any) -> List[str]:
        # Return empty list if payload is not a dictionary
        if not isinstance(payload, dict):
            return []

        # Extract item records from the response
        items = self._extract_item_objects(payload)
        # Accumulate ISBNs found across all items
        isbns: List[str] = []

        # Process each item record
        for item in items:
            # Search for ISBN fields in the JSON structure
            self._collect_isbns_from_json(item, isbns)
            # Also check if there's MODS XML embedded in the item
            mods_xml = self._get_mods_xml_if_present(item)
            if mods_xml:
                # Extract ISBNs from the embedded MODS XML
                isbns.extend(self._extract_isbns_from_mods_xml(mods_xml))

        # Return deduplicated list of ISBNs
        return self._dedupe_keep_order(isbns)

    def _collect_isbns_from_json(self, obj: Any, isbns: List[str]) -> None:
        # Recursively search through JSON structure for ISBN values
        if isinstance(obj, dict):
            for key, value in obj.items():
                # Normalize key to lowercase for comparison
                key_lower = str(key).strip().lower()
                # Check for direct ISBN fields
                if key_lower in {"isbn", "isbn_10", "isbn_13"}:
                    # Handle both list and single values
                    values = value if isinstance(value, list) else [value]
                    for item in values:
                        if isinstance(item, str):
                            # Normalize and store the ISBN
                            normalized = normalize_isbn(item.strip())
                            if normalized:
                                isbns.append(normalized)
                # Handle MODS-style identifier fields with type attribute
                elif key_lower == "identifier" and isinstance(value, list):
                    for entry in value:
                        if isinstance(entry, dict):
                            # MODS format: {"@type": "isbn", "#text": "..."}
                            if str(entry.get("@type", "")).strip().lower() == "isbn":
                                text = str(entry.get("#text", "")).strip()
                                if text:
                                    normalized = normalize_isbn(text)
                                    if normalized:
                                        isbns.append(normalized)
                        elif isinstance(entry, str):
                            # Simple string identifier
                            normalized = normalize_isbn(entry.strip())
                            if normalized:
                                isbns.append(normalized)
                else:
                    # Recursively search nested objects
                    self._collect_isbns_from_json(value, isbns)
        elif isinstance(obj, list):
            # Recursively search list items
            for item in obj:
                self._collect_isbns_from_json(item, isbns)

    def _extract_isbns_from_mods_xml(self, xml_text: str) -> List[str]:
        # Initialize accumulator for found ISBNs
        isbns: List[str] = []
        try:
            # Parse the XML string into an element tree
            root = et.fromstring(xml_text)
        except Exception:
            # Return empty list if XML parsing fails
            return isbns

        # Iterate through all elements in the XML tree
        for elem in root.iter():
            # Look for identifier elements (namespace-agnostic check by tag name)
            if elem.tag.lower().endswith("identifier"):
                # Check the type attribute to see if this is an ISBN
                identifier_type = str(elem.attrib.get("type", "")).strip().lower()
                if identifier_type == "isbn" and elem.text:
                    # Normalize and store the ISBN
                    normalized = normalize_isbn(elem.text.strip())
                    if normalized:
                        isbns.append(normalized)
        # Return the collected ISBNs
        return isbns

    def extract_call_numbers(self, isbn: str, payload: Any) -> ApiResult:
        """
        Convert Harvard response payload into the unified ApiResult contract.
        """
        # Extract candidate call numbers grouped by type
        candidates = self._extract_candidates(payload)
        # Take the first (highest confidence) candidate from each category
        lccn = candidates["lc"][0] if candidates["lc"] else None
        nlmcn = candidates["nlm"][0] if candidates["nlm"] else None
        # Also extract related ISBNs found in the response
        isbns = self._extract_isbns(payload)

        # Validate extracted call numbers against expected formats
        lccn = validate_lccn(lccn, source=self.source)
        nlmcn = validate_nlmcn(nlmcn, source=self.source)

        # Return success if any valid call number was extracted
        if lccn or nlmcn:
            return ApiResult(
                isbn=isbn,
                source=self.source,
                status="success",
                lccn=lccn,
                nlmcn=nlmcn,
                raw=payload,
                isbns=isbns,
            )

        # Return not_found if no valid call numbers were extracted
        return ApiResult(
            isbn=isbn,
            source=self.source,
            status="not_found",
            raw=payload,
            isbns=isbns,
        )

    # -------------------------
    # Helpers
    # -------------------------

    def _find_json_call_number_candidates(
        self, obj: Dict[str, Any]
    ) -> Tuple[List[str], List[str], List[str]]:
        # Initialize buckets for different classification types
        lc: List[str] = []
        nlm: List[str] = []
        other: List[str] = []

        # Common field names that hold actual call numbers / shelf locators.
        # Deliberately excludes "lccn", "number_lccn", "identifier-lccn" because
        # those fields carry LC *control* numbers (MARC 010, e.g. "2007039987"),
        # not LC *classification* call numbers (MARC 050).
        keys_of_interest = {
            "shelflocator",
            "shelf_locator",
            "shelfLocator",
            "callnumber",
            "call_number",
            "callNumber",
            "classification",
        }

        # Recursive function to walk the JSON tree looking for interesting keys
        def walk(x: Any) -> None:
            if isinstance(x, dict):
                for k, v in x.items():
                    # Check if this key is one we're looking for
                    if isinstance(k, str) and k in keys_of_interest:
                        # Handle both list and scalar values
                        if isinstance(v, list):
                            for item in v:
                                self._bucket_candidate(str(item), lc, nlm, other)
                        else:
                            self._bucket_candidate(str(v), lc, nlm, other)
                    # Recurse into nested values
                    walk(v)
            elif isinstance(x, list):
                # Recurse into list items
                for it in x:
                    walk(it)

        # Start the recursive walk from the root object
        walk(obj)
        return lc, nlm, other

    def _extract_from_mods_like_json(
        self, obj: Dict[str, Any]
    ) -> Tuple[List[str], List[str], List[str]]:
        """
        Extract candidates from common LibraryCloud MODS-like JSON fields.
        """
        # Initialize buckets for different classification types
        lc: List[str] = []
        nlm: List[str] = []
        other: List[str] = []

        # Helper function to normalize values to lists for uniform processing
        def as_list(v: Any) -> List[Any]:
            if isinstance(v, list):
                return v
            if v is None:
                return []
            return [v]

        # Extract from identifier field: {"@type":"lccn","#text":"..."}
        # Note: MODS format uses @ for attributes and # for text content
        for ident in as_list(obj.get("identifier")):
            if not isinstance(ident, dict):
                continue
            # Get the identifier type and text content
            ident_type = str(ident.get("@type", "")).strip().lower()
            text = str(ident.get("#text", "")).strip()
            if not text:
                continue

            if ident_type == "lccn":
                # This is the LC control number (MARC 010, e.g. "2007039987"),
                # NOT an LC classification call number (MARC 050).  Skip it.
                continue
            elif ident_type in {"isbn", "issn", "uri"}:
                # Skip non-classification identifiers
                continue
            else:
                # Route other identifier types for classification
                self._bucket_candidate(text, lc, nlm, other)

        # Extract from classification field: {"@authority":"lcc|nlm","#text":"..."}
        # The authority attribute tells us what standard is being used
        for cls in as_list(obj.get("classification")):
            if not isinstance(cls, dict):
                continue
            # Get the authority standard and classification text
            authority = str(cls.get("@authority", "")).strip().lower()
            text = str(cls.get("#text", "")).strip()
            if not text:
                continue

            # Route to appropriate bucket based on authority if known
            if "nlm" in authority:
                self._bucket_candidate(text, lc, nlm, other, force="nlm")
            elif "lcc" in authority or authority == "lc":
                self._bucket_candidate(text, lc, nlm, other, force="lc")
            else:
                # Use heuristics to classify if authority is unknown
                self._bucket_candidate(text, lc, nlm, other)

        # Extract from location/shelfLocator field (often contains call numbers)
        for location in as_list(obj.get("location")):
            if not isinstance(location, dict):
                continue
            # Extract the shelf locator from within location
            for shelf in as_list(location.get("shelfLocator")):
                if isinstance(shelf, dict):
                    # MODS format: extract text from #text field
                    text = str(shelf.get("#text", "")).strip()
                    if text:
                        self._bucket_candidate(text, lc, nlm, other)
                elif isinstance(shelf, str):
                    # Direct string value
                    self._bucket_candidate(shelf, lc, nlm, other)

        return lc, nlm, other

    def _get_mods_xml_if_present(self, item: Dict[str, Any]) -> Optional[str]:
        """
        LibraryCloud responses sometimes embed MODS as XML text or nested dicts.
        This tries to locate a plausible MODS XML blob.
        """
        # Search for common field names that might contain XML
        for key in ("mods", "MODS", "metadata", "xml", "record"):
            val = item.get(key)
            # Check if it's a string containing XML
            if isinstance(val, str) and "<mods" in val.lower():
                return val
            # Sometimes XML is nested inside another dictionary
            if isinstance(val, dict):
                for subkey, subval in val.items():
                    if isinstance(subval, str) and "<mods" in subval.lower():
                        return subval
        # No XML found
        return None

    def _extract_from_mods_xml(
        self, xml_text: str
    ) -> Tuple[List[str], List[str], List[str]]:
        # Initialize buckets for different classification types
        lc: List[str] = []
        nlm: List[str] = []
        other: List[str] = []

        # Parse the XML string into an element tree
        try:
            root = et.fromstring(xml_text)
        except Exception:
            # Return empty results if XML parsing fails
            return lc, nlm, other

        # Helper function to check tag names in a namespace-agnostic way
        # (XML namespaces can be complex, so we match by tag suffix)
        def tag_endswith(elem: et.Element, suffix: str) -> bool:
            return elem.tag.lower().endswith(suffix.lower())

        # Iterate through all elements in the XML tree
        for elem in root.iter():
            # Extract shelf locator elements (typically contain call numbers)
            if tag_endswith(elem, "shelfLocator") and elem.text:
                self._bucket_candidate(elem.text, lc, nlm, other)

            # Extract classification elements
            if tag_endswith(elem, "classification") and elem.text:
                # Check if authority attribute indicates the classification type
                authority = (elem.attrib.get("authority") or "").lower()
                text = elem.text
                if "nlm" in authority:
                    # Known to be NLM classification
                    self._bucket_candidate(text, lc, nlm, other, force="nlm")
                elif "lcc" in authority or "lc" in authority:
                    # Known to be LC classification
                    self._bucket_candidate(text, lc, nlm, other, force="lc")
                else:
                    # Unknown authority, use heuristics
                    self._bucket_candidate(text, lc, nlm, other)

        return lc, nlm, other

    def _bucket_candidate(
        self,
        value: str,
        lc: List[str],
        nlm: List[str],
        other: List[str],
        force: Optional[str] = None,
    ) -> None:
        """
        Assign a call-number candidate to the LC, NLM, or "other" bucket.

        When ``force`` is provided (set by callers that know the authority from
        metadata), the candidate is placed directly without heuristics.

        When ``force`` is None, a regex heuristic is applied:
        - Strings that start with 1–3 uppercase letters immediately followed by
          a digit look like a real classification (LC or NLM).
        - Strings whose letter prefix begins with a ``W``-class prefix (the NLM
          schedule) are routed to the NLM bucket.
        - Everything else goes to ``other`` for later inspection.

        Parameters
        ----------
        value : str
            Raw candidate string to classify.
        lc : list[str]
            Accumulator for LC Classification candidates.
        nlm : list[str]
            Accumulator for NLM Classification candidates.
        other : list[str]
            Accumulator for unclassified candidates.
        force : str | None
            If ``"lc"`` or ``"nlm"``, skip heuristics and route directly.
        """
        # Trim whitespace from the candidate
        candidate = value.strip()
        if not candidate:
            return

        # If the authority is explicitly known, route directly
        if force == "lc":
            lc.append(candidate)
            return
        if force == "nlm":
            nlm.append(candidate)
            return

        # Apply heuristic pattern matching for unknown authorities
        # Pattern: 1–3 uppercase letters optionally followed by whitespace, then a digit
        # Examples: "QA 76.73" (LC), "WG 120" (NLM)
        # This distinguishes real classifications from random text
        m = re.match(r"^[A-Z]{1,3}\s*\d", candidate)
        if m:
            # Successfully matched the pattern - looks like a real classification
            # NLM schedule occupies all W* two-letter classes plus single "W".
            # Route any candidate whose prefix matches a known W-class to the NLM bucket
            if candidate.startswith(("W", "WA", "WB", "WC", "WD", "WE", "WF", "WG", "WH", "WI", "WJ", "WK", "WL", "WM", "WN", "WO", "WP", "WQ", "WR", "WS", "WT", "WU", "WV", "WW", "WX", "WY", "WZ")):
                # NLM classification (W-prefix)
                nlm.append(candidate)
            else:
                # LC classification (other letter prefixes)
                lc.append(candidate)
        else:
            # Does not match the classification pattern - store for manual inspection
            other.append(candidate)

    def _dedupe_keep_order(self, values: List[str]) -> List[str]:
        # Remove duplicate values while preserving order of first occurrence
        seen = set()
        out: List[str] = []
        for v in values:
            # Only add if we haven't seen this value before
            if v not in seen:
                seen.add(v)
                out.append(v)
        return out
