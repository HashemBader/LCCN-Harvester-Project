from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol
from src.database import DatabaseManager, MainRecord, utc_now_iso, today_yyyymmdd
from src.utils.isbn_validator import pick_lowest_isbn
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
    isbns: tuple[str, ...] = ()
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
    not_in_local_catalog: int = 0


@dataclass(frozen=True)
class ProcessOutcome:
    status: str
    record: Optional[MainRecord]
    attempted_rows: tuple[tuple[str, Optional[str], str, Optional[int], Optional[str]], ...]


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
    ):
        self.db = db
        self.retry_days = retry_days
        self.bypass_retry_isbns = set(bypass_retry_isbns or [])
        self.bypass_cache_isbns = set(bypass_cache_isbns or [])
        self.progress_cb = progress_cb
        self.cancel_check = cancel_check
        self.call_number_mode = self._normalize_call_number_mode(call_number_mode)
        self.stop_rule = self._normalize_stop_rule(stop_rule)
        self.max_workers = max(1, int(max_workers))
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        # In db_only mode API targets are never consulted; bypass_cache_isbns is ignored.
        self.db_only = db_only

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

    @staticmethod
    def _normalize_stop_rule(rule: str) -> str:
        normalized = (rule or "").strip().lower()
        if normalized in {"stop_either", "stop_lccn", "stop_nlmcn", "continue_both"}:
            return normalized
        return "stop_either"

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

    @staticmethod
    def _classify_other_error_target(error_text: str) -> str:
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
        return "LCCN" if call_number_type == "lccn" else "NLMCN"

    def _emit_attempt_failure(
        self,
        *,
        isbn: str,
        target: str,
        call_number_type: str,
        reason: str,
        attempted_date: Optional[int] = None,
    ) -> None:
        self._emit(
            "attempt_failed",
            {
                "isbn": isbn,
                "target": target,
                "attempt_type": call_number_type,
                "attempted_date": attempted_date or today_yyyymmdd(),
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
        pending_attempted: list[tuple[str, Optional[str], str, Optional[int], Optional[str]]],
    ) -> ProcessOutcome:
        self._check_cancelled()
        self._emit("isbn_start", {"isbn": isbn})

        cached_rec = None
        found_lccn: Optional[str] = None
        found_lccn_source: Optional[str] = None
        found_nlmcn: Optional[str] = None
        found_nlmcn_source: Optional[str] = None
        attempted_rows: list[tuple[str, Optional[str], str, Optional[int], Optional[str]]] = []

        if isbn not in self.bypass_cache_isbns:
            cached_rec = self.db.get_main(isbn)
        if cached_rec is not None:
            found_lccn = cached_rec.lccn
            found_lccn_source = getattr(cached_rec, "lccn_source", None) or cached_rec.source
            found_nlmcn = cached_rec.nlmcn
            found_nlmcn_source = getattr(cached_rec, "nlmcn_source", None) or cached_rec.source
            if self._should_stop_with_found(bool(found_lccn), bool(found_nlmcn)):
                record = self._build_record(
                    isbn=isbn,
                    lccn=found_lccn,
                    lccn_source=found_lccn_source,
                    nlmcn=found_nlmcn,
                    nlmcn_source=found_nlmcn_source,
                )
                self._emit_result("cached", isbn=isbn, target=record.source or "Cache", record=record)
                return ProcessOutcome("cached", record, tuple())

        # db_only mode: never hit any API target. If we reach here the ISBN was
        # not in the local DB (or had insufficient data). Report and stop.
        if self.db_only:
            self._emit("not_in_local_catalog", {"isbn": isbn})
            return ProcessOutcome("not_in_local_catalog", None, tuple())

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
                self.db.should_skip_retry(isbn, last_target, call_number_type, retry_days=self.retry_days)
                for call_number_type in required_types
            ):
                skipped_retry_targets.append(last_target)
                continue

            self._emit("target_start", {"isbn": isbn, "target": last_target})
            raw_result = target.lookup(isbn)
            attempt_time = today_yyyymmdd()
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

        # Check if we accumulated a fully successful result.
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
                rec = None
            else:
                pending_main.append(rec)
            if not dry_run and attempted_rows:
                pending_attempted.extend(attempted_rows)

            return ProcessOutcome("success", rec, tuple(attempted_rows))

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
        pending_attempted: list[tuple[str, Optional[str], str, Optional[int], Optional[str]]],
    ) -> str:
        outcome = self._process_isbn_internal(
            isbn,
            dry_run=dry_run,
            pending_main=pending_main,
            pending_attempted=pending_attempted,
        )
        return outcome.status

    def process_isbn_group(
        self,
        primary_isbn: str,
        linked_isbns: list[str],
        *,
        dry_run: bool,
        pending_main: list[MainRecord],
        pending_attempted: list[tuple[str, Optional[str], str, Optional[int], Optional[str]]],
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

    def _build_linked_crossref_record(self, record: MainRecord, canonical_isbn: str) -> MainRecord:
        return self._build_record(
            isbn=record.isbn,
            lccn=record.lccn,
            lccn_source=(f"Linked from {canonical_isbn}" if record.lccn else None),
            nlmcn=record.nlmcn,
            nlmcn_source=(f"Linked from {canonical_isbn}" if record.nlmcn else None),
        )

    def _detect_implicit_linked_isbns(
        self,
        pending_main: list[MainRecord],
        pending_linked: list[tuple[str, str]],
    ) -> None:
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

        # Union-find helper for building connected ISBN groups.
        parent: dict[str, str] = {}

        def find(isbn: str) -> str:
            parent.setdefault(isbn, isbn)
            while parent[isbn] != isbn:
                parent[isbn] = parent[parent[isbn]]
                isbn = parent[isbn]
            return isbn

        def union(a: str, b: str) -> None:
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

        cached_hits = 0
        skipped_recent_fail = 0
        attempted = 0
        successes = 0
        failures = 0
        not_in_local_catalog = 0

        # --- Sprint 5: batching buffers ---
        pending_main: list[MainRecord] = []
        pending_attempted: list[tuple[str, Optional[str], str, Optional[int], Optional[str]]] = []
        pending_linked: list[tuple[str, str]] = []

        dynamic_batch_size = max(self.DEFAULT_FLUSH_BATCH_SIZE, min(1000, len(isbns) // 100))

        def flush() -> None:
            """Flush buffered DB writes in a single transaction."""
            wrote_main = len(pending_main)
            if dry_run:
                pending_main.clear()
                pending_attempted.clear()
                pending_linked.clear()
                return

            if not pending_main and not pending_attempted and not pending_linked:
                return

            if self.call_number_mode == "both" and self.stop_rule != "continue_both":
                successful_isbns = {record.isbn for record in pending_main}
                filtered_attempted = [
                    row for row in pending_attempted if row[0] not in successful_isbns
                ]
            else:
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
        # --- end Sprint 5 batching ---

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
                    local_attempted: list[tuple[str, Optional[str], str, Optional[int], Optional[str]]] = []
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
                    cached_rec = self.db.get_main(isbn)
                if cached_rec is not None:
                    found_lccn = cached_rec.lccn
                    found_lccn_source = getattr(cached_rec, "lccn_source", None) or cached_rec.source
                    found_nlmcn = cached_rec.nlmcn
                    found_nlmcn_source = getattr(cached_rec, "nlmcn_source", None) or cached_rec.source
                    if self._should_stop_with_found(bool(found_lccn), bool(found_nlmcn)):
                        self._emit("cached", {
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
                attempted_rows: list[tuple[str, Optional[str], str, Optional[int], Optional[str]]] = []

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
                    attempt_time = today_yyyymmdd()
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
                for status, recs, att, linked_rows in ex.map(worker, isbns):
                    self._check_cancelled()
                    # main-thread batching writes
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
