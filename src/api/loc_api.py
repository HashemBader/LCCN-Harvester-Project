"""
loc_api.py

Library of Congress (LoC) SRU API client.

Implements ISBN search against LoC's bibliographic SRU service and extracts
call numbers from MARCXML fields 050 (LCC) and 060 (NLM).
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
    Library of Congress API client.

    Uses LoC SRU endpoint with MARCXML records.
    """

    source_name = "loc"
    base_url = "http://lx2.loc.gov:210/LCDB"
    namespaces = {
        "zs": "http://www.loc.gov/zing/srw/",
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
        Extract call numbers from LoC SRU MARCXML response using marc_parser.
        """
        if not isinstance(payload, ET.Element):
            return ApiResult(
                isbn=isbn,
                source=self.source,
                status="error",
                error_message="Unexpected LoC payload format",
            )

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

        marc_record = payload.find(".//marc:record", self.namespaces)
        if marc_record is None:
            return ApiResult(
                isbn=isbn,
                source=self.source,
                status="not_found",
                error_message="LoC record found but MARC payload missing",
            )

        # Use marc_parser to extract call numbers
        lccn, nlmcn = marc_parser.extract_call_numbers_from_xml(marc_record, self.namespaces)

        # Validate extracted call numbers
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
            )

        return ApiResult(
            isbn=isbn,
            source=self.source,
            status="not_found",
            error_message="Record found but no usable call number",
            raw={"numberOfRecords": records_count},
        )
