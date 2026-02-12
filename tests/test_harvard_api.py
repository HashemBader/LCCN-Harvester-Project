from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from api.harvard_api import HarvardApiClient


def test_harvard_extracts_lccn_from_items_mods_identifier() -> None:
    client = HarvardApiClient()
    payload = {
        "pagination": {"numFound": 1},
        "items": {
            "mods": [
                {
                    "identifier": [
                        {"@type": "isbn", "#text": "9780451524935"},
                        {"@type": "lccn", "#text": "2017056545"},
                    ]
                }
            ]
        },
    }

    result = client.extract_call_numbers("9780451524935", payload)
    assert result.status == "success"
    assert result.lccn == "2017056545"


def test_harvard_extracts_classification_with_authority_lcc() -> None:
    client = HarvardApiClient()
    payload = {
        "pagination": {"numFound": "1"},
        "items": {
            "mods": [
                {
                    "classification": [
                        {"@authority": "lcc", "#text": "PS3562.E353 T6 2002"}
                    ]
                }
            ]
        },
    }

    result = client.extract_call_numbers("0060935464", payload)
    assert result.status == "success"
    assert result.lccn == "PS3562.E353 T6 2002"


def test_harvard_items_mods_shape_detected_as_records() -> None:
    client = HarvardApiClient()
    payload = {"pagination": {"numFound": 1}, "items": {"mods": [{}]}}
    assert client._has_records(payload) is True


def test_harvard_build_fallback_uses_keyword_query() -> None:
    client = HarvardApiClient()
    url = client.build_fallback_url("9780451524935")
    assert "q=9780451524935" in url
    assert "identifier%3A" not in url
