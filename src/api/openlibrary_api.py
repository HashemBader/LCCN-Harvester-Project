"""
Module: openlibrary_api.py
Part of the LCCN Harvester Project.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from src.api.base_api import ApiResult, BaseApiClient


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
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
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

        # OpenLibrary fields:
        # 'lc_classifications' (list)
        # 'dewey_decimal_class' (list) - ignores
        # call_number is often missing or under 'identifiers'
        
        lccn: Optional[str] = None
        
        lccs = payload.get("lc_classifications", [])
        if lccs:
            lccn = lccs[0]
            
        # NLM? OL isn't great for NLM usually.
        
        if lccn:
             return ApiResult(
                isbn=isbn,
                source=self.source,
                status="success",
                lccn=lccn,
                raw=payload
            )
            
        return ApiResult(
            isbn=isbn,
            source=self.source,
            status="not_found" # if no call number, effectively not found for our purpose
        )
