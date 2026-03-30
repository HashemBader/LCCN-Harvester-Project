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

from src.api.base_api import ApiResult, BaseApiClient
from src.api.http_utils import urlopen_with_ca
from src.utils.call_number_validators import validate_lccn, validate_nlmcn
from src.utils.isbn_validator import normalize_isbn



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

    def _extract_isbns(self, payload: Any) -> list[str]:
        if not isinstance(payload, dict):
            return []

        def _collect_values(value: Any) -> list[str]:
            if isinstance(value, list):
                return [str(item).strip() for item in value if isinstance(item, str)]
            if isinstance(value, str):
                return [value.strip()]
            return []

        isbns: list[str] = []
        for key in ("isbn", "isbn_10", "isbn_13"):
            values = _collect_values(payload.get(key))
            for raw in values:
                normalized = normalize_isbn(raw)
                if normalized:
                    isbns.append(normalized)

        identifiers = payload.get("identifiers")
        if isinstance(identifiers, dict):
            for key in ("isbn", "isbn_10", "isbn_13"):
                values = _collect_values(identifiers.get(key))
                for raw in values:
                    normalized = normalize_isbn(raw)
                    if normalized:
                        isbns.append(normalized)

        return list(dict.fromkeys(isbns))

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

        # Note: OpenLibrary's top-level "lccn" field and identifiers.lccn are
        # LC control numbers (MARC 010, e.g. "2001016794"), NOT LC classification
        # call numbers (MARC 050).  We do not fall back to those.

        # Validate extracted call numbers
        lccn = validate_lccn(lccn, source=self.source)
        nlmcn = validate_nlmcn(nlmcn, source=self.source)

        isbns = self._extract_isbns(payload)

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
            
        return ApiResult(
            isbn=isbn,
            source=self.source,
            status="not_found", # if no call number, effectively not found for our purpose
            isbns=isbns,
        )
