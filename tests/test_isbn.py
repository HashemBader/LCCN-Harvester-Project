"""
Module: test_isbn.py
Part of the LCCN Harvester Project.
"""
from pathlib import Path

from src.harvester.run_harvest import run_harvest


def test_run_harvest_dry_run_counts(tmp_path: Path):
    tsv = tmp_path / "isbns.tsv"
    tsv.write_text("isbn\n9780132350884\n0000000000\n", encoding="utf-8")

    summary = run_harvest(tsv, dry_run=True, db_path=tmp_path / "db.sqlite3", retry_days=7)

    assert summary.total_isbns == 2
    # In dry-run we should never write failures
    assert summary.failures == 0
    assert summary.successes == 0


def test_run_harvest_non_dry_run_writes_attempted(tmp_path: Path):
    tsv = tmp_path / "isbns.tsv"
    tsv.write_text("isbn\n1234567890\n", encoding="utf-8")

    summary = run_harvest(tsv, dry_run=False, db_path=tmp_path / "db.sqlite3", retry_days=7)

    # Sprint 2 placeholder: records attempted failure
    assert summary.total_isbns == 1
    assert summary.attempted == 1
    assert summary.failures == 1
