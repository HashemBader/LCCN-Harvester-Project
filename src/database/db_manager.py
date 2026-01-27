from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional


# -------------------------
# Date helpers (requirements: yyyymmdd integers)
# -------------------------
def today_yyyymmdd() -> int:
    """Return today's UTC date as integer yyyymmdd."""
    return int(datetime.now(timezone.utc).strftime("%Y%m%d"))


def yyyymmdd_to_date(value: int) -> date:
    """Convert integer yyyymmdd -> datetime.date."""
    s = str(value)
    return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))


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


# -------------------------
# Data models
# -------------------------
@dataclass(frozen=True)
class MainRecord:
    isbn: str
    lccn: Optional[str] = None
    nlmcn: Optional[str] = None
    classification: Optional[str] = None
    source: Optional[str] = None
    date_added: Optional[int] = None  # yyyymmdd int


@dataclass(frozen=True)
class AttemptedRecord:
    isbn: str
    target: str
    last_attempted: Optional[int] = None  # yyyymmdd int
    fail_count: int = 1
    last_error: Optional[str] = None


# -------------------------
# Database manager
# -------------------------
class DatabaseManager:
    """
    SQLite manager aligned with requirements schema:

    Table main:
      isbn (PK), lccn, nlmcn, classification, source, date_added (yyyymmdd int)

    Table attempted:
      (isbn, target) (composite PK),
      last_attempted (yyyymmdd int), fail_count, last_error
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

        This manager opens a new SQLite connection per operation.
        """
        return

    # -------------------------
    # MAIN TABLE HELPERS
    # -------------------------
    def get_main(self, isbn: str) -> Optional[MainRecord]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT isbn, lccn, nlmcn, classification, source, date_added "
                "FROM main WHERE isbn = ?",
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
            date_added=int(row["date_added"]),
        )

    def upsert_main(self, record: MainRecord, *, clear_attempted_on_success: bool = True) -> None:
        """
        Insert/update a main record.

        - If date_added missing, set to today yyyymmdd.
        - If classification missing, derive from lccn.
        - Optionally clears ALL attempted entries for that ISBN on success.
        """
        date_added = record.date_added or today_yyyymmdd()
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
    # ATTEMPTED TABLE HELPERS (per isbn+target)
    # -------------------------
    def get_attempted(self, isbn: str, target: str) -> Optional[AttemptedRecord]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT isbn, target, last_attempted, fail_count, last_error "
                "FROM attempted WHERE isbn = ? AND target = ?",
                (isbn, target),
            ).fetchone()

        if not row:
            return None

        return AttemptedRecord(
            isbn=row["isbn"],
            target=row["target"],
            last_attempted=int(row["last_attempted"]),
            fail_count=int(row["fail_count"]),
            last_error=row["last_error"],
        )

    def upsert_attempted(
        self,
        *,
        isbn: str,
        target: str,
        last_error: Optional[str] = None,
        attempted_date: Optional[int] = None,
    ) -> None:
        """
        Record a failed attempt for a specific (isbn, target).

        - attempted_date stored as yyyymmdd int (defaults to today).
        - On conflict (isbn, target), increments fail_count and updates last_attempted/last_error.
        """
        attempted_date = attempted_date or today_yyyymmdd()

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO attempted (isbn, target, last_attempted, fail_count, last_error)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(isbn, target) DO UPDATE SET
                    last_attempted = excluded.last_attempted,
                    fail_count = attempted.fail_count + 1,
                    last_error = excluded.last_error
                """,
                (isbn, target, attempted_date, last_error),
            )
            conn.commit()

    def clear_attempted(self, isbn: str, target: Optional[str] = None) -> None:
        """
        Clear attempted entries.

        - If target is provided: clears only that (isbn, target)
        - If target is None: clears ALL attempted rows for that isbn
        """
        with self.connect() as conn:
            if target is None:
                conn.execute("DELETE FROM attempted WHERE isbn = ?", (isbn,))
            else:
                conn.execute("DELETE FROM attempted WHERE isbn = ? AND target = ?", (isbn, target))
            conn.commit()

    def should_skip_retry(self, isbn: str, target: str, retry_days: int) -> bool:
        """
        Return True if this (isbn, target) was attempted within the last `retry_days` days.
        """
        att = self.get_attempted(isbn, target)
        if att is None or att.last_attempted is None:
            return False

        last_dt = yyyymmdd_to_date(att.last_attempted)
        now_dt = yyyymmdd_to_date(today_yyyymmdd())

        return (now_dt - last_dt).days < retry_days


# Smoke test:
#   python -m src.database.db_manager
if __name__ == "__main__":
    db = DatabaseManager()
    db.init_db()

    db.upsert_main(MainRecord(isbn="9780132350884", lccn="QA76.76", source="LoC"))
    print("Main:", db.get_main("9780132350884"))

    db.upsert_attempted(isbn="0000000000", target="Harvard", last_error="Not found")
    print("Attempted:", db.get_attempted("0000000000", "Harvard"))
