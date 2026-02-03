"""
harvester_cli.py

Command-line entry point for the LCCN Harvester.

Sprint 3+:
- Accepts a required --input argument pointing to a TSV file of ISBNs.
- Validates that the file exists and is a regular file.
- Initializes the SQLite database (creates tables via schema.sql if needed).
- Previews parsed ISBNs using the SAME reader as the pipeline.
- Calls run_harvest(input_path, dry_run) and prints a summary.
"""

import argparse
import sys
from pathlib import Path

from src.database import DatabaseManager
from src.harvester.run_harvest import run_harvest, read_isbns_from_tsv
from utils import isbn_validator

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="lccn-harvester",
        description=(
            "Command-line interface for the LCCN Harvester.\n"
            "Accepts a TSV file of ISBNs and runs the harvest pipeline."
        ),
    )

    parser.add_argument(
        "--input",
        "-i",
        dest="input_file",
        required=True,
        help="Path to the TSV file containing ISBNs.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Dry-run mode (no DB writes).",
    )

    return parser.parse_args(argv)


def validate_input_file(path_str: str) -> Path:
    path = Path(path_str).expanduser().resolve()

    if not path.exists():
        print(f"ERROR: Input file does not exist: {path}", file=sys.stderr)
        sys.exit(1)

    if not path.is_file():
        print(f"ERROR: Input path is not a file: {path}", file=sys.stderr)
        sys.exit(1)

    return path


def init_database_or_exit() -> DatabaseManager:
    try:
        db = DatabaseManager()  # default: data/lccn_harvester.sqlite3
        db.init_db()
        return db
    except Exception as e:
        print(f"ERROR: Failed to initialize database: {e}", file=sys.stderr)
        sys.exit(1)


# def normalize_isbn(raw: str) -> str:
#     """
#     Normalize ISBN input into a clean string.
#
#     Rules:
#     - Strip leading/trailing whitespace
#     - Remove hyphens and spaces
#     - Keep as text (never convert to int)
#     """
#     return raw.strip().replace("-", "").replace(" ", "")


def read_isbns_from_tsv(input_path: Path) -> List[str]:
    """
    Read ISBN values from a TSV file.

    Expected format:
    - Tab-separated values (TSV)
    - ISBN is assumed to be in the first column
    - Header row is allowed (will be skipped if detected)
    - Blank lines are ignored

    Parameters
    ----------
    input_path : Path
        Path to input TSV file.

    Returns
    -------
    list[str]
        A list of normalized ISBN strings (may include invalid ISBNs for now).
    """
    isbns: List[str] = []

    # utf-8-sig handles BOM that sometimes appears in exported TSV files
    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t")

        for row_index, row in enumerate(reader, start=1):
            if not row:
                continue  # empty line

            first_cell = row[0].strip()
            if not first_cell:
                continue  # blank first column

            # Skip a header row if the first column looks like "ISBN"
            if row_index == 1 and first_cell.lower() in {"isbn", "isbns", "isbn13", "isbn10"}:
                continue

            isbn = isbn_validator.normalize_isbn(first_cell)
            if isbn_validator.validate_isbn(isbn):
                isbns.append(isbn)

    return isbns


def main(argv=None) -> int:
    args = parse_args(argv)
    input_path = validate_input_file(args.input_file)

    db = None
    try:
        db = init_database_or_exit()

        # Preview ISBNs using the same function as the pipeline
        isbns = read_isbns_from_tsv(input_path)

        print("LCCN Harvester")
        print(f"- Input TSV: {input_path}")
        print(f"- Dry run:   {args.dry_run}")
        print("- Database:  initialized (tables ready)")
        print(f"- ISBNs:     parsed {len(isbns)} entries")

        preview = ", ".join(isbns[:5])
        print(f"- Preview:   {preview}" if preview else "- Preview:   (none)")
        print()

        summary = run_harvest(input_path=input_path, dry_run=args.dry_run)

        print("Summary:")
        print(f"- Total ISBNs:          {summary.total_isbns}")
        print(f"- Cached hits:          {summary.cached_hits}")
        print(f"- Skipped recent fails: {summary.skipped_recent_fail}")
        print(f"- Attempted:            {summary.attempted}")
        print(f"- Successes:            {summary.successes}")
        print(f"- Failures:             {summary.failures}")

        return 0

    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
