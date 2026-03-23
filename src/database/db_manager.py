from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Iterable, Sequence




def utc_now_iso() -> str:
    """Return current UTC time as ISO-8601 string (no microseconds).

    Deprecated: kept for any callers that still need ISO strings.
    New code should use today_yyyymmdd() instead.
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today_yyyymmdd() -> int:
    """Return today's local date as a yyyymmdd integer (e.g. 20260317)."""
    return int(datetime.now().strftime("%Y%m%d"))


def normalize_to_yyyymmdd(value: Optional[int | str]) -> Optional[int]:
    """Convert supported date values to a yyyymmdd integer."""
    if value in (None, ""):
        return None
    if isinstance(value, int):
        return value

    text = str(value).strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        return int(text)

    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return int(dt.strftime("%Y%m%d"))


def yyyymmdd_to_iso_date(value: Optional[int | str]) -> Optional[str]:
    """Convert yyyymmdd storage values into an ISO date string."""
    if value in (None, ""):
        return None

    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"

    return text


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
    date_added: Optional[int | str] = None  # stored as yyyymmdd, returned compatibly for callers


@dataclass(frozen=True)
class AttemptedRecord:
    isbn: str
    last_target: Optional[str] = None
    attempt_type: str = "both"
    last_attempted: Optional[int] = None  # yyyymmdd integer (e.g. 20260317)
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
            schema_path = Path(__file__).with_name("schema.sql")

        # Auto-repair: if the existing file is malformed, wipe and start fresh
        if not self._is_db_healthy():
            import logging
            logging.getLogger(__name__).error(
                "Database at %s is malformed – resetting to a clean state.", self.db_path
            )
            self._reset_db_files()

        schema_sql = schema_path.read_text(encoding="utf-8")

        with self.connect() as conn:
            conn.executescript(schema_sql)
            self._migrate_main_schema_if_needed(conn)
            self._migrate_attempted_schema_if_needed(conn)
            self._migrate_dates_to_yyyymmdd(conn)

    def _migrate_main_schema_if_needed(self, conn: sqlite3.Connection) -> None:
        """Ensure main table has per-type source columns."""
        cols = conn.execute("PRAGMA table_info(main)").fetchall()
        if not cols:
            return

        col_names = {row["name"] for row in cols}
        if "lccn_source" not in col_names:
            conn.execute("ALTER TABLE main ADD COLUMN lccn_source TEXT")
            conn.execute(
                "UPDATE main SET lccn_source = source WHERE lccn IS NOT NULL AND lccn_source IS NULL"
            )
        if "nlmcn_source" not in col_names:
            conn.execute("ALTER TABLE main ADD COLUMN nlmcn_source TEXT")
            conn.execute(
                "UPDATE main SET nlmcn_source = source WHERE nlmcn IS NOT NULL AND nlmcn_source IS NULL"
            )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_main_lccn_source ON main(lccn_source)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_main_nlmcn_source ON main(nlmcn_source)")

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
                last_attempted    TEXT NOT NULL,
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

    def _migrate_dates_to_yyyymmdd(self, conn: sqlite3.Connection) -> None:
        """
        One-off migration: convert any legacy ISO text dates stored in
        main.date_added, attempted.last_attempted, and subjects.date_added
        to yyyymmdd integers.

        A row is considered a legacy ISO string when the stored value is TEXT
        (typeof) and contains a '-' character (e.g. '2025-06-01T12:00:00+00:00').
        Rows that already hold an 8-digit integer are left untouched.

        Safe to call repeatedly — it skips rows that are already integers.
        """
        import logging
        log = logging.getLogger(__name__)

        def _iso_to_yyyymmdd(value: str) -> Optional[int]:
            """Parse a date string and return yyyymmdd int, or None on failure.
            Handles both ISO strings ('2026-03-08T...') and bare yyyymmdd strings ('20260308').
            """
            try:
                s = str(value).strip()
                # Already a bare yyyymmdd string — just cast directly
                if len(s) == 8 and s.isdigit():
                    return int(s)
                # Accept both date-only '2025-06-01' and full datetime strings
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                return int(dt.strftime("%Y%m%d"))
            except Exception:
                return None

        # -- main.date_added --
        rows_main = conn.execute(
            "SELECT isbn, date_added FROM main WHERE typeof(date_added) = 'text'"
        ).fetchall()
        for row in rows_main:
            new_val = _iso_to_yyyymmdd(row["date_added"])
            if new_val is not None:
                conn.execute("UPDATE main SET date_added = ? WHERE isbn = ?", (new_val, row["isbn"]))
            else:
                log.warning("Could not convert main.date_added=%r for isbn=%s", row["date_added"], row["isbn"])

        # -- attempted.last_attempted --
        rows_att = conn.execute(
            "SELECT isbn, last_target, attempt_type, last_attempted "
            "FROM attempted WHERE typeof(last_attempted) = 'text'"
        ).fetchall()
        for row in rows_att:
            new_val = _iso_to_yyyymmdd(row["last_attempted"])
            if new_val is not None:
                conn.execute(
                    "UPDATE attempted SET last_attempted = ? "
                    "WHERE isbn = ? AND last_target = ? AND attempt_type = ?",
                    (new_val, row["isbn"], row["last_target"], row["attempt_type"]),
                )
            else:
                log.warning(
                    "Could not convert attempted.last_attempted=%r for isbn=%s",
                    row["last_attempted"], row["isbn"],
                )

        # -- subjects.date_added (stretch table, may not exist yet) --
        try:
            rows_subj = conn.execute(
                "SELECT id, date_added FROM subjects WHERE typeof(date_added) = 'text'"
            ).fetchall()
            for row in rows_subj:
                new_val = _iso_to_yyyymmdd(row["date_added"])
                if new_val is not None:
                    conn.execute("UPDATE subjects SET date_added = ? WHERE id = ?", (new_val, row["id"]))
                else:
                    log.warning("Could not convert subjects.date_added=%r for id=%s", row["date_added"], row["id"])
        except Exception:
            pass  # subjects table may not exist in all deployments

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
    def get_main(self, isbn: str) -> Optional[MainRecord]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT isbn, lccn, lccn_source, nlmcn, nlmcn_source, classification, source, date_added
                FROM main
                WHERE isbn = ?
                """,
                (isbn,),
            ).fetchone()

        if not row:
            return None

        return MainRecord(
            isbn=row["isbn"],
            lccn=row["lccn"],
            lccn_source=row["lccn_source"] if "lccn_source" in row.keys() else row["source"],
            nlmcn=row["nlmcn"],
            nlmcn_source=row["nlmcn_source"] if "nlmcn_source" in row.keys() else row["source"],
            classification=row["classification"],
            source=row["source"],
            date_added=yyyymmdd_to_iso_date(row["date_added"]),
        )

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

        rows: list[tuple] = []
        isbns: list[str] = []
        for r in records:
            date_added = normalize_to_yyyymmdd(r.date_added) or today_yyyymmdd()
            classification = r.classification or classification_from_lccn(r.lccn)
            rows.append(
                (
                    r.isbn,
                    r.lccn,
                    r.lccn_source or r.source,
                    r.nlmcn,
                    r.nlmcn_source or r.source,
                    classification,
                    self._combine_sources(r.lccn_source or r.source, r.nlmcn_source or r.source),
                    date_added,
                )
            )
            isbns.append(r.isbn)

        conn.executemany(
            """
            INSERT INTO main (isbn, lccn, lccn_source, nlmcn, nlmcn_source, classification, source, date_added)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(isbn) DO UPDATE SET
                lccn = excluded.lccn,
                lccn_source = excluded.lccn_source,
                nlmcn = excluded.nlmcn,
                nlmcn_source = excluded.nlmcn_source,
                classification = excluded.classification,
                source = excluded.source,
                date_added = excluded.date_added
            """,
            rows,
        )

        if clear_attempted_on_success:
            self.clear_attempted_many(conn, isbns)

    def _upsert_main_conn(
        self,
        conn: sqlite3.Connection,
        record: MainRecord,
        *,
        clear_attempted_on_success: bool,
    ) -> None:
        date_added = normalize_to_yyyymmdd(record.date_added) or today_yyyymmdd()
        classification = record.classification or classification_from_lccn(record.lccn)
        source = self._combine_sources(
            record.lccn_source or record.source,
            record.nlmcn_source or record.source,
        )

        conn.execute(
            """
            INSERT INTO main (isbn, lccn, lccn_source, nlmcn, nlmcn_source, classification, source, date_added)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(isbn) DO UPDATE SET
                lccn = excluded.lccn,
                lccn_source = excluded.lccn_source,
                nlmcn = excluded.nlmcn,
                nlmcn_source = excluded.nlmcn_source,
                classification = excluded.classification,
                source = excluded.source,
                date_added = excluded.date_added
            """,
            (
                record.isbn,
                record.lccn,
                record.lccn_source or record.source,
                record.nlmcn,
                record.nlmcn_source or record.source,
                classification,
                source,
                date_added,
            ),
        )

        if clear_attempted_on_success:
            conn.execute("DELETE FROM attempted WHERE isbn = ?", (record.isbn,))

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

        last_attempted is stored as a yyyymmdd integer; compare as a date by parsing
        it back to a date object.
        """
        att = self.get_attempted_for(isbn, last_target, attempt_type)
        if att is None or not att.last_attempted:
            return False

        last_val = att.last_attempted
        try:
            # Support both legacy ISO strings (migration period) and new yyyymmdd integers
            if isinstance(last_val, int) or (isinstance(last_val, str) and last_val.isdigit() and len(last_val) == 8):
                last_str = str(last_val)
                last_date = datetime(int(last_str[:4]), int(last_str[4:6]), int(last_str[6:8]), tzinfo=timezone.utc)
            else:
                last_date = datetime.fromisoformat(str(last_val))
                if last_date.tzinfo is None:
                    last_date = last_date.replace(tzinfo=timezone.utc)
        except Exception:
            return False

        now = datetime.now(timezone.utc)
        return (now - last_date) < timedelta(days=retry_days)

    def upsert_attempted(
        self,
        *,
        isbn: str,
        last_target: Optional[str],
        attempt_type: str = "both",
        last_error: Optional[str] = None,
        attempted_time: Optional[int] = None,
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
        rows: Sequence[tuple[str, Optional[str], str, Optional[int], Optional[str]]],
    ) -> None:
        """
        Batch upsert attempted rows within an existing transaction connection.

        rows items are:
          (isbn, last_target, attempt_type, attempted_time, last_error)
          where attempted_time is a yyyymmdd integer (e.g. 20260317)
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
                    attempted_time or today_yyyymmdd(),
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
        attempted_time: Optional[int],
    ) -> None:
        attempted_time = attempted_time or today_yyyymmdd()

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

    @staticmethod
    def _combine_sources(*values: Optional[str]) -> Optional[str]:
        parts: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in parts:
                parts.append(text)
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
                SELECT isbn, lccn, lccn_source, nlmcn, nlmcn_source, classification, source, date_added
                FROM main
                ORDER BY date_added DESC
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
            found = conn.execute("SELECT COUNT(*) FROM main").fetchone()[0]
            failed = conn.execute("SELECT COUNT(*) FROM attempted").fetchone()[0]
            invalid = conn.execute(
                "SELECT COUNT(*) FROM attempted WHERE lower(coalesce(last_error, '')) LIKE '%invalid isbn%'"
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
                            coalesce(lccn, '') ||
                            CASE
                                WHEN lccn IS NOT NULL AND nlmcn IS NOT NULL THEN ' | '
                                ELSE ''
                            END ||
                            coalesce(nlmcn, '')
                        ) AS detail,
                        date_added AS time
                    FROM main
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
