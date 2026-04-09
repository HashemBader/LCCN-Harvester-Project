"""
Module: harvester_cli.py
Part of the LCCN Harvester Project.

Command-line entry point for the LCCN Harvester.

This module wires together argument parsing, input validation, database
initialisation, and the core harvest pipeline into a single runnable CLI
command.  It is the ``__main__`` module for direct invocation and is also
exposed as a console-script entry point via ``src/main.py``.

Workflow
--------
1. Parse CLI arguments (``--input``, ``--dry-run``, ``--stop-rule``).
2. Validate that the input TSV file exists and is a regular file.
3. Initialise the SQLite database (creates tables if they do not yet exist).
4. Print a pre-run summary including a preview of the first five ISBNs.
5. Invoke ``run_harvest()`` and print the resulting harvest statistics.
6. Always close the database connection in the ``finally`` block.

Exit codes
----------
0   — Harvest completed (successes and failures are reported in the summary,
      not reflected in the exit code).
1   — Fatal error before the harvest started (bad input file, DB init failure).
"""

import argparse
import sys
from pathlib import Path

from src.database import DatabaseManager
from src.harvester.run_harvest import run_harvest, parse_isbn_file
from src.utils import isbn_validator


def parse_args(argv=None):
    """
    Parse and return command-line arguments for the LCCN Harvester CLI.

    Args:
        argv (list[str] | None): Argument list to parse.  Defaults to
            ``sys.argv[1:]`` when ``None`` (standard ``argparse`` behaviour).
            Pass an explicit list in tests to avoid reading the real ``sys.argv``.

    Returns:
        argparse.Namespace: Parsed arguments with attributes:
            - ``input_file`` (str): Path to the TSV file of ISBNs.
            - ``dry_run`` (bool): When ``True``, the pipeline skips DB writes.
            - ``stop_rule`` (str): Controls when to stop querying targets for a
              given ISBN when harvesting both LCCN and NLMCN call numbers.
    """
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

    # stop_rule governs the multi-target search strategy when both LCCN and
    # NLMCN call numbers are requested.  The choices map to constants defined
    # in the orchestrator:
    #   stop_either   — stop as soon as either call number is found
    #   stop_lccn     — stop once an LCCN is found (keep searching for NLMCN)
    #   stop_nlmcn    — stop once an NLMCN is found (keep searching for LCCN)
    #   continue_both — always query all targets regardless of what was found
    parser.add_argument(
        "--stop-rule",
        choices=["stop_either", "stop_lccn", "stop_nlmcn", "continue_both"],
        default="stop_either",
        help="When to stop searching targets (if call_number_mode is 'both').",
    )

    return parser.parse_args(argv)


def validate_input_file(path_str: str) -> Path:
    """
    Resolve and validate the input file path, exiting on failure.

    Expands ``~`` and resolves symlinks so the returned ``Path`` is always
    absolute.  Prints a descriptive error to ``stderr`` and calls
    ``sys.exit(1)`` if the path does not exist or is not a regular file
    (e.g. it points to a directory).

    Args:
        path_str (str): Raw path string as supplied by the user on the CLI.

    Returns:
        Path: Resolved, validated absolute path to the input file.
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
    Initialise the SQLite database, exiting the process on failure.

    Creates a ``DatabaseManager`` using the project-default database path
    (``data/lccn_harvester.sqlite3``) and calls ``init_db()`` to apply the
    schema (idempotent — safe to call on an already-initialised database).

    Returns:
        DatabaseManager: A ready-to-use database manager instance with all
            required tables created.

    Side effects:
        Calls ``sys.exit(1)`` if the database cannot be created or the schema
        cannot be applied, printing the error to ``stderr``.
    """
    try:
        db = DatabaseManager()  # default path: data/lccn_harvester.sqlite3
        db.init_db()
        return db
    except Exception as e:
        print(f"ERROR: Failed to initialize database: {e}", file=sys.stderr)
        sys.exit(1)


def main(argv=None) -> int:
    """
    Run the LCCN Harvester CLI end-to-end.

    Orchestrates argument parsing, validation, database setup, pre-run
    reporting, the harvest pipeline call, and post-run summary output.
    Always closes the database connection via a ``finally`` block.

    Args:
        argv (list[str] | None): CLI arguments.  Defaults to ``sys.argv[1:]``.
            Useful for programmatic invocation in tests.

    Returns:
        int: Exit code — ``0`` on success, ``1`` on fatal pre-harvest error
            (validation or database failures call ``sys.exit`` internally).
    """
    args = parse_args(argv)
    input_path = validate_input_file(args.input_file)

    db = None
    try:
        db = init_database_or_exit()

        # Parse the ISBN file using the same reader as the harvest pipeline so
        # that the preview count exactly matches what will be processed.
        isbns = parse_isbn_file(input_path).unique_valid

        print("LCCN Harvester")
        print(f"- Input TSV: {input_path}")
        print(f"- Dry run:   {args.dry_run}")
        print("- Database:  initialized (tables ready)")
        print(f"- ISBNs:     parsed {len(isbns)} entries")

        # Show up to 5 ISBNs as a quick sanity-check for the user.
        preview = ", ".join(isbns[:5])
        print(f"- Preview:   {preview}" if preview else "- Preview:   (none)")
        print()

        summary = run_harvest(
            input_path=input_path,
            dry_run=args.dry_run,
            stop_rule=args.stop_rule
        )

        # Print the harvest summary returned by run_harvest().
        print("Summary:")
        print(f"- Total ISBNs:          {summary.total_isbns}")
        print(f"- Cached hits:          {summary.cached_hits}")
        print(f"- Skipped recent fails: {summary.skipped_recent_fail}")
        print(f"- Attempted:            {summary.attempted}")
        print(f"- Successes:            {summary.successes}")
        print(f"- Failures:             {summary.failures}")

        return 0

    finally:
        # Always close the DB connection even if an unhandled exception escapes
        # the try block; swallow any close() error to avoid masking the original.
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
