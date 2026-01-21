"""
harvester_cli.py

Initial command-line entry point for the LCCN Harvester.

For Sprint 2 this script:
- Accepts a required --input argument pointing to a TSV file of ISBNs.
- Validates that the file exists and is a regular file.
- Prints a summary of what would be done.

Later sprints will replace the placeholder with a real call to the harvest
pipeline (e.g., run_harvest()).
"""

import argparse
import sys
from pathlib import Path


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


def main(argv=None) -> int:
    """
    Main entry point for the CLI.

    Steps:
    1. Parse arguments.
    2. Validate the input TSV path.
    3. Print a confirmation message (no real harvesting yet).

    Returns
    -------
    int
        Exit code (0 for success, non-zero for errors).
    """
    args = parse_args(argv)
    input_path = validate_input_file(args.input_file)

    # Placeholder for future integration with the real harvest pipeline.
    # Example of what we will eventually call:
    #   run_harvest(input_path=input_path, dry_run=args.dry_run)

    print("LCCN Harvester (CLI skeleton)")
    print(f"- Input TSV: {input_path}")
    print(f"- Dry run:   {args.dry_run}")
    print()
    print(
        "No harvesting is performed yet. "
        "This CLI only validates the file path and confirms the options."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
