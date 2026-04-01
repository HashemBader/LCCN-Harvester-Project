-- LCCN Harvester - SQLite Schema
-- Core tables: main (successful results) + attempted (failed / retry tracking)
-- Optional tables included as stretch; app can ignore for now.

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
    date_added      INTEGER NOT NULL, -- yyyymmdd (e.g. 20260317)
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
    last_attempted    INTEGER NOT NULL,  -- yyyymmdd (e.g. 20260317)
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

