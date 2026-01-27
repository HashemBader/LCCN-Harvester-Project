from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


def utc_now_iso() -> str:
    """Return current UTC time as ISO-8601 string (no microseconds)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def classification_from_lccn(lccn: Optional[str]) -> Optional[str]:
    """Derive LoC classification letters (1-3 leading letters) from an LCCN string."""
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
    Minimal SQLite manager for:
      - main: successful ISBN -> call number results
      - attempted: failed lookups + retry tracking

    Intended usage:
      db = DatabaseManager()  # uses default DB path
      db.init_db()
      db.upsert_main(...)
      db.upsert_attempted(...)
    """

    def __init__(self, db_path: Path | str = "data/lccn_harvester.sqlite3"):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        """Open a connection and ensure foreign keys are enabled."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_db(self) -> None:
        """Initialize database schema from schema.sql located in this package folder."""
        schema_path = Path(__file__).with_name("schema.sql")
        schema_sql = schema_path.read_text(encoding="utf-8")

        with self.connect() as conn:
            conn.executescript(schema_sql)
            conn.commit()

    def close(self) -> None:
        """
        Compatibility no-op.

        This manager opens a new SQLite connection per operation (self.connect()).
        There is no long-lived connection to close, but the CLI expects db.close().
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
        """
        Insert/update a main record.
        - isbn is the key
        - if date_added missing, set to now
        - if classification missing, derive from lccn
        - optionally clear attempted record once it succeeds
        """
        date_added = record.date_added or utc_now_iso()
        classification = record.classification or classification_from_lccn(record.lccn)

        with self.connect() as conn:
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

            conn.commit()

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
        """
        Record a failed attempt.
        - If ISBN already exists in attempted, increment fail_count and update last_* fields.
        """
        attempted_time = attempted_time or utc_now_iso()

        with self.connect() as conn:
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
            conn.commit()

    def clear_attempted(self, isbn: str) -> None:
        """Remove an ISBN from attempted table (useful once it succeeds)."""
        with self.connect() as conn:
            conn.execute("DELETE FROM attempted WHERE isbn = ?", (isbn,))
            conn.commit()


# Quick smoke test (run from project root):
#   python -m src.database.db_manager
if __name__ == "__main__":
    db = DatabaseManager()
    db.init_db()

    db.upsert_main(MainRecord(isbn="9780132350884", lccn="QA76.76", source="LoC"))
    print("Main:", db.get_main("9780132350884"))

    db.upsert_attempted(isbn="0000000000", last_target="Harvard", last_error="Not found")
    print("Attempted:", db.get_attempted("0000000000"))
