# export_main_tsv.py
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Union

EXPORT_HEADER = ["ISBN", "LCCN", "NLMCN", "Classification", "Source", "Date Added"]


def export_main_to_tsv(db_path: Union[str, Path], out_path: Union[str, Path]) -> Path:
    """
    Purpose:
        Export all rows from the SQLite `main` table to a TSV file.

    Arguments:
        db_path: Path to the SQLite database file.
        out_path: Path to the TSV output file.

    Return Values:
        Path to the written TSV file.

    Raises:
        FileNotFoundError: If db_path does not exist.
        RuntimeError: If `main` table does not exist.
    """
    db_path = Path(db_path)
    out_path = Path(out_path)

    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='main'")
        if cursor.fetchone() is None:
            raise RuntimeError("Table 'main' not found in database.")

        cursor.execute(
            """
            SELECT isbn, lccn, nlmcn, loc_class, source, date_added
            FROM main
            ORDER BY isbn
            """
        )

        rows = cursor.fetchall()

    with out_path.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.writer(file_handle, delimiter="\t")
        writer.writerow(EXPORT_HEADER)
        writer.writerows(rows)

    return out_path