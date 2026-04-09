from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3

from src.database import DatabaseManager
from src.harvester.orchestrator import HarvestOrchestrator, ProcessOutcome, TargetResult
from src.harvester.run_harvest import run_harvest


class _LccnOnlyTarget:
    name = "TargetA"

    def lookup(self, isbn: str) -> TargetResult:
        return TargetResult(success=True, lccn="QA76.73", source="LoC-A")


class _NlmOnlyTarget:
    name = "TargetB"

    def lookup(self, isbn: str) -> TargetResult:
        return TargetResult(success=True, nlmcn="W1 1234", source="NLM-B")


class _NlmOnlyNoSourceTarget:
    name = "TargetB"

    def lookup(self, isbn: str) -> TargetResult:
        # Edge case: missing source should fall back to target name.
        return TargetResult(success=True, nlmcn="W1 9999", source=None)


def _write_single_isbn_input(path: Path, isbn: str = "9780132350884") -> None:
    path.write_text(f"isbn\n{isbn}\n", encoding="utf-8")


def test_full_run_cross_target_sources_dates_stop_rule_and_process_outcome(tmp_path: Path) -> None:
    input_tsv = tmp_path / "input.tsv"
    db_path = tmp_path / "harvest.sqlite3"
    isbn = "9780132350884"
    _write_single_isbn_input(input_tsv, isbn)

    events: list[tuple[str, dict]] = []

    summary = run_harvest(
        input_path=input_tsv,
        dry_run=False,
        db_path=db_path,
        targets=[_LccnOnlyTarget(), _NlmOnlyTarget()],
        call_number_mode="both",
        stop_rule="continue_both",
        both_stop_policy="both",
        progress_cb=lambda event, payload: events.append((event, payload)),
    )

    assert summary.total_isbns == 1
    assert summary.successes == 1
    assert summary.failures == 0
    assert summary.cached_hits == 0
    assert summary.skipped_recent_fail == 0

    # The stop-rule decision should be made once for this ISBN and produce one success event.
    assert len([event for event, _ in events if event == "success"]) == 1
    assert len([event for event, _ in events if event == "failed"]) == 0
    assert len([event for event, _ in events if event == "target_start"]) == 2

    db = DatabaseManager(db_path)
    record = db.get_main(isbn)
    assert record is not None
    assert record.lccn == "QA76.73"
    assert record.nlmcn == "W1 1234"
    assert record.lccn_source == "LoC-A"
    assert record.nlmcn_source == "NLM-B"
    assert record.source == "LoC-A + NLM-B"

    assert record.date_added is not None
    dt = datetime.fromisoformat(record.date_added)
    assert isinstance(dt.year, int) and 2000 <= dt.year <= 2100
    assert isinstance(dt.month, int) and 1 <= dt.month <= 12
    assert isinstance(dt.day, int) and 1 <= dt.day <= 31

    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT call_number_type, call_number, source
            FROM main
            WHERE isbn = ?
            ORDER BY call_number_type
            """,
            (isbn,),
        ).fetchall()
    assert rows == [("lccn", "QA76.73", "LoC-A"), ("nlmcn", "W1 1234", "NLM-B")]

    assert db.get_all_attempted_for(isbn) == []

    orch = HarvestOrchestrator(
        db=db,
        targets=[_LccnOnlyTarget(), _NlmOnlyTarget()],
        call_number_mode="both",
        stop_rule="continue_both",
        both_stop_policy="both",
        selected_sources={"LoC-A", "NLM-B"},
    )
    outcome = orch._process_isbn_internal(
        isbn,
        dry_run=True,
        pending_main=[],
        pending_attempted=[],
    )
    assert isinstance(outcome, ProcessOutcome)
    assert outcome.status == "cached"


def test_full_run_cross_target_missing_source_falls_back_to_target_name(tmp_path: Path) -> None:
    input_tsv = tmp_path / "input.tsv"
    db_path = tmp_path / "harvest.sqlite3"
    isbn = "9780132350884"
    _write_single_isbn_input(input_tsv, isbn)

    summary = run_harvest(
        input_path=input_tsv,
        dry_run=False,
        db_path=db_path,
        targets=[_LccnOnlyTarget(), _NlmOnlyNoSourceTarget()],
        call_number_mode="both",
        stop_rule="continue_both",
        both_stop_policy="both",
    )

    assert summary.successes == 1
    assert summary.failures == 0

    db = DatabaseManager(db_path)
    record = db.get_main(isbn)
    assert record is not None
    assert record.lccn_source == "LoC-A"
    assert record.nlmcn_source == "TargetB"
    assert record.source == "LoC-A + TargetB"

    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT call_number_type, source
            FROM main
            WHERE isbn = ?
            ORDER BY call_number_type
            """,
            (isbn,),
        ).fetchall()
    assert rows == [("lccn", "LoC-A"), ("nlmcn", "TargetB")]

    orch = HarvestOrchestrator(
        db=db,
        targets=[_LccnOnlyTarget(), _NlmOnlyNoSourceTarget()],
        call_number_mode="both",
        stop_rule="continue_both",
        both_stop_policy="both",
    )
    outcome = orch._process_isbn_internal(
        "0000000000000",
        dry_run=True,
        pending_main=[],
        pending_attempted=[],
    )
    assert isinstance(outcome, ProcessOutcome)
    assert outcome.status == "success"
    assert outcome.record is None
    assert outcome.attempted_rows == ()


