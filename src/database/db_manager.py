"""
Module: db_manager.py
Part of the LCCN Harvester Project.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


class DatabaseManager:
    """
    Creates/opens the SQLite database and initializes tables using schema.sql.
    This translates the planned DB design into real SQLite code.

    Default DB location: ./data/lccn_harvester.db
    """

    def __init__(self, db_path: str | Path = Path("data") / "lccn_harvester.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row

    def init_db(self) -> None:
        """Run schema.sql to create tables/indexes if they do not exist."""
        schema_path = Path(__file__).with_name("schema.sql")
        schema_sql = schema_path.read_text(encoding="utf-8")

        with self._conn:
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._conn.executescript(schema_sql)

    def get_connection(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        self._conn.close()
