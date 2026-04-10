"""
Module: main.py
Part of the LCCN Harvester Project.

Package-level ``__main__`` shim for the LCCN Harvester CLI.

This module exists so the harvester can be invoked as a Python package::

    python -m src

It simply delegates to ``harvester_cli.main()``, which owns all argument
parsing, validation, and pipeline orchestration logic.  Keeping this file
minimal ensures there is a single authoritative entry point in
``harvester_cli.py`` regardless of how the process is started.
"""
import sys

# Relative import used intentionally — this module is always run as part of
# the src package, so an absolute import of src.harvester_cli is not needed.
from .harvester_cli import main as cli_main


if __name__ == "__main__":
    sys.exit(cli_main())
