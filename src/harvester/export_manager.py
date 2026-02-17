"""
Module: export_manager.py
Handles data export in TSV/CSV/JSON formats.
"""
import csv
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.database.db_manager import DatabaseManager, MainRecord, AttemptedRecord


class ExportManager:
    """Manages the export of harvested data."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db = DatabaseManager(db_path)
        else:
            self.db = DatabaseManager() # Use default

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
        """Export a single source to a file."""
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
        """
        Fetch data from database and filter columns.
        Returns (data_rows, headers).
        """
        # Define field mappings (Display Name -> DB Field / Object Attr)
        main_field_map = {
            "ISBN": "isbn",
            "LCCN": "lccn",
            "NLMCN": "nlmcn",
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
                # For Main, respect selected_columns
                # If no columns selected, default to all available in map
                if not selected_columns:
                    headers = list(main_field_map.keys())
                else:
                    headers = [col for col in selected_columns if col in main_field_map]
                
                # If somehow headers is still empty (e.g. invalid columns passed), fallback to all
                if not headers:
                    headers = list(main_field_map.keys())

                fields = [main_field_map[h] for h in headers]
                query = f"SELECT {', '.join(fields)} FROM main ORDER BY isbn"
                cursor = conn.execute(query)
                rows = cursor.fetchall()
                
                data = [list(row) for row in rows]
                return data, headers

            elif source == "attempted":
                # For Attempted, use fixed columns as UI doesn't allow selecting them yet
                # Or we could map 'ISBN' from selected_columns, but other columns don't match.
                # Let's use all attempted fields.
                headers = list(attempted_field_map.keys())
                fields = [attempted_field_map[h] for h in headers]
                
                query = f"SELECT {', '.join(fields)} FROM attempted ORDER BY isbn"
                cursor = conn.execute(query)
                rows = cursor.fetchall()
                
                data = [list(row) for row in rows]
                return data, headers
            
            else:
                raise ValueError(f"Unknown source: {source}")

    def _export_tsv(self, data: List[List[Any]], headers: List[str], path: Path, include_header: bool):
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter="\t")
            if include_header:
                writer.writerow(headers)
            writer.writerows(data)

    def _export_csv(self, data: List[List[Any]], headers: List[str], path: Path, include_header: bool):
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if include_header:
                writer.writerow(headers)
            writer.writerows(data)

    def _export_json(self, data: List[List[Any]], headers: List[str], path: Path):
        objects: List[Dict[str, Any]] = []
        for row in data:
            obj = {headers[i]: row[i] if i < len(row) else None for i in range(len(headers))}
            objects.append(obj)

        with path.open("w", encoding="utf-8") as f:
            json.dump(objects, f, ensure_ascii=False, indent=2)
