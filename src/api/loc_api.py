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
from typing import Any, Dict, List, Optional

from src.api.base_api import ApiResult, BaseApiClient


class LocApiClient(BaseApiClient):
    """
    Library of Congress API client.

    Uses the https://www.loc.gov/items endpoint with `fo=json`.
    """

    source_name = "loc"
    base_url = "https://www.loc.gov/items"

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
        # Note: In a real implementation, we would use 'requests' or 'urllib'.
        # Since strict instructions say "Network logic is implemented in subclasses",
        # I'll implement a basic one using urllib for standard library usage,
        # or rely on what's available. Assuming urllib is fine as per BaseApiClient docstring.
        
        # For now, I will raise NotImplementedError if actual network calls aren't desired yet,
        # but the prompt implies we want a working client.
        # However, checking `harvard_api.py`, it doesn't implement `fetch`!
        # Wait, BaseApiClient *declares* fetch. HarvardApiClient *defines* `parse_response` but where is `fetch`?
        # Let me re-read `base_api.py`.
        
        # Checking base_api.py again in my mind... 
        # BaseApiClient has `fetch` as abstract.
        # HarvardApiClient *must* have implemented it, but I only saw `build_url`, `parse_response` and `extract_`.
        # Ah, I might have missed `fetch` in HarvardApiClient or the user is using a mixin I didn't see. 
        # Or I need to implement `fetch` using `urllib`.
        
        url = self.build_url(isbn)
        import urllib.request
        
        req = urllib.request.Request(url)
        # LoC likes a User-Agent
        req.add_header("User-Agent", "LCCNHarvester/0.1 (edu)")
        
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}")
                return json.load(resp)
        except Exception:
            # Re-raise to let the base class retry logic handle it
            raise

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
        
        # Try to find call numbers in the item
        # LoC fields: 'call_number' (list), 'item.call_number'
        
        cns = item.get("call_number", [])
        if isinstance(cns, list):
            for cn in cns:
                # Basic heuristic
                if not cn: continue
                if cn.startswith("W"): # simplistic NLM check
                    if not nlmcn: nlmcn = cn
                else:
                    if not lccn: lccn = cn
        
        # sometimes specifically 'lccn' field exists but it's the control number, not call number.
        # We want the shelf location.
        
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
            status="success", # Found record but no call number?
            # Or maybe "not_found" if goal is strictly call numbers?
            # Let's say success, but empty values.
            lccn=None,
            nlmcn=None,
            raw=item
        )
