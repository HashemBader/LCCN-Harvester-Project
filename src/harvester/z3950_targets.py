"""
Z39.50 harvest target implementations for the LCCN Harvester.

This module provides:

  Z3950Target              -- A frozen dataclass implementing ``HarvestTarget``
                              for a single Z39.50 server.  Each ``lookup()``
                              call opens a fresh connection, performs an ISBN
                              search, and extracts call numbers from the
                              returned MARC records.
  build_default_z3950_targets -- Factory that reads target definitions from
                                 ``data/targets.tsv`` (preferred) or
                                 ``data/targets.json`` (fallback) and returns
                                 an ordered list ready for the orchestrator.

Thread-local Z39.50 connection pooling helpers (``_get_z3950_client`` /
``_release_z3950_client``) are also defined here but are currently unused by
``Z3950Target.lookup`` which opens a new connection per call.  They exist for
future optimisation.

Dependencies:
  PyZ3950 / src.z3950.client  -- imported lazily so a missing installation
                                 does not prevent the app from starting.
"""
from __future__ import annotations

import csv
import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any

from src.harvester.orchestrator import HarvestTarget, TargetResult

logger = logging.getLogger(__name__)

# Thread-local storage for per-thread Z39.50 connection caches.
# Each thread maintains its own dict keyed by (host, port, database, syntax).
_z3950_thread_local = threading.local()

def _get_z3950_client(host: str, port: int, database: str, syntax: str):
    """Retrieve or create a persistent Z39.50 connection for the current thread.

    Connections are stored in ``_z3950_thread_local.clients`` so each worker
    thread keeps its own pool without locking.  Currently unused by
    ``Z3950Target.lookup`` (which opens a fresh connection per call) but
    available for future connection-reuse optimisation.

    Args:
        host:     Z39.50 server hostname or IP.
        port:     TCP port number.
        database: Z39.50 database identifier.
        syntax:   MARC record syntax (e.g. ``"USMARC"``).

    Returns:
        A connected ``Z3950Client`` instance for the current thread.
    """
    if not hasattr(_z3950_thread_local, "clients"):
        _z3950_thread_local.clients = {}

    key = (host, port, database, syntax)
    client = _z3950_thread_local.clients.get(key)

    if not client:
        # Import lazily so missing deps don't crash app startup
        try:
            from src.z3950.client import Z3950Client  # type: ignore
        except ImportError:
            from z3950.client import Z3950Client  # type: ignore

        client = Z3950Client(host=host, port=port, database=database, syntax=syntax)
        client.connect()
        _z3950_thread_local.clients[key] = client

    return client

def _release_z3950_client(host: str, port: int, database: str, syntax: str):
    """Close and discard the thread-local Z39.50 connection for the given server.

    Silently ignores errors on ``close()`` so a broken server connection does
    not propagate an exception during cleanup.

    Args:
        host:     Z39.50 server hostname or IP.
        port:     TCP port number.
        database: Z39.50 database identifier.
        syntax:   MARC record syntax.
    """
    if hasattr(_z3950_thread_local, "clients"):
        key = (host, port, database, syntax)
        client = _z3950_thread_local.clients.pop(key, None)
        if client:
            try:
                client.close()
            except Exception:
                pass



def _parse_bool(v: object, default: bool = False) -> bool:
    """Coerce a config value to bool, accepting common truthy string literals."""
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in {"true", "1", "yes", "y", "on"}


def _safe_int(v: object, default: int = 0) -> int:
    """Convert *v* to an integer, returning *default* on any conversion error."""
    try:
        return int(str(v).strip())
    except Exception:
        return default


@dataclass(frozen=True)
class Z3950Target(HarvestTarget):
    """HarvestTarget adapter around the Z3950Client (``src/z3950/client.py``).

    Opens a new connection for every ``lookup()`` call (no persistent state),
    performs a ``bib-1`` ISBN search, and extracts LC call numbers from MARC
    fields 050 and 060.

    Attributes:
        name:          Display name shown in logs and the UI.
        host:          Z39.50 server hostname or IP address.
        port:          TCP port (default for Z39.50 is 210).
        database:      Z39.50 database identifier (e.g. ``"Voyager"``).
        record_syntax: MARC record syntax requested from the server (``"USMARC"``).
        rank:          Sort priority (lower = tried earlier by the orchestrator).
        selected:      Whether this target is enabled in the current profile.
    """
    name: str
    host: str
    port: int
    database: str
    record_syntax: str = "USMARC"
    rank: int = 999
    selected: bool = True

    def lookup(self, isbn: str) -> TargetResult:
        """Search *isbn* via Z39.50 and return LC/NLM call numbers if found.

        Returns:
            ``TargetResult(success=True, lccn=..., nlmcn=...)`` on success, or
            ``TargetResult(success=False, error=...)`` if the server returns no
            records, no 050/060 field is present, or the connection fails.
        """
        syntax = self.record_syntax or "USMARC"

        try:
            from src.z3950.client import Z3950Client
        except ImportError:
            return TargetResult(success=False, source=self.name, error="Z3950 client unavailable")

        try:
            with Z3950Client(host=self.host, port=self.port, database=self.database, syntax=syntax) as client:
                # 1-second pause between queries to respect Z39.50 server rate limits
                # and avoid triggering IP bans during large batch harvests.
                time.sleep(1.0)

                records = client.search_by_isbn(isbn)

            if not records:
                return TargetResult(
                    success=False,
                    source=self.name,
                    error="No records found",
                )

            from src.z3950.marc_decoder import extract_call_numbers_from_pymarc
            from src.utils.call_number_validators import validate_lccn, validate_nlmcn

            lccn = None
            nlmcn = None
            for rec in records:
                raw_lccn, raw_nlmcn = extract_call_numbers_from_pymarc(rec)
                lccn = validate_lccn(raw_lccn)
                nlmcn = validate_nlmcn(raw_nlmcn)
                if lccn or nlmcn:
                    break

            if lccn or nlmcn:
                return TargetResult(
                    success=True,
                    lccn=lccn,
                    nlmcn=nlmcn,
                    source=self.name,
                )

            return TargetResult(
                success=False,
                source=self.name,
                error="Record found but no 050/060 call number",
            )

        except Exception as e:
            return TargetResult(
                success=False,
                source=self.name,
                error=str(e),
            )


def build_default_z3950_targets(
    *,
    tsv_path: Path | str = "data/targets.tsv",
    json_path: Path | str = "data/targets.json",
) -> list[HarvestTarget]:
    """Build enabled Z39.50 targets from config files, sorted by rank.

    Reads TSV first (preferred legacy format used by TargetsManager), then
    falls back to JSON (GUI TargetsTab format) if the TSV yields no targets.
    Only rows where ``selected`` is truthy and ``host``, ``database``, and
    ``port`` are all present are included.

    Args:
        tsv_path:  Path to the tab-separated targets file.
        json_path: Path to the JSON targets file (fallback).

    Returns:
        A list of ``Z3950Target`` instances sorted ascending by ``rank``.
        Returns an empty list if neither file exists or contains valid rows.
    """
    tsv_path = Path(tsv_path)
    json_path = Path(json_path)

    targets: list[Z3950Target] = []

    # 1) TSV format (preferred: used by TargetsManager and the CLI)
    if tsv_path.exists():
        try:
            with tsv_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f, delimiter="\t")
                for row in reader:
                    ttype = (row.get("target_type") or "").strip().lower()
                    # Only include rows explicitly tagged as Z39.50 targets
                    if "z" not in ttype:
                        continue

                    selected = _parse_bool(row.get("selected"), default=True)
                    if not selected:
                        continue

                    host = (row.get("host") or "").strip()
                    port = _safe_int(row.get("port"), 210)
                    database = (row.get("database") or "").strip()
                    name = (row.get("name") or "Z39.50").strip()
                    syntax = (row.get("record_syntax") or "USMARC").strip()
                    rank = _safe_int(row.get("rank"), 999)

                    if host and database and port:
                        targets.append(
                            Z3950Target(
                                name=name,
                                host=host,
                                port=port,
                                database=database,
                                record_syntax=syntax,
                                rank=rank,
                                selected=True,
                            )
                        )
        except Exception as e:
            logger.warning("Failed reading %s: %s", tsv_path, e)

    # 2) JSON format (GUI TargetsTab)
    if not targets and json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for row in data:
                    ttype = str(row.get("type", "")).strip().lower()
                    if ttype != "z3950":
                        continue
                    if not _parse_bool(row.get("selected"), default=True):
                        continue

                    name = str(row.get("name", "Z39.50")).strip()
                    host = str(row.get("host", "")).strip()
                    port = _safe_int(row.get("port"), 210)
                    database = str(row.get("database", "")).strip()
                    rank = _safe_int(row.get("rank"), 999)

                    if host and database and port:
                        targets.append(
                            Z3950Target(
                                name=name,
                                host=host,
                                port=port,
                                database=database,
                                record_syntax="USMARC",
                                rank=rank,
                                selected=True,
                            )
                        )
        except Exception as e:
            logger.warning("Failed reading %s: %s", json_path, e)

    targets.sort(key=lambda t: getattr(t, "rank", 999))
    return targets
