"""
Lightweight TSV export of the ``main`` database table.

This module provides a single public function, ``export_main_to_tsv``, that
reads the ``main`` SQLite table and writes a tab-separated file with one row
per ISBN.  It does NOT depend on ``DatabaseManager`` or ``ExportManager`` and
can therefore be used as a standalone script or imported without the full
application stack.

Output columns (defined by ``EXPORT_HEADER``):
    ISBN, LCCN, NLMCN, Classification, Source, Date Added

The multi-row-per-ISBN storage format (one row per call_number_type/source)
is collapsed into a single row per ISBN via SQL ``MAX()``/``GROUP BY``.
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Union

# Column names written as the first row of every exported TSV file.
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

        # Pivot the multi-row-per-ISBN storage into one row per ISBN.
        # Conditional MAX() selects the LCCN/NLMCN from their respective
        # call_number_type rows while ignoring NULLs from the other type.
        # group_concat(DISTINCT source) merges source labels from all rows.
        cursor.execute(
            """
            SELECT
                isbn,
                MAX(CASE WHEN call_number_type = 'lccn' THEN call_number END) AS lccn,
                MAX(CASE WHEN call_number_type = 'nlmcn' THEN call_number END) AS nlmcn,
                MAX(CASE WHEN call_number_type = 'lccn' THEN classification END) AS classification,
                group_concat(DISTINCT source) AS source,
                MAX(date_added) AS date_added
            FROM main
            GROUP BY isbn
            ORDER BY isbn
            """
        )

        rows = cursor.fetchall()

    def _fmt_date(val) -> str:
        """Normalise any stored date value to ``"YYYY-MM-DD"``.

        Handles both ISO datetime strings (``"YYYY-MM-DD ..."`` or
        ``"YYYY-MM-DD"```) and compact integer-style strings (``"YYYYMMDD"``).
        Unknown formats are returned unchanged.
        """
        s = str(val).strip()
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            return s[:10]  # Trim any time component from "YYYY-MM-DD HH:MM:SS"
        if len(s) == 8 and s.isdigit():
            return f"{s[:4]}-{s[4:6]}-{s[6:]}"  # "YYYYMMDD" → "YYYY-MM-DD"
        return s

    with out_path.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.writer(file_handle, delimiter="\t")
        writer.writerow(EXPORT_HEADER)
        # Replace the raw date_added value (last column) with a formatted date string
        writer.writerows(
            (*row[:-1], _fmt_date(row[-1])) for row in rows
        )

    return out_path
