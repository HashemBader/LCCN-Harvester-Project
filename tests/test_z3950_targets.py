"""
Tests for src/harvester/z3950_targets.py

Covers:
- Z3950Target.lookup(): success path (real pymarc Record with 050)
- Z3950Target.lookup(): no records found → not_found
- Z3950Target.lookup(): record has no 050/060 → not_found
- Z3950Target.lookup(): Z3950Client import failure → error result
- build_default_z3950_targets(): reads from TSV file
- build_default_z3950_targets(): reads from JSON file
- build_default_z3950_targets(): skips deselected targets
- build_default_z3950_targets(): results are sorted by rank
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from pymarc import Field, Record, Subfield

from src.harvester.z3950_targets import Z3950Target, build_default_z3950_targets


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_target(**kw):
    defaults = dict(name="Test", host="z3950.test.org", port=210, database="testdb")
    return Z3950Target(**{**defaults, **kw})


def _field(tag: str, ind2: str, *pairs: tuple) -> Field:
    """Build a pymarc 5.x Field from (code, value) pairs."""
    return Field(
        tag=tag,
        indicators=[" ", ind2],
        subfields=[Subfield(code, val) for code, val in pairs],
    )


def _record_with_050(a: str, b: str, ind2: str = "0") -> Record:
    r = Record()
    r.add_field(_field("050", ind2, ("a", a), ("b", b)))
    return r


# ---------------------------------------------------------------------------
# Z3950Target.lookup()
# ---------------------------------------------------------------------------


def test_lookup_success_returns_lccn(tmp_path):
    """A record containing MARC 050 $a+$b is extracted and validated correctly."""
    record = _record_with_050("QA76.73", "P38")

    with patch("src.z3950.client.Z3950Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value.__enter__.return_value = mock_client
        mock_cls.return_value.__exit__.return_value = False
        mock_client.search_by_isbn.return_value = [record]

        target = _make_target()
        result = target.lookup("0131103628")

    assert result.success is True
    assert result.lccn == "QA76.73 P38"
    assert result.nlmcn is None
    assert result.source == "Test"


def test_lookup_success_four_digit_class():
    """4-digit LC class numbers (PS, HF, …) survive extraction + validation."""
    record = Record()
    record.add_field(_field("050", "0", ("a", "PS3562.E353"), ("b", "T6 2002")))

    with patch("src.z3950.client.Z3950Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value.__enter__.return_value = mock_client
        mock_cls.return_value.__exit__.return_value = False
        mock_client.search_by_isbn.return_value = [record]

        result = _make_target().lookup("0060935464")

    assert result.success is True
    assert result.lccn == "PS3562.E353 T6 2002"


def test_lookup_success_nlmcn_060():
    """A record with only MARC 060 (NLM call number) is returned correctly."""
    record = Record()
    record.add_field(_field("060", " ", ("a", "WG 120.5")))

    with patch("src.z3950.client.Z3950Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value.__enter__.return_value = mock_client
        mock_cls.return_value.__exit__.return_value = False
        mock_client.search_by_isbn.return_value = [record]

        result = _make_target().lookup("0000000000")

    assert result.success is True
    assert result.lccn is None
    assert result.nlmcn == "WG 120.5"


def test_lookup_prefers_lc_assigned_050():
    """When multiple 050 fields exist, the ind2='0' (LC-assigned) value is used."""
    record = Record()
    record.add_field(_field("050", "4", ("a", "PZ7.C6837"), ("b", "WrongCopy 1999")))
    record.add_field(_field("050", "0", ("a", "PZ7.C6837"), ("b", "LCCopy 2008")))

    with patch("src.z3950.client.Z3950Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value.__enter__.return_value = mock_client
        mock_cls.return_value.__exit__.return_value = False
        mock_client.search_by_isbn.return_value = [record]

        result = _make_target().lookup("0000000000")

    assert result.success is True
    assert result.lccn == "PZ7.C6837 LCCopy 2008"


def test_lookup_no_records_returns_not_found():
    with patch("src.z3950.client.Z3950Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value.__enter__.return_value = mock_client
        mock_cls.return_value.__exit__.return_value = False
        mock_client.search_by_isbn.return_value = []

        result = _make_target().lookup("0000000000")

    assert result.success is False
    assert "no records" in result.error.lower()


def test_lookup_record_without_050_060_returns_not_found():
    """A record that has no 050 or 060 field should return a not-found result."""
    record = Record()
    record.add_field(_field("020", " ", ("a", "0451524934")))

    with patch("src.z3950.client.Z3950Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value.__enter__.return_value = mock_client
        mock_cls.return_value.__exit__.return_value = False
        mock_client.search_by_isbn.return_value = [record]

        result = _make_target().lookup("0000000000")

    assert result.success is False
    assert "050/060" in result.error


def test_lookup_client_import_failure_returns_error():
    """When the Z3950Client cannot be imported, a clean error result is returned."""
    with patch.dict("sys.modules", {"src.z3950.client": None, "z3950.client": None}):
        result = _make_target().lookup("0000000000")

    assert result.success is False
    assert result.error


# ---------------------------------------------------------------------------
# build_default_z3950_targets()
# ---------------------------------------------------------------------------


def test_build_targets_from_tsv(tmp_path):
    tsv = (
        "name\ttarget_type\thost\tport\tdatabase\trecord_syntax\trank\tselected\n"
        "LOC\tz3950\tlcweb.loc.gov\t210\tNameAuthority\tUSMARC\t1\tTrue\n"
        "Harvard\tz3950\tz39.harvard.edu\t210\thollisMARCCW\tUSMARC\t2\tTrue\n"
    )
    tsv_path = tmp_path / "targets.tsv"
    tsv_path.write_text(tsv, encoding="utf-8")

    targets = build_default_z3950_targets(
        tsv_path=tsv_path,
        json_path=tmp_path / "nonexistent.json",
    )
    assert len(targets) == 2
    assert targets[0].name == "LOC"
    assert targets[0].host == "lcweb.loc.gov"
    assert targets[0].port == 210
    assert targets[1].name == "Harvard"


def test_build_targets_from_tsv_skips_deselected(tmp_path):
    tsv = (
        "name\ttarget_type\thost\tport\tdatabase\trecord_syntax\trank\tselected\n"
        "LOC\tz3950\tlcweb.loc.gov\t210\tNameAuthority\tUSMARC\t1\tTrue\n"
        "Harvard\tz3950\tz39.harvard.edu\t210\thollisMARCCW\tUSMARC\t2\tFalse\n"
    )
    tsv_path = tmp_path / "targets.tsv"
    tsv_path.write_text(tsv, encoding="utf-8")

    targets = build_default_z3950_targets(
        tsv_path=tsv_path,
        json_path=tmp_path / "nonexistent.json",
    )
    assert len(targets) == 1
    assert targets[0].name == "LOC"


def test_build_targets_from_json(tmp_path):
    data = [
        {
            "type": "z3950",
            "name": "Toronto",
            "host": "130.63.4.241",
            "port": 210,
            "database": "unicorn",
            "rank": 1,
            "selected": True,
        },
        {
            "type": "z3950",
            "name": "Oxford",
            "host": "library.ox.ac.uk",
            "port": 210,
            "database": "ADVANCE",
            "rank": 2,
            "selected": True,
        },
    ]
    json_path = tmp_path / "targets.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")

    targets = build_default_z3950_targets(
        tsv_path=tmp_path / "nonexistent.tsv",
        json_path=json_path,
    )
    assert len(targets) == 2
    assert targets[0].name == "Toronto"
    assert targets[0].host == "130.63.4.241"


def test_build_targets_sorted_by_rank(tmp_path):
    """Targets are always returned sorted by rank, regardless of file order."""
    data = [
        {"type": "z3950", "name": "C", "host": "c.test", "port": 210, "database": "db", "rank": 3, "selected": True},
        {"type": "z3950", "name": "A", "host": "a.test", "port": 210, "database": "db", "rank": 1, "selected": True},
        {"type": "z3950", "name": "B", "host": "b.test", "port": 210, "database": "db", "rank": 2, "selected": True},
    ]
    json_path = tmp_path / "targets.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")

    targets = build_default_z3950_targets(
        tsv_path=tmp_path / "nonexistent.tsv",
        json_path=json_path,
    )
    assert [t.name for t in targets] == ["A", "B", "C"]


def test_build_targets_json_skips_non_z3950(tmp_path):
    """API targets in the JSON file are ignored; only 'z3950' type is loaded."""
    data = [
        {"type": "z3950", "name": "LOC Z39.50", "host": "z.loc.gov", "port": 210, "database": "db", "rank": 1, "selected": True},
        {"type": "api", "name": "LOC API", "host": "api.loc.gov", "port": 80, "database": "", "rank": 2, "selected": True},
    ]
    json_path = tmp_path / "targets.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")

    targets = build_default_z3950_targets(
        tsv_path=tmp_path / "nonexistent.tsv",
        json_path=json_path,
    )
    assert len(targets) == 1
    assert targets[0].name == "LOC Z39.50"
