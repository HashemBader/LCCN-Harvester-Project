from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Protocol

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import DatabaseManager, MainRecord


# Progress callback signature (Sprint 4 GUI signals can wrap this easily)
# event examples: "isbn_start", "cached", "skip_retry", "target_start", "success", "failed"
ProgressCallback = Callable[[str, dict], None]


class HarvestTarget(Protocol):
    """A target data source the orchestrator can try (API, Z39.50, etc.)."""

    name: str

    def lookup(self, isbn: str) -> "TargetResult":
        """Return TargetResult (success + data or failure + error)."""
        ...


@dataclass(frozen=True)
class TargetResult:
    success: bool
    lccn: Optional[str] = None
    nlmcn: Optional[str] = None
    source: Optional[str] = None
    error: Optional[str] = None


class PlaceholderTarget:
    """
    Sprint 3 starter target.
    Always fails with a clear message until real targets are wired.
    """

    name = "(placeholder)"

    def lookup(self, isbn: str) -> TargetResult:
        return TargetResult(
            success=False,
            source=self.name,
            error="Harvest target not implemented yet (placeholder)",
        )


@dataclass(frozen=True)
class HarvestSummary:
    total_isbns: int
    cached_hits: int
    skipped_recent_fail: int
    attempted: int
    successes: int
    failures: int
    dry_run: bool


class HarvestOrchestrator:
    """
    Full orchestrator for Sprint 3:
    - Target order
    - Cache lookup
    - Retry logic
    - Stop-on-first-result
    - DB writes (main/attempted)
    - Optional progress callback hook
    """

    def __init__(
        self,
        db: DatabaseManager,
        targets: Optional[list[HarvestTarget]] = None,
        *,
        retry_days: int = 7,
        bypass_retry_isbns: Optional[set[str]] = None,
        progress_cb: Optional[ProgressCallback] = None,
    ):
        self.db = db
        self.retry_days = retry_days
        self.bypass_retry_isbns = set(bypass_retry_isbns or [])
        self.progress_cb = progress_cb

        # If no real targets wired yet, keep Sprint-2 behavior with a placeholder.
        self.targets: list[HarvestTarget] = targets if targets else [PlaceholderTarget()]

    def _emit(self, event: str, payload: dict) -> None:
        if self.progress_cb:
            self.progress_cb(event, payload)

    def process_isbn(self, isbn: str, *, dry_run: bool) -> str:
        """
        Process one ISBN.
        Returns status string: "cached" | "skip_retry" | "success" | "failed"
        """
        self._emit("isbn_start", {"isbn": isbn})

        # 1) cache check
        if self.db.get_main(isbn) is not None:
            self._emit("cached", {"isbn": isbn})
            return "cached"

        # 2) retry-skip check
        if isbn not in self.bypass_retry_isbns and self.db.should_skip_retry(
            isbn, retry_days=self.retry_days
        ):
            self._emit("skip_retry", {"isbn": isbn, "retry_days": self.retry_days})
            return "skip_retry"

        # 3) try targets in order
        last_error: Optional[str] = None
        last_target: Optional[str] = None

        for target in self.targets:
            last_target = getattr(target, "name", target.__class__.__name__)
            self._emit("target_start", {"isbn": isbn, "target": last_target})

            result = target.lookup(isbn)

            if result.success:
                self._emit("success", {"isbn": isbn, "target": last_target})

                if not dry_run:
                    rec = MainRecord(
                        isbn=isbn,
                        lccn=result.lccn,
                        nlmcn=result.nlmcn,
                        source=result.source or last_target,
                    )
                    self.db.upsert_main(rec, clear_attempted_on_success=True)

                return "success"

            # failure from this target; continue
            last_error = result.error or "Unknown error"

        # 4) all targets failed
        self._emit(
            "failed",
            {"isbn": isbn, "last_target": last_target, "last_error": last_error},
        )

        if not dry_run:
            self.db.upsert_attempted(
                isbn=isbn,
                last_target=last_target,
                last_error=last_error,
            )

        return "failed"

    def run(self, isbns: list[str], *, dry_run: bool) -> HarvestSummary:
        cached_hits = 0
        skipped_recent_fail = 0
        attempted = 0
        successes = 0
        failures = 0

        for isbn in isbns:
            status = self.process_isbn(isbn, dry_run=dry_run)

            if status == "cached":
                cached_hits += 1
            elif status == "skip_retry":
                skipped_recent_fail += 1
            else:
                attempted += 1
                if status == "success":
                    successes += 1
                else:
                    failures += 1

        return HarvestSummary(
            total_isbns=len(isbns),
            cached_hits=cached_hits,
            skipped_recent_fail=skipped_recent_fail,
            attempted=attempted,
            successes=successes,
            failures=failures,
            dry_run=dry_run,
        )
