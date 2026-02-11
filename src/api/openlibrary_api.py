"""
openlibrary_api.py

OpenLibrary API client.

Performs ISBN-based lookup using OpenLibrary's Books API and extracts
best-effort identifiers/classifications (e.g., LCCN identifiers and LC
classification strings when present).

Sprint 3 Task 4: Implement OpenLibrary API.
"""

from __future__ import annotations

import json
import urllib.error
from typing import Any, Optional

from api.base_api import ApiResult, BaseApiClient
from api.http_utils import urlopen_with_ca


class OpenLibraryApiClient(BaseApiClient):
    """
    Open Library API client.
    Uses the Books API: https://openlibrary.org/isbn/{isbn}.json
    """

    source_name = "openlibrary"
    base_url = "https://openlibrary.org/isbn"

    @property
    def source(self) -> str:
        return self.source_name

    def fetch(self, isbn: str) -> Any:
        url = f"{self.base_url}/{isbn}.json"
        
        import urllib.request
        
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "LCCNHarvester/0.1 (edu)")
        
        try:
            with urlopen_with_ca(req, timeout=self.timeout_seconds) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}")
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None # distinct from network error
            raise e

    def extract_call_numbers(self, isbn: str, payload: Any) -> ApiResult:
        if payload is None:
             return ApiResult(
                isbn=isbn,
                source=self.source,
                status="not_found"
            )

        lccn: Optional[str] = None
        nlmcn: Optional[str] = None

        # Most common field: lc_classifications (actual call numbers like "QA76.73.J38")
        lccs = payload.get("lc_classifications", [])
        if isinstance(lccs, list) and lccs:
            lccn = str(lccs[0]).strip() or None

        # Alternate shape used in some OL payloads.
        if not lccn and isinstance(payload.get("classifications"), dict):
            alt = payload["classifications"].get("lc_classifications", [])
            if isinstance(alt, list) and alt:
                lccn = str(alt[0]).strip() or None

        # Check top-level lccn field (LCCN identifier, e.g., "2001016794")
        if not lccn:
            top_level_lccn = payload.get("lccn", [])
            if isinstance(top_level_lccn, list) and top_level_lccn:
                lccn = str(top_level_lccn[0]).strip() or None

        # Fallback: identifiers.lccn (not shelf call number, but better than empty).
        identifiers = payload.get("identifiers", {})
        if not lccn and isinstance(identifiers, dict):
            lccn_values = identifiers.get("lccn", [])
            if isinstance(lccn_values, list) and lccn_values:
                lccn = str(lccn_values[0]).strip() or None
        
        if lccn or nlmcn:
             return ApiResult(
                isbn=isbn,
                source=self.source,
                status="success",
                lccn=lccn,
                nlmcn=nlmcn,
                raw=payload
            )
            
        return ApiResult(
            isbn=isbn,
            source=self.source,
            status="not_found" # if no call number, effectively not found for our purpose
        )
