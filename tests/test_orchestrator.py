"""
Module: test_orchestrator.py
Tests for HarvestOrchestrator, focusing on _process_isbn_internal return types.
"""
from pathlib import Path
from src.harvester.orchestrator import HarvestOrchestrator, ProcessOutcome, TargetResult
from src.database import DatabaseManager, MainRecord


class MockTarget:
    def __init__(self, name: str, result: TargetResult):
        self.name = name
        self.result = result

    def lookup(self, isbn: str) -> TargetResult:
        return self.result


def test_process_isbn_internal_returns_process_outcome_in_all_branches(tmp_path: Path):
    db_path = tmp_path / "test.sqlite3"
    db = DatabaseManager(db_path)
    db.init_db()

    # Test cached branch
    rec = MainRecord(isbn="1234567890", lccn="QA123", source="Test")
    db.upsert_main(rec)

    orchestrator = HarvestOrchestrator(db, targets=[], call_number_mode="lccn", stop_rule="stop_either")
    pending_main = []
    pending_attempted = []

    outcome = orchestrator._process_isbn_internal(
        "1234567890",
        dry_run=False,
        pending_main=pending_main,
        pending_attempted=pending_attempted
    )
    assert isinstance(outcome, ProcessOutcome)
    assert outcome.status == "cached"

    # Test that process_isbn can consume it
    status = orchestrator.process_isbn(
        "1234567890",
        dry_run=False,
        pending_main=pending_main,
        pending_attempted=pending_attempted
    )
    assert status == "cached"

    # Test success branch
    success_target = MockTarget("SuccessTarget", TargetResult(success=True, lccn="QA456"))
    orchestrator_success = HarvestOrchestrator(db, targets=[success_target], call_number_mode="lccn", stop_rule="stop_either")

    outcome = orchestrator_success._process_isbn_internal(
        "0987654321",
        dry_run=False,
        pending_main=[],
        pending_attempted=[]
    )
    assert isinstance(outcome, ProcessOutcome)
    assert outcome.status == "success"

    status = orchestrator_success.process_isbn(
        "0987654321",
        dry_run=False,
        pending_main=[],
        pending_attempted=[]
    )
    assert status == "success"

    # Test skip_retry branch
    # To trigger skip_retry, need targets that are skipped due to retry
    # First, insert attempted rows to make it skip
    db.upsert_attempted(isbn="1111111111", last_target="SkipTarget", attempt_type="lccn", last_error="test error")
    skip_target = MockTarget("SkipTarget", TargetResult(success=False, error="not found"))
    orchestrator_skip = HarvestOrchestrator(db, targets=[skip_target], call_number_mode="lccn", stop_rule="stop_either", retry_days=1)

    outcome = orchestrator_skip._process_isbn_internal(
        "1111111111",
        dry_run=False,
        pending_main=[],
        pending_attempted=[]
    )
    assert isinstance(outcome, ProcessOutcome)
    assert outcome.status == "skip_retry"

    status = orchestrator_skip.process_isbn(
        "1111111111",
        dry_run=False,
        pending_main=[],
        pending_attempted=[]
    )
    assert status == "skip_retry"

    # Test failed branch
    fail_target = MockTarget("FailTarget", TargetResult(success=False, error="not found"))
    orchestrator_fail = HarvestOrchestrator(db, targets=[fail_target], call_number_mode="lccn", stop_rule="stop_either")

    outcome = orchestrator_fail._process_isbn_internal(
        "2222222222",
        dry_run=False,
        pending_main=[],
        pending_attempted=[]
    )
    assert isinstance(outcome, ProcessOutcome)
    assert outcome.status == "failed"

    status = orchestrator_fail.process_isbn(
        "2222222222",
        dry_run=False,
        pending_main=[],
        pending_attempted=[]
    )
    assert status == "failed"


def test_cross_target_accumulation_lccn_from_a_nlmcn_from_b(tmp_path: Path):
    db_path = tmp_path / "test.sqlite3"
    db = DatabaseManager(db_path)
    db.init_db()

    # Target A returns only LCCN
    target_a = MockTarget("TargetA", TargetResult(success=True, lccn="QA123"))
    # Target B returns only NLM
    target_b = MockTarget("TargetB", TargetResult(success=True, nlmcn="1234567"))

    orchestrator = HarvestOrchestrator(
        db,
        targets=[target_a, target_b],
        call_number_mode="both",
        stop_rule="continue_both"
    )

    outcome = orchestrator._process_isbn_internal(
        "3333333333",
        dry_run=False,
        pending_main=[],
        pending_attempted=[]
    )

    assert isinstance(outcome, ProcessOutcome)
    assert outcome.status == "success"
    assert outcome.record is not None
    assert outcome.record.lccn == "QA123"
    assert outcome.record.nlmcn == "1234567"
    assert outcome.attempted_rows == ()  # No failures recorded


def test_lccn_nlmcn_sources_stored_separately(tmp_path: Path):
    db_path = tmp_path / "test.sqlite3"
    db = DatabaseManager(db_path)
    db.init_db()

    # Target A returns only LCCN with source "SourceA"
    target_a = MockTarget("TargetA", TargetResult(success=True, lccn="QA123", source="SourceA"))
    # Target B returns only NLM with source "SourceB"
    target_b = MockTarget("TargetB", TargetResult(success=True, nlmcn="1234567", source="SourceB"))

    orchestrator = HarvestOrchestrator(
        db,
        targets=[target_a, target_b],
        call_number_mode="both",
        stop_rule="continue_both"
    )

    outcome = orchestrator._process_isbn_internal(
        "4444444444",
        dry_run=False,
        pending_main=[],
        pending_attempted=[]
    )

    assert isinstance(outcome, ProcessOutcome)
    assert outcome.status == "success"
    assert outcome.record is not None
    assert outcome.record.lccn == "QA123"
    assert outcome.record.nlmcn == "1234567"
    assert outcome.record.lccn_source == "SourceA"
    assert outcome.record.nlmcn_source == "SourceB"

    # Test single-source run
    single_target = MockTarget("SingleTarget", TargetResult(success=True, lccn="QA789", nlmcn="9876543", source="SingleSource"))
    orchestrator_single = HarvestOrchestrator(
        db,
        targets=[single_target],
        call_number_mode="both",
        stop_rule="continue_both"
    )

    outcome_single = orchestrator_single._process_isbn_internal(
        "5555555555",
        dry_run=False,
        pending_main=[],
        pending_attempted=[]
    )

    assert isinstance(outcome_single, ProcessOutcome)
    assert outcome_single.status == "success"
    assert outcome_single.record is not None
    assert outcome_single.record.lccn == "QA789"
    assert outcome_single.record.nlmcn == "9876543"
    assert outcome_single.record.lccn_source == "SingleSource"
    assert outcome_single.record.nlmcn_source == "SingleSource"

    
