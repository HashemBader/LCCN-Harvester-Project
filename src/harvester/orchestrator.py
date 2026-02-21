from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol
from src.database import DatabaseManager, MainRecord, utc_now_iso
from concurrent.futures import ThreadPoolExecutor



# Progress callback signature (Sprint 4 GUI signals can wrap this easily)
# event examples: "isbn_start", "cached", "skip_retry", "target_start", "success", "failed"
ProgressCallback = Callable[[str, dict], None]
CancelCheck = Callable[[], bool]


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


class HarvestCancelled(Exception):
    """Raised when a harvest run is cancelled by the caller."""


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

    DEFAULT_FLUSH_BATCH_SIZE = 50

    def __init__(
        self,
        db: DatabaseManager,
        targets: Optional[list[HarvestTarget]] = None,
        *,
        retry_days: int = 7,
        max_workers: int = 1,
        call_number_mode: str = "both",
        bypass_retry_isbns: Optional[set[str]] = None,
        bypass_cache_isbns: Optional[set[str]] = None,
        progress_cb: Optional[ProgressCallback] = None,
        cancel_check: Optional[CancelCheck] = None,
    ):
        self.db = db
        self.retry_days = retry_days
        self.bypass_retry_isbns = set(bypass_retry_isbns or [])
        self.bypass_cache_isbns = set(bypass_cache_isbns or [])
        self.progress_cb = progress_cb
        self.cancel_check = cancel_check
        self.call_number_mode = self._normalize_call_number_mode(call_number_mode)
        self.max_workers = max(1, int(max_workers))
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)    

        # If no real targets wired yet, keep Sprint-2 behavior with a placeholder.
        self.targets: list[HarvestTarget] = targets if targets else [PlaceholderTarget()]

    def _emit(self, event: str, payload: dict) -> None:
        if self.progress_cb:
            self.progress_cb(event, payload)

    def _check_cancelled(self) -> None:
        if self.cancel_check and self.cancel_check():
            raise HarvestCancelled("Harvest cancelled by user")

    @staticmethod
    def _normalize_call_number_mode(mode: str) -> str:
        mode_normalized = (mode or "").strip().lower()
        if mode_normalized in {"lccn", "nlmcn", "both"}:
            return mode_normalized
        return "both"

    def _filter_result_by_mode(self, result: TargetResult) -> TargetResult:
        if not result.success or self.call_number_mode == "both":
            return result

        if self.call_number_mode == "lccn":
            if result.lccn:
                return TargetResult(
                    success=True,
                    lccn=result.lccn,
                    nlmcn=None,
                    source=result.source,
                    error=result.error,
                )
            return TargetResult(success=False, source=result.source, error="No LCCN call number")

        if self.call_number_mode == "nlmcn":
            if result.nlmcn:
                return TargetResult(
                    success=True,
                    lccn=None,
                    nlmcn=result.nlmcn,
                    source=result.source,
                    error=result.error,
                )
            return TargetResult(success=False, source=result.source, error="No NLMCN call number")

        return result

    def process_isbn(
        self,
        isbn: str,
        *,
        dry_run: bool,
        pending_main: list[MainRecord],
        pending_attempted: list[tuple[str, Optional[str], Optional[str], Optional[str]]],
    ) -> str:

        """
        Process one ISBN.
        Returns status string: "cached" | "skip_retry" | "success" | "failed"
        """
        self._check_cancelled()
        self._emit("isbn_start", {"isbn": isbn})

        # 1) cache check
        if isbn not in self.bypass_cache_isbns and self.db.get_main(isbn) is not None:
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
        not_found_targets: list[str] = []
        other_errors: list[str] = []

        for target in self.targets:
            self._check_cancelled()
            last_target = getattr(target, "name", target.__class__.__name__)
            self._emit("target_start", {"isbn": isbn, "target": last_target})

            result = self._filter_result_by_mode(target.lookup(isbn))

            if result.success:
                self._emit("success", {"isbn": isbn, "target": last_target})

                if not dry_run:
                    rec = MainRecord(
                        isbn=isbn,
                        lccn=result.lccn,
                        nlmcn=result.nlmcn,
                        source=result.source or last_target,
                    )
                    pending_main.append(rec)


                return "success"

            # failure from this target; continue
            last_error = result.error or "Unknown error"
            err = (result.error or "").strip()
            if err.lower().startswith("no records found in"):
                not_found_targets.append(last_target)
            elif err:
                other_errors.append(f"{last_target}: {err}")

        # 4) all targets failed
        if not_found_targets and not other_errors:
            last_error = "Not found in: " + ", ".join(not_found_targets)
        elif not_found_targets and other_errors:
            last_error = (
                "Not found in: "
                + ", ".join(not_found_targets)
                + " | Other errors: "
                + " ; ".join(other_errors)
            )
        elif other_errors:
            last_error = " ; ".join(other_errors)

        self._emit(
            "failed",
            {"isbn": isbn, "last_target": last_target, "last_error": last_error},
        )

        if not dry_run:
            pending_attempted.append((isbn, last_target, utc_now_iso(), last_error))

        return "failed"
    def run(self, isbns: list[str], *, dry_run: bool) -> HarvestSummary:
        cached_hits = 0
        skipped_recent_fail = 0
        attempted = 0
        successes = 0
        failures = 0

        # --- Sprint 5: batching buffers ---
        pending_main: list[MainRecord] = []
        pending_attempted: list[tuple[str, Optional[str], Optional[str], Optional[str]]] = []

        def flush() -> None:
            """Flush buffered DB writes in a single transaction."""
            wrote_main = len(pending_main)
            wrote_attempted = len(pending_attempted)
            if dry_run:
                pending_main.clear()
                pending_attempted.clear()
                return

            if not pending_main and not pending_attempted:
                return

            with self.db.transaction() as conn:
                self.db.upsert_main_many(conn, pending_main, clear_attempted_on_success=True)
                self.db.upsert_attempted_many(conn, pending_attempted)

            pending_main.clear()
            pending_attempted.clear()
            self._emit("db_flush", {"main": wrote_main, "attempted": wrote_attempted})
        # --- end Sprint 5 batching ---

        def _one(isbn: str) -> str:
            # NOTE: This will append into pending_main / pending_attempted.
            # That is NOT thread-safe, so we only use threads if max_workers == 1.
            # Parallel mode is handled below with a safe path.
            return self.process_isbn(
                isbn,
                dry_run=dry_run,
                pending_main=pending_main,
                pending_attempted=pending_attempted,
            )

        if self.max_workers <= 1:
            # --- sequential (your current behavior) ---
            for isbn in isbns:
                self._check_cancelled()
                status = _one(isbn)

                if (len(pending_main) + len(pending_attempted)) >= self.DEFAULT_FLUSH_BATCH_SIZE:
                    flush()

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

                self._emit("stats", {
                    "total": len(isbns),
                    "cached": cached_hits,
                    "skipped": skipped_recent_fail,
                    "attempted": attempted,
                    "successes": successes,
                    "failures": failures,
                })

        else:
            # --- parallel mode (SAFE): threads do lookup only, main thread writes DB in batches ---
            def worker(isbn: str):
                self._check_cancelled()
                # Only compute outcome; do NOT touch shared pending_* lists here.
                # Also: emitting progress from threads is okay only if your GUI callback is thread-safe.
                self._emit("isbn_start", {"isbn": isbn})

                if isbn not in self.bypass_cache_isbns and self.db.get_main(isbn) is not None:
                    self._emit("cached", {"isbn": isbn})
                    return ("cached", None, None)

                if isbn not in self.bypass_retry_isbns and self.db.should_skip_retry(isbn, retry_days=self.retry_days):
                    self._emit("skip_retry", {"isbn": isbn, "retry_days": self.retry_days})
                    return ("skip_retry", None, None)

                last_error = None
                last_target = None
                not_found_targets: list[str] = []
                other_errors: list[str] = []

                for target in self.targets:
                    self._check_cancelled()
                    last_target = getattr(target, "name", target.__class__.__name__)
                    self._emit("target_start", {"isbn": isbn, "target": last_target})

                    result = self._filter_result_by_mode(target.lookup(isbn))
                    if result.success:
                        self._emit("success", {"isbn": isbn, "target": last_target})

                        rec = None
                        if not dry_run:
                            rec = MainRecord(
                                isbn=isbn,
                                lccn=result.lccn,
                                nlmcn=result.nlmcn,
                                source=result.source or last_target,
                            )
                        return ("success", rec, None)

                    last_error = result.error or "Unknown error"
                    err = (result.error or "").strip()
                    if err.lower().startswith("no records found in"):
                        not_found_targets.append(last_target)
                    elif err:
                        other_errors.append(f"{last_target}: {err}")

                if not_found_targets and not other_errors:
                    last_error = "Not found in: " + ", ".join(not_found_targets)
                elif not_found_targets and other_errors:
                    last_error = (
                        "Not found in: "
                        + ", ".join(not_found_targets)
                        + " | Other errors: "
                        + " ; ".join(other_errors)
                    )
                elif other_errors:
                    last_error = " ; ".join(other_errors)

                self._emit("failed", {"isbn": isbn, "last_target": last_target, "last_error": last_error})

                att = None
                if not dry_run:
                    att = (isbn, last_target, utc_now_iso(), last_error)
                return ("failed", None, att)

            with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
                for status, rec, att in ex.map(worker, isbns):
                    self._check_cancelled()
                    # main-thread batching writes
                    if rec is not None:
                        pending_main.append(rec)
                    if att is not None:
                        pending_attempted.append(att)

                    if (len(pending_main) + len(pending_attempted)) >= self.DEFAULT_FLUSH_BATCH_SIZE:
                        flush()

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

                    self._emit("stats", {
                        "total": len(isbns),
                        "cached": cached_hits,
                        "skipped": skipped_recent_fail,
                        "attempted": attempted,
                        "successes": successes,
                        "failures": failures,
                    })

        # Flush any trailing buffered writes so short runs are persisted.
        flush()

        return HarvestSummary(
            total_isbns=len(isbns),
            cached_hits=cached_hits,
            skipped_recent_fail=skipped_recent_fail,
            attempted=attempted,
            successes=successes,
            failures=failures,
            dry_run=dry_run,
        )
