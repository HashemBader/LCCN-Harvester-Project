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
import xml.etree.ElementTree as et
from typing import Any, Dict, List, Optional, Tuple

from api.base_api import ApiResult, BaseApiClient


class HarvardApiClient(BaseApiClient):
    """
    Harvard LibraryCloud Item API client.

    Performs identifier=ISBN searches and extracts call-number candidates from:
    - JSON fields (e.g., shelfLocator / classification-like keys)
    - MODS XML if present (e.g., <shelfLocator>, <classification>)
    """

    source_name = "harvard"
    base_url = "https://api.lib.harvard.edu/v2/items.json"

    def build_url(self, isbn: str) -> str:
        """
        Build the Harvard LibraryCloud query URL for an ISBN.
        """
        params = {
            "identifier": isbn,
            # Keep results small; Harvard API supports pagination fields in general.
            "limit": "1",
        }
        return f"{self.base_url}?{urllib.parse.urlencode(params)}"

    def parse_response(self, body: bytes) -> Any:
        """
        Parse HTTP response body into a Python object (expected JSON).
        """
        # Harvard returns JSON at /items.json endpoints.
        return json.loads(body.decode("utf-8", errors="replace"))

    def extract_call_numbers(self, parsed: Any) -> Dict[str, List[str]]:
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

        # LibraryCloud typically returns a wrapper with "items" or "records".
        items = []
        if isinstance(parsed, dict):
            if isinstance(parsed.get("items"), list):
                items = parsed["items"]
            elif isinstance(parsed.get("records"), list):
                items = parsed["records"]

        if not items:
            return {"lc": [], "nlm": [], "other": []}

        item0 = items[0] if isinstance(items[0], dict) else {}

        # 1) Try extracting from obvious JSON keys
        json_candidates = self._find_json_call_number_candidates(item0)
        lc.extend(json_candidates[0])
        nlm.extend(json_candidates[1])
        other.extend(json_candidates[2])

        # 2) Try extracting from embedded MODS XML if present
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
        }

        def walk(x: Any) -> None:
            if isinstance(x, dict):
                for k, v in x.items():
                    if isinstance(k, str) and k in keys_of_interest:
                        self._bucket_candidate(str(v), lc, nlm, other)
                    walk(v)
            elif isinstance(x, list):
                for it in x:
                    walk(it)

        walk(obj)
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
