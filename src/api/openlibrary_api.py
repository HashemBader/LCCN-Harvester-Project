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
import urllib.parse
import urllib.request
from typing import Any, Optional

from .base_api import ApiResult, BaseApiClient


class OpenLibraryApiClient(BaseApiClient):
    """
    OpenLibrary client for ISBN-based lookup.

    Uses the OpenLibrary Books API:
      https://openlibrary.org/api/books?bibkeys=ISBN:<isbn>&format=json&jscmd=data

    Notes
    -----
    - OpenLibrary does not always provide LoC/NLM call numbers.
    - We extract best-effort fields:
      - LCCN identifiers (if present)
      - LC classification strings (if present)
    """

    BASE_URL = "https://openlibrary.org/api/books"

    @property
    def source(self) -> str:
        return "openlibrary"

    def fetch(self, isbn: str) -> Any:
        """
        Fetch OpenLibrary Books API JSON for a given ISBN.

        Parameters
        ----------
        isbn : str
            Normalized ISBN string.

        Returns
        -------
        Any
            Parsed JSON object (dict).

        Raises
        ------
        Exception
            For network/HTTP errors or JSON parse errors.
        """
        clean_isbn = self._normalize_isbn(isbn)
        bibkey = f"ISBN:{clean_isbn}"

        params = {
            "bibkeys": bibkey,
            "format": "json",
            "jscmd": "data",
        }
        url = f"{self.BASE_URL}?{urllib.parse.urlencode(params)}"

        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "LCCN-Harvester/1.0 (course project)",
            },
            method="GET",
        )

        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
            status_code = getattr(resp, "status", 200)
            if status_code != 200:
                raise RuntimeError(f"OpenLibrary HTTP {status_code}")
            raw_bytes = resp.read()

        try:
            return json.loads(raw_bytes.decode("utf-8"))
        except Exception as e:
            raise RuntimeError(f"Failed to parse OpenLibrary JSON: {e}") from e

    def extract_call_numbers(self, isbn: str, payload: Any) -> ApiResult:
        """
        Extract best-effort identifiers/classification strings from OpenLibrary.

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
                error_message="OpenLibrary payload is not a JSON object",
            )

        clean_isbn = self._normalize_isbn(isbn)
        key = f"ISBN:{clean_isbn}"
        record = payload.get(key)

        if not isinstance(record, dict):
            return ApiResult(
                isbn=isbn,
                source=self.source,
                status="not_found",
                raw=payload,
            )

        # Best-effort extraction:
        # 1) LCCN identifiers (OpenLibrary often includes identifiers.lccn)
        lccn_identifier = self._extract_lccn_identifier(record)

        # 2) LC classification strings (sometimes classifications.lc_classifications)
        lc_classification = self._extract_lc_classification(record)

        # If we found anything useful -> success; else not_found
        if lccn_identifier or lc_classification:
            # NOTE: For now, ApiResult has only lccn/nlmcn fields.
            # We'll store LC classification (call-number-like) in lccn field if present,
            # otherwise store the LCCN identifier there. Raw keeps everything.
            chosen = lc_classification or lccn_identifier
            return ApiResult(
                isbn=isbn,
                source=self.source,
                status="success",
                lccn=chosen,
                nlmcn=None,
                raw=record,
            )

        return ApiResult(
            isbn=isbn,
            source=self.source,
            status="not_found",
            raw=record,
        )

    @staticmethod
    def _normalize_isbn(raw: str) -> str:
        return raw.strip().replace("-", "").replace(" ", "")

    @staticmethod
    def _extract_lccn_identifier(record: dict) -> Optional[str]:
        identifiers = record.get("identifiers")
        if not isinstance(identifiers, dict):
            return None

        lccn = identifiers.get("lccn")
        if isinstance(lccn, str) and lccn.strip():
            return lccn.strip()

        if isinstance(lccn, list):
            for v in lccn:
                if isinstance(v, str) and v.strip():
                    return v.strip()

        return None

    @staticmethod
    def _extract_lc_classification(record: dict) -> Optional[str]:
        classifications = record.get("classifications")
        if not isinstance(classifications, dict):
            return None

        lc = classifications.get("lc_classifications")
        if isinstance(lc, str) and lc.strip():
            return lc.strip()

        if isinstance(lc, list):
            for v in lc:
                if isinstance(v, str) and v.strip():
                    return v.strip()

        return None
