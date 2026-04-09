"""
Database access layer for the LCCN Harvester project.

This module owns all read/write access to the SQLite database and is the
single source of truth for three logical data stores:

  main          -- Successful harvests: ISBN → call number (LCCN / NLM CN),
                   one row per (isbn, call_number_type, source) triple.
  attempted     -- Failed/pending lookups and retry counters, keyed by
                   (isbn, last_target, attempt_type).
  linked_isbns  -- Canonical ISBN grouping: maps every non-canonical ISBN to
                   its "lowest" (canonical) sibling so duplicate editions can
                   share a single result row.

Key design decisions:
  - Every public method opens its own short-lived connection via
    ``connect()`` and commits/rolls back atomically.
  - Batch operations accept an open ``sqlite3.Connection`` so the caller can
    wrap multiple operations in a single transaction via ``transaction()``.
  - Schema migrations are run automatically on ``init_db()`` so the app
    tolerates databases created by older releases.
  - All date values are stored as ``YYYYMMDD`` integers; conversion helpers
    live in ``date_utils``.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Iterable, Sequence

logger = logging.getLogger(__name__)

from .date_utils import (
    classification_from_lccn,
    normalize_to_datetime_str,
    normalize_to_yyyymmdd_int,
    now_datetime_str,
    today_yyyymmdd,
    yyyymmdd_to_iso_date,
)
from .records import AttemptedRecord, MainRecord

class DatabaseManager:
    """SQLite access layer for the LCCN Harvester's three core tables.

    Manages all reads and writes to the ``main``, ``attempted``, and
    ``linked_isbns`` tables.  Every public method that does not accept an
    explicit ``conn`` argument opens its own short-lived connection via
    ``connect()``, commits on success, and rolls back + closes on any error.
    Methods that accept a ``conn`` argument are intended to be called from
    within a ``transaction()`` block so multiple operations can be grouped
    into a single atomic write.

    Attributes:
        db_path: Resolved ``Path`` to the SQLite database file.
    """

    def __init__(self, db_path: Path | str = "data/lccn_harvester.sqlite3"):
        self.db_path = Path(db_path)

    @staticmethod
    def _default_schema_path() -> Path:
        """Resolve the bundled schema path in both source and frozen runs."""
        module_path = Path(__file__).resolve()
        candidates: list[Path] = [module_path.with_name("schema.sql")]

        # PyInstaller can place imported modules under either
        # ``.../Frameworks/database`` or ``.../Frameworks/src/database`` on macOS.
        # Walk a couple of ancestor layouts so the frozen app can still find the
        # bundled schema even if ``__file__`` shifts between those structures.
        for parent_index in (1, 2, 3):
            try:
                candidates.append(module_path.parents[parent_index] / "database" / "schema.sql")
            except IndexError:
                break

        if getattr(sys, "frozen", False):
            try:
                from config.app_paths import get_bundle_root
                bundle_root = get_bundle_root()
                candidates.extend(
                    [
                        bundle_root / "database" / "schema.sql",
                        bundle_root / "src" / "database" / "schema.sql",
                    ]
                )
            except Exception:
                pass

            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                root = Path(meipass)
                candidates.extend(
                    [
                        root / "database" / "schema.sql",
                        root / "src" / "database" / "schema.sql",
                    ]
                )

        for path in candidates:
            if path.exists():
                return path

        return candidates[0]

    @contextmanager
    def connect(self):
        """Open a connection, yield it, then always commit-or-rollback and close.

        Using ``sqlite3.Connection`` as a plain ``with`` statement only commits
        or rolls back - it never closes the handle.  That leaves the WAL file
        active and can corrupt the database if the process is killed.  This
        context manager guarantees the connection is closed after every
        ``with self.connect() as conn:`` block regardless of whether an
        exception is raised.

        Yields:
            An open ``sqlite3.Connection`` configured with ``Row`` factory and
            safety/performance PRAGMAs (WAL, FULL sync, busy timeout).

        Raises:
            Any exception raised inside the block (after rolling back).
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row

        # Safety + performance pragmas
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")     # better concurrent reads/writes
        conn.execute("PRAGMA synchronous = FULL;")     # fsync WAL on every commit – prevents corruption on crash
        conn.execute("PRAGMA temp_store = MEMORY;")    # faster temp operations
        conn.execute("PRAGMA busy_timeout = 5000;")    # wait up to 5 s if db is locked

        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()  # always release – checkpoints WAL and frees the file lock


    def _is_db_healthy(self) -> bool:
        """Return True if the database file passes a quick integrity check."""
        if not self.db_path.exists():
            return True  # Will be created fresh
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            result = conn.execute("PRAGMA quick_check").fetchone()
            conn.close()
            return result is not None and result[0] == "ok"
        except Exception:
            return False

    def _reset_db_files(self) -> None:
        """Delete the DB and any WAL/SHM side-files so it can be recreated clean."""
        for suffix in ("", "-shm", "-wal"):
            path = self.db_path.parent / (self.db_path.name + suffix)
            try:
                if path.exists():
                    path.unlink()
                    logger.warning("Deleted corrupt DB file: %s", path)
            except Exception as exc:
                logger.error("Could not delete %s: %s", path, exc)

    def init_db(self, schema_path: Optional[Path] = None) -> None:
        """Initialise the database from ``schema.sql`` and run any pending migrations.

        Loads ``schema.sql`` (auto-resolved if not supplied), applies the DDL,
        then runs the three Python-level migration helpers to handle databases
        created by older releases.  If the existing database file fails the
        ``PRAGMA quick_check``, it is automatically deleted and recreated from
        scratch before the schema is applied.

        Args:
            schema_path: Optional explicit path to the SQL schema file.
                         Defaults to ``schema.sql`` in the same directory as
                         this module (with PyInstaller-aware fallback paths).
        """
        if schema_path is None:
            schema_path = self._default_schema_path()

        # Auto-repair: if the existing file is malformed, wipe and start fresh
        if not self._is_db_healthy():
            logger.error(
                "Database at %s is malformed – resetting to a clean state.", self.db_path
            )
            self._reset_db_files()

        schema_sql = schema_path.read_text(encoding="utf-8")

        with self.connect() as conn:
            try:
                conn.executescript(schema_sql)
            except sqlite3.OperationalError as exc:
                # Older deployments may already have a legacy ``main`` table whose
                # columns do not match the current schema. In that case the schema
                # script can fail while creating indexes before our Python
                # migrations get a chance to run.
                if "no such column" not in str(exc).lower():
                    raise
                self._migrate_main_schema_if_needed(conn)
                self._migrate_attempted_schema_if_needed(conn)
                self._migrate_linked_isbns_schema_if_needed(conn)
                conn.executescript(schema_sql)
            self._migrate_main_schema_if_needed(conn)
            self._migrate_attempted_schema_if_needed(conn)
            self._migrate_linked_isbns_schema_if_needed(conn)
            self._migrate_dates_to_yyyymmdd(conn)

    def _migrate_main_schema_if_needed(self, conn: sqlite3.Connection) -> None:
        """Migrate ``main`` to the multi-row-per-ISBN schema if the table is outdated.

        Older releases stored a single row per ISBN with separate ``lccn`` and
        ``nlmcn`` columns.  The current schema stores one row per
        ``(isbn, call_number_type, source)`` triple so multiple sources can be
        recorded for the same ISBN.  This method renames the old table to
        ``main_legacy``, creates the new schema, migrates existing rows, then
        drops the legacy table.

        Args:
            conn: An open database connection from ``connect()`` or ``transaction()``.
        """
        cols = conn.execute("PRAGMA table_info(main)").fetchall()
        if not cols:
            return

        col_names = {row["name"] for row in cols}
        pk_cols = [
            row["name"]
            for row in sorted(cols, key=lambda row: int(row["pk"]))
            if int(row["pk"]) > 0
        ]
        desired_pk = ["isbn", "call_number_type", "source"]

        if (
            "call_number_type" in col_names
            and "call_number" in col_names
            and "source" in col_names
            and pk_cols == desired_pk
        ):
            conn.execute("CREATE INDEX IF NOT EXISTS idx_main_source ON main(source)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_main_date_added ON main(date_added)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_main_type ON main(call_number_type)")
            return

        conn.execute("ALTER TABLE main RENAME TO main_legacy")
        conn.execute(
            """
            CREATE TABLE main (
                isbn             TEXT NOT NULL,
                call_number      TEXT NOT NULL,
                call_number_type TEXT NOT NULL,
                classification   TEXT,
                source           TEXT NOT NULL DEFAULT '',
                date_added       INTEGER NOT NULL,
                PRIMARY KEY (isbn, call_number_type, source)
            )
            """
        )

        def _legacy_select(name: str) -> str:
            return name if name in col_names else f"NULL AS {name}"

        legacy_rows = conn.execute(
            f"""
            SELECT
                {_legacy_select("isbn")},
                {_legacy_select("lccn")},
                {_legacy_select("lccn_source")},
                {_legacy_select("nlmcn")},
                {_legacy_select("nlmcn_source")},
                {_legacy_select("classification")},
                {_legacy_select("source")},
                {_legacy_select("date_added")}
            FROM main_legacy
            """
        ).fetchall()
        for row in legacy_rows:
            date_added = normalize_to_yyyymmdd_int(row["date_added"])
            if row["lccn"]:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO main
                        (isbn, call_number, call_number_type, classification, source, date_added)
                    VALUES (?, ?, 'lccn', ?, ?, ?)
                    """,
                    (
                        row["isbn"],
                        row["lccn"],
                        row["classification"] or classification_from_lccn(row["lccn"]),
                        (row["lccn_source"] if "lccn_source" in row.keys() else row["source"]) or "",
                        date_added,
                    ),
                )
            if row["nlmcn"]:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO main
                        (isbn, call_number, call_number_type, classification, source, date_added)
                    VALUES (?, ?, 'nlmcn', ?, ?, ?)
                    """,
                    (
                        row["isbn"],
                        row["nlmcn"],
                        None,
                        (row["nlmcn_source"] if "nlmcn_source" in row.keys() else row["source"]) or "",
                        date_added,
                    ),
                )

        conn.execute("DROP TABLE main_legacy")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_main_source ON main(source)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_main_date_added ON main(date_added)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_main_type ON main(call_number_type)")

    def _migrate_attempted_schema_if_needed(self, conn: sqlite3.Connection) -> None:
        """Migrate ``attempted`` to the composite primary key schema if outdated.

        Older releases keyed ``attempted`` on ``isbn`` alone.  The current
        schema uses ``PRIMARY KEY (isbn, last_target, attempt_type)`` so each
        target/type combination can be tracked and retried independently.

        Args:
            conn: An open database connection from ``connect()`` or ``transaction()``.
        """
        cols = conn.execute("PRAGMA table_info(attempted)").fetchall()
        if not cols:
            return

        col_names = {row["name"] for row in cols}
        pk_cols = [row["name"] for row in cols if int(row["pk"]) > 0]
        desired_pk = ["isbn", "last_target", "attempt_type"]

        if "attempt_type" in col_names and pk_cols == desired_pk:
            return

        conn.execute("ALTER TABLE attempted RENAME TO attempted_legacy")
        conn.execute(
            """
            CREATE TABLE attempted (
                isbn              TEXT NOT NULL,
                last_target       TEXT NOT NULL,
                attempt_type      TEXT NOT NULL DEFAULT 'both',
                last_attempted    INTEGER NOT NULL,
                fail_count        INTEGER NOT NULL DEFAULT 1,
                last_error        TEXT,
                PRIMARY KEY (isbn, last_target, attempt_type)
            )
            """
        )

        legacy_rows = conn.execute(
            """
            SELECT isbn, last_target, last_attempted, fail_count, last_error
            FROM attempted_legacy
            """
        ).fetchall()
        for row in legacy_rows:
            conn.execute(
                """
                INSERT INTO attempted (isbn, last_target, attempt_type, last_attempted, fail_count, last_error)
                VALUES (?, ?, 'both', ?, ?, ?)
                """,
                (
                    row["isbn"],
                    row["last_target"] or "",
                    normalize_to_yyyymmdd_int(row["last_attempted"]),
                    row["fail_count"] or 1,
                    row["last_error"],
                ),
            )
        conn.execute("DROP TABLE attempted_legacy")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_attempted_last_attempted ON attempted(last_attempted)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_attempted_last_target ON attempted(last_target)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_attempted_isbn ON attempted(isbn)")

    def _migrate_linked_isbns_schema_if_needed(self, conn: sqlite3.Connection) -> None:
        """Migrate ``linked_isbns`` to the current schema if the table is outdated.

        The current schema uses ``lowest_isbn`` / ``other_isbn`` column names,
        a composite primary key ``(lowest_isbn, other_isbn)``, and a
        ``UNIQUE`` constraint on ``other_isbn`` alone (so each non-canonical
        ISBN maps to exactly one canonical).  Older releases used different
        column names or lacked the unique constraint.

        Args:
            conn: An open database connection from ``connect()`` or ``transaction()``.
        """
        cols = conn.execute("PRAGMA table_info(linked_isbns)").fetchall()
        if not cols:
            return

        col_names = {row["name"] for row in cols}
        pk_cols = [row["name"] for row in sorted(cols, key=lambda row: int(row["pk"])) if int(row["pk"]) > 0]
        desired_pk = ["lowest_isbn", "other_isbn"]
        has_other_unique = False
        # Inspect every index on the table to find whether a UNIQUE index on
        # exactly the single column "other_isbn" already exists.
        for idx in conn.execute("PRAGMA index_list(linked_isbns)").fetchall():
            if int(idx["unique"]) != 1:
                continue
            index_name = idx["name"]
            indexed_cols = [
                row["name"]
                for row in conn.execute(f"PRAGMA index_info({index_name})").fetchall()
            ]
            if indexed_cols == ["other_isbn"]:
                has_other_unique = True
                break

        if {"lowest_isbn", "other_isbn"}.issubset(col_names) and pk_cols == desired_pk and has_other_unique:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_linked_lowest ON linked_isbns(lowest_isbn)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_linked_other ON linked_isbns(other_isbn)")
            return

        conn.execute("ALTER TABLE linked_isbns RENAME TO linked_isbns_legacy")
        conn.execute(
            """
            CREATE TABLE linked_isbns (
                lowest_isbn      TEXT NOT NULL,
                other_isbn       TEXT NOT NULL UNIQUE,
                PRIMARY KEY (lowest_isbn, other_isbn),
                CHECK (lowest_isbn <> other_isbn)
            )
            """
        )

        def _legacy_select(name: str) -> str:
            return name if name in col_names else f"NULL AS {name}"

        legacy_rows = conn.execute(
            f"""
            SELECT
                {_legacy_select("lowest_isbn")},
                {_legacy_select("other_isbn")},
                {_legacy_select("isbn")},
                {_legacy_select("canonical_isbn")}
            FROM linked_isbns_legacy
            """
        ).fetchall()
        for row in legacy_rows:
            lowest_isbn = (row["lowest_isbn"] or row["canonical_isbn"] or "").strip()
            other_isbn = (row["other_isbn"] or row["isbn"] or "").strip()
            if not lowest_isbn or not other_isbn or lowest_isbn == other_isbn:
                continue
            conn.execute(
                """
                INSERT INTO linked_isbns (lowest_isbn, other_isbn)
                VALUES (?, ?)
                ON CONFLICT(other_isbn) DO UPDATE SET
                    lowest_isbn = excluded.lowest_isbn
                """,
                (lowest_isbn, other_isbn),
            )

        conn.execute("DROP TABLE linked_isbns_legacy")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_linked_lowest ON linked_isbns(lowest_isbn)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_linked_other ON linked_isbns(other_isbn)")

    def _migrate_dates_to_yyyymmdd(self, conn: sqlite3.Connection) -> None:
        """Normalize stored date fields to ``YYYYMMDD`` integers."""
        # -- main.date_added --
        rows_main = conn.execute(
            "SELECT rowid, date_added FROM main WHERE typeof(date_added) IN ('integer', 'text')"
        ).fetchall()
        for row in rows_main:
            old_val = row["date_added"]
            new_val = normalize_to_yyyymmdd_int(old_val)
            if new_val != old_val:
                conn.execute("UPDATE main SET date_added = ? WHERE rowid = ?", (new_val, row["rowid"]))

        # -- attempted.last_attempted --
        rows_att = conn.execute(
            "SELECT rowid, last_attempted FROM attempted WHERE typeof(last_attempted) IN ('integer', 'text')"
        ).fetchall()
        for row in rows_att:
            old_val = row["last_attempted"]
            new_val = normalize_to_yyyymmdd_int(old_val)
            if new_val != old_val:
                conn.execute("UPDATE attempted SET last_attempted = ? WHERE rowid = ?", (new_val, row["rowid"]))

        if rows_main or rows_att:
            logger.info(
                "_migrate_dates_to_yyyymmdd: converted %d main rows and %d attempted rows",
                len(rows_main), len(rows_att),
            )

    @contextmanager
    def transaction(self):
        """Open a transactional connection for use with batch ``*_many`` methods.

        A thin alias over ``connect()`` that exists so call sites can express
        intent: ``transaction()`` signals a multi-operation batch, while
        ``connect()`` signals a single-operation read.  Commit/rollback/close
        semantics are identical to ``connect()``.

        Yields:
            An open ``sqlite3.Connection`` (same as ``connect()``).
        """
        with self.connect() as conn:
            yield conn

    def close(self) -> None:
        """No-op kept for API compatibility with older call sites.

        ``DatabaseManager`` uses short-lived per-operation connections via
        ``connect()`` and explicit batch transactions via ``transaction()``;
        there is no persistent connection to close.
        """
        return



    # -------------------------
    # MAIN TABLE HELPERS
    # -------------------------
    @staticmethod
    def _record_success_types(record: MainRecord) -> tuple[str, ...]:
        """Return which call-number types are populated in *record* (e.g. ``('lccn',)``)."""
        types: list[str] = []
        if record.lccn:
            types.append("lccn")
        if record.nlmcn:
            types.append("nlmcn")
        return tuple(types)

    @staticmethod
    def _aggregate_main_rows(rows: Sequence[sqlite3.Row]) -> Optional[MainRecord]:
        """Collapse multiple per-type DB rows for one ISBN into a single ``MainRecord``.

        The ``main`` table stores one row per ``(isbn, call_number_type, source)``.
        This method merges all rows for the same ISBN into the combined
        ``MainRecord`` shape expected by callers (lccn, nlmcn, source, date_added).

        The first ``lccn`` row and first ``nlmcn`` row encountered win; the
        latest ``date_added`` across all rows is used as the record's date.

        Args:
            rows: Raw ``sqlite3.Row`` objects from the ``main`` table for a
                  single ISBN, ordered by ``date_added DESC, call_number_type, source``.

        Returns:
            A combined ``MainRecord``, or ``None`` if *rows* is empty.
        """
        if not rows:
            return None

        isbn = rows[0]["isbn"]
        lccn = None
        lccn_source = None
        nlmcn = None
        nlmcn_source = None
        classification = None
        sources: list[str] = []
        latest_date: Optional[int | str] = None

        for row in rows:
            call_type = str(row["call_number_type"] or "").strip().lower()
            call_number = row["call_number"]
            source = row["source"]
            if source and source not in sources:
                sources.append(source)
            row_date = normalize_to_datetime_str(row["date_added"])
            current_latest = normalize_to_datetime_str(latest_date)
            latest_date = max(current_latest or "", row_date or "") or latest_date
            if call_type == "lccn":
                if lccn is None:
                    lccn = call_number
                    lccn_source = source
                    classification = row["classification"] or classification_from_lccn(call_number)
            elif call_type == "nlmcn":
                if nlmcn is None:
                    nlmcn = call_number
                    nlmcn_source = source

        return MainRecord(
            isbn=isbn,
            lccn=lccn,
            lccn_source=lccn_source,
            nlmcn=nlmcn,
            nlmcn_source=nlmcn_source,
            classification=classification,
            source=DatabaseManager._combine_sources(*sources),
            date_added=yyyymmdd_to_iso_date(latest_date),
        )

    def _explode_main_record(self, record: MainRecord) -> list[tuple[str, str, str, Optional[str], Optional[str], int]]:
        """Expand a combined ``MainRecord`` into the row-per-type tuples stored in ``main``.

        A single ``MainRecord`` can contain both an LCCN and an NLMCN.  The
        ``main`` table stores these as separate rows, so this method produces
        up to two tuples: one for ``call_number_type='lccn'`` and one for
        ``call_number_type='nlmcn'``.

        Returns:
            A list of ``(isbn, call_number, call_number_type, classification,
            source, date_added_int)`` tuples ready for ``executemany``.
        """
        date_added = normalize_to_yyyymmdd_int(record.date_added)
        rows: list[tuple[str, str, str, Optional[str], Optional[str], int]] = []
        if record.lccn:
            rows.append(
                (
                    record.isbn,
                    record.lccn,
                    "lccn",
                    record.classification or classification_from_lccn(record.lccn),
                    record.lccn_source or record.source or "",
                    date_added,
                )
            )
        if record.nlmcn:
            rows.append(
                (
                    record.isbn,
                    record.nlmcn,
                    "nlmcn",
                    None,
                    record.nlmcn_source or record.source or "",
                    date_added,
                )
            )
        return rows

    def get_main(self, isbn: str, *, allowed_sources: Optional[Iterable[str]] = None) -> Optional[MainRecord]:
        """Fetch the combined MainRecord for *isbn*, optionally filtered by source list.

        Args:
            isbn: The ISBN to look up.
            allowed_sources: When provided, only rows whose ``source`` column
                matches one of these values are included.  An explicit empty
                iterable (not ``None``) means "no allowed sources" and always
                returns ``None``.

        Returns:
            A ``MainRecord`` aggregated from all matching rows, or ``None`` if
            no rows exist (or none survive the source filter).
        """
        allowed = None if allowed_sources is None else [str(source).strip() for source in allowed_sources if str(source).strip()]
        if allowed_sources is not None and not allowed:
            return None

        with self.connect() as conn:
            if allowed is None:
                rows = conn.execute(
                    """
                    SELECT isbn, call_number, call_number_type, classification, source, date_added
                    FROM main
                    WHERE isbn = ?
                    ORDER BY date_added DESC, call_number_type, source
                    """,
                    (isbn,),
                ).fetchall()
            else:
                placeholders = ",".join("?" for _ in allowed)
                rows = conn.execute(
                    f"""
                    SELECT isbn, call_number, call_number_type, classification, source, date_added
                    FROM main
                    WHERE isbn = ? AND source IN ({placeholders})
                    ORDER BY date_added DESC, call_number_type, source
                    """,
                    (isbn, *allowed),
                ).fetchall()

        return self._aggregate_main_rows(rows)

    def get_main_rows(self, isbn: str) -> list[sqlite3.Row]:
        """Return raw ``main`` table rows for *isbn* (one per call_number_type/source pair)."""
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT isbn, call_number, call_number_type, classification, source, date_added
                FROM main
                WHERE isbn = ?
                ORDER BY call_number_type, source, date_added DESC
                """,
                (isbn,),
            ).fetchall()

    def find_isbns_by_call_number(
        self,
        call_number_type: str,
        call_number: str,
        *,
        exclude_isbn: str | None = None,
    ) -> list[str]:
        """Return ISBNs that already share the same call number in main."""
        if not call_number_type or not call_number:
            return []

        with self.connect() as conn:
            if exclude_isbn:
                rows = conn.execute(
                    "SELECT DISTINCT isbn FROM main WHERE call_number_type = ? AND call_number = ? AND isbn <> ?",
                    (call_number_type, call_number, exclude_isbn),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT DISTINCT isbn FROM main WHERE call_number_type = ? AND call_number = ?",
                    (call_number_type, call_number),
                ).fetchall()

        return [str(row["isbn"]) for row in rows]

    def upsert_main(self, record: MainRecord, *, clear_attempted_on_success: bool = True) -> None:
        """Insert or update a single MainRecord in its own transaction.

        Args:
            record: The successful harvest result to persist.
            clear_attempted_on_success: When ``True`` (default), any matching
                rows in ``attempted`` are removed so the ISBN is no longer
                treated as a failed lookup.
        """
        with self.transaction() as conn:
            self._upsert_main_conn(conn, record, clear_attempted_on_success=clear_attempted_on_success)

    def upsert_main_many(
        self,
        conn: sqlite3.Connection,
        records: Sequence[MainRecord],
        *,
        clear_attempted_on_success: bool = True,
    ) -> None:
        """Batch upsert combined ``MainRecord`` objects within an existing transaction.

        Each ``MainRecord`` is first exploded into its per-type rows via
        ``_explode_main_record``, then written with ``INSERT … ON CONFLICT DO
        UPDATE`` so existing rows are updated rather than duplicated.  When
        ``clear_attempted_on_success=True`` any ``attempted`` rows for the
        successfully written (isbn, call_number_type) pairs are removed.

        Args:
            conn:                       An open connection from ``transaction()``.
            records:                    ``MainRecord`` objects to persist.
            clear_attempted_on_success: Remove corresponding ``attempted`` rows
                                        after a successful upsert.
        """
        if not records:
            return

        rows: list[tuple[str, str, str, Optional[str], Optional[str], str]] = []
        successful_pairs: list[tuple[str, str]] = []
        for r in records:
            exploded = self._explode_main_record(r)
            rows.extend(exploded)
            successful_pairs.extend((r.isbn, call_number_type) for _, _, call_number_type, _, _, _ in exploded)

        if not rows:
            return

        conn.executemany(
            """
            INSERT INTO main (isbn, call_number, call_number_type, classification, source, date_added)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(isbn, call_number_type, source) DO UPDATE SET
                call_number = excluded.call_number,
                classification = excluded.classification,
                date_added = excluded.date_added
            """,
            rows,
        )

        if clear_attempted_on_success:
            self.clear_attempted_pairs_many(conn, successful_pairs)

    def _upsert_main_conn(
        self,
        conn: sqlite3.Connection,
        record: MainRecord,
        *,
        clear_attempted_on_success: bool,
    ) -> None:
        self.upsert_main_many(conn, [record], clear_attempted_on_success=clear_attempted_on_success)

    # -------------------------
    # LINKED ISBN HELPERS
    # -------------------------
    def get_lowest_isbn(self, isbn: str) -> str:
        """Return the canonical lowest ISBN for *isbn*, or the ISBN itself if unlinked."""
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT lowest_isbn
                FROM linked_isbns
                WHERE other_isbn = ?
                LIMIT 1
                """,
                (isbn,),
            ).fetchone()
        if row and row["lowest_isbn"]:
            return str(row["lowest_isbn"])
        return isbn

    def get_linked_isbns(self, lowest_isbn: str) -> list[str]:
        """Return all ISBNs linked to the supplied canonical lowest ISBN."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT other_isbn
                FROM linked_isbns
                WHERE lowest_isbn = ?
                ORDER BY other_isbn
                """,
                (lowest_isbn,),
            ).fetchall()
        return [str(row["other_isbn"]) for row in rows]

    def upsert_linked_isbn(self, *, lowest_isbn: str, other_isbn: str) -> None:
        """Insert or update a linked ISBN mapping."""
        with self.transaction() as conn:
            self._upsert_linked_isbn_conn(conn, lowest_isbn=lowest_isbn, other_isbn=other_isbn)

    def _upsert_linked_isbn_conn(
        self,
        conn: sqlite3.Connection,
        *,
        lowest_isbn: str,
        other_isbn: str,
    ) -> None:
        lowest_isbn = (lowest_isbn or "").strip()
        other_isbn = (other_isbn or "").strip()
        if not lowest_isbn or not other_isbn:
            raise ValueError("lowest_isbn and other_isbn are required")
        if lowest_isbn == other_isbn:
            raise ValueError("lowest_isbn and other_isbn must be different")

        conn.execute(
            """
            INSERT INTO linked_isbns (lowest_isbn, other_isbn)
            VALUES (?, ?)
            ON CONFLICT(other_isbn) DO UPDATE SET
                lowest_isbn = excluded.lowest_isbn
            """,
            (lowest_isbn, other_isbn),
        )

    # -------------------------
    # ATTEMPTED TABLE HELPERS
    # -------------------------
    def get_attempted(self, isbn: str) -> Optional[AttemptedRecord]:
        """
        Return the most recent attempted row for this ISBN (any target/type).
        Kept for compatibility with existing UI code that only needs a quick
        existence check.  Prefer ``get_attempted_for`` or
        ``get_all_attempted_for`` when target/type specificity matters.
        """
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT isbn, last_target, attempt_type, last_attempted, fail_count, last_error
                FROM attempted
                WHERE isbn = ?
                ORDER BY last_attempted DESC
                LIMIT 1
                """,
                (isbn,),
            ).fetchone()

        if not row:
            return None

        return AttemptedRecord(
            isbn=row["isbn"],
            last_target=row["last_target"],
            attempt_type=row["attempt_type"] or "both",
            last_attempted=row["last_attempted"],
            fail_count=int(row["fail_count"]),
            last_error=row["last_error"],
        )

    def get_all_attempted_for(self, isbn: str) -> list[AttemptedRecord]:
        """Return every attempted row for *isbn* across all targets and types.

        Use this (rather than the coarse ``get_attempted``) when you need to
        inspect or assert per-target / per-type retry state.
        Results are ordered by ``last_attempted`` descending (most recent first).
        """
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT isbn, last_target, attempt_type, last_attempted, fail_count, last_error
                FROM attempted
                WHERE isbn = ?
                ORDER BY last_attempted DESC
                """,
                (isbn,),
            ).fetchall()

        return [
            AttemptedRecord(
                isbn=row["isbn"],
                last_target=row["last_target"],
                attempt_type=row["attempt_type"] or "both",
                last_attempted=row["last_attempted"],
                fail_count=int(row["fail_count"]),
                last_error=row["last_error"],
            )
            for row in rows
        ]

    def get_attempted_for(self, isbn: str, last_target: str, attempt_type: str) -> Optional[AttemptedRecord]:
        """Return attempted row for a specific ISBN+target+type key."""
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT isbn, last_target, attempt_type, last_attempted, fail_count, last_error
                FROM attempted
                WHERE isbn = ? AND last_target = ? AND attempt_type = ?
                """,
                (isbn, last_target, attempt_type),
            ).fetchone()
        if not row:
            return None
        return AttemptedRecord(
            isbn=row["isbn"],
            last_target=row["last_target"],
            attempt_type=row["attempt_type"] or "both",
            last_attempted=row["last_attempted"],
            fail_count=int(row["fail_count"]),
            last_error=row["last_error"],
        )

    def should_skip_retry(self, isbn: str, last_target: str, attempt_type: str, retry_days: int) -> bool:
        """Return True when the retry window for this ISBN/target/type is still active.

        ``attempted.last_attempted`` is normalized to a ``YYYYMMDD`` integer, but
        older databases may still contain legacy ISO strings during migration.
        This helper accepts both formats so retry behavior stays stable.
        """
        att = self.get_attempted_for(isbn, last_target, attempt_type)
        if att is None or not att.last_attempted:
            return False

        last_val = att.last_attempted
        try:
            # Parse the stored date accepting multiple historical formats:
            # "YYYY-MM-DD HH:MM:SS"  -- ISO datetime string (legacy storage)
            # "YYYY-MM-DDT..." / "...Z"  -- ISO-8601 with optional Z suffix
            # 20240315 (int) or "20240315" (str) -- current compact integer format
            if isinstance(last_val, str):
                if " " in last_val:
                    last_date = datetime.strptime(last_val, "%Y-%m-%d %H:%M:%S")
                else:
                    last_date = datetime.fromisoformat(last_val.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
            elif isinstance(last_val, int) and len(str(last_val)) == 8:
                s = str(last_val)
                last_date = datetime(int(s[:4]), int(s[4:6]), int(s[6:8]))
            elif isinstance(last_val, str) and last_val.isdigit() and len(last_val) == 8:
                last_date = datetime(int(last_val[:4]), int(last_val[4:6]), int(last_val[6:8]))
            else:
                return False  # Unrecognised format — do not suppress retry
        except Exception:
            return False  # Any parse error: allow the retry to proceed

        now = datetime.now()
        return (now - last_date) < timedelta(days=retry_days)

    def upsert_attempted(
        self,
        *,
        isbn: str,
        last_target: Optional[str],
        attempt_type: str = "both",
        last_error: Optional[str] = None,
        attempted_time: Optional[str] = None,
    ) -> None:
        """Record a failed lookup attempt in its own transaction.

        If a row already exists for the (isbn, last_target, attempt_type) key,
        ``fail_count`` is incremented and the error/timestamp are updated.

        Args:
            isbn: The ISBN that was attempted.
            last_target: Identifier of the lookup target that was tried.
            attempt_type: ``'lccn'``, ``'nlmcn'``, or ``'both'`` (default).
            last_error: Human-readable error message from the failed attempt.
            attempted_time: ISO datetime string or ``YYYYMMDD`` integer string
                for when the attempt occurred; defaults to today if ``None``.
        """
        with self.transaction() as conn:
            self._upsert_attempted_conn(
                conn,
                isbn=isbn,
                last_target=last_target,
                attempt_type=attempt_type,
                last_error=last_error,
                attempted_time=attempted_time,
            )

    def upsert_attempted_many(
        self,
        conn: sqlite3.Connection,
        rows: Sequence[tuple[str, Optional[str], str, Optional[str], Optional[str]]],
    ) -> None:
        """Batch upsert failed-lookup rows within an existing transaction.

        On conflict (same ``isbn``, ``last_target``, ``attempt_type`` key),
        ``fail_count`` is incremented and the timestamp / error message are
        updated to the most recent values.

        Args:
            conn: An open connection from ``transaction()``.
            rows: Iterable of 5-tuples
                  ``(isbn, last_target, attempt_type, attempted_time, last_error)``
                  where *attempted_time* may be an ISO datetime string or a
                  ``YYYYMMDD`` integer (or ``None`` to default to today).
        """
        if not rows:
            return

        fixed_rows = []
        for isbn, last_target, attempt_type, attempted_time, last_error in rows:
            fixed_rows.append(
                (
                    isbn,
                    last_target or "",
                    attempt_type or "both",
                    normalize_to_yyyymmdd_int(attempted_time),
                    last_error,
                )
            )

        conn.executemany(
            """
            INSERT INTO attempted (isbn, last_target, attempt_type, last_attempted, fail_count, last_error)
            VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(isbn, last_target, attempt_type) DO UPDATE SET
                last_target = excluded.last_target,
                attempt_type = excluded.attempt_type,
                last_attempted = excluded.last_attempted,
                fail_count = attempted.fail_count + 1,
                last_error = excluded.last_error
            """,
            fixed_rows,
        )

    def _upsert_attempted_conn(
        self,
        conn: sqlite3.Connection,
        *,
        isbn: str,
        last_target: Optional[str],
        attempt_type: str,
        last_error: Optional[str],
        attempted_time: Optional[str],
    ) -> None:
        attempted_time = normalize_to_yyyymmdd_int(attempted_time)

        conn.execute(
            """
            INSERT INTO attempted (isbn, last_target, attempt_type, last_attempted, fail_count, last_error)
            VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(isbn, last_target, attempt_type) DO UPDATE SET
                last_target = excluded.last_target,
                attempt_type = excluded.attempt_type,
                last_attempted = excluded.last_attempted,
                fail_count = attempted.fail_count + 1,
                last_error = excluded.last_error
            """,
            (isbn, last_target or "", attempt_type or "both", attempted_time, last_error),
        )

    def clear_attempted(self, isbn: str) -> None:
        """Delete all attempted rows for *isbn* (all targets and types)."""
        with self.connect() as conn:
            conn.execute("DELETE FROM attempted WHERE isbn = ?", (isbn,))

    def clear_attempted_many(self, conn: sqlite3.Connection, isbns: Iterable[str]) -> None:
        """Delete all attempted rows for the given ISBNs within an open connection.

        Args:
            conn: An open database connection (must be within a transaction).
            isbns: ISBNs whose attempted rows should be removed.
        """
        isbns_list = list(isbns)
        if not isbns_list:
            return

        # SQLite caps bound variables per statement at ~999; chunk to stay safe
        CHUNK = 900
        for i in range(0, len(isbns_list), CHUNK):
            chunk = isbns_list[i : i + CHUNK]
            placeholders = ",".join("?" for _ in chunk)
            conn.execute(f"DELETE FROM attempted WHERE isbn IN ({placeholders})", tuple(chunk))

    def clear_attempted_for(self, isbn: str, attempt_type: str) -> None:
        """Delete attempted rows for *isbn* restricted to a specific *attempt_type*."""
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM attempted WHERE isbn = ? AND attempt_type = ?",
                (isbn, attempt_type),
            )

    def clear_attempted_pairs_many(
        self,
        conn: sqlite3.Connection,
        pairs: Iterable[tuple[str, str]],
    ) -> None:
        """Delete attempted rows matching (isbn, attempt_type) pairs within an open connection.

        Used after a batch upsert of successful main results to clean up the
        corresponding failure entries in one pass.

        Args:
            conn: An open database connection (must be within a transaction).
            pairs: Iterable of ``(isbn, attempt_type)`` tuples to remove.
        """
        pairs_list = [(isbn, attempt_type) for isbn, attempt_type in pairs if isbn and attempt_type]
        if not pairs_list:
            return

        # Each pair needs 2 bound variables; keep total well below SQLite's ~999 limit
        CHUNK = 400
        for i in range(0, len(pairs_list), CHUNK):
            chunk = pairs_list[i : i + CHUNK]
            placeholders = ",".join("(?, ?)" for _ in chunk)
            params: list[str] = []
            for isbn, attempt_type in chunk:
                params.extend([isbn, attempt_type])
            conn.execute(
                f"DELETE FROM attempted WHERE (isbn, attempt_type) IN ({placeholders})",
                tuple(params),
            )

    def upsert_linked_isbns_many(
        self,
        conn: sqlite3.Connection,
        pairs: Iterable[tuple[str, str]],
    ) -> None:
        """Record lowest → other mappings in the linked_isbns table.

        pairs: iterable of (lowest_isbn, other_isbn).
        Self-mappings are ignored because the table enforces lowest != other.
        """
        rows = [
            (lowest, other)
            for lowest, other in pairs
            if lowest and other and lowest != other
        ]
        if not rows:
            return
        conn.executemany(
            """
            INSERT INTO linked_isbns (lowest_isbn, other_isbn)
            VALUES (?, ?)
            ON CONFLICT(other_isbn) DO UPDATE SET lowest_isbn = excluded.lowest_isbn
            """,
            rows,
        )

    def _rewrite_to_lowest_isbn_conn(
        self,
        conn: sqlite3.Connection,
        *,
        lowest_isbn: str,
        other_isbn: str,
    ) -> None:
        """Merge all data rows from *other_isbn* into *lowest_isbn* and record the link.

        Steps performed within the supplied connection:
          1. For each ``main`` row under *other_isbn*, upsert it under
             *lowest_isbn*, keeping the call_number from the more recent row.
          2. Delete all ``main`` rows for *other_isbn*.
          3. Copy ``attempted`` rows from *other_isbn* to *lowest_isbn``
             (accumulating fail_count).
          4. Delete all ``attempted`` rows for *other_isbn*.
          5. Update any ``linked_isbns`` rows that still reference *other_isbn*
             as their canonical to point at *lowest_isbn* instead.
          6. Insert the ``(lowest_isbn, other_isbn)`` pair into ``linked_isbns``.

        Foreign-key enforcement is temporarily disabled for this operation
        because the ``subjects`` table has a legacy FK to ``main(isbn)`` on a
        non-unique column which causes a ``"foreign key mismatch"`` error on
        ``DELETE`` when FK enforcement is on.

        Args:
            conn:        An open connection from ``transaction()``.
            lowest_isbn: The canonical ISBN that will own all merged data.
            other_isbn:  The non-canonical ISBN being retired.

        Raises:
            ValueError: If either argument is empty or both are equal.
        """
        lowest_isbn = (lowest_isbn or "").strip()
        other_isbn = (other_isbn or "").strip()
        if not lowest_isbn or not other_isbn:
            raise ValueError("lowest_isbn and other_isbn are required")
        if lowest_isbn == other_isbn:
            return

        # The subjects table has a legacy FK to main(isbn) where isbn is not
        # unique (main's PK is composite).  SQLite raises "foreign key mismatch"
        # on DELETE when FK enforcement is on, so we disable it for this
        # operation.  This PRAGMA must be issued before the first DML statement
        # so it takes effect before Python's sqlite3 module auto-begins a
        # transaction.
        conn.execute("PRAGMA foreign_keys = OFF;")

        moved_main_rows = conn.execute(
            """
            SELECT call_number, call_number_type, classification, source, date_added
            FROM main
            WHERE isbn = ?
            ORDER BY call_number_type
            """,
            (other_isbn,),
        ).fetchall()
        for row in moved_main_rows:
            existing = conn.execute(
                """
                SELECT call_number, classification, source, date_added
                FROM main
                WHERE isbn = ? AND call_number_type = ? AND source = ?
                LIMIT 1
                """,
                (lowest_isbn, row["call_number_type"], row["source"] or ""),
            ).fetchone()
            existing_date = normalize_to_datetime_str(existing["date_added"]) if existing else ""
            row_date = normalize_to_datetime_str(row["date_added"]) or ""
            # Keep the call_number from the more recent row; prefer other_isbn on tie
            # so a freshly harvested result always wins over an older canonical row.
            merged_call_number = (
                row["call_number"]
                if row_date >= existing_date
                else existing["call_number"]
            )
            merged_source = self._combine_sources(
                existing["source"] if existing else None,
                row["source"],
            )
            merged_classification = (
                existing["classification"]
                if existing and existing["classification"]
                else row["classification"]
            )
            merged_date = max(existing_date, row_date) or now_datetime_str()
            conn.execute(
                """
                INSERT INTO main (isbn, call_number, call_number_type, classification, source, date_added)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(isbn, call_number_type, source) DO UPDATE SET
                    call_number = excluded.call_number,
                    classification = excluded.classification,
                    source = excluded.source,
                    date_added = excluded.date_added
                """,
                (
                    lowest_isbn,
                    merged_call_number,
                    row["call_number_type"],
                    merged_classification,
                    row["source"] or "",
                    merged_date,
                ),
            )
        conn.execute("DELETE FROM main WHERE isbn = ?", (other_isbn,))

        conn.execute(
            """
            INSERT INTO attempted (isbn, last_target, attempt_type, last_attempted, fail_count, last_error)
            SELECT ?, last_target, attempt_type, last_attempted, fail_count, last_error
            FROM attempted
            WHERE isbn = ?
            ON CONFLICT(isbn, last_target, attempt_type) DO UPDATE SET
                last_attempted = CASE
                    WHEN excluded.last_attempted > attempted.last_attempted
                    THEN excluded.last_attempted
                    ELSE attempted.last_attempted
                END,
                fail_count = attempted.fail_count + excluded.fail_count,
                last_error = CASE
                    WHEN excluded.last_attempted >= attempted.last_attempted
                    THEN excluded.last_error
                    ELSE attempted.last_error
                END
            """,
            (lowest_isbn, other_isbn),
        )
        conn.execute("DELETE FROM attempted WHERE isbn = ?", (other_isbn,))

        conn.execute("DELETE FROM linked_isbns WHERE other_isbn = ?", (lowest_isbn,))
        conn.execute(
            "DELETE FROM linked_isbns WHERE lowest_isbn = ? AND other_isbn = ?",
            (other_isbn, lowest_isbn),
        )
        conn.execute(
            """
            UPDATE linked_isbns
            SET lowest_isbn = ?
            WHERE lowest_isbn = ?
              AND other_isbn <> ?
            """,
            (lowest_isbn, other_isbn, lowest_isbn),
        )
        self._upsert_linked_isbn_conn(conn, lowest_isbn=lowest_isbn, other_isbn=other_isbn)

    def rewrite_to_lowest_isbn_many(
        self,
        conn: sqlite3.Connection,
        pairs: Iterable[tuple[str, str]],
    ) -> None:
        """Apply ``_rewrite_to_lowest_isbn_conn`` for every (lowest, other) pair.

        Args:
            conn: An open database connection (must be within a transaction).
            pairs: Iterable of ``(lowest_isbn, other_isbn)`` tuples.
                   Pairs where both values are equal or either is empty are skipped.
        """
        if not pairs:
            return
        for lowest_isbn, other_isbn in pairs:
            if lowest_isbn and other_isbn and lowest_isbn != other_isbn:
                self._rewrite_to_lowest_isbn_conn(
                    conn,
                    lowest_isbn=lowest_isbn,
                    other_isbn=other_isbn,
                )

    def rewrite_to_lowest_isbn(self, *, lowest_isbn: str, other_isbn: str) -> None:
        """Move main/attempted rows from *other_isbn* to *lowest_isbn* and record the link."""
        with self.connect() as conn:
            self._rewrite_to_lowest_isbn_conn(conn, lowest_isbn=lowest_isbn, other_isbn=other_isbn)

    @staticmethod
    def _combine_sources(*values: Optional[str]) -> Optional[str]:
        """Merge multiple source strings into a single ``" + "``-delimited string.

        Each input value may itself be a delimited list (using ``+``, ``,``,
        ``;``, or ``|`` as separators).  Duplicates are removed while
        preserving first-seen order.  A known alias (``UCB`` → ``UBC``) is
        normalised.

        Returns:
            A deduplicated source string like ``"LoC + Harvard"``, or ``None``
            if all inputs are empty/None.
        """
        parts: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            # Split on any of the common source-list delimiters (+, comma, semicolon,
            # pipe) so that existing composite strings like "LoC + Harvard" are
            # expanded into individual tokens before deduplication.
            for piece in re.split(r"[+,;|]", text):
                cleaned = piece.strip()
                # Normalise a known legacy alias: "UCB" should read as "UBC"
                if cleaned.upper() == "UCB":
                    cleaned = "UBC"
                elif cleaned.upper() == "UBC":
                    cleaned = "UBC"
                if cleaned and cleaned not in parts:
                    parts.append(cleaned)
        if not parts:
            return None
        return " + ".join(parts)

    # -------------------------
    # GUI compatibility helpers
    # -------------------------
    def get_all_results(self, limit: int = 1000):
        """Return the most recent successful harvest results for dashboard/results views.

        Pivots the multi-row ``main`` table into one aggregated row per ISBN
        using conditional ``MAX()`` so both LCCN and NLMCN appear in the same
        result row.

        Args:
            limit: Maximum number of rows to return (ordered by newest first).

        Returns:
            A list of ``sqlite3.Row`` objects with columns: ``isbn``,
            ``lccn``, ``lccn_source``, ``nlmcn``, ``nlmcn_source``,
            ``classification``, ``source``, ``date_added``.
        """
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT
                    isbn,
                    MAX(CASE WHEN call_number_type = 'lccn' THEN call_number END) AS lccn,
                    MAX(CASE WHEN call_number_type = 'lccn' THEN source END) AS lccn_source,
                    MAX(CASE WHEN call_number_type = 'nlmcn' THEN call_number END) AS nlmcn,
                    MAX(CASE WHEN call_number_type = 'nlmcn' THEN source END) AS nlmcn_source,
                    MAX(CASE WHEN call_number_type = 'lccn' THEN classification END) AS classification,
                    group_concat(DISTINCT source) AS source,
                    MAX(date_added) AS date_added
                FROM main
                GROUP BY isbn
                ORDER BY MAX(date_added) DESC, isbn
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def get_failed_attempts(self, limit: int = 1000):
        """Return failed/attempted records for dashboard and results views.

        Also classifies rows whose ``last_error`` contains ``"invalid isbn"``
        with a ``status`` of ``'Invalid'`` rather than ``'Failed'``.

        Args:
            limit: Maximum number of rows to return (ordered by most recent first).

        Returns:
            A list of ``sqlite3.Row`` objects with columns: ``isbn``,
            ``last_target``, ``last_attempted``, ``fail_count``,
            ``last_error``, ``status``.
        """
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT
                    isbn,
                    last_target,
                    last_attempted,
                    fail_count,
                    last_error,
                    CASE
                        WHEN lower(coalesce(last_error, '')) LIKE '%invalid isbn%' THEN 'Invalid'
                        ELSE 'Failed'
                    END AS status
                FROM attempted
                ORDER BY last_attempted DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def clear_all_results(self) -> None:
        """Clear both successful and failed result tables."""
        with self.transaction() as conn:
            conn.execute("DELETE FROM main")
            conn.execute("DELETE FROM attempted")

    def get_global_stats(self) -> dict:
        """Return aggregate counts used by the dashboard summary cards.

        Returns:
            A dict with keys:
              ``"processed"`` -- total distinct ISBNs seen (found + failed),
              ``"found"``     -- distinct ISBNs with a call number in ``main``,
              ``"failed"``    -- distinct ISBNs in ``attempted`` (no result yet),
              ``"invalid"``   -- subset of failed whose error mentions ``"invalid isbn"``.
        """
        with self.connect() as conn:
            found = conn.execute("SELECT COUNT(DISTINCT isbn) FROM main").fetchone()[0]
            failed = conn.execute("SELECT COUNT(DISTINCT isbn) FROM attempted").fetchone()[0]
            invalid = conn.execute(
                "SELECT COUNT(DISTINCT isbn) FROM attempted WHERE lower(coalesce(last_error, '')) LIKE '%invalid isbn%'"
            ).fetchone()[0]
        return {
            "processed": int(found) + int(failed),
            "found": int(found),
            "failed": int(failed),
            "invalid": int(invalid),
        }

    def get_recent_results(self, limit: int = 10) -> list[dict]:
        """Return a merged chronological list of recent successes and failures.

        Combines rows from both the ``main`` and ``attempted`` tables in a
        single ``UNION ALL`` query so the activity list on the dashboard shows
        all recent events in time order regardless of outcome.

        Args:
            limit: Maximum number of events to return (most recent first).

        Returns:
            A list of dicts with keys: ``isbn``, ``status``, ``detail``, ``time``.
            ``status`` is one of ``"Found"``, ``"Failed"``, or ``"Invalid"``.
        """
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT isbn, status, detail, time
                FROM (
                    SELECT
                        isbn,
                        'Found' AS status,
                        trim(
                            coalesce(MAX(CASE WHEN call_number_type = 'lccn' THEN call_number END), '') ||
                            CASE
                                WHEN
                                    MAX(CASE WHEN call_number_type = 'lccn' THEN call_number END) IS NOT NULL
                                    AND MAX(CASE WHEN call_number_type = 'nlmcn' THEN call_number END) IS NOT NULL
                                THEN ' | '
                                ELSE ''
                            END ||
                            coalesce(MAX(CASE WHEN call_number_type = 'nlmcn' THEN call_number END), '')
                        ) AS detail,
                        MAX(date_added) AS time
                    FROM main
                    GROUP BY isbn
                    UNION ALL
                    SELECT
                        isbn,
                        CASE
                            WHEN lower(coalesce(last_error, '')) LIKE '%invalid isbn%' THEN 'Invalid'
                            ELSE 'Failed'
                        END AS status,
                        coalesce(last_error, '') AS detail,
                        last_attempted AS time
                    FROM attempted
                )
                ORDER BY time DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


if __name__ == "__main__":
    # Manual smoke test for local development when running this module directly.
    db = DatabaseManager("data/lccn_harvester.sqlite3")
    db.init_db()

    db.upsert_main(MainRecord(isbn="9780132350884", lccn="QA76.76", source="LoC"))
    print("Main:", db.get_main("9780132350884"))

    db.upsert_attempted(isbn="0000000000", last_target="Harvard", last_error="Not found")
    print("Attempted:", db.get_attempted("0000000000"))
