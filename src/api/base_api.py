"""
base_api.py

Defines a common base class and result model for all external API clients used by
the LCCN Harvester project (LoC, Harvard, OpenLibrary).

All API clients should inherit from BaseApiClient and return ApiResult objects so
the harvest orchestrator can treat clients uniformly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Optional


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

    # The ISBN identifier being searched for
    isbn: str
    # The name of the API source (e.g., "loc", "harvard")
    source: str
    # The outcome of the search: "success", "not_found", or "error"
    status: str
    # Library of Congress call number result (if retrieved)
    lccn: Optional[str] = None
    # National Library of Medicine call number result (if retrieved)
    nlmcn: Optional[str] = None
    # Raw API response data for debugging and future processing
    raw: Optional[Any] = None
    # Additional ISBNs found during the search (e.g., related editions)
    isbns: List[str] = field(default_factory=list)
    # Error message if the search failed or encountered an exception
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

    def __init__(self, timeout_seconds: int = 10, max_retries: int = 0) -> None:
        # Store the timeout duration for network requests
        self.timeout_seconds = timeout_seconds
        # Store the maximum number of retry attempts for failed requests
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
        # Track the last error message encountered during retries
        last_error: Optional[str] = None

        # Attempt fetching and parsing, with retries up to max_retries times
        for attempt in range(1, self.max_retries + 2):
            try:
                # Fetch raw data from the external API service
                payload = self.fetch(isbn)
                # Extract call numbers from the fetched payload
                result = self.extract_call_numbers(isbn, payload)
                # Set the source field to ensure consistency across all API clients
                result.source = self.source
                # Return successful result immediately
                return result
            except Exception as e:
                # Store the error message for later use if all retries fail
                last_error = str(e)
                # Continue retrying only if we haven't exhausted max_retries
                if attempt <= self.max_retries:
                    continue
                # Exit retry loop when max_retries is exhausted
                break

        # Return an error result when all retry attempts have failed
        return ApiResult(
            isbn=isbn,
            source=self.source,
            status="error",
            error_message=last_error or "unknown error",
        )
