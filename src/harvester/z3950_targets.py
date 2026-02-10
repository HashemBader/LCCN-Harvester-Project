from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any

from harvester.orchestrator import HarvestTarget, TargetResult

logger = logging.getLogger(__name__)


def _parse_bool(v: object, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in {"true", "1", "yes", "y", "on"}


def _safe_int(v: object, default: int = 0) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _extract_callnum_from_field(field: Any) -> Optional[str]:
    """
    Extract a human-readable call number from a MARC field like 050 or 060.

    Typical structure:
      050 $a QA76.76 $b .C65 2008
      060 $a W 26.5 $b ...
    """
    try:
        # pymarc Field supports get_subfields()
        parts: list[str] = []
        for code in ("a", "b", "c"):
            vals = field.get_subfields(code) or []
            for val in vals:
                val = (val or "").strip()
                if val:
                    parts.append(val)
        call = " ".join(parts).strip()
        return call or None
    except Exception:
        return None


def _extract_call_numbers(records: list[Any]) -> tuple[Optional[str], Optional[str]]:
    """
    From MARC records, try to pull:
      - LCCN call number from 050
      - NLM call number from 060
    """
    for rec in records:
        lccn = None
        nlmcn = None

        try:
            f050 = rec.get_fields("050") or []
            for f in f050:
                lccn = _extract_callnum_from_field(f)
                if lccn:
                    break
        except Exception:
            pass

        try:
            f060 = rec.get_fields("060") or []
            for f in f060:
                nlmcn = _extract_callnum_from_field(f)
                if nlmcn:
                    break
        except Exception:
            pass

        if lccn or nlmcn:
            return lccn, nlmcn

    return None, None


@dataclass(frozen=True)
class Z3950Target(HarvestTarget):
    """
    HarvestTarget adapter around the Z3950Client (client.py).
    """
    name: str
    host: str
    port: int
    database: str
    record_syntax: str = "USMARC"
    rank: int = 999
    selected: bool = True

    def lookup(self, isbn: str) -> TargetResult:
        # Import lazily so missing deps don’t crash app startup
        try:
            # Try both common layouts (you keep whichever matches your repo)
            try:
                from z3950.client import Z3950Client  # type: ignore
            except Exception:
                from z3950.client import Z3950Client  # type: ignore
        except Exception as e:
            return TargetResult(
                success=False,
                source=self.name,
                error=f"Z39.50 client import failed: {e}",
            )

        try:
            with Z3950Client(
                host=self.host,
                port=self.port,
                database=self.database,
                syntax=self.record_syntax or "USMARC",
            ) as client:
                records = client.search_by_isbn(isbn)

            if not records:
                return TargetResult(
                    success=False,
                    source=self.name,
                    error="No records found",
                )

            lccn, nlmcn = _extract_call_numbers(records)
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
    """
    Build Z39.50 targets from either:
      - data/targets.tsv (TargetsManager format), OR
      - data/targets.json (TargetsTab format)

    Returns an ordered list (sorted by rank).
    """
    tsv_path = Path(tsv_path)
    json_path = Path(json_path)

    targets: list[Z3950Target] = []

    # 1) TSV format
    if tsv_path.exists():
        try:
            with tsv_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f, delimiter="\t")
                for row in reader:
                    ttype = (row.get("target_type") or "").strip().lower()
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
