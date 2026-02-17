from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from src.api.base_api import BaseApiClient, ApiResult
from src.harvester.orchestrator import HarvestTarget, TargetResult, PlaceholderTarget

logger = logging.getLogger(__name__)


def _as_bool(value: object, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass
class ApiClientTarget(HarvestTarget):
    """
    Adapter: wraps a BaseApiClient and exposes HarvestTarget.lookup().
    """
    client: BaseApiClient
    name: str

    def lookup(self, isbn: str) -> TargetResult:
        r: ApiResult = self.client.search(isbn)

        if r.status == "success" and (r.lccn or r.nlmcn):
            return TargetResult(
                success=True,
                lccn=r.lccn,
                nlmcn=r.nlmcn,
                source=r.source,
            )

        # not found / error
        msg = r.error_message or r.status
        return TargetResult(
            success=False,
            source=r.source,
            error=msg,
        )


def build_default_api_targets() -> list[HarvestTarget]:
    """
    Best-effort: build targets that exist in the repo.
    If none are available, fall back to PlaceholderTarget.
    """
    def _make_loc() -> ApiClientTarget:
        from src.api.loc_api import LocApiClient
        return ApiClientTarget(LocApiClient(), name="Library of Congress")

    def _make_harvard() -> ApiClientTarget:
        from src.api.harvard_api import HarvardApiClient
        return ApiClientTarget(HarvardApiClient(), name="Harvard")

    def _make_openlibrary() -> ApiClientTarget:
        from src.api.openlibrary_api import OpenLibraryApiClient
        return ApiClientTarget(OpenLibraryApiClient(), name="OpenLibrary")

    factories = {
        "library of congress": _make_loc,
        "loc": _make_loc,
        "harvard": _make_harvard,
        "harvard librarycloud": _make_harvard,
        "openlibrary": _make_openlibrary,
        "open library": _make_openlibrary,
    }

    configured_names: list[str] = []
    cfg_path = Path("data/targets.json")
    if cfg_path.exists():
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                api_rows = [
                    row for row in raw
                    if isinstance(row, dict) and str(row.get("type", "")).strip().lower() == "api"
                ]
                api_rows.sort(
                    key=lambda row: int(str(row.get("rank", 999)).strip())
                    if str(row.get("rank", "")).strip().isdigit()
                    else 999
                )
                for row in api_rows:
                    if _as_bool(row.get("selected", True)):
                        configured_names.append(str(row.get("name", "")).strip().lower())
        except Exception as e:
            logger.warning("Failed reading API target config %s: %s", cfg_path, e)

    if not configured_names:
        configured_names = ["library of congress", "harvard", "openlibrary"]

    targets: list[HarvestTarget] = []
    seen: set[str] = set()
    for key in configured_names:
        if not key or key in seen:
            continue
        seen.add(key)
        maker = factories.get(key)
        if not maker:
            logger.warning("Unknown API target in config: %s", key)
            continue
        try:
            targets.append(maker())
        except Exception as e:
            logger.warning("API target not available (%s): %s", key, e)

    return targets if targets else [PlaceholderTarget()]
