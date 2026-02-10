from __future__ import annotations

import logging
from dataclasses import dataclass

from api.base_api import BaseApiClient, ApiResult
from harvester.orchestrator import HarvestTarget, TargetResult, PlaceholderTarget

logger = logging.getLogger(__name__)


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
    targets: list[HarvestTarget] = []

    # LoC
    try:
        from api.loc_api import LocApiClient
        targets.append(ApiClientTarget(LocApiClient(), name="loc"))
    except Exception as e:
        logger.warning("LoC API target not available: %s", e)

    # Harvard
    try:
        from api.harvard_api import HarvardApiClient
        targets.append(ApiClientTarget(HarvardApiClient(), name="harvard"))
    except Exception as e:
        logger.warning("Harvard API target not available: %s", e)

    # OpenLibrary
    try:
        from api.openlibrary_api import OpenLibraryApiClient
        targets.append(ApiClientTarget(OpenLibraryApiClient(), name="openlibrary"))
    except Exception as e:
        logger.warning("OpenLibrary API target not available: %s", e)

    return targets if targets else [PlaceholderTarget()]
