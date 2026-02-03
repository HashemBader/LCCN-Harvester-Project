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


class LocApiClient(BaseApiClient):
    """
    LoC API client for ISBN-based lookup.

    Notes
    -----
    - Uses the LoC JSON endpoint under /books/ with q=isbn:<ISBN>&fo=json.
    - Extraction is best-effort because LoC fields vary by record.
    - MARC parsing/normalization should be handled by dedicated parsing modules
      later; this client focuses on fetching and shallow extraction.
    """

    BASE_URL = "https://www.loc.gov/books/"

    @property
    def source(self) -> str:
        return "loc"

    def fetch(self, isbn: str) -> Any:
        """
        Fetch LoC search results JSON for a given ISBN.

        Parameters
        ----------
        isbn : str
            Normalized ISBN string.

        Returns
        -------
        Any
            Parsed JSON object (dict) returned by LoC.

        Raises
        ------
        Exception
            If the HTTP request fails or JSON cannot be parsed.
        """
        clean_isbn = self._normalize_isbn(isbn)
        query = f"isbn:{clean_isbn}"

        params = {
            "q": query,
            "fo": "json",
        }
        url = f"{self.BASE_URL}?{urllib.parse.urlencode(params)}"

        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                # Some services behave better when User-Agent is explicit
                "User-Agent": "LCCN-Harvester/1.0 (course project)",
            },
            method="GET",
        )

        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
            status_code = getattr(resp, "status", 200)
            if status_code != 200:
                raise RuntimeError(f"LoC HTTP {status_code}")

            raw_bytes = resp.read()

        try:
            return json.loads(raw_bytes.decode("utf-8"))
        except Exception as e:
            raise RuntimeError(f"Failed to parse LoC JSON: {e}") from e

    def extract_call_numbers(self, isbn: str, payload: Any) -> ApiResult:
        """
        Extract useful fields from the LoC JSON response.

        Parameters
        ----------
        isbn : str
            Normalized ISBN string.
        payload : Any
            Parsed JSON dict returned by fetch().

        Returns
        -------
        ApiResult
            Standardized result.
        """
        if not isinstance(payload, dict):
            return ApiResult(
                isbn=isbn,
                source=self.source,
                status="error",
                raw=payload,
                error_message="LoC payload is not a JSON object",
            )

        results = payload.get("results")
        if not isinstance(results, list) or len(results) == 0:
            return ApiResult(
                isbn=isbn,
                source=self.source,
                status="not_found",
                raw=payload,
            )

        # Pick "best" result. For now: first item.
        # Later you can improve ranking using fields like "date", "title", etc.
        item = results[0] if isinstance(results[0], dict) else None
        if item is None:
            return ApiResult(
                isbn=isbn,
                source=self.source,
                status="not_found",
                raw=payload,
            )

        lccn = self._extract_lccn(item)
        loc_call_number = self._extract_loc_call_number(item)

        # If we extracted anything useful -> success, else not_found
        if lccn or loc_call_number:
            return ApiResult(
                isbn=isbn,
                source=self.source,
                status="success",
                lccn=loc_call_number,  # store LoC call number in lccn field (per our current ApiResult)
                nlmcn=None,
                raw=item,
                error_message=None,
            )

        return ApiResult(
            isbn=isbn,
            source=self.source,
            status="not_found",
            raw=item,
        )

    @staticmethod
    def _normalize_isbn(raw: str) -> str:
        """
        Normalize ISBN input into a clean string.

        - Strip whitespace
        - Remove hyphens/spaces
        - Keep as text (never int)
        """
        return raw.strip().replace("-", "").replace(" ", "")

    @staticmethod
    def _extract_lccn(item: dict) -> Optional[str]:
        """
        Extract LCCN from a LoC result item if present.

        LoC sometimes provides "lccn" as a string or list. We normalize to string.
        """
        value = item.get("lccn")
        if isinstance(value, str) and value.strip():
            return value.strip()

        if isinstance(value, list):
            for v in value:
                if isinstance(v, str) and v.strip():
                    return v.strip()

        return None

    @staticmethod
    def _extract_loc_call_number(item: dict) -> Optional[str]:
        """
        Extract a LoC call number if present.

        Depending on the record, this might appear under different keys.
        We try a few common possibilities.
        """
        for key in ("call_number", "call_numbers", "classification"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

            if isinstance(value, list):
                for v in value:
                    if isinstance(v, str) and v.strip():
                        return v.strip()

        return None
