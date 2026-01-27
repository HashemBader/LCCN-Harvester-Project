"""
Module: main.py
Part of the LCCN Harvester Project.
"""
import sys

from .harvester_cli import main as cli_main


if __name__ == "__main__":
    sys.exit(cli_main())
