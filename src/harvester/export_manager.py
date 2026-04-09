"""
Data export service for the LCCN Harvester.

Reads records from the local SQLite database and writes them to disk in
TSV, CSV, or JSON format.  The caller passes a configuration dict that
controls which table (``main`` or ``attempted``), which columns, and which
output format to use.

Usage example::

    mgr = ExportManager("data/lccn_harvester.sqlite3")
    result = mgr.export({
        "source": "main",
        "format": "tsv",
        "columns": ["ISBN", "LCCN", "Source"],
        "output_path": "exports/results.tsv",
        "include_header": True,
    })
    if result["success"]:
        print("Exported to", result["files"])

When ``source="both"``, two files are written: one with ``_success`` appended
to the stem (for the ``main`` table) and one with ``_failed`` (for the
``attempted`` table).
"""
import csv
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.database.db_manager import DatabaseManager, MainRecord, AttemptedRecord, yyyymmdd_to_iso_date


class ExportManager:
    """Serialise harvested data from SQLite to TSV, CSV, or JSON files.

    All export operations are driven by a single configuration dict passed to
    ``export()``.  The class handles file creation, column selection, and
    optional header rows.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db = DatabaseManager(db_path)
        else:
            self.db = DatabaseManager()  # Use default path

    def export(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute export based on configuration.
        
        Args:
            config: Dictionary containing export configuration:
                - source: "main", "attempted", or "both"
                - format: "tsv", "csv", or "json"
                - columns: List of column names to include (for main)
                - output_path: str, destination path
                - include_header: bool
        
        Returns:
            Dict with 'success' (bool) and 'message' (str) or 'files' (list of paths).
        """
        source = config.get("source", "main")
        format_type = str(config.get("format", "tsv")).strip().lower()
        output_path = Path(config["output_path"])

        if format_type not in {"tsv", "csv", "json"}:
            raise ValueError(f"Unsupported export format: {format_type}")
        
        exported_files = []
        
        try:
            if source == "both":
                # Handle Main
                main_path = self._get_modified_path(output_path, "_success")
                self._export_source("main", config, main_path)
                exported_files.append(str(main_path))
                
                # Handle Attempted
                attempted_path = self._get_modified_path(output_path, "_failed")
                self._export_source("attempted", config, attempted_path)
                exported_files.append(str(attempted_path))
            else:
                self._export_source(source, config, output_path)
                exported_files.append(str(output_path))
                
            return {
                "success": True, 
                "message": f"Successfully exported to {', '.join(exported_files)}",
                "files": exported_files
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Export failed: {str(e)}"
            }

    def _get_modified_path(self, original_path: Path, suffix: str) -> Path:
        """Insert a suffix before the file extension."""
        return original_path.with_name(f"{original_path.stem}{suffix}{original_path.suffix}")

    def _export_source(self, source: str, config: Dict[str, Any], path: Path):
        """Fetch data for *source* and write it to *path* in the configured format."""
        data, headers = self._fetch_data(source, config.get("columns", []))
        
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        format_type = str(config.get("format", "tsv")).strip().lower()
        include_header = config.get("include_header", True)

        if format_type == "tsv":
            self._export_tsv(data, headers, path, include_header=include_header)
        elif format_type == "csv":
            self._export_csv(data, headers, path, include_header=include_header)
        elif format_type == "json":
            self._export_json(data, headers, path)
        else:
            raise ValueError(f"Unsupported export format: {format_type}")

    def _fetch_data(self, source: str, selected_columns: List[str]) -> tuple[List[List[Any]], List[str]]:
        """Fetch rows from *source* and apply column selection.

        Args:
            source:           ``"main"`` or ``"attempted"``.
            selected_columns: Display names of columns to include.  Falls back
                              to all available columns when empty or invalid.

        Returns:
            A ``(data_rows, headers)`` tuple where each row in ``data_rows``
            is a list of formatted cell values aligned to *headers*.

        Raises:
            ValueError: If *source* is not ``"main"`` or ``"attempted"``.
        """
        # Mapping from user-visible column names to DB attribute names
        main_field_map = {
            "ISBN": "isbn",
            "LCCN": "lccn",
            "LCCN Source": "lccn_source",
            "NLMCN": "nlmcn",
            "NLM": "nlmcn",
            "NLM Source": "nlmcn_source",
            "Classification": "classification",
            "Source": "source",
            "Date Added": "date_added"
        }
        
        attempted_field_map = {
            "ISBN": "isbn",
            "Last Target": "last_target", 
            "Last Attempted": "last_attempted",
            "Fail Count": "fail_count", 
            "Last Error": "last_error"
        }

        with self.db.connect() as conn:
            if source == "main":
                # Apply the caller's column selection; fall back to all columns if none given
                # or if all supplied names are invalid (not in the field map).
                if not selected_columns:
                    headers = list(main_field_map.keys())
                else:
                    headers = [col for col in selected_columns if col in main_field_map]

                # Guard: if every supplied column was unknown, export all columns
                if not headers:
                    headers = list(main_field_map.keys())

                # Fetch all successful results and sort alphabetically by ISBN
                rows = self.db.get_all_results(limit=100000)
                rows = sorted(rows, key=lambda row: str(row["isbn"]))
                data = [
                    [
                        self._format_export_value(
                            main_field_map[h],
                            row[main_field_map[h]] if main_field_map[h] in row.keys() else None
                        )
                        for h in headers
                    ]
                    for row in rows
                ]
                return data, headers

            elif source == "attempted":
                # ``attempted`` always exports all columns; the UI does not yet
                # expose per-column selection for this table.
                headers = list(attempted_field_map.keys())
                fields = [attempted_field_map[h] for h in headers]

                # Build the SELECT dynamically from the whitelisted field map to
                # avoid SQL injection from user-supplied column names.
                query = f"SELECT {', '.join(fields)} FROM attempted ORDER BY isbn"
                cursor = conn.execute(query)
                rows = cursor.fetchall()
                
                data = [
                    [self._format_export_value(field, value) for field, value in zip(fields, row)]
                    for row in rows
                ]
                return data, headers
            
            else:
                raise ValueError(f"Unknown source: {source}")

    def _export_tsv(self, data: List[List[Any]], headers: List[str], path: Path, include_header: bool):
        """Write *data* to *path* as a UTF-8 tab-separated file."""
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter="\t")
            if include_header:
                writer.writerow(headers)
            writer.writerows(data)

    def _export_csv(self, data: List[List[Any]], headers: List[str], path: Path, include_header: bool):
        """Write *data* to *path* as a UTF-8 comma-separated file."""
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if include_header:
                writer.writerow(headers)
            writer.writerows(data)

    def _export_json(self, data: List[List[Any]], headers: List[str], path: Path):
        """Write *data* to *path* as a pretty-printed JSON array of objects."""
        objects: List[Dict[str, Any]] = []
        for row in data:
            obj = {headers[i]: row[i] if i < len(row) else None for i in range(len(headers))}
            objects.append(obj)

        with path.open("w", encoding="utf-8") as f:
            json.dump(objects, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _format_export_value(field_name: str, value: Any) -> Any:
        """Coerce *value* to a human-friendly representation for export.

        Date fields stored as ``YYYYMMDD`` integers are converted to
        ``"YYYY-MM-DD"`` strings; all other values are returned as-is.
        """
        if field_name in {"date_added", "last_attempted"}:
            return yyyymmdd_to_iso_date(value)
        return value
