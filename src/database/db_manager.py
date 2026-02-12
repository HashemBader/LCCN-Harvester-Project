from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Iterable, Sequence




def utc_now_iso() -> str:
    """Return current UTC time as ISO-8601 string (no microseconds)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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
    nlmcn: Optional[str] = None
    classification: Optional[str] = None
    source: Optional[str] = None
    date_added: Optional[str] = None  # ISO string


@dataclass(frozen=True)
class AttemptedRecord:
    isbn: str
    last_target: Optional[str] = None
    last_attempted: Optional[str] = None  # ISO string
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

    def connect(self) -> sqlite3.Connection:
        """Open a connection and apply performance-friendly PRAGMAs."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # timeout helps when multiple threads/processes try to write
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row

        # Safety + perf pragmas
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")      # better concurrent reads/writes
        conn.execute("PRAGMA synchronous = NORMAL;")    # faster than FULL, still safe enough
        conn.execute("PRAGMA temp_store = MEMORY;")     # faster temp operations
        conn.execute("PRAGMA busy_timeout = 5000;")     # wait up to 5s if db is busy

        return conn


    def init_db(self, schema_path: Optional[Path] = None) -> None:
        """
        Initialize database using schema.sql.
        If schema_path is None, it loads schema.sql from the same folder as this file.
        """
        if schema_path is None:
            schema_path = Path(__file__).with_name("schema.sql")

        schema_sql = schema_path.read_text(encoding="utf-8")

        with self.connect() as conn:
            conn.executescript(schema_sql)
            conn.commit()

    @contextmanager
    def transaction(self) -> sqlite3.Connection:
        """
        Open a transaction connection.
        - Commits if the block succeeds
        - Rolls back if an exception is raised
        """
        conn = self.connect()
        try:
            conn.execute("BEGIN;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

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
                "SELECT isbn, lccn, nlmcn, classification, source, date_added FROM main WHERE isbn = ?",
                (isbn,),
            ).fetchone()

        if not row:
            return None

        return MainRecord(
            isbn=row["isbn"],
            lccn=row["lccn"],
            nlmcn=row["nlmcn"],
            classification=row["classification"],
            source=row["source"],
            date_added=row["date_added"],
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
            date_added = r.date_added or utc_now_iso()
            classification = r.classification or classification_from_lccn(r.lccn)
            rows.append((r.isbn, r.lccn, r.nlmcn, classification, r.source, date_added))
            isbns.append(r.isbn)

        conn.executemany(
            """
            INSERT INTO main (isbn, lccn, nlmcn, classification, source, date_added)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(isbn) DO UPDATE SET
                lccn = excluded.lccn,
                nlmcn = excluded.nlmcn,
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
        date_added = record.date_added or utc_now_iso()
        classification = record.classification or classification_from_lccn(record.lccn)

        conn.execute(
            """
            INSERT INTO main (isbn, lccn, nlmcn, classification, source, date_added)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(isbn) DO UPDATE SET
                lccn = excluded.lccn,
                nlmcn = excluded.nlmcn,
                classification = excluded.classification,
                source = excluded.source,
                date_added = excluded.date_added
            """,
            (record.isbn, record.lccn, record.nlmcn, classification, record.source, date_added),
        )

        if clear_attempted_on_success:
            conn.execute("DELETE FROM attempted WHERE isbn = ?", (record.isbn,))

    # -------------------------
    # ATTEMPTED TABLE HELPERS
    # -------------------------
    def get_attempted(self, isbn: str) -> Optional[AttemptedRecord]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT isbn, last_target, last_attempted, fail_count, last_error FROM attempted WHERE isbn = ?",
                (isbn,),
            ).fetchone()

        if not row:
            return None

        return AttemptedRecord(
            isbn=row["isbn"],
            last_target=row["last_target"],
            last_attempted=row["last_attempted"],
            fail_count=int(row["fail_count"]),
            last_error=row["last_error"],
        )

    def should_skip_retry(self, isbn: str, retry_days: int) -> bool:
        """Return True if this ISBN was attempted within the last `retry_days` days."""
        att = self.get_attempted(isbn)
        if att is None or not att.last_attempted:
            return False

        last = datetime.fromisoformat(att.last_attempted)
        now = datetime.now(timezone.utc)
        return (now - last) < timedelta(days=retry_days)

    def upsert_attempted(
        self,
        *,
        isbn: str,
        last_target: Optional[str],
        last_error: Optional[str] = None,
        attempted_time: Optional[str] = None,
    ) -> None:
        with self.transaction() as conn:
            self._upsert_attempted_conn(
                conn,
                isbn=isbn,
                last_target=last_target,
                last_error=last_error,
                attempted_time=attempted_time,
            )

    def upsert_attempted_many(
        self,
        conn: sqlite3.Connection,
        rows: Sequence[tuple[str, Optional[str], Optional[str], Optional[str]]],
    ) -> None:
        """
        Batch upsert attempted rows within an existing transaction connection.

        rows items are:
          (isbn, last_target, attempted_time, last_error)
        """
        if not rows:
            return

        fixed_rows = []
        for isbn, last_target, attempted_time, last_error in rows:
            fixed_rows.append((isbn, last_target, attempted_time or utc_now_iso(), last_error))

        conn.executemany(
            """
            INSERT INTO attempted (isbn, last_target, last_attempted, fail_count, last_error)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(isbn) DO UPDATE SET
                last_target = excluded.last_target,
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
        last_error: Optional[str],
        attempted_time: Optional[str],
    ) -> None:
        attempted_time = attempted_time or utc_now_iso()

        conn.execute(
            """
            INSERT INTO attempted (isbn, last_target, last_attempted, fail_count, last_error)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(isbn) DO UPDATE SET
                last_target = excluded.last_target,
                last_attempted = excluded.last_attempted,
                fail_count = attempted.fail_count + 1,
                last_error = excluded.last_error
            """,
            (isbn, last_target, attempted_time, last_error),
        )

    def clear_attempted(self, isbn: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM attempted WHERE isbn = ?", (isbn,))
            conn.commit()

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

    # -------------------------
    # V2 GUI COMPATIBILITY HELPERS
    # -------------------------
    def get_all_results(self, limit: int = 1000):
        """Return successful records for results/dashboard views."""
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT isbn, lccn, nlmcn, classification, source, date_added
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
