"""
Harvest orchestration: cache checking, multi-target lookup, retry suppression,
and batched DB writes.

This is the core runtime engine of the LCCN Harvester.  The
``HarvestOrchestrator`` class drives a complete harvest run from start to
finish without any knowledge of the UI or specific data sources.

Key concepts
------------
Call-number mode (``call_number_mode``)
    ``"lccn"``  -- only Library of Congress call numbers are sought.
    ``"nlmcn"`` -- only NLM call numbers are sought.
    ``"both"``  -- both types are sought (default).

Stop rule (``stop_rule``)
    Controls when the orchestrator is satisfied and stops querying further
    targets for a given ISBN.  Possible values:
      ``"stop_either"``   -- stop as soon as ANY call number is found.
      ``"stop_lccn"``     -- stop when an LCCN is found (continues for NLMCN).
      ``"stop_nlmcn"``    -- stop when an NLMCN is found.
      ``"continue_both"`` -- continue until BOTH types are found.

Progress events (``progress_cb``)
    The optional callback receives ``(event_name: str, payload: dict)`` for
    every significant step.  Common event names:
      ``isbn_start``, ``cached``, ``linked_cached``, ``target_start``,
      ``success``, ``linked_success``, ``failed``, ``skip_retry``,
      ``attempt_failed``, ``not_in_local_catalog``, ``stats``, ``db_flush``.

Batched writes
    Results are staged in in-memory lists (``pending_main``,
    ``pending_attempted``, ``pending_linked``) and flushed to SQLite in a
    single transaction every ``dynamic_batch_size`` ISBNs to reduce I/O
    overhead.

Linked ISBNs
    Different ISBNs for the same edition (e.g. 10-digit vs 13-digit) can be
    grouped before the run via the ``linked`` argument to ``run()``.  The
    orchestrator also *detects* implicit groups at flush time when distinct
    ISBNs share the same call number (``_detect_implicit_linked_isbns``).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from src.database import DatabaseManager, MainRecord, now_datetime_str
from src.utils.isbn_validator import pick_lowest_isbn

# Callback types used for real-time harvest progress reporting.
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
    """Result returned by a single ``HarvestTarget.lookup()`` call.

    Attributes:
        success: ``True`` when at least one call number was found.
        lccn:    Library of Congress call number, or ``None``.
        nlmcn:   NLM call number, or ``None``.
        source:  Name of the target that produced this result.
        isbns:   Additional ISBNs encountered in the record (e.g. linked editions).
        error:   Human-readable failure reason when ``success=False``.
    """
    success: bool
    lccn: Optional[str] = None
    nlmcn: Optional[str] = None
    source: Optional[str] = None
    isbns: tuple[str, ...] = ()
    error: Optional[str] = None


class PlaceholderTarget:
    """
    Fallback target used when no real targets have been configured.
    Always returns a failure so the orchestrator can still complete gracefully.
    """

    name = "(placeholder)"

    def lookup(self, isbn: str) -> TargetResult:
        return TargetResult(
            success=False,
            source=self.name,
            error="No harvest targets configured.",
        )


@dataclass(frozen=True)
class HarvestSummary:
    """Aggregate statistics returned by ``HarvestOrchestrator.run()``.

    Attributes:
        total_isbns:          Total number of ISBNs submitted to this run.
        cached_hits:          ISBNs satisfied from the local DB without any API call.
        skipped_recent_fail:  ISBNs skipped because they failed recently (within
                              ``retry_days``) and the retry window has not expired.
        attempted:            ISBNs that triggered at least one external lookup.
        successes:            ISBNs for which a call number was found.
        failures:             ISBNs that were attempted but no call number found.
        dry_run:              ``True`` if no DB writes were made.
        not_in_local_catalog: ISBNs skipped in ``db_only`` mode (not in local DB).
    """
    total_isbns: int
    cached_hits: int
    skipped_recent_fail: int
    attempted: int
    successes: int
    failures: int
    dry_run: bool
    not_in_local_catalog: int = 0


@dataclass(frozen=True)
class ProcessOutcome:
    """Internal result of ``_process_isbn_internal`` for a single ISBN.

    Attributes:
        status:        One of ``"success"``, ``"failed"``, ``"cached"``,
                       ``"skip_retry"``, or ``"not_in_local_catalog"``.
        record:        The resulting ``MainRecord`` (or ``None`` on failure).
        attempted_rows: Rows to write into the ``attempted`` table; empty on cache hits.
    """
    status: str
    record: Optional[MainRecord]
    attempted_rows: tuple[tuple[str, Optional[str], str, Optional[str], Optional[str]], ...]


class HarvestCancelled(Exception):
    """Raised when a harvest run is cancelled by the caller."""


class HarvestOrchestrator:
    """Core runtime engine that drives a full harvest batch.

    Responsibilities:
      - Walks configured ``HarvestTarget`` instances in order for each ISBN.
      - Checks the local DB cache before making any external network call.
      - Enforces retry suppression: skips ISBNs that failed recently (within
        ``retry_days``) unless the ISBN is in ``bypass_retry_isbns``.
      - Applies the configured ``call_number_mode`` and ``stop_rule`` to decide
        when to stop querying further targets for a given ISBN.
      - Stages results in memory (``pending_main``, ``pending_attempted``,
        ``pending_linked``) and flushes them to SQLite in batched transactions.
      - Fires optional ``progress_cb`` events for every meaningful step so the
        GUI can update its progress display without coupling to DB internals.
      - Detects implicit linked-ISBN groups when distinct ISBNs share a
        harvested call number.

    Attributes:
        db:                  The ``DatabaseManager`` used for all DB I/O.
        targets:             Ordered list of ``HarvestTarget`` data sources.
        retry_days:          Days to suppress retrying a previously failed ISBN.
        bypass_retry_isbns:  ISBNs forced to skip the retry suppression window.
        bypass_cache_isbns:  ISBNs forced to skip the DB cache check.
        progress_cb:         Optional ``(event_name, payload_dict)`` callback.
        cancel_check:        Optional callable that returns ``True`` to abort.
        call_number_mode:    One of ``"lccn"``, ``"nlmcn"``, or ``"both"``.
        stop_rule:           One of ``"stop_either"``, ``"stop_lccn"``,
                             ``"stop_nlmcn"``, or ``"continue_both"``.
        max_workers:         Parallel worker threads (1 = sequential).
        db_only:             When ``True``, no external API calls are made.
        selected_sources:    Source names whose cached results are trusted.
    """

    DEFAULT_FLUSH_BATCH_SIZE = 1

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
        stop_rule: str = "stop_either",
        db_only: bool = False,
        both_stop_policy: str | None = None,
        selected_sources: Optional[set[str]] = None,
    ):
        """Configure a harvest run.

        Args:
            db:                   The database manager used for cache reads and result writes.
            targets:              Ordered list of data sources to query.  Defaults to a
                                  ``PlaceholderTarget`` when ``None`` or empty.
            retry_days:           Number of days to suppress re-trying a previously failed ISBN.
            max_workers:          Number of parallel threads for lookup (1 = sequential).
            call_number_mode:     ``"lccn"``, ``"nlmcn"``, or ``"both"`` (default).
            bypass_retry_isbns:   ISBNs that should be re-tried even within the retry window.
            bypass_cache_isbns:   ISBNs that should skip the cache check and always hit targets.
            progress_cb:          Optional ``(event, payload)`` callback for progress events.
            cancel_check:         Optional callable returning ``True`` when the run should stop.
            stop_rule:            When to stop querying further targets after a hit (see module docs).
            db_only:              When ``True``, only the local DB is consulted; no API calls are made.
            both_stop_policy:     Deprecated; use ``stop_rule`` instead.
            selected_sources:     Restrict cache reads to rows from these source names only.
        """
        self.db = db
        self.retry_days = retry_days
        self.bypass_retry_isbns = set(bypass_retry_isbns or [])
        self.bypass_cache_isbns = set(bypass_cache_isbns or [])
        self.progress_cb = progress_cb
        self.cancel_check = cancel_check
        self.call_number_mode = self._normalize_call_number_mode(call_number_mode)
        self.stop_rule = self._normalize_stop_rule(stop_rule)
        self.max_workers = max(1, int(max_workers))
        # In db_only mode API targets are never consulted; bypass_cache_isbns is ignored.
        self.db_only = db_only
        self.selected_sources = {
            str(source).strip()
            for source in (selected_sources or set())
            if str(source).strip()
        }

        # If no real targets wired yet, keep Sprint-2 behavior with a placeholder.
        self.targets: list[HarvestTarget] = targets if targets else [PlaceholderTarget()]
        if not self.selected_sources:
            self.selected_sources = {
                str(getattr(target, "name", "")).strip()
                for target in self.targets
                if str(getattr(target, "name", "")).strip() and getattr(target, "name", "") != "(placeholder)"
            }

    def _allowed_cached_sources(self) -> Optional[set[str]]:
        """Return the source whitelist used when reading from the DB cache.

        Returns ``None`` (no filter) when ``selected_sources`` is empty,
        meaning any cached row is acceptable regardless of which target produced
        it.  When sources are configured, only cached rows from those sources
        count as a hit so the orchestrator will still query the missing sources.
        """
        return self.selected_sources or None

    def _emit(self, event: str, payload: dict) -> None:
        """Fire a named progress event to the registered callback, if any.

        Args:
            event:   Short string identifier (e.g. ``"isbn_start"``, ``"cached"``).
            payload: Arbitrary dict with event-specific data for the UI.
        """
        if self.progress_cb:
            self.progress_cb(event, payload)

    def _check_cancelled(self) -> None:
        """Raise ``HarvestCancelled`` if the caller has signalled a stop."""
        if self.cancel_check and self.cancel_check():
            raise HarvestCancelled("Harvest cancelled by user")

    @staticmethod
    def _normalize_call_number_mode(mode: str) -> str:
        """Validate and normalise *mode* to a known ``call_number_mode`` value.

        Falls back to ``"both"`` for any unrecognised input.
        """
        mode_normalized = (mode or "").strip().lower()
        if mode_normalized in {"lccn", "nlmcn", "both"}:
            return mode_normalized
        return "both"

    @staticmethod
    def _normalize_stop_rule(rule: str) -> str:
        """Validate and normalise *rule* to a known ``stop_rule`` value.

        Falls back to ``"stop_either"`` for any unrecognised input.
        """
        normalized = (rule or "").strip().lower()
        if normalized in {"stop_either", "stop_lccn", "stop_nlmcn", "continue_both"}:
            return normalized
        return "stop_either"

    def _filter_result_by_mode(self, result: TargetResult) -> TargetResult:
        """Strip call-number fields from *result* that are outside the configured mode.

        When ``call_number_mode`` is ``"lccn"`` and the result only contains an
        NLMCN, the result is converted to a failure so the orchestrator knows
        to keep looking.  The reverse applies for ``"nlmcn"`` mode.  In
        ``"both"`` mode the result is returned unchanged.
        """
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

    @staticmethod
    def _classify_other_error_target(error_text: str) -> str:
        """Bucket an error string into ``"z3950_unsupported"``, ``"offline"``, or ``"other"``."""
        e = (error_text or "").strip().lower()
        if "z39.50 support not available" in e:
            return "z3950_unsupported"
        if (
            "remote end closed connection without response" in e
            or "timed out" in e
            or "connection refused" in e
            or "connection reset" in e
            or "temporary failure in name resolution" in e
            or "name or service not known" in e
        ):
            return "offline"
        return "other"

    def _build_failed_payload(
        self,
        *,
        isbn: str,
        last_target: Optional[str],
        last_error: Optional[str],
        not_found_targets: list[str],
        other_errors: list[tuple[str, str]],
    ) -> dict:
        """Build the ``"failed"`` event payload dict for the progress callback.

        Classifies errors from each target into three categories so the UI can
        display them with appropriate context (e.g. show a Z39.50 warning once
        instead of per-target).
        """
        z3950_unsupported_targets: list[str] = []
        offline_targets: list[str] = []
        other_error_items: list[str] = []

        for target_name, err in other_errors:
            bucket = self._classify_other_error_target(err)
            if bucket == "z3950_unsupported":
                z3950_unsupported_targets.append(target_name)
            elif bucket == "offline":
                offline_targets.append(target_name)
            else:
                other_error_items.append(f"{target_name}: {err}")

        return {
            "isbn": isbn,
            "last_target": last_target,
            "last_error": last_error,
            "attempt_type": self.call_number_mode,
            "not_found_targets": not_found_targets,
            "z3950_unsupported_targets": z3950_unsupported_targets,
            "offline_targets": offline_targets,
            "other_errors": other_error_items,
        }

    def _should_stop_with_found(self, has_lccn: bool, has_nlmcn: bool) -> bool:
        """Return ``True`` when the accumulated results satisfy the configured stop rule.

        Used both to short-circuit the target loop and to decide whether a
        partial result (e.g. LCCN found but no NLMCN in ``continue_both`` mode)
        should be treated as a success or a failure.

        Args:
            has_lccn:  Whether an LC call number has been found so far.
            has_nlmcn: Whether an NLM call number has been found so far.
        """
        if self.call_number_mode == "lccn":
            return has_lccn
        if self.call_number_mode == "nlmcn":
            return has_nlmcn
        if self.stop_rule == "stop_lccn":
            return has_lccn
        if self.stop_rule == "stop_nlmcn":
            return has_nlmcn
        if self.stop_rule == "stop_either":
            return has_lccn or has_nlmcn
        return has_lccn and has_nlmcn  # continue_both

    def _required_types(self, has_lccn: bool, has_nlmcn: bool) -> list[str]:
        """Return the call-number types still needed to satisfy the stop rule.

        When the returned list is empty the orchestrator should break out of
        the target loop (the stop condition is already met).

        Args:
            has_lccn:  Whether an LC call number has been found.
            has_nlmcn: Whether an NLM call number has been found.

        Returns:
            A list containing ``"lccn"`` and/or ``"nlmcn"`` that are still
            missing, or an empty list if the stop rule is already satisfied.
        """
        if self.call_number_mode == "lccn":
            return [] if has_lccn else ["lccn"]
        if self.call_number_mode == "nlmcn":
            return [] if has_nlmcn else ["nlmcn"]
        if self.stop_rule == "stop_lccn":
            return [] if has_lccn else ["lccn"]
        if self.stop_rule == "stop_nlmcn":
            return [] if has_nlmcn else ["nlmcn"]
        if self.stop_rule == "stop_either":
            return [] if (has_lccn or has_nlmcn) else ["lccn", "nlmcn"]
        needed: list[str] = []  # continue_both
        if not has_lccn:
            needed.append("lccn")
        if not has_nlmcn:
            needed.append("nlmcn")
        return needed

    @staticmethod
    def _type_label(call_number_type: str) -> str:
        """Return the human-readable label for a call_number_type key (``"lccn"`` → ``"LCCN"``)."""
        return "LCCN" if call_number_type == "lccn" else "NLMCN"

    def _emit_attempt_failure(
        self,
        *,
        isbn: str,
        target: str,
        call_number_type: str,
        reason: str,
        attempted_date: Optional[str] = None,
    ) -> None:
        self._emit(
            "attempt_failed",
            {
                "isbn": isbn,
                "target": target,
                "attempt_type": call_number_type,
                "attempted_date": attempted_date or now_datetime_str(),
                "reason": reason,
            },
        )

    @staticmethod
    def _build_record(
        *,
        isbn: str,
        lccn: Optional[str],
        lccn_source: Optional[str],
        nlmcn: Optional[str],
        nlmcn_source: Optional[str],
    ) -> MainRecord:
        """Construct a ``MainRecord`` from harvested call-number data.

        The combined ``source`` field is assembled from ``lccn_source`` and
        ``nlmcn_source`` (deduplicated, joined with ``" + "``).
        """
        combined_sources: list[str] = []
        for value in (lccn_source, nlmcn_source):
            text = str(value or "").strip()
            if text and text not in combined_sources:
                combined_sources.append(text)
        return MainRecord(
            isbn=isbn,
            lccn=lccn,
            lccn_source=lccn_source,
            nlmcn=nlmcn,
            nlmcn_source=nlmcn_source,
            source=" + ".join(combined_sources) if combined_sources else None,
        )

    def _emit_result(self, event_name: str, *, isbn: str, target: str, record: MainRecord) -> None:
        """Emit a success/cached event with a standardised payload dict."""
        self._emit(
            event_name,
            {
                "isbn": isbn,
                "target": target,
                "source": record.source,
                "lccn": record.lccn,
                "lccn_source": record.lccn_source,
                "nlmcn": record.nlmcn,
                "nlmcn_source": record.nlmcn_source,
            },
        )

    def _process_isbn_internal(
        self,
        isbn: str,
        *,
        dry_run: bool,
        pending_main: list[MainRecord],
        pending_attempted: list[tuple[str, Optional[str], str, Optional[str], Optional[str]]],
    ) -> ProcessOutcome:
        """Core single-ISBN processing logic shared by sequential and parallel paths.

        Execution order:
          1. Emit ``isbn_start``.
          2. Resolve canonical (lowest) ISBN via ``linked_isbns``.
          3. Check the DB cache (skipped if ISBN is in ``bypass_cache_isbns``).
          4. If cache satisfies the stop rule, emit ``cached`` / ``linked_cached``
             and return immediately without touching any target.
          5. In ``db_only`` mode, emit ``not_in_local_catalog`` and return.
          6. Walk ``self.targets`` in order; for each:
             - Skip if the ISBN is within the retry suppression window for all
               required call-number types (unless in ``bypass_retry_isbns``).
             - Call ``target.lookup(isbn)`` and apply ``_filter_result_by_mode``.
             - Accumulate the best LCCN / NLMCN seen across all targets.
             - Break as soon as the stop rule is satisfied.
          7. Evaluate the accumulated state and return the appropriate outcome.

        Args:
            isbn:             ISBN to process (may be non-canonical; resolved internally).
            dry_run:          When ``True``, results are computed but not written.
            pending_main:     Mutable list; successful ``MainRecord``s are appended here.
            pending_attempted: Mutable list; failed-attempt tuples are appended here.

        Returns:
            A ``ProcessOutcome`` with status, optional record, and attempt rows.
        """
        self._check_cancelled()
        self._emit("isbn_start", {"isbn": isbn})

        # Resolve to the canonical (lowest) ISBN for all DB reads/writes.
        # API lookups still use the original isbn so the request matches the input.
        store_isbn = self.db.get_lowest_isbn(isbn)
        is_linked_input = store_isbn != isbn

        cached_rec = None
        found_lccn: Optional[str] = None
        found_lccn_source: Optional[str] = None
        found_nlmcn: Optional[str] = None
        found_nlmcn_source: Optional[str] = None
        attempted_rows: list[tuple[str, Optional[str], str, Optional[str], Optional[str]]] = []

        if isbn not in self.bypass_cache_isbns:
            cached_rec = self.db.get_main(store_isbn, allowed_sources=self._allowed_cached_sources())
        if cached_rec is not None:
            found_lccn = cached_rec.lccn
            found_lccn_source = getattr(cached_rec, "lccn_source", None) or cached_rec.source
            found_nlmcn = cached_rec.nlmcn
            found_nlmcn_source = getattr(cached_rec, "nlmcn_source", None) or cached_rec.source
            if self._should_stop_with_found(bool(found_lccn), bool(found_nlmcn)):
                record = self._build_record(
                    isbn=store_isbn,
                    lccn=found_lccn,
                    lccn_source=found_lccn_source,
                    nlmcn=found_nlmcn,
                    nlmcn_source=found_nlmcn_source,
                )
                event_name = "linked_cached" if is_linked_input else "cached"
                self._emit_result(event_name, isbn=isbn, target=record.source or "Cache", record=record)
                return ProcessOutcome("cached", record, tuple())

        # db_only mode: never hit any API target. If we reach here the ISBN was
        # not in the local DB (or had insufficient data). Report and stop.
        if self.db_only:
            self._emit("not_in_local_catalog", {"isbn": isbn})
            return ProcessOutcome("not_in_local_catalog", None, tuple())

        # No cache hit: walk the selected targets and remember the best data we
        # see so stop rules can decide whether to continue or exit early.
        last_error: Optional[str] = None
        last_target: Optional[str] = None
        not_found_targets: list[str] = []
        other_errors: list[tuple[str, str]] = []
        skipped_retry_targets: list[str] = []
        
        # Accumulate results for "both" mode — seed from cache so mid-run
        # decisions see everything already known.
        best_lccn: Optional[str] = found_lccn
        best_lccn_source: Optional[str] = found_lccn_source
        best_nlmcn: Optional[str] = found_nlmcn
        best_nlmcn_source: Optional[str] = found_nlmcn_source

        for target in self.targets:
            self._check_cancelled()
            last_target = getattr(target, "name", target.__class__.__name__)
            required_types = self._required_types(bool(best_lccn), bool(best_nlmcn))
            if not required_types:
                break

            if isbn not in self.bypass_retry_isbns and all(
                self.db.should_skip_retry(store_isbn, last_target, call_number_type, retry_days=self.retry_days)
                for call_number_type in required_types
            ):
                skipped_retry_targets.append(last_target)
                continue

            self._emit("target_start", {"isbn": isbn, "target": last_target})
            raw_result = target.lookup(isbn)
            attempt_time = now_datetime_str()
            source_name = raw_result.source or last_target

            if self.call_number_mode == "lccn":
                result = self._filter_result_by_mode(raw_result)
            elif self.call_number_mode == "nlmcn":
                result = self._filter_result_by_mode(raw_result)
            else:
                result = raw_result

            if result.success:
                if result.lccn and not best_lccn:
                    best_lccn = result.lccn
                    best_lccn_source = result.source or last_target
                if result.nlmcn and not best_nlmcn:
                    best_nlmcn = result.nlmcn
                    best_nlmcn_source = result.source or last_target

                should_stop = False
                
                # Evaluate stop rule if in both mode, otherwise break immediately
                if self.call_number_mode == "both":
                    if self.stop_rule == "stop_either":
                        should_stop = True
                    elif self.stop_rule == "stop_lccn" and best_lccn:
                        should_stop = True
                    elif self.stop_rule == "stop_nlmcn" and best_nlmcn:
                        should_stop = True
                    elif self.stop_rule == "continue_both" and best_lccn and best_nlmcn:
                        should_stop = True
                else:
                    should_stop = True

                if should_stop:
                    break
                continue

            # failure from this target; continue
            last_error = result.error or "Unknown error"
            err = (result.error or "").strip()
            if err.lower().startswith("no records found in"):
                not_found_targets.append(last_target)
            elif err:
                other_errors.append((last_target, err))
            for call_number_type in required_types:
                reason = err or f"No {self._type_label(call_number_type)} call number"
                attempted_rows.append((store_isbn, last_target, call_number_type, attempt_time, reason))
                self._emit_attempt_failure(
                    isbn=isbn,
                    target=last_target,
                    call_number_type=call_number_type,
                    attempted_date=attempt_time,
                    reason=reason,
                )

        has_partial_result = bool(best_lccn or best_nlmcn)
        requires_both_for_success = (
            self.call_number_mode == "both" and self.stop_rule == "continue_both"
        )
        has_complete_result = self._should_stop_with_found(bool(best_lccn), bool(best_nlmcn))

        # Check if we accumulated a fully successful result.
        if has_partial_result and (not requires_both_for_success or has_complete_result):
            rec = self._build_record(
                isbn=store_isbn,
                lccn=best_lccn,
                lccn_source=best_lccn_source,
                nlmcn=best_nlmcn,
                nlmcn_source=best_nlmcn_source,
            )
            event_name = "linked_success" if is_linked_input else "success"
            self._emit_result(event_name, isbn=isbn, target=rec.source or "Unknown", record=rec)

            if dry_run:
                rec = None
            else:
                pending_main.append(rec)
            if not dry_run and attempted_rows:
                pending_attempted.extend(attempted_rows)

            return ProcessOutcome("success", rec, tuple(attempted_rows))

        if has_partial_result:
            rec = self._build_record(
                isbn=store_isbn,
                lccn=best_lccn,
                lccn_source=best_lccn_source,
                nlmcn=best_nlmcn,
                nlmcn_source=best_nlmcn_source,
            )
            found_labels = []
            missing_labels = []
            if best_lccn:
                found_labels.append("LCCN")
            else:
                missing_labels.append("LCCN")
            if best_nlmcn:
                found_labels.append("NLMCN")
            else:
                missing_labels.append("NLMCN")
            last_error = (
                f"Found {' and '.join(found_labels)} only; missing {' and '.join(missing_labels)}"
            )

            if not dry_run:
                pending_main.append(rec)
                if attempted_rows:
                    pending_attempted.extend(attempted_rows)

            self._emit(
                "failed",
                self._build_failed_payload(
                    isbn=isbn,
                    last_target=last_target,
                    last_error=last_error,
                    not_found_targets=not_found_targets,
                    other_errors=other_errors,
                ),
            )
            return ProcessOutcome("failed", rec if dry_run else None, tuple(attempted_rows))

        if skipped_retry_targets and not not_found_targets and not other_errors:
            self._emit(
                "skip_retry",
                {
                    "isbn": isbn,
                    "retry_days": self.retry_days,
                    "targets": skipped_retry_targets,
                    "attempt_type": self.call_number_mode,
                },
            )
            return ProcessOutcome("skip_retry", None, tuple())

        if not_found_targets and not other_errors:
            last_error = "Not found in: " + ", ".join(not_found_targets)
        elif not_found_targets and other_errors:
            last_error = (
                "Not found in: "
                + ", ".join(not_found_targets)
                + " | Other errors: "
                + " ; ".join(f"{t}: {e}" for t, e in other_errors)
            )
        elif other_errors:
            last_error = " ; ".join(f"{t}: {e}" for t, e in other_errors)

        self._emit(
            "failed",
            self._build_failed_payload(
                isbn=isbn,
                last_target=last_target,
                last_error=last_error,
                not_found_targets=not_found_targets,
                other_errors=other_errors,
            ),
        )
        if not dry_run and attempted_rows:
            pending_attempted.extend(attempted_rows)
        return ProcessOutcome("failed", None, tuple(attempted_rows))


    def process_isbn(
        self,
        isbn: str,
        *,
        dry_run: bool,
        pending_main: list[MainRecord],
        pending_attempted: list[tuple[str, Optional[str], str, Optional[str], Optional[str]]],
        pending_linked: Optional[list[tuple[str, str]]] = None,
    ) -> str:
        """Process a single ISBN and stage the result into the provided batch buffers.

        This is the public single-ISBN entry point.  It delegates to
        ``_process_isbn_internal`` and then queues any linked-ISBN pair so the
        batch flush can rewrite rows stored under non-canonical ISBNs.

        Args:
            isbn:             The ISBN to harvest.
            dry_run:          When ``True``, no records are added to the buffers.
            pending_main:     Buffer for successful ``MainRecord`` objects.
            pending_attempted: Buffer for failed-lookup tuples.
            pending_linked:   Optional buffer for (lowest, other) ISBN pairs.

        Returns:
            The outcome status string (``"success"``, ``"failed"``, ``"cached"``,
            ``"skip_retry"``, or ``"not_in_local_catalog"``).
        """
        outcome = self._process_isbn_internal(
            isbn,
            dry_run=dry_run,
            pending_main=pending_main,
            pending_attempted=pending_attempted,
        )
        # If this ISBN resolves to a lower canonical already in linked_isbns,
        # queue the pair so the batch flush rewrites any old rows stored under isbn.
        if pending_linked is not None:
            store_isbn = self.db.get_lowest_isbn(isbn)
            if store_isbn != isbn:
                pending_linked.append((store_isbn, isbn))
        return outcome.status

    def process_isbn_group(
        self,
        primary_isbn: str,
        linked_isbns: list[str],
        *,
        dry_run: bool,
        pending_main: list[MainRecord],
        pending_attempted: list[tuple[str, Optional[str], str, Optional[str], Optional[str]]],
        pending_linked: list[tuple[str, str]],
    ) -> str:
        """Try primary_isbn then each linked variant in order until a call number is found.

        On the first success:
          - The result is stored under ``primary_isbn`` (same as a normal harvest).
          - Cross-reference records are queued for every OTHER isbn in the group
            (source tagged as ``"Linked from <primary_isbn>"``).

        On total failure across the whole group:
          - The attempted table entry is written for ``primary_isbn`` only.
          - Linked variants are NOT added to attempted (they may succeed in a
            future run when paired with a different primary).
        """
        all_isbns = [primary_isbn] + [iv for iv in linked_isbns if iv != primary_isbn]

        # Use the numerically lowest ISBN as the canonical key for DB writes.
        # Trailing ISBN checksum letters are treated like 9 for ordering.
        canonical_isbn = pick_lowest_isbn(all_isbns)

        winning_record: Optional[MainRecord] = None
        winning_isbn: Optional[str] = None

        for candidate in all_isbns:
            self._check_cancelled()
            outcome = self._process_isbn_internal(
                candidate,
                dry_run=dry_run,
                pending_main=[],          # we collect the result ourselves below
                pending_attempted=[],     # ditto
            )
            if outcome.status in ("success", "cached"):
                winning_record = outcome.record
                winning_isbn = candidate
                break

        if winning_record is None:
            # All candidates exhausted — write attempted under the canonical ISBN.
            self._process_isbn_internal(
                canonical_isbn,
                dry_run=dry_run,
                pending_main=pending_main,
                pending_attempted=pending_attempted,
            )
            return "failed"

        # --- We have a result.  Write under canonical_isbn. ---
        source_label = winning_record.source or winning_isbn or "Linked ISBN"

        canonical_rec = self._build_record(
            isbn=canonical_isbn,
            lccn=winning_record.lccn,
            lccn_source=winning_record.lccn_source or (
                f"Linked from {winning_isbn}" if winning_isbn != canonical_isbn else None
            ),
            nlmcn=winning_record.nlmcn,
            nlmcn_source=winning_record.nlmcn_source or (
                f"Linked from {winning_isbn}" if winning_isbn != canonical_isbn else None
            ),
        )
        if not dry_run:
            pending_main.append(canonical_rec)

        self._emit_result(
            "success" if winning_isbn == canonical_isbn else "linked_success",
            isbn=canonical_isbn, target=source_label, record=canonical_rec,
        )

        # Only record the linked mapping; do not keep non-canonical ISBN rows in main.
        linked_pairs: list[tuple[str, str]] = [
            (canonical_isbn, other_isbn)
            for other_isbn in all_isbns
            if other_isbn != canonical_isbn
        ]

        if not dry_run:
            pending_linked.extend(linked_pairs)

        return "success"

    def _detect_implicit_linked_isbns(
        self,
        pending_main: list[MainRecord],
        pending_linked: list[tuple[str, str]],
    ) -> None:
        """Infer implicit linked-ISBN groups from shared call numbers in the current batch.

        When two or more ISBNs in ``pending_main`` (or already in the DB)
        resolve to the same LCCN or NLMCN they are almost certainly different
        editions of the same work.  This method clusters such ISBNs, picks the
        numerically lowest one as the canonical key, rewrites ``pending_main``
        in-place so all records use the canonical ISBN, and appends
        ``(canonical, other)`` pairs to ``pending_linked`` for the DB flush.

        Uses a union-find algorithm to cluster ISBNs that share the same LC or
        NLM call number (either within the current batch or already present in
        the DB).  The lowest ISBN in each cluster becomes the canonical key and
        all others are added to ``pending_linked`` as ``(canonical, other)``
        pairs.  The ``pending_main`` list is rewritten in-place so every
        record is stored under its canonical ISBN.

        Args:
            pending_main:   In-flight main records (mutated in place).
            pending_linked: In-flight linked-ISBN pairs (extended in place).
        """
        if not pending_main:
            return

        # Group ISBNs by shared call number signatures.
        record_by_isbn = {record.isbn: record for record in pending_main}
        signatures: dict[tuple[str, str], set[str]] = {}
        for record in pending_main:
            if record.lccn:
                signatures.setdefault(("lccn", record.lccn), set()).add(record.isbn)
            if record.nlmcn:
                signatures.setdefault(("nlmcn", record.nlmcn), set()).add(record.isbn)

        # Find any existing ISBNs in the DB that share the same call numbers.
        existing_records: dict[str, MainRecord] = {}
        for call_type, call_number in list(signatures.keys()):
            db_isbns = self.db.find_isbns_by_call_number(call_type, call_number)
            for isbn in db_isbns:
                signatures[(call_type, call_number)].add(isbn)
                if isbn not in existing_records and isbn not in record_by_isbn:
                    existing = self.db.get_main(isbn)
                    if existing is not None:
                        existing_records[isbn] = existing

        # Union-find (disjoint-set) data structure for grouping ISBNs that
        # share a call number.  Path compression is applied in find() so
        # repeated queries stay O(α(n)) amortised.
        parent: dict[str, str] = {}

        def find(isbn: str) -> str:
            """Return the root representative of *isbn*'s connected component."""
            parent.setdefault(isbn, isbn)
            while parent[isbn] != isbn:
                parent[isbn] = parent[parent[isbn]]  # path compression (halving)
                isbn = parent[isbn]
            return isbn

        def union(a: str, b: str) -> None:
            """Merge the components containing *a* and *b*."""
            root_a = find(a)
            root_b = find(b)
            if root_a != root_b:
                parent[root_b] = root_a

        for isbns in signatures.values():
            isbns = list(isbns)
            for i in range(1, len(isbns)):
                union(isbns[0], isbns[i])

        components: dict[str, set[str]] = {}
        for isbn in parent:
            root = find(isbn)
            components.setdefault(root, set()).add(isbn)

        # Only keep groups where more than one ISBN share a call number.
        isbn_to_canonical: dict[str, str] = {}
        for group in components.values():
            if len(group) < 2:
                continue
            canonical_isbn = pick_lowest_isbn(group)
            for other_isbn in group:
                if other_isbn != canonical_isbn:
                    isbn_to_canonical[other_isbn] = canonical_isbn
                    pending_linked.append((canonical_isbn, other_isbn))

        if not isbn_to_canonical:
            return

        # Deduplicate pairs while preserving insertion order (Python 3.7+ dict guarantee)
        pending_linked[:] = list(dict.fromkeys(pending_linked))

        def _merge_records(primary: MainRecord, secondary: MainRecord) -> MainRecord:
            return self._build_record(
                isbn=primary.isbn,
                lccn=primary.lccn or secondary.lccn,
                lccn_source=primary.lccn_source or secondary.lccn_source,
                nlmcn=primary.nlmcn or secondary.nlmcn,
                nlmcn_source=primary.nlmcn_source or secondary.nlmcn_source,
            )

        canonical_records: dict[str, MainRecord] = {}
        for record in pending_main:
            canonical = isbn_to_canonical.get(record.isbn)
            if not canonical:
                canonical_records[record.isbn] = record
                continue

            if canonical in canonical_records:
                canonical_records[canonical] = _merge_records(canonical_records[canonical],
                                                             self._build_record(
                                                                 isbn=canonical,
                                                                 lccn=record.lccn,
                                                                 lccn_source=record.lccn_source,
                                                                 nlmcn=record.nlmcn,
                                                                 nlmcn_source=record.nlmcn_source,
                                                             ))
            else:
                canonical_records[canonical] = self._build_record(
                    isbn=canonical,
                    lccn=record.lccn,
                    lccn_source=record.lccn_source,
                    nlmcn=record.nlmcn,
                    nlmcn_source=record.nlmcn_source,
                )

        for isbn, canonical in isbn_to_canonical.items():
            if canonical not in canonical_records and isbn in existing_records:
                canonical_records[canonical] = self._build_record(
                    isbn=canonical,
                    lccn=existing_records[isbn].lccn,
                    lccn_source=existing_records[isbn].lccn_source,
                    nlmcn=existing_records[isbn].nlmcn,
                    nlmcn_source=existing_records[isbn].nlmcn_source,
                )
            elif canonical in canonical_records and isbn in existing_records:
                canonical_records[canonical] = _merge_records(canonical_records[canonical],
                                                             self._build_record(
                                                                 isbn=canonical,
                                                                 lccn=existing_records[isbn].lccn,
                                                                 lccn_source=existing_records[isbn].lccn_source,
                                                                 nlmcn=existing_records[isbn].nlmcn,
                                                                 nlmcn_source=existing_records[isbn].nlmcn_source,
                                                             ))

        pending_main[:] = list(canonical_records.values())

    def run(self, isbns: list[str], *, dry_run: bool,
            linked: Optional[dict[str, list[str]]] = None) -> HarvestSummary:
        """Run a harvest batch over *isbns* and return aggregate statistics.

        Processes each ISBN (or ISBN group if ``linked`` is provided), staging
        results in memory and flushing to SQLite in transaction chunks sized
        proportionally to the batch.  A final flush is always performed after
        the last ISBN.

        Args:
            isbns:   Ordered list of ISBNs to harvest.
            dry_run: When ``True``, targets are queried but no DB writes occur.
            linked:  Optional mapping of primary ISBN → list of variant ISBNs.
                     When present, each group is tried together via
                     ``process_isbn_group``.

        Returns:
            A ``HarvestSummary`` with counts for all outcome categories.

        Raises:
            HarvestCancelled: If ``cancel_check`` returns ``True`` mid-run.
        """

        cached_hits = 0
        skipped_recent_fail = 0
        attempted = 0
        successes = 0
        failures = 0
        not_in_local_catalog = 0

        # Batching buffers — accumulated writes are flushed together for performance.
        pending_main: list[MainRecord] = []
        pending_attempted: list[tuple[str, Optional[str], str, Optional[str], Optional[str]]] = []
        pending_linked: list[tuple[str, str]] = []

        # Scale flush frequency with batch size: flush every ~1% of input ISBNs
        # but clamp between DEFAULT_FLUSH_BATCH_SIZE and 1000 rows.
        dynamic_batch_size = max(self.DEFAULT_FLUSH_BATCH_SIZE, min(1000, len(isbns) // 100))

        def flush() -> None:
            """Flush buffered DB writes in a single atomic transaction.

            Filters ``pending_attempted`` to remove entries whose ISBN (or
            isbn+type pair in ``continue_both`` mode) already has a success
            record in ``pending_main`` so a successful result from this batch
            doesn't leave a stale failure row behind.  Then writes linked-ISBN
            rewrites, main records, filtered attempted rows, and linked-ISBN
            pairs inside a single ``transaction()`` call.
            """
            wrote_main = len(pending_main)
            if dry_run:
                # In dry-run mode results are computed but never persisted
                pending_main.clear()
                pending_attempted.clear()
                pending_linked.clear()
                return

            if not pending_main and not pending_attempted and not pending_linked:
                return

            if self.call_number_mode == "both" and self.stop_rule != "continue_both":
                # In this mode a success for any type clears all attempted rows for the ISBN
                successful_isbns = {record.isbn for record in pending_main}
                filtered_attempted = [
                    row for row in pending_attempted if row[0] not in successful_isbns
                ]
            else:
                # In single-type or continue_both mode, clear only attempted rows
                # whose exact (isbn, call_number_type) pair succeeded this batch
                successful_pairs = {
                    (record.isbn, call_type)
                    for record in pending_main
                    for call_type in self.db._record_success_types(record)
                }
                filtered_attempted = [
                    row for row in pending_attempted if (row[0], row[2]) not in successful_pairs
                ]

            # Detect implicit linked ISBNs when the same call number appears across
            # different ISBNs in the current batch or already in the DB.
            self._detect_implicit_linked_isbns(pending_main, pending_linked)

            wrote_attempted = len(filtered_attempted)

            with self.db.transaction() as conn:
                if pending_linked:
                    self.db.rewrite_to_lowest_isbn_many(conn, pending_linked)
                self.db.upsert_main_many(conn, pending_main, clear_attempted_on_success=True)
                self.db.upsert_attempted_many(conn, filtered_attempted)
                self.db.upsert_linked_isbns_many(conn, pending_linked)

            pending_main.clear()
            pending_attempted.clear()
            pending_linked.clear()
            self._emit("db_flush", {"main": wrote_main, "attempted": wrote_attempted})

        _linked = linked or {}

        def _one(isbn: str) -> str:
            # NOTE: This will append into pending_main / pending_attempted.
            # That is NOT thread-safe, so we only use threads if max_workers == 1.
            # Parallel mode is handled below with a safe path.
            variants = _linked.get(isbn)
            if variants:
                return self.process_isbn_group(
                    isbn,
                    variants,
                    dry_run=dry_run,
                    pending_main=pending_main,
                    pending_attempted=pending_attempted,
                    pending_linked=pending_linked,
                )
            return self.process_isbn(
                isbn,
                dry_run=dry_run,
                pending_main=pending_main,
                pending_attempted=pending_attempted,
                pending_linked=pending_linked,
            )

        if self.max_workers <= 1:
            # --- sequential (your current behavior) ---
            for isbn in isbns:
                self._check_cancelled()
                status = _one(isbn)

                if (len(pending_main) + len(pending_attempted)) >= dynamic_batch_size:
                    flush()

                if status == "cached":
                    cached_hits += 1
                elif status == "skip_retry":
                    skipped_recent_fail += 1
                elif status == "not_in_local_catalog":
                    not_in_local_catalog += 1
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
                    "not_in_local_catalog": not_in_local_catalog,
                })

        else:
            # --- parallel mode (SAFE): threads do lookup only, main thread writes DB in batches ---
            def worker(isbn: str):
                self._check_cancelled()
                # Only compute outcome; do NOT touch shared pending_* lists here.
                # Also: emitting progress from threads is okay only if your GUI callback is thread-safe.
                self._emit("isbn_start", {"isbn": isbn})

                variants = _linked.get(isbn)
                if variants:
                    local_main: list[MainRecord] = []
                    local_attempted: list[tuple[str, Optional[str], str, Optional[str], Optional[str]]] = []
                    local_linked: list[tuple[str, str]] = []
                    status = self.process_isbn_group(
                        isbn,
                        variants,
                        dry_run=dry_run,
                        pending_main=local_main,
                        pending_attempted=local_attempted,
                        pending_linked=local_linked,
                    )
                    return status, local_main, local_attempted, local_linked

                cached_rec = None
                found_lccn: Optional[str] = None
                found_lccn_source: Optional[str] = None
                found_nlmcn: Optional[str] = None
                found_nlmcn_source: Optional[str] = None
                if isbn not in self.bypass_cache_isbns:
                    store_isbn_for_cache = self.db.get_lowest_isbn(isbn)
                    cached_rec = self.db.get_main(store_isbn_for_cache, allowed_sources=self._allowed_cached_sources())
                    is_linked_input = store_isbn_for_cache != isbn
                else:
                    is_linked_input = False
                if cached_rec is not None:
                    found_lccn = cached_rec.lccn
                    found_lccn_source = getattr(cached_rec, "lccn_source", None) or cached_rec.source
                    found_nlmcn = cached_rec.nlmcn
                    found_nlmcn_source = getattr(cached_rec, "nlmcn_source", None) or cached_rec.source
                    if self._should_stop_with_found(bool(found_lccn), bool(found_nlmcn)):
                        event_name = "linked_cached" if is_linked_input else "cached"
                        self._emit(event_name, {
                            "isbn": isbn,
                            "source": cached_rec.source,
                            "lccn": cached_rec.lccn,
                            "lccn_source": found_lccn_source,
                            "nlmcn": cached_rec.nlmcn,
                            "nlmcn_source": found_nlmcn_source,
                        })
                        return ("cached", [], [], [])

                # db_only: skip all API targets
                if self.db_only:
                    self._emit("not_in_local_catalog", {"isbn": isbn})
                    return ("not_in_local_catalog", [], (), [])

                last_error = None
                last_target = None
                not_found_targets: list[str] = []
                other_errors: list[tuple[str, str]] = []
                skipped_retry_targets: list[str] = []
                attempted_rows: list[tuple[str, Optional[str], str, Optional[str], Optional[str]]] = []

                # Accumulate best results and apply stop_rule (mirrors process_isbn)
                best_lccn: Optional[str] = found_lccn
                best_lccn_source: Optional[str] = found_lccn_source
                best_nlmcn: Optional[str] = found_nlmcn
                best_nlmcn_source: Optional[str] = found_nlmcn_source

                for target in self.targets:
                    self._check_cancelled()
                    last_target = getattr(target, "name", target.__class__.__name__)
                    required_types = self._required_types(bool(best_lccn), bool(best_nlmcn))
                    if not required_types:
                        break

                    if isbn not in self.bypass_retry_isbns and all(
                        self.db.should_skip_retry(
                            isbn,
                            last_target,
                            call_number_type,
                            retry_days=self.retry_days,
                        )
                        for call_number_type in required_types
                    ):
                        skipped_retry_targets.append(last_target)
                        continue

                    self._emit("target_start", {"isbn": isbn, "target": last_target})

                    raw_result = target.lookup(isbn)
                    attempt_time = now_datetime_str()
                    result = self._filter_result_by_mode(raw_result) if self.call_number_mode != "both" else raw_result
                    if result.success:
                        if result.lccn and not best_lccn:
                            best_lccn = result.lccn
                            best_lccn_source = result.source or last_target
                        if result.nlmcn and not best_nlmcn:
                            best_nlmcn = result.nlmcn
                            best_nlmcn_source = result.source or last_target

                        should_stop = False
                        if self.call_number_mode == "both":
                            if self.stop_rule == "stop_either":
                                should_stop = True
                            elif self.stop_rule == "stop_lccn" and best_lccn:
                                should_stop = True
                            elif self.stop_rule == "stop_nlmcn" and best_nlmcn:
                                should_stop = True
                            elif self.stop_rule == "continue_both" and best_lccn and best_nlmcn:
                                should_stop = True
                        else:
                            should_stop = True

                        if should_stop:
                            break

                        # Not stopping yet — continue to next target for the missing counterpart.
                        continue

                    last_error = result.error or "Unknown error"
                    err = (result.error or "").strip()
                    if err.lower().startswith("no records found in"):
                        not_found_targets.append(last_target)
                    elif err:
                        other_errors.append((last_target, err))
                    for call_number_type in required_types:
                        reason = err or f"No {self._type_label(call_number_type)} call number"
                        attempted_rows.append((isbn, last_target, call_number_type, attempt_time, reason))
                        self._emit_attempt_failure(
                            isbn=isbn,
                            target=last_target,
                            call_number_type=call_number_type,
                            attempted_date=attempt_time,
                            reason=reason,
                        )

                has_partial_result = bool(best_lccn or best_nlmcn)
                requires_both_for_success = (
                    self.call_number_mode == "both" and self.stop_rule == "continue_both"
                )
                has_complete_result = self._should_stop_with_found(bool(best_lccn), bool(best_nlmcn))

                if has_partial_result and (not requires_both_for_success or has_complete_result):
                    rec = self._build_record(
                        isbn=isbn,
                        lccn=best_lccn,
                        lccn_source=best_lccn_source,
                        nlmcn=best_nlmcn,
                        nlmcn_source=best_nlmcn_source,
                    )
                    self._emit_result("success", isbn=isbn, target=rec.source or "Unknown", record=rec)
                    if dry_run:
                        return ("success", [], attempted_rows, [])
                    return ("success", [rec], attempted_rows, [])

                if has_partial_result:
                    rec = self._build_record(
                        isbn=isbn,
                        lccn=best_lccn,
                        lccn_source=best_lccn_source,
                        nlmcn=best_nlmcn,
                        nlmcn_source=best_nlmcn_source,
                    )
                    found_labels = []
                    missing_labels = []
                    if best_lccn:
                        found_labels.append("LCCN")
                    else:
                        missing_labels.append("LCCN")
                    if best_nlmcn:
                        found_labels.append("NLMCN")
                    else:
                        missing_labels.append("NLMCN")
                    last_error = (
                        f"Found {' and '.join(found_labels)} only; missing {' and '.join(missing_labels)}"
                    )

                    self._emit("failed", self._build_failed_payload(
                        isbn=isbn,
                        last_target=last_target,
                        last_error=last_error,
                        not_found_targets=not_found_targets,
                        other_errors=other_errors,
                    ))

                    return ("failed", [] if dry_run else [rec], attempted_rows, [])

                if skipped_retry_targets and not not_found_targets and not other_errors:
                    self._emit(
                        "skip_retry",
                        {
                            "isbn": isbn,
                            "retry_days": self.retry_days,
                            "targets": skipped_retry_targets,
                            "attempt_type": self.call_number_mode,
                        },
                    )
                    return ("skip_retry", [], [], [])

                if not_found_targets and not other_errors:
                    last_error = "Not found in: " + ", ".join(not_found_targets)
                elif not_found_targets and other_errors:
                    last_error = (
                        "Not found in: "
                        + ", ".join(not_found_targets)
                        + " | Other errors: "
                        + " ; ".join(f"{t}: {e}" for t, e in other_errors)
                    )
                elif other_errors:
                    last_error = " ; ".join(f"{t}: {e}" for t, e in other_errors)

                self._emit("failed", self._build_failed_payload(
                    isbn=isbn,
                    last_target=last_target,
                    last_error=last_error,
                    not_found_targets=not_found_targets,
                    other_errors=other_errors,
                ))

                return ("failed", [], attempted_rows, [])

            with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
                # ex.map preserves input order, so each result corresponds to
                # the ISBN at the same position in `isbns`.  Each worker returns
                # (status, recs, att, linked_rows) where the last three lists
                # are thread-local and safe to extend onto the shared buffers
                # here in the main thread.
                for status, recs, att, linked_rows in ex.map(worker, isbns):
                    self._check_cancelled()
                    # Accumulate thread-local results into the main-thread batch buffers
                    if recs:
                        pending_main.extend(recs)
                    if att:
                        pending_attempted.extend(att)
                    if linked_rows:
                        pending_linked.extend(linked_rows)

                    if (len(pending_main) + len(pending_attempted)) >= dynamic_batch_size:
                        flush()

                    if status == "cached":
                        cached_hits += 1
                    elif status == "skip_retry":
                        skipped_recent_fail += 1
                    elif status == "not_in_local_catalog":
                        not_in_local_catalog += 1
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
                        "not_in_local_catalog": not_in_local_catalog,
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
            not_in_local_catalog=not_in_local_catalog,
        )
