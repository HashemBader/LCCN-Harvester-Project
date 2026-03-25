from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
import xml.etree.ElementTree as ET

from src.config.profile_manager import ProfileManager
from src.database.db_manager import DatabaseManager, MainRecord, today_yyyymmdd
from src.utils.marc_parser import (
    extract_call_numbers_from_json,
    extract_call_numbers_from_xml,
    extract_isbns_from_json,
    extract_isbns_from_xml,
)


@dataclass(frozen=True)
class ParsedMarcImportRecord:
    isbns: tuple[str, ...]
    lccn: Optional[str] = None
    nlmcn: Optional[str] = None
    source: Optional[str] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class MarcImportSummary:
    main_rows: int = 0
    attempted_rows: int = 0
    skipped_records: int = 0


class MarcImportService:
    """Persist MARC-derived records into the standard SQLite tables."""

    DEFAULT_ERROR = "MARC import record missing call number"

    def __init__(
        self,
        db_path: Path | str = "data/lccn_harvester.sqlite3",
        *,
        profile_manager: Optional[ProfileManager] = None,
        profile_name: Optional[str] = None,
    ):
        self.db = DatabaseManager(db_path)
        self.profile_manager = profile_manager
        self.profile_name = profile_name

    @staticmethod
    def parse_json_record(record: dict, *, source_name: Optional[str] = None) -> ParsedMarcImportRecord:
        isbns = tuple(dict.fromkeys(extract_isbns_from_json(record)))
        lccn, nlmcn = extract_call_numbers_from_json(record)
        return ParsedMarcImportRecord(isbns=isbns, lccn=lccn, nlmcn=nlmcn, source=source_name)

    @staticmethod
    def parse_xml_record(
        element: ET.Element,
        *,
        source_name: Optional[str] = None,
        namespaces: Optional[dict[str, str]] = None,
    ) -> ParsedMarcImportRecord:
        isbns = tuple(dict.fromkeys(extract_isbns_from_xml(element, namespaces=namespaces)))
        lccn, nlmcn = extract_call_numbers_from_xml(element, namespaces=namespaces)
        return ParsedMarcImportRecord(isbns=isbns, lccn=lccn, nlmcn=nlmcn, source=source_name)

    def import_json_records(
        self,
        records: Iterable[dict],
        *,
        source_name: str,
        import_date: Optional[int] = None,
        save_source_to_active_profile: bool = True,
    ) -> MarcImportSummary:
        parsed_records = [
            self.parse_json_record(record, source_name=source_name)
            for record in records
        ]
        return self.persist_records(
            parsed_records,
            source_name=source_name,
            import_date=import_date,
            save_source_to_active_profile=save_source_to_active_profile,
        )

    def import_xml_records(
        self,
        records: Iterable[ET.Element],
        *,
        source_name: str,
        namespaces: Optional[dict[str, str]] = None,
        import_date: Optional[int] = None,
        save_source_to_active_profile: bool = True,
    ) -> MarcImportSummary:
        parsed_records = [
            self.parse_xml_record(record, source_name=source_name, namespaces=namespaces)
            for record in records
        ]
        return self.persist_records(
            parsed_records,
            source_name=source_name,
            import_date=import_date,
            save_source_to_active_profile=save_source_to_active_profile,
        )

    def persist_records(
        self,
        records: Iterable[ParsedMarcImportRecord],
        *,
        source_name: str,
        import_date: Optional[int] = None,
        save_source_to_active_profile: bool = True,
    ) -> MarcImportSummary:
        self.db.init_db()

        normalized_source = (source_name or "").strip() or "MARC Import"
        if save_source_to_active_profile and self.profile_manager is not None:
            if self.profile_name is None:
                self.profile_name = self.profile_manager.get_active_profile()
            self.profile_manager.set_active_profile_setting("last_marc_import_source", normalized_source)

        date_value = import_date or today_yyyymmdd()
        main_rows = 0
        attempted_rows = 0
        skipped_records = 0

        with self.db.transaction() as conn:
            attempted_batch: list[tuple[str, Optional[str], str, Optional[int], Optional[str]]] = []
            main_batch: list[MainRecord] = []

            for record in records:
                isbns = tuple(dict.fromkeys(str(isbn).strip() for isbn in record.isbns if str(isbn).strip()))
                if not isbns:
                    skipped_records += 1
                    continue

                record_source = (record.source or normalized_source).strip() or "MARC Import"
                lowest_isbn = min(isbns)
                other_isbns = [isbn for isbn in isbns if isbn != lowest_isbn]

                if record.lccn or record.nlmcn:
                    main_batch.append(
                        MainRecord(
                            isbn=lowest_isbn,
                            lccn=record.lccn,
                            lccn_source=record_source if record.lccn else None,
                            nlmcn=record.nlmcn,
                            nlmcn_source=record_source if record.nlmcn else None,
                            source=record_source,
                            date_added=date_value,
                        )
                    )
                    main_rows += 1
                    for other_isbn in other_isbns:
                        self.db._upsert_linked_isbn_conn(conn, lowest_isbn=lowest_isbn, other_isbn=other_isbn)
                else:
                    error_text = (record.error or self.DEFAULT_ERROR).strip() or self.DEFAULT_ERROR
                    for isbn in isbns:
                        attempted_batch.append((isbn, record_source, "both", date_value, error_text))
                        attempted_rows += 1

            if main_batch:
                self.db.upsert_main_many(conn, main_batch, clear_attempted_on_success=True)
            if attempted_batch:
                self.db.upsert_attempted_many(conn, attempted_batch)

        return MarcImportSummary(
            main_rows=main_rows,
            attempted_rows=attempted_rows,
            skipped_records=skipped_records,
        )
