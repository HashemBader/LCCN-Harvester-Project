"""
harvester_cli.py

Initial command-line entry point for the LCCN Harvester.

For Sprint 2 this script:
- Accepts a required --input argument pointing to a TSV file of ISBNs.
- Validates that the file exists and is a regular file.
- Initializes the SQLite database (creates tables via schema.sql if needed).
- Parses ISBNs from the TSV file (simple stub; no harvesting yet).
- Prints a summary of what would be done.

Later sprints will replace the placeholders with real pipeline logic.
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import List
from utils import isbn_validator

from database import DatabaseManager

from src.database import DatabaseManager

from src.harvester.run_harvest import run_harvest



def parse_args(argv=None):
    """
    Parse command-line arguments for the harvester CLI.

    Parameters
    ----------
    argv : list[str] | None
        Optional list of arguments for testing. If None, uses sys.argv[1:].

    Returns
    -------
    argparse.Namespace
        Parsed arguments with attributes:
        - input_file: path string to the TSV file containing ISBNs.
        - dry_run: boolean flag (reserved for later use).
    """
    parser = argparse.ArgumentParser(
        prog="lccn-harvester",
        description=(
            "Initial command-line interface for the LCCN Harvester.\n"
            "Accepts a TSV file of ISBNs and prepares it for processing."
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
        help=(
            "Run in dry-run mode. Reserved for later use; "
            "does not change behaviour in this sprint."
        ),
    )

    return parser.parse_args(argv)


def validate_input_file(path_str: str) -> Path:
    """
    Validate that the input file exists and is a regular file.

    Parameters
    ----------
    path_str : str
        String path provided by the user.

    Returns
    -------
    Path
        Resolved Path object for the input file.

    Exits with status code 1 on error.
    """
    path = Path(path_str).expanduser().resolve()

    if not path.exists():
        print(f"ERROR: Input file does not exist: {path}", file=sys.stderr)
        sys.exit(1)

    if not path.is_file():
        print(f"ERROR: Input path is not a file: {path}", file=sys.stderr)
        sys.exit(1)

    return path


def init_database_or_exit() -> DatabaseManager:
    """
    Create/open the SQLite database and initialize tables using schema.sql.

    Returns
    -------
    DatabaseManager
        Initialized DatabaseManager instance.

    Exits with status code 1 on error.
    """
    try:
        db = DatabaseManager()  # default: data/lccn_harvester.db
        db.init_db()
        return db
    except Exception as e:
        print(f"ERROR: Failed to initialize database: {e}", file=sys.stderr)
        sys.exit(1)


def normalize_isbn(raw: str) -> str:
    """
    Normalize ISBN input into a clean string.

    Rules:
    - Strip leading/trailing whitespace
    - Remove hyphens and spaces
    - Keep as text (never convert to int)
    """
    return raw.strip().replace("-", "").replace(" ", "")


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

            isbn = normalize_isbn(first_cell)
            if isbn_validator.validate_isbn(isbn):
                isbns.append(isbn)

    return isbns


def main(argv=None) -> int:
    """
    Main entry point for the CLI.

    Steps:
    1. Parse arguments.
    2. Validate the input TSV path.
    3. Initialize the database (create tables if needed).
    4. Parse ISBNs from TSV (stub).
    5. Print a confirmation message (no real harvesting yet).

    Returns
    -------
    int
        Exit code (0 for success, non-zero for errors).
    """
    args = parse_args(argv)
    input_path = validate_input_file(args.input_file)

    db = None
    try:
        db = init_database_or_exit()

        # TSV processing stub (no validation/lookup yet)
        isbns = read_isbns_from_tsv(input_path)

        print("LCCN Harvester (CLI skeleton)")
        print(f"- Input TSV: {input_path}")
        print(f"- Dry run:   {args.dry_run}")
        print("- Database:  initialized (tables ready)")
        print(f"- ISBNs:     parsed {len(isbns)} entries")

        preview = ", ".join(isbns[:5])
        print(f"- Preview:   {preview}" if preview else "- Preview:   (none)")
        print()
        print(
            "No harvesting is performed yet. "
            "This CLI validates the file path, initializes the database, and parses ISBNs from TSV."
        )

        return 0

    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass



if __name__ == "__main__":
    sys.exit(main())
