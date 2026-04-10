"""
MARC record import service for the LCCN Harvester.

Allows bibliographic records obtained from external catalogue exports (in JSON
or XML/MARC-XML format) to be imported directly into the local SQLite database
without going through the live harvest pipeline.  This is useful for bulk
seeding from institution-supplied data dumps.

Workflow:
  1. Caller obtains a collection of MARC records (JSON dicts or XML elements).
  2. ``MarcImportService.import_json_records`` or ``import_xml_records``
     parses each record into a ``ParsedMarcImportRecord`` (ISBNs + call numbers).
  3. ``persist_records`` batches the parsed records into the ``main`` table
     (success) or the ``attempted`` table (no call number found) inside a
     single transaction.

Linked-ISBN handling:
  When a record contains multiple ISBNs (e.g. ISBN-10 and ISBN-13), the
  numerically lowest one is stored as the canonical key and any non-canonical
  variants are rewritten via ``_rewrite_to_lowest_isbn_conn`` so all existing
  rows migrate to the canonical key.

Classes:
    ParsedMarcImportRecord -- Intermediate DTO produced by the record parsers.
    MarcImportSummary      -- Outcome counts returned by ``persist_records``.
    MarcImportService      -- Orchestrates parsing and persistence.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
import xml.etree.ElementTree as ET

from src.config.profile_manager import ProfileManager
from src.database.db_manager import DatabaseManager, MainRecord, now_datetime_str, normalize_to_yyyymmdd_int
from src.utils.isbn_validator import pick_lowest_isbn
from src.utils.marc_parser import (
    extract_call_numbers_from_json,
    extract_call_numbers_from_xml,
    extract_isbns_from_json,
    extract_isbns_from_xml,
)


@dataclass(frozen=True)
class ParsedMarcImportRecord:
    """Intermediate result of parsing a single MARC record.

    Attributes:
        isbns:  All ISBNs found in the record (may be empty).
        lccn:   LC call number from MARC field 050 (or ``None``).
        nlmcn:  NLM call number from MARC field 060 (or ``None``).
        source: Name of the institution / catalogue that supplied the record.
        error:  Non-fatal parse error message (informational only).
    """
    isbns: tuple[str, ...]
    lccn: Optional[str] = None
    nlmcn: Optional[str] = None
    source: Optional[str] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class MarcImportSummary:
    """Outcome statistics from a single ``persist_records`` call.

    Attributes:
        main_rows:       Records written to the ``main`` table (had call numbers).
        attempted_rows:  Records written to ``attempted`` (no call numbers found).
        skipped_records: Records skipped entirely because they had no ISBNs.
    """
    main_rows: int = 0
    attempted_rows: int = 0
    skipped_records: int = 0


class MarcImportService:
    """Persist MARC-derived records into the standard SQLite tables.

    Supports two record formats:
      - JSON dicts as returned by ``src.api`` clients (e.g. Harvard LibraryCloud).
      - XML ``Element`` objects in MARC-XML / OAI-DC form.

    Both paths ultimately call ``persist_records`` which writes results inside a
    single atomic transaction.
    """

    # Fallback error message stored in ``attempted`` when a record has no call number
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
        """Parse a single JSON MARC record dict into a ``ParsedMarcImportRecord``.

        Args:
            record:      A MARC record represented as a Python dict (e.g. from the LoC or
                         Harvard API response).
            source_name: Optional catalogue name to attach to the result.
        """
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
        """Parse a single MARC-XML ``Element`` into a ``ParsedMarcImportRecord``.

        Args:
            element:    An ``xml.etree.ElementTree.Element`` representing one MARC record.
            source_name: Optional catalogue name to attach to the result.
            namespaces:  XML namespace map passed to ``ElementTree.find``/``findall``.
        """
        isbns = tuple(dict.fromkeys(extract_isbns_from_xml(element, namespaces=namespaces)))
        lccn, nlmcn = extract_call_numbers_from_xml(element, namespaces=namespaces)
        return ParsedMarcImportRecord(isbns=isbns, lccn=lccn, nlmcn=nlmcn, source=source_name)

    def import_json_records(
        self,
        records: Iterable[dict],
        *,
        source_name: str,
        import_date: Optional[str] = None,
        save_source_to_active_profile: bool = True,
    ) -> MarcImportSummary:
        """Parse and persist an iterable of JSON MARC records.

        Convenience wrapper that calls ``parse_json_record`` on each item and
        then delegates to ``persist_records``.

        Args:
            records:                       Iterable of raw MARC JSON dicts.
            source_name:                   Catalogue / institution name stored with each result.
            import_date:                   Override the harvest timestamp (ISO string or ``None``
                                           to use the current time).
            save_source_to_active_profile: When ``True``, persist *source_name* into the
                                           active profile settings for display in the UI.
        """
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
        import_date: Optional[str] = None,
        save_source_to_active_profile: bool = True,
    ) -> MarcImportSummary:
        """Parse and persist an iterable of MARC-XML elements.

        Convenience wrapper that calls ``parse_xml_record`` on each element and
        then delegates to ``persist_records``.

        Args:
            records:                       Iterable of ``ET.Element`` MARC records.
            source_name:                   Catalogue / institution name stored with each result.
            namespaces:                    XML namespace map for element lookups.
            import_date:                   Override the harvest timestamp.
            save_source_to_active_profile: When ``True``, persist *source_name* into the
                                           active profile settings.
        """
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
        import_date: Optional[str] = None,
        save_source_to_active_profile: bool = True,
        source_file_name: Optional[str] = None,
        source_file_hash: Optional[str] = None,
        replace_existing_source: bool = False,
    ) -> MarcImportSummary:
        """Write parsed MARC records to the database in a single transaction.

        For each record:
          - If it has at least one call number (LCCN or NLMCN): added to the
            ``main`` table under the lowest/canonical ISBN.  Any other ISBNs in
            the record are rewritten to the canonical key.
          - If it has no call numbers: added to ``attempted`` so the normal
            harvest pipeline can retry it later.
          - If it has no ISBNs at all: silently skipped.

        Args:
            records:                       Parsed records to persist.
            source_name:                   Display name stored in ``source`` columns.
            import_date:                   Override harvest timestamp (ISO or ``None`` for now).
            save_source_to_active_profile: Persist *source_name* to the active profile settings.

        Returns:
            A ``MarcImportSummary`` with counts for each outcome category.
        """
        self.db.init_db()

        normalized_source = (source_name or "").strip() or "MARC Import"
        if save_source_to_active_profile and self.profile_manager is not None:
            if self.profile_name is None:
                self.profile_name = self.profile_manager.get_active_profile()
            self.profile_manager.set_active_profile_setting("last_marc_import_source", normalized_source)

        date_value = import_date or now_datetime_str()
        main_rows = 0
        attempted_rows = 0
        skipped_records = 0

        with self.db.transaction() as conn:
            if replace_existing_source:
                conn.execute("DELETE FROM main WHERE source = ?", (normalized_source,))
                conn.execute("DELETE FROM attempted WHERE last_target = ?", (normalized_source,))
            attempted_batch: list[tuple[str, Optional[str], str, Optional[str], Optional[str]]] = []
            main_batch: list[MainRecord] = []

            for record in records:
                # Deduplicate and strip whitespace from ISBNs within this record
                isbns = tuple(dict.fromkeys(str(isbn).strip() for isbn in record.isbns if str(isbn).strip()))
                if not isbns:
                    # Records with no usable ISBNs cannot be stored; skip entirely
                    skipped_records += 1
                    continue

                record_source = (record.source or normalized_source).strip() or "MARC Import"
                # Choose the numerically lowest ISBN as the canonical key so
                # different editions of the same title converge to one row.
                lowest_isbn = pick_lowest_isbn(isbns)
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
                        # Rewrite (not just upsert) so any rows already stored
                        # under other_isbn are migrated to lowest_isbn in the same
                        # transaction, preventing orphaned non-canonical rows.
                        self.db._rewrite_to_lowest_isbn_conn(conn, lowest_isbn=lowest_isbn, other_isbn=other_isbn)
                else:
                    error_text = (record.error or self.DEFAULT_ERROR).strip() or self.DEFAULT_ERROR
                    for isbn in isbns:
                        attempted_batch.append((isbn, record_source, "both", date_value, error_text))
                        attempted_rows += 1

            if main_batch:
                self.db.upsert_main_many(conn, main_batch, clear_attempted_on_success=True)
            if attempted_batch:
                self.db.upsert_attempted_many(conn, attempted_batch)
            if source_file_name and source_file_hash:
                conn.execute(
                    """
                    INSERT INTO marc_imports (source_name, file_name, file_hash, imported_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(source_name) DO UPDATE SET
                        file_name = excluded.file_name,
                        file_hash = excluded.file_hash,
                        imported_at = excluded.imported_at
                    """,
                    (
                        normalized_source,
                        source_file_name,
                        source_file_hash,
                        normalize_to_yyyymmdd_int(date_value),
                    ),
                )

        return MarcImportSummary(
            main_rows=main_rows,
            attempted_rows=attempted_rows,
            skipped_records=skipped_records,
        )
