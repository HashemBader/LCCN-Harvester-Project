-- LCCN Harvester - SQLite Schema
-- Core tables: main (successful results) + attempted (failed / retry tracking)
-- Implemented stretch support: linked_isbns. Untackled stretch tables such as
-- subjects are intentionally not created in this shipped schema.

PRAGMA foreign_keys = ON;

-- =========================
-- Main results table
-- =========================
CREATE TABLE IF NOT EXISTS main (
    isbn            TEXT NOT NULL,
    call_number     TEXT NOT NULL,
    call_number_type TEXT NOT NULL, -- 'lccn' or 'nlmcn'
    classification  TEXT,
    source          TEXT NOT NULL DEFAULT '',
    date_added      INTEGER NOT NULL, -- yyyymmdd integer (e.g. 20260409)
    PRIMARY KEY (isbn, call_number_type, source)
);

CREATE INDEX IF NOT EXISTS idx_main_source ON main(source);
CREATE INDEX IF NOT EXISTS idx_main_date_added ON main(date_added);
CREATE INDEX IF NOT EXISTS idx_main_type ON main(call_number_type);

-- =========================
-- Attempted / failure tracking table
-- =========================
CREATE TABLE IF NOT EXISTS attempted (
    isbn              TEXT NOT NULL,
    last_target       TEXT NOT NULL,
    attempt_type      TEXT NOT NULL DEFAULT 'both',
    last_attempted    INTEGER NOT NULL,  -- yyyymmdd integer (e.g. 20260409)
    fail_count        INTEGER NOT NULL DEFAULT 1,
    last_error        TEXT,
    PRIMARY KEY (isbn, last_target, attempt_type)
);

CREATE INDEX IF NOT EXISTS idx_attempted_last_attempted ON attempted(last_attempted);
CREATE INDEX IF NOT EXISTS idx_attempted_last_target ON attempted(last_target);
CREATE INDEX IF NOT EXISTS idx_attempted_isbn ON attempted(isbn);

-- =========================
-- Stretch: Linked ISBNs
-- =========================
CREATE TABLE IF NOT EXISTS linked_isbns (
    lowest_isbn      TEXT NOT NULL,
    other_isbn       TEXT NOT NULL UNIQUE,
    PRIMARY KEY (lowest_isbn, other_isbn),
    CHECK (lowest_isbn <> other_isbn)
);

CREATE INDEX IF NOT EXISTS idx_linked_lowest ON linked_isbns(lowest_isbn);
CREATE INDEX IF NOT EXISTS idx_linked_other ON linked_isbns(other_isbn);

-- =========================
-- MARC import history
-- =========================
CREATE TABLE IF NOT EXISTS marc_imports (
    source_name     TEXT PRIMARY KEY,
    file_name       TEXT NOT NULL,
    file_hash       TEXT NOT NULL,
    imported_at     INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_marc_imports_file_hash ON marc_imports(file_hash);

