from __future__ import annotations

import sqlite3
import sys
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Iterable, Sequence




def now_datetime_str() -> str:
    """Return current local datetime as an ISO-8601 string (e.g. 2026-03-17 12:00:00)."""
    return datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def normalize_to_datetime_str(value: Optional[int | str]) -> Optional[str]:
    """Convert supported date values to an ISO-8601 datetime string."""
    if value in (None, ""):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # If already in YYYY-MM-DD HH:MM:SS format
        if len(text) == 19 and text[4] == "-" and text[10] == " " and text[13] == ":":
            return text
        # If bare yyyymmdd string
        if len(text) == 8 and text.isdigit():
            return f"{text[:4]}-{text[4:6]}-{text[6:8]} 00:00:00"
        
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return text
    
    if isinstance(value, int):
        s = str(value)
        if len(s) == 8:
            return f"{s[:4]}-{s[4:6]}-{s[6:8]} 00:00:00"
    
    return str(value)


def yyyymmdd_to_iso_date(value: Optional[int | str]) -> Optional[str]:
    """Deprecated: Convert legacy values into an ISO date string."""
    return normalize_to_datetime_str(value)


def classification_from_lccn(lccn: Optional[str]) -> Optional[str]:
    """
    Best-effort: derive LoC classification letters (1-3 leading letters) from an LCCN.
    Example: 'QA76.73.P98' -> 'QA'
    """
    if not lccn:
        return None
    letters: list[str] = []
    for ch in lccn.strip():
        if ch.isalpha():
            letters.append(ch.upper())
            if len(letters) == 3:
                break
        else:
            break
    return "".join(letters) if letters else None


@dataclass(frozen=True)
class MainRecord:
    isbn: str
    lccn: Optional[str] = None
    lccn_source: Optional[str] = None
    nlmcn: Optional[str] = None
    nlmcn_source: Optional[str] = None
    classification: Optional[str] = None
    source: Optional[str] = None
    date_added: Optional[str] = None  # stored as ISO-8601 string


@dataclass(frozen=True)
class AttemptedRecord:
    isbn: str
    last_target: Optional[str] = None
    attempt_type: str = "both"
    last_attempted: Optional[str] = None  # ISO-8601 string
    fail_count: int = 1
    last_error: Optional[str] = None


class DatabaseManager:
    """
    SQLite manager for:
      - main: successful ISBN -> call number results
      - attempted: failed lookups + retry tracking

    Sprint 5 requirement:
      - provide transactions + batch upserts for performance and atomicity.
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
        """
        Open a connection, yield it, commit on success, rollback on error,
        and ALWAYS close it.

        ``sqlite3.Connection`` used as a plain ``with`` statement only commits
        or rolls back – it never closes the connection.  That leaks open handles
        which keep the WAL file active and can corrupt the database if the
        process is killed.  This wrapper guarantees the connection is closed
        after every ``with self.connect() as conn:`` block.
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
        import logging
        for suffix in ("", "-shm", "-wal"):
            path = self.db_path.parent / (self.db_path.name + suffix)
            try:
                if path.exists():
                    path.unlink()
                    logging.getLogger(__name__).warning("Deleted corrupt DB file: %s", path)
            except Exception as exc:
                logging.getLogger(__name__).error("Could not delete %s: %s", path, exc)

    def init_db(self, schema_path: Optional[Path] = None) -> None:
        """
        Initialize database using schema.sql.
        If schema_path is None, it loads schema.sql from the same folder as this file.
        If the database file is corrupt, it is automatically deleted and recreated.
        """
        if schema_path is None:
            schema_path = self._default_schema_path()

        # Auto-repair: if the existing file is malformed, wipe and start fresh
        if not self._is_db_healthy():
            import logging
            logging.getLogger(__name__).error(
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
            self._migrate_dates_to_datetime(conn)

    def _migrate_main_schema_if_needed(self, conn: sqlite3.Connection) -> None:
        """Ensure main table supports multiple source rows per ISBN + type."""
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
            date_added = normalize_to_datetime_str(row["date_added"]) or now_datetime_str()
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
        """
        Ensure attempted table uses target/type-specific primary key:
          PRIMARY KEY (isbn, last_target, attempt_type)
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
                last_attempted    DATETIME NOT NULL,
                fail_count        INTEGER NOT NULL DEFAULT 1,
                last_error        TEXT,
                PRIMARY KEY (isbn, last_target, attempt_type)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO attempted (isbn, last_target, attempt_type, last_attempted, fail_count, last_error)
            SELECT
                isbn,
                COALESCE(last_target, ''),
                'both',
                last_attempted,
                fail_count,
                last_error
            FROM attempted_legacy
            """
        )
        conn.execute("DROP TABLE attempted_legacy")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_attempted_last_attempted ON attempted(last_attempted)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_attempted_last_target ON attempted(last_target)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_attempted_isbn ON attempted(isbn)")

    def _migrate_linked_isbns_schema_if_needed(self, conn: sqlite3.Connection) -> None:
        """Ensure linked_isbns uses lowest/other columns and preserves legacy mappings."""
        cols = conn.execute("PRAGMA table_info(linked_isbns)").fetchall()
        if not cols:
            return

        col_names = {row["name"] for row in cols}
        pk_cols = [row["name"] for row in sorted(cols, key=lambda row: int(row["pk"])) if int(row["pk"]) > 0]
        desired_pk = ["lowest_isbn", "other_isbn"]
        has_other_unique = False
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

    def _migrate_dates_to_datetime(self, conn: sqlite3.Connection) -> None:
        """
        One-off migration: convert any legacy yyyymmdd integers stored in
        main.date_added and attempted.last_attempted to ISO datetime strings.
        """
        import logging
        log = logging.getLogger(__name__)

        def _to_datetime_str(value) -> Optional[str]:
            return normalize_to_datetime_str(value)

        # -- main.date_added --
        rows_main = conn.execute(
            "SELECT rowid, date_added FROM main WHERE typeof(date_added) IN ('integer', 'text')"
        ).fetchall()
        for row in rows_main:
            old_val = row["date_added"]
            new_val = _to_datetime_str(old_val)
            if new_val and new_val != str(old_val):
                conn.execute("UPDATE main SET date_added = ? WHERE rowid = ?", (new_val, row["rowid"]))

        # -- attempted.last_attempted --
        rows_att = conn.execute(
            "SELECT rowid, last_attempted FROM attempted WHERE typeof(last_attempted) IN ('integer', 'text')"
        ).fetchall()
        for row in rows_att:
            old_val = row["last_attempted"]
            new_val = _to_datetime_str(old_val)
            if new_val and new_val != str(old_val):
                conn.execute("UPDATE attempted SET last_attempted = ? WHERE rowid = ?", (new_val, row["rowid"]))

        if rows_main or rows_att:
            log.info(
                "_migrate_dates_to_yyyymmdd: converted %d main rows and %d attempted rows",
                len(rows_main), len(rows_att),
            )

    @contextmanager
    def transaction(self):
        """
        Open a transaction connection.
        - Commits if the block succeeds
        - Rolls back if an exception is raised
        - Always closes the connection (delegates to connect())
        """
        with self.connect() as conn:
            yield conn

    def close(self) -> None:
        """
        Compatibility no-op.

        This manager uses short-lived connections for single ops,
        and explicit transaction() for batch operations.
        """
        return



    # -------------------------
    # MAIN TABLE HELPERS
    # -------------------------
    @staticmethod
    def _record_success_types(record: MainRecord) -> tuple[str, ...]:
        types: list[str] = []
        if record.lccn:
            types.append("lccn")
        if record.nlmcn:
            types.append("nlmcn")
        return tuple(types)

    @staticmethod
    def _aggregate_main_rows(rows: Sequence[sqlite3.Row]) -> Optional[MainRecord]:
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
            date_added=latest_date,
        )

    def _explode_main_record(self, record: MainRecord) -> list[tuple[str, str, str, Optional[str], Optional[str], str]]:
        date_added = normalize_to_datetime_str(record.date_added) or now_datetime_str()
        rows: list[tuple[str, str, str, Optional[str], Optional[str], str]] = []
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

    def upsert_main(self, record: MainRecord, *, clear_attempted_on_success: bool = True) -> None:
        with self.transaction() as conn:
            self._upsert_main_conn(conn, record, clear_attempted_on_success=clear_attempted_on_success)

    def upsert_main_many(
        self,
        conn: sqlite3.Connection,
        records: Sequence[MainRecord],
        *,
        clear_attempted_on_success: bool = True,
    ) -> None:
        """Batch upsert main records within an existing transaction connection."""
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
        """Return True if this ISBN+target+type key was attempted within retry window.

        last_attempted is stored as a DATETIME string; compare as a date by parsing
        it back to a datetime object.
        """
        att = self.get_attempted_for(isbn, last_target, attempt_type)
        if att is None or not att.last_attempted:
            return False

        last_val = att.last_attempted
        try:
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
                return False
        except Exception:
            return False

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
        """
        Batch upsert attempted rows within an existing transaction connection.

        rows items are:
          (isbn, last_target, attempt_type, attempted_time, last_error)
          where attempted_time is an ISO-8601 string (e.g. 2026-03-17 12:00:00)
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
                    attempted_time or now_datetime_str(),
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
        attempted_time = attempted_time or now_datetime_str()

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
        with self.connect() as conn:
            conn.execute("DELETE FROM attempted WHERE isbn = ?", (isbn,))

    def clear_attempted_many(self, conn: sqlite3.Connection, isbns: Iterable[str]) -> None:
        isbns_list = list(isbns)
        if not isbns_list:
            return

        # SQLite has a limit on variables; chunk if needed
        CHUNK = 900
        for i in range(0, len(isbns_list), CHUNK):
            chunk = isbns_list[i : i + CHUNK]
            placeholders = ",".join("?" for _ in chunk)
            conn.execute(f"DELETE FROM attempted WHERE isbn IN ({placeholders})", tuple(chunk))

    def clear_attempted_for(self, isbn: str, attempt_type: str) -> None:
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
        pairs_list = [(isbn, attempt_type) for isbn, attempt_type in pairs if isbn and attempt_type]
        if not pairs_list:
            return

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
        parts: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            for piece in re.split(r"[+,;|]", text):
                cleaned = piece.strip()
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
    # V2 GUI COMPATIBILITY HELPERS
    # -------------------------
    def get_all_results(self, limit: int = 1000):
        """Return successful records for results/dashboard views."""
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
        """Return failed/attempted records for results/dashboard views."""
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
        """Return aggregate stats used by dashboard cards."""
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
        """Return merged recent successes/failures for dashboard activity list."""
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
    db = DatabaseManager("data/lccn_harvester.sqlite3")
    db.init_db()

    db.upsert_main(MainRecord(isbn="9780132350884", lccn="QA76.76", source="LoC"))
    print("Main:", db.get_main("9780132350884"))

    db.upsert_attempted(isbn="0000000000", last_target="Harvard", last_error="Not found")
    print("Attempted:", db.get_attempted("0000000000"))
