"""
harvard_api.py

Harvard LibraryCloud API client (Item API).

This client performs ISBN-based lookups using the LibraryCloud Item API and
extracts call-number-like values (best-effort) from the response.

Primary query style (per Harvard docs):
- https://api.lib.harvard.edu/v2/items?identifier=<ISBN>
JSON example endpoints are also documented (e.g., /v2/items.json).  See Harvard docs.

Notes
-----
- Response schemas can vary; extraction is best-effort.
- This module does NOT validate ISBN checksums (that is handled elsewhere).
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as et
from typing import Any, Dict, List, Optional, Tuple

from src.api.base_api import ApiResult, BaseApiClient
from src.api.http_utils import urlopen_with_ca
from src.utils.call_number_validators import validate_lccn, validate_nlmcn


class HarvardApiClient(BaseApiClient):
    """
    Harvard LibraryCloud Item API client.

    Performs identifier=ISBN searches and extracts call-number candidates from:
    - JSON fields (e.g., shelfLocator / classification-like keys)
    - MODS XML if present (e.g., <shelfLocator>, <classification>)
    """

    source_name = "Harvard"
    base_url = "https://api.lib.harvard.edu/v2/items.json"

    @property
    def source(self) -> str:
        return self.source_name

    def fetch(self, isbn: str) -> Any:
        primary = None
        try:
            primary = self._request_json(self.build_url(isbn))
            if self._has_records(primary):
                return primary
        except Exception:
            # Primary query path failed; try fallback shape before bubbling up.
            pass

        fallback = self._request_json(self.build_fallback_url(isbn))
        if self._has_records(fallback):
            return fallback

        # Keep prior payload for debugging if we had one.
        return fallback if fallback is not None else primary

    def build_url(self, isbn: str) -> str:
        """
        Build the Harvard LibraryCloud query URL for an ISBN.

        Uses the identifier field which searches by ISBN (no hyphens/spaces).
        Per Harvard docs: "an item by its ISBN"
        """
        params = {
            "identifier": isbn,
            "limit": "1",
        }
        return f"{self.base_url}?{urllib.parse.urlencode(params)}"

    def build_fallback_url(self, isbn: str) -> str:
        """
        Fallback: keyword search across all fields.

        If identifier= returns nothing for a specific ISBN,
        this searches the ISBN as text across all fields.
        """
        params = {
            "q": isbn,  # Just the ISBN as keyword, not "identifier:isbn"
            "limit": "1",
        }
        return f"{self.base_url}?{urllib.parse.urlencode(params)}"

    def _request_json(self, url: str) -> Any:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X)")
        req.add_header("Accept", "application/json,text/plain,*/*")

        with urlopen_with_ca(req, timeout=self.timeout_seconds) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")
            return self.parse_response(resp.read())

    def _has_records(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False

        # Check pagination numFound field (Harvard's way)
        pagination = payload.get("pagination", {})
        if isinstance(pagination, dict):
            try:
                num_found = int(pagination.get("numFound", 0))
            except (TypeError, ValueError):
                num_found = 0
            if num_found > 0:
                return True

        # Fallback: check items structure
        items = payload.get("items")
        records = payload.get("records")

        # Harvard returns items as dict with 'mods' key
        if isinstance(items, dict) and "mods" in items:
            mods = items.get("mods")
            return (isinstance(mods, list) and len(mods) > 0) or isinstance(mods, dict)

        # Other formats may return items/records as lists
        return (isinstance(items, list) and len(items) > 0) or (
            isinstance(records, list) and len(records) > 0
        )

    def parse_response(self, body: bytes) -> Any:
        """
        Parse HTTP response body into a Python object (expected JSON).
        """
        # Harvard returns JSON at /items.json endpoints.
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
        lc: List[str] = []
        nlm: List[str] = []
        other: List[str] = []

        items = self._extract_item_objects(parsed)

        if not items:
            return {"lc": [], "nlm": [], "other": []}

        item0 = items[0] if isinstance(items[0], dict) else {}

        # 1) Try extracting from structured MODS-style JSON fields first.
        structured = self._extract_from_mods_like_json(item0)
        lc.extend(structured[0])
        nlm.extend(structured[1])
        other.extend(structured[2])

        # 2) Try extracting from obvious JSON keys
        json_candidates = self._find_json_call_number_candidates(item0)
        lc.extend(json_candidates[0])
        nlm.extend(json_candidates[1])
        other.extend(json_candidates[2])

        # 3) Try extracting from embedded MODS XML if present
        mods_xml = self._get_mods_xml_if_present(item0)
        if mods_xml:
            mods_candidates = self._extract_from_mods_xml(mods_xml)
            lc.extend(mods_candidates[0])
            nlm.extend(mods_candidates[1])
            other.extend(mods_candidates[2])

        # Deduplicate while preserving order
        return {
            "lc": self._dedupe_keep_order(lc),
            "nlm": self._dedupe_keep_order(nlm),
            "other": self._dedupe_keep_order(other),
        }

    def _extract_item_objects(self, parsed: Any) -> List[Dict[str, Any]]:
        if not isinstance(parsed, dict):
            return []

        # Common LibraryCloud JSON shape: {"items": {"mods": [ ... ]}}
        items = parsed.get("items")
        if isinstance(items, dict):
            mods = items.get("mods")
            if isinstance(mods, list):
                return [m for m in mods if isinstance(m, dict)]
            if isinstance(mods, dict):
                return [mods]

        # Alternate shapes
        if isinstance(items, list):
            return [m for m in items if isinstance(m, dict)]

        records = parsed.get("records")
        if isinstance(records, list):
            return [m for m in records if isinstance(m, dict)]

        return []

    def extract_call_numbers(self, isbn: str, payload: Any) -> ApiResult:
        """
        Convert Harvard response payload into the unified ApiResult contract.
        """
        candidates = self._extract_candidates(payload)
        lccn = candidates["lc"][0] if candidates["lc"] else None
        nlmcn = candidates["nlm"][0] if candidates["nlm"] else None

        # Validate extracted call numbers
        lccn = validate_lccn(lccn, source=self.source)
        nlmcn = validate_nlmcn(nlmcn, source=self.source)

        if lccn or nlmcn:
            return ApiResult(
                isbn=isbn,
                source=self.source,
                status="success",
                lccn=lccn,
                nlmcn=nlmcn,
                raw=payload,
            )

        return ApiResult(
            isbn=isbn,
            source=self.source,
            status="not_found",
            raw=payload,
        )

    # -------------------------
    # Helpers
    # -------------------------

    def _find_json_call_number_candidates(
        self, obj: Dict[str, Any]
    ) -> Tuple[List[str], List[str], List[str]]:
        lc: List[str] = []
        nlm: List[str] = []
        other: List[str] = []

        # Common field names in various metadata payloads
        keys_of_interest = {
            "shelflocator",
            "shelf_locator",
            "shelfLocator",
            "callnumber",
            "call_number",
            "callNumber",
            "classification",
            "lccn",
            "number_lccn",
            "identifier-lccn",
        }

        def walk(x: Any) -> None:
            if isinstance(x, dict):
                for k, v in x.items():
                    if isinstance(k, str) and (k in keys_of_interest or "lccn" in k.lower()):
                        force_lc = "lccn" in k.lower()
                        if isinstance(v, list):
                            for item in v:
                                self._bucket_candidate(str(item), lc, nlm, other, force="lc" if force_lc else None)
                        else:
                            self._bucket_candidate(str(v), lc, nlm, other, force="lc" if force_lc else None)
                    walk(v)
            elif isinstance(x, list):
                for it in x:
                    walk(it)

        walk(obj)
        return lc, nlm, other

    def _extract_from_mods_like_json(
        self, obj: Dict[str, Any]
    ) -> Tuple[List[str], List[str], List[str]]:
        """
        Extract candidates from common LibraryCloud MODS-like JSON fields.
        """
        lc: List[str] = []
        nlm: List[str] = []
        other: List[str] = []

        def as_list(v: Any) -> List[Any]:
            if isinstance(v, list):
                return v
            if v is None:
                return []
            return [v]

        # identifier: {"@type":"lccn","#text":"..."}
        for ident in as_list(obj.get("identifier")):
            if not isinstance(ident, dict):
                continue
            ident_type = str(ident.get("@type", "")).strip().lower()
            text = str(ident.get("#text", "")).strip()
            if not text:
                continue

            if ident_type == "lccn":
                self._bucket_candidate(text, lc, nlm, other, force="lc")
            elif ident_type in {"isbn", "issn", "uri"}:
                continue
            else:
                self._bucket_candidate(text, lc, nlm, other)

        # classification: {"@authority":"lcc|nlm","#text":"..."}
        for cls in as_list(obj.get("classification")):
            if not isinstance(cls, dict):
                continue
            authority = str(cls.get("@authority", "")).strip().lower()
            text = str(cls.get("#text", "")).strip()
            if not text:
                continue

            if "nlm" in authority:
                self._bucket_candidate(text, lc, nlm, other, force="nlm")
            elif "lcc" in authority or authority == "lc":
                self._bucket_candidate(text, lc, nlm, other, force="lc")
            else:
                self._bucket_candidate(text, lc, nlm, other)

        # location.shelfLocator
        for location in as_list(obj.get("location")):
            if not isinstance(location, dict):
                continue
            for shelf in as_list(location.get("shelfLocator")):
                if isinstance(shelf, dict):
                    text = str(shelf.get("#text", "")).strip()
                    if text:
                        self._bucket_candidate(text, lc, nlm, other)
                elif isinstance(shelf, str):
                    self._bucket_candidate(shelf, lc, nlm, other)

        return lc, nlm, other

    def _get_mods_xml_if_present(self, item: Dict[str, Any]) -> Optional[str]:
        """
        LibraryCloud responses sometimes embed MODS as XML text or nested dicts.
        This tries to locate a plausible MODS XML blob.
        """
        # Some responses include fields like "mods" or "metadata" with XML
        for key in ("mods", "MODS", "metadata", "xml", "record"):
            val = item.get(key)
            if isinstance(val, str) and "<mods" in val.lower():
                return val
            # Sometimes nested
            if isinstance(val, dict):
                for subkey, subval in val.items():
                    if isinstance(subval, str) and "<mods" in subval.lower():
                        return subval
        return None

    def _extract_from_mods_xml(
        self, xml_text: str
    ) -> Tuple[List[str], List[str], List[str]]:
        lc: List[str] = []
        nlm: List[str] = []
        other: List[str] = []

        try:
            root = et.fromstring(xml_text)
        except Exception:
            return lc, nlm, other

        # Namespace-agnostic tag checks by suffix
        def tag_endswith(elem: et.Element, suffix: str) -> bool:
            return elem.tag.lower().endswith(suffix.lower())

        for elem in root.iter():
            if tag_endswith(elem, "shelfLocator") and elem.text:
                self._bucket_candidate(elem.text, lc, nlm, other)

            if tag_endswith(elem, "classification") and elem.text:
                # Sometimes classification has authority attributes
                authority = (elem.attrib.get("authority") or "").lower()
                text = elem.text
                if "nlm" in authority:
                    self._bucket_candidate(text, lc, nlm, other, force="nlm")
                elif "lcc" in authority or "lc" in authority:
                    self._bucket_candidate(text, lc, nlm, other, force="lc")
                else:
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
        Put a candidate value into lc/nlm/other buckets.
        """
        candidate = value.strip()
        if not candidate:
            return

        if force == "lc":
            lc.append(candidate)
            return
        if force == "nlm":
            nlm.append(candidate)
            return

        # Heuristic: NLM call numbers often start with 1-2 letters then digits (e.g., "WG 120")
        # LC call numbers often start with 1-3 letters then digits (e.g., "QA 76.73")
        # Without full parsing rules, keep it conservative.
        # If it contains a space after 1-3 letters, treat as likely classification.
        import re

        m = re.match(r"^[A-Z]{1,3}\s*\d", candidate)
        if m:
            # If it starts with W* it's often NLM, but not guaranteed. Keep W* bias to NLM.
            if candidate.startswith(("W", "WA", "WB", "WC", "WD", "WE", "WF", "WG", "WH", "WI", "WJ", "WK", "WL", "WM", "WN", "WO", "WP", "WQ", "WR", "WS", "WT", "WU", "WV", "WW", "WX", "WY", "WZ")):
                nlm.append(candidate)
            else:
                lc.append(candidate)
        else:
            other.append(candidate)

    def _dedupe_keep_order(self, values: List[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for v in values:
            if v not in seen:
                seen.add(v)
                out.append(v)
        return out
