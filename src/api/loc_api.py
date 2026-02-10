"""
loc_api.py

Library of Congress (LoC) JSON API client.

Implements ISBN search using the LoC JSON endpoint and extracts identifiers
(e.g., LCCN) and call number fields when available.

This module is part of Sprint 3 Task 2: Implement Library of Congress API.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Optional

from api.base_api import ApiResult, BaseApiClient
from api.http_utils import urlopen_with_ca


class LocApiClient(BaseApiClient):
    """
    Library of Congress API client.

    Uses the https://www.loc.gov/items endpoint with `fo=json`.
    """

    source_name = "loc"
    base_url = "https://www.loc.gov/items"
    fallback_url = "https://www.loc.gov/books/"

    @property
    def source(self) -> str:
        return self.source_name

    def build_url(self, isbn: str) -> str:
        """
        Build the LoC query URL for an ISBN.
        Query syntax: q=isbn:{isbn}
        """
        params = {
            "q": f"isbn:{isbn}",
            "fo": "json",
            "at": "results",
        }
        return f"{self.base_url}?{urllib.parse.urlencode(params)}"

    def fetch(self, isbn: str) -> Any:
        urls = [
            self.build_url(isbn),
            f"{self.fallback_url}?{urllib.parse.urlencode({'q': f'isbn:{isbn}', 'fo': 'json'})}",
        ]
        last_exc = None
        for url in urls:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X)")
            req.add_header("Accept", "application/json,text/plain,*/*")
            try:
                with urlopen_with_ca(req, timeout=self.timeout_seconds) as resp:
                    if resp.status != 200:
                        raise Exception(f"HTTP {resp.status}")
                    return json.load(resp)
            except Exception as e:
                last_exc = e
                continue
        raise last_exc if last_exc else Exception("LoC request failed")

    def _walk_for_candidates(self, obj: Any, out: list[str]) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = str(k).lower()
                if key in {
                    "call_number",
                    "callnumber",
                    "classification",
                    "shelflocator",
                    "number_lccn",
                    "lccn",
                    "identifier-lccn",
                }:
                    if isinstance(v, list):
                        for item in v:
                            if isinstance(item, str) and item.strip():
                                out.append(item.strip())
                    elif isinstance(v, str) and v.strip():
                        out.append(v.strip())
                self._walk_for_candidates(v, out)
        elif isinstance(obj, list):
            for item in obj:
                self._walk_for_candidates(item, out)

    def extract_call_numbers(self, isbn: str, payload: Any) -> ApiResult:
        """
        Extract call numbers from LoC JSON response.
        """
        lccn: Optional[str] = None
        nlmcn: Optional[str] = None
        
        # LoC results are usually in a 'results' list
        results = payload.get("results", [])
        if not results:
             return ApiResult(
                isbn=isbn,
                source=self.source,
                status="not_found"
            )

        item = results[0]
        candidates: list[str] = []
        self._walk_for_candidates(item, candidates)
        for cn in candidates:
            if cn.startswith("W"):
                if not nlmcn:
                    nlmcn = cn
            elif not lccn:
                lccn = cn
        
        if lccn or nlmcn:
            return ApiResult(
                isbn=isbn,
                source=self.source,
                status="success",
                lccn=lccn,
                nlmcn=nlmcn,
                raw=item
            )
        
        return ApiResult(
            isbn=isbn,
            source=self.source,
            status="not_found",
            error_message="Record found but no usable call number",
            raw=item
        )
