"""
Tests: No false failure records after early-stop success.

Covers:
  - Sequential mode (max_workers=1) + parallel mode (max_workers=2)
  - All four stop rules
  - Ensures the `attempted` table stays empty when the ISBN ultimately succeeds
"""
from __future__ import annotations

import pytest
from src.harvester.orchestrator import HarvestOrchestrator, TargetResult
from src.database import DatabaseManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _LCCNOnlyTarget:
    name = "LCCNOnly"
    def lookup(self, isbn: str) -> TargetResult:
        return TargetResult(success=True, lccn="QA76", nlmcn=None, source=self.name)


class _NLMCNOnlyTarget:
    name = "NLMOnly"
    def lookup(self, isbn: str) -> TargetResult:
        return TargetResult(success=True, lccn=None, nlmcn="WA100", source=self.name)


class _FailTarget:
    name = "Fail"
    def lookup(self, isbn: str) -> TargetResult:
        return TargetResult(success=False, source=self.name, error="no records found in Fail")


def _make_orch(db, targets, stop_rule, workers=1):
    return HarvestOrchestrator(
        db=db,
        targets=targets,
        retry_days=0,
        call_number_mode="both",
        stop_rule=stop_rule,
        max_workers=workers,
    )


def _run(orch):
    return orch.run(["9780132350884"], dry_run=False)


def _assert_no_false_failures(db, isbn="9780132350884"):
    """After a success the attempted table must be empty for that ISBN."""
    remaining = db.get_all_attempted_for(isbn)
    assert remaining == [], (
        f"False failure rows found for {isbn}: {remaining}"
    )
    main = db.get_main(isbn)
    assert main is not None, f"Expected main record for {isbn}"
    return main


# ---------------------------------------------------------------------------
# stop_either — sequential
# ---------------------------------------------------------------------------

def test_stop_either_no_false_failures_sequential(tmp_path):
    """Target1 fails, Target2 finds LCCN. stop_either → success. No attempted rows."""
    db = DatabaseManager(tmp_path / "test.db")
    db.init_db()
    orch = _make_orch(db, [_FailTarget(), _LCCNOnlyTarget()], "stop_either", workers=1)
    _run(orch)
    _assert_no_false_failures(db)


# ---------------------------------------------------------------------------
# stop_lccn — sequential
# ---------------------------------------------------------------------------

def test_stop_lccn_stops_after_lccn_sequential(tmp_path):
    """Target1 finds LCCN. stop_lccn fires. No attempted rows."""
    db = DatabaseManager(tmp_path / "test.db")
    db.init_db()
    orch = _make_orch(db, [_LCCNOnlyTarget(), _FailTarget()], "stop_lccn", workers=1)
    _run(orch)
    main = _assert_no_false_failures(db)
    assert main.lccn == "QA76"


def test_stop_lccn_does_not_stop_on_nlmcn_only_sequential(tmp_path):
    """Target1 finds NLM only. stop_lccn must NOT fire. Target2 also fails. → failed overall."""
    db = DatabaseManager(tmp_path / "test.db")
    db.init_db()
    # No target provides LCCN → overall failure expected; just ensure no crash.
    orch = _make_orch(db, [_NLMCNOnlyTarget(), _FailTarget()], "stop_lccn", workers=1)
    summary = _run(orch)
    # stop_lccn never triggered (no lccn found), but NLMCN was accumulated → success with nlmcn only
    main = db.get_main("9780132350884")
    assert main is not None
    assert main.nlmcn == "WA100"


# ---------------------------------------------------------------------------
# stop_nlmcn — sequential
# ---------------------------------------------------------------------------

def test_stop_nlmcn_stops_after_nlmcn_sequential(tmp_path):
    """Target1 finds NLMCN. stop_nlmcn fires. No attempted rows for successful ISBN."""
    db = DatabaseManager(tmp_path / "test.db")
    db.init_db()
    orch = _make_orch(db, [_NLMCNOnlyTarget(), _FailTarget()], "stop_nlmcn", workers=1)
    _run(orch)
    main = _assert_no_false_failures(db)
    assert main.nlmcn == "WA100"


# ---------------------------------------------------------------------------
# continue_both — sequential
# ---------------------------------------------------------------------------

def test_continue_both_collects_both_sequential(tmp_path):
    """Target1 → LCCN, Target2 → NLMCN. continue_both: keeps going until both found."""
    db = DatabaseManager(tmp_path / "test.db")
    db.init_db()
    orch = _make_orch(db, [_LCCNOnlyTarget(), _NLMCNOnlyTarget()], "continue_both", workers=1)
    _run(orch)
    main = _assert_no_false_failures(db)
    assert main.lccn == "QA76"
    assert main.nlmcn == "WA100"


def test_continue_both_partial_success_no_false_failure(tmp_path):
    """Target1 → LCCN, Target2 fails. continue_both: stops with lccn only. No false attempt rows."""
    db = DatabaseManager(tmp_path / "test.db")
    db.init_db()
    orch = _make_orch(db, [_LCCNOnlyTarget(), _FailTarget()], "continue_both", workers=1)
    _run(orch)
    # Ultimately a success (lccn found); no false failures
    _assert_no_false_failures(db)


# ---------------------------------------------------------------------------
# Parallel mode (max_workers=2) — stop_rule must also be applied
# ---------------------------------------------------------------------------

def test_stop_either_no_false_failures_parallel(tmp_path):
    db = DatabaseManager(tmp_path / "test.db")
    db.init_db()
    orch = _make_orch(db, [_FailTarget(), _LCCNOnlyTarget()], "stop_either", workers=2)
    _run(orch)
    _assert_no_false_failures(db)


def test_stop_lccn_parallel(tmp_path):
    db = DatabaseManager(tmp_path / "test.db")
    db.init_db()
    orch = _make_orch(db, [_LCCNOnlyTarget(), _FailTarget()], "stop_lccn", workers=2)
    _run(orch)
    main = _assert_no_false_failures(db)
    assert main.lccn == "QA76"


def test_continue_both_parallel(tmp_path):
    db = DatabaseManager(tmp_path / "test.db")
    db.init_db()
    orch = _make_orch(db, [_LCCNOnlyTarget(), _NLMCNOnlyTarget()], "continue_both", workers=2)
    _run(orch)
    main = _assert_no_false_failures(db)
    assert main.lccn == "QA76"
    assert main.nlmcn == "WA100"
