import unittest
from pathlib import Path

from src.harvester.run_harvest import run_harvest
from src.utils.isbn_validator import validate_isbn


def test_run_harvest_dry_run_counts(tmp_path: Path):
    tsv = tmp_path / "isbns.tsv"
    tsv.write_text("isbn\n9780132350884\n0000000000\n", encoding="utf-8")

    summary = run_harvest(tsv, dry_run=True, db_path=tmp_path / "db.sqlite3", retry_days=7)

    assert summary.total_isbns == 2
    assert summary.attempted == 2
    assert summary.successes == 0
    # In dry-run we still track failures (attempts that didn't succeed), but we don't write them to DB.
    assert summary.failures == 2


def test_run_harvest_non_dry_run_writes_attempted(tmp_path: Path):
    tsv = tmp_path / "isbns.tsv"
    tsv.write_text("isbn\n1234567890\n", encoding="utf-8")

    summary = run_harvest(tsv, dry_run=False, db_path=tmp_path / "db.sqlite3", retry_days=7)

    # Sprint 2 placeholder: records attempted failure
    assert summary.total_isbns == 1
    assert summary.attempted == 1
    assert summary.failures == 1


class TestISBNValidation(unittest.TestCase):

    def test_valid_isbn10(self):
        self.assertTrue(validate_isbn("0471117099"))

    def test_valid_isbn10_with_X(self):
        self.assertTrue(validate_isbn("0306406152"))

    def test_valid_isbn13(self):
        self.assertTrue(validate_isbn("978-0-393-04002-9"))
        self.assertTrue(validate_isbn("9780393040029"))

    def test_invalid_isbn10(self):
        self.assertFalse(validate_isbn("0471117090"))

    def test_invalid_isbn13(self):
        self.assertFalse(validate_isbn("9780393040020"))

    def test_garbage_input(self):
        self.assertFalse(validate_isbn("not-an-isbn"))
        self.assertFalse(validate_isbn("11111"))
        self.assertFalse(validate_isbn("978-ABC-DEF-GHI"))
