"""
base_api.py

Defines a common base class and result model for all external API clients used by
the LCCN Harvester project (LoC, Harvard, OpenLibrary).

All API clients should inherit from BaseApiClient and return ApiResult objects so
the harvest orchestrator can treat clients uniformly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ApiResult:
    """
    Standardized output returned by any API client.

    Attributes
    ----------
    isbn : str
        The ISBN that was searched (normalized as a string).
    source : str
        Source identifier (e.g., "loc", "harvard", "openlibrary").
    status : str
        One of: "success", "not_found", "error".
    lccn : str | None
        Library of Congress call number (if found).
    nlmcn : str | None
        National Library of Medicine call number (if found).
    raw : Any | None
        Raw response or parsed payload for debugging / future use.
    error_message : str | None
        Error details when status == "error".
    """

    isbn: str
    source: str
    status: str
    lccn: Optional[str] = None
    nlmcn: Optional[str] = None
    raw: Optional[Any] = None
    error_message: Optional[str] = None


class BaseApiClient(ABC):
    """
    Abstract base class for all API clients.

    This class centralizes shared configuration such as timeouts and retry policy.
    Subclasses must implement fetch() and extract_call_numbers().

    Notes
    -----
    - Network logic is implemented in subclasses (requests/urllib/etc.).
    - Parsing should be kept lightweight here; deeper MARC parsing/normalization
      should be handled by dedicated modules to avoid duplication.
    """

    def __init__(self, timeout_seconds: int = 10, max_retries: int = 2) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    @property
    @abstractmethod
    def source(self) -> str:
        """
        Return a stable source identifier for this client (e.g., "loc").
        """
        raise NotImplementedError

    @abstractmethod
    def fetch(self, isbn: str) -> Any:
        """
        Fetch raw data for the given ISBN from the external service.

        Parameters
        ----------
        isbn : str
            Normalized ISBN string.

        Returns
        -------
        Any
            Raw response data (dict, str, bytes, etc.) depending on the API.

        Raises
        ------
        Exception
            For network errors, invalid responses, etc. Caller may retry.
        """
        raise NotImplementedError

    @abstractmethod
    def extract_call_numbers(self, isbn: str, payload: Any) -> ApiResult:
        """
        Extract call numbers from the API payload and return an ApiResult.

        Parameters
        ----------
        isbn : str
            Normalized ISBN string.
        payload : Any
            Data returned by fetch() (already decoded/parsed as needed).

        Returns
        -------
        ApiResult
            Standard result object including status and extracted call numbers.
        """
        raise NotImplementedError

    def search(self, isbn: str) -> ApiResult:
        """
        High-level search wrapper with basic retry behavior.

        Parameters
        ----------
        isbn : str
            Normalized ISBN string.

        Returns
        -------
        ApiResult
            ApiResult with status "success", "not_found", or "error".
        """
        last_error: Optional[str] = None

        for attempt in range(1, self.max_retries + 2):
            try:
                payload = self.fetch(isbn)
                result = self.extract_call_numbers(isbn, payload)
                # Ensure consistent source field
                result.source = self.source
                return result
            except Exception as e:
                last_error = str(e)
                # Retry on exceptions up to max_retries
                if attempt <= self.max_retries:
                    continue
                break

        return ApiResult(
            isbn=isbn,
            source=self.source,
            status="error",
            error_message=last_error or "unknown error",
        )
