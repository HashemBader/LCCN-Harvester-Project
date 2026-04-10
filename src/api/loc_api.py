"""
loc_api.py

Library of Congress (LoC) SRU API client.

Implements ISBN search against LoC's bibliographic SRU service and extracts
call numbers from MARCXML fields 050 (LCC) and 060 (NLM).

Protocol overview
-----------------
The LoC exposes a Z39.50-derived Search/Retrieve via URL (SRU) service at
``lx2.loc.gov:210/LCDB``.  Queries use CQL (Contextual Query Language):
  - ``bath.isbn={isbn}`` searches the standard bath profile ISBN index.
  - ``recordSchema=marcxml`` requests MARCXML output (the default for LoC).
  - ``maximumRecords=1`` limits results to the single best match.

The MARCXML response is an SRW envelope (``zs:`` namespace) wrapping one or
more ``marc:record`` elements.  Call numbers live in:
  - MARC 050 $a/$b — Library of Congress Classification (LCC)
  - MARC 060 $a/$b — National Library of Medicine Classification (NLM/MeSH)

Extraction is delegated to :mod:`src.utils.marc_parser` and validation to
:mod:`src.utils.call_number_validators`.
"""

from __future__ import annotations

import urllib.parse
import urllib.request
from typing import Any, Optional
import xml.etree.ElementTree as ET

from src.api.base_api import ApiResult, BaseApiClient
from src.api.http_utils import urlopen_with_ca
from src.utils.call_number_validators import validate_lccn, validate_nlmcn
from src.utils import marc_parser


class LocApiClient(BaseApiClient):
    """
    Library of Congress SRU API client.

    Sends CQL ISBN queries to LoC's SRU endpoint and parses the MARCXML
    response to extract LC (050) and NLM (060) call numbers.

    Attributes
    ----------
    source_name : str
        Stable identifier returned by the ``source`` property; used as the
        ``source`` field in every :class:`~src.api.base_api.ApiResult`.
    base_url : str
        Root URL of the LoC SRU database endpoint.
    namespaces : dict
        XML namespace prefixes required to parse the SRW envelope (``zs:``)
        and the embedded MARCXML records (``marc:``).
    """

    source_name = "loc"
    # LoC SRU endpoint — port 210 is the standard Z39.50/SRU port.
    base_url = "http://lx2.loc.gov:210/LCDB"
    namespaces = {
        # SRW (Search/Retrieve Web service) envelope namespace
        "zs": "http://www.loc.gov/zing/srw/",
        # MARC 21 XML (MARCXML) namespace for bibliographic record data
        "marc": "http://www.loc.gov/MARC21/slim",
    }

    @property
    def source(self) -> str:
        return self.source_name

    def build_url(self, isbn: str) -> str:
        """
        Build the LoC SRU query URL for an ISBN.
        Query syntax: bath.isbn={isbn}
        """
        params = {
            "operation": "searchRetrieve",
            "version": "1.1",
            "query": f"bath.isbn={isbn}",
            "recordSchema": "marcxml",
            "maximumRecords": "1",
        }
        return f"{self.base_url}?{urllib.parse.urlencode(params)}"

    def fetch(self, isbn: str) -> Any:
        """
        Fetch the MARCXML SRU response for an ISBN from the LoC endpoint.

        Parameters
        ----------
        isbn : str
            Normalized ISBN string (no hyphens).

        Returns
        -------
        xml.etree.ElementTree.Element
            Parsed root element of the SRW response envelope.

        Raises
        ------
        Exception
            On non-200 HTTP status or unparseable XML.
        """
        url = self.build_url(isbn)
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X)")
        req.add_header("Accept", "application/xml,text/xml,*/*")

        with urlopen_with_ca(req, timeout=self.timeout_seconds) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")
            xml_bytes = resp.read()

        try:
            return ET.fromstring(xml_bytes)
        except Exception as e:
            raise Exception(f"Invalid LoC SRU XML response: {e}")

    def extract_call_numbers(self, isbn: str, payload: Any) -> ApiResult:
        """
        Extract call numbers from a parsed LoC SRU MARCXML response.

        Walks the SRW envelope to find the ``zs:numberOfRecords`` element,
        then locates the first ``marc:record`` element and delegates field
        extraction to :mod:`src.utils.marc_parser`.

        Parameters
        ----------
        isbn : str
            Normalized ISBN string used as the search key.
        payload : xml.etree.ElementTree.Element
            Parsed SRW envelope element returned by :meth:`fetch`.

        Returns
        -------
        ApiResult
            - ``status="success"`` if at least one call number was found and
              validated.
            - ``status="not_found"`` if the LoC record count is 0, the MARC
              record element is absent, or no valid call number could be
              extracted.
            - ``status="error"`` if the payload is not an XML element (i.e.,
              ``fetch`` returned something unexpected).
        """
        if not isinstance(payload, ET.Element):
            return ApiResult(
                isbn=isbn,
                source=self.source,
                status="error",
                error_message="Unexpected LoC payload format",
            )

        # zs:numberOfRecords is the SRW standard element that reports how many
        # bibliographic records matched the query.
        records_count_text = payload.findtext("zs:numberOfRecords", default="0", namespaces=self.namespaces)
        try:
            records_count = int((records_count_text or "0").strip())
        except ValueError:
            records_count = 0

        if records_count <= 0:
            return ApiResult(
                isbn=isbn,
                source=self.source,
                status="not_found",
            )

        # Descend into the SRW response envelope to find the first MARCXML record.
        marc_record = payload.find(".//marc:record", self.namespaces)
        if marc_record is None:
            return ApiResult(
                isbn=isbn,
                source=self.source,
                status="not_found",
                error_message="LoC record found but MARC payload missing",
            )

        # Delegate subfield extraction + normalization to the shared MARC parser.
        lccn, nlmcn = marc_parser.extract_call_numbers_from_xml(marc_record, self.namespaces)
        # dict.fromkeys preserves insertion order while deduplicating ISBNs.
        isbns = list(dict.fromkeys(marc_parser.extract_isbns_from_xml(marc_record, self.namespaces)))

        # Validate extracted call numbers against format rules before storing.
        lccn = validate_lccn(lccn, source=self.source)
        nlmcn = validate_nlmcn(nlmcn, source=self.source)

        if lccn or nlmcn:
            return ApiResult(
                isbn=isbn,
                source=self.source,
                status="success",
                lccn=lccn,
                nlmcn=nlmcn,
                raw={"numberOfRecords": records_count},
                isbns=isbns,
            )

        return ApiResult(
            isbn=isbn,
            source=self.source,
            status="not_found",
            error_message="Record found but no usable call number",
            raw={"numberOfRecords": records_count},
            isbns=isbns,
        )
