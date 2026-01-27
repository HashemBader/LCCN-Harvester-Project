-- LCCN Harvester - SQLite Schema (requirements-aligned)
-- Core tables: main (successful results) + attempted (failed / retry tracking)
-- Optional tables included as stretch; app can ignore for now.

PRAGMA foreign_keys = ON;

-- =========================
-- Main results table
-- =========================
CREATE TABLE IF NOT EXISTS main (
    isbn            TEXT PRIMARY KEY,
    lccn            TEXT,
    nlmcn           TEXT,
    classification  TEXT,
    source          TEXT,
    -- requirement: yyyymmdd as integer
    date_added      INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_main_source ON main(source);
CREATE INDEX IF NOT EXISTS idx_main_date_added ON main(date_added);

-- =========================
-- Attempted / failure tracking table (per ISBN + per target)
-- =========================
CREATE TABLE IF NOT EXISTS attempted (
    isbn            TEXT NOT NULL,
    target          TEXT NOT NULL,
    -- requirement: date attempted (store as yyyymmdd integer)
    last_attempted  INTEGER NOT NULL,
    fail_count      INTEGER NOT NULL DEFAULT 1,
    last_error      TEXT,
    PRIMARY KEY (isbn, target)
);

CREATE INDEX IF NOT EXISTS idx_attempted_last_attempted ON attempted(last_attempted);
CREATE INDEX IF NOT EXISTS idx_attempted_target ON attempted(target);
CREATE INDEX IF NOT EXISTS idx_attempted_isbn ON attempted(isbn);

-- =========================
-- Stretch: Linked ISBNs
-- =========================
CREATE TABLE IF NOT EXISTS linked_isbns (
    isbn             TEXT PRIMARY KEY,
    canonical_isbn   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_linked_canonical ON linked_isbns(canonical_isbn);

-- =========================
-- Stretch: Subjects harvested from MARC 6XX fields
-- =========================
CREATE TABLE IF NOT EXISTS subjects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    isbn        TEXT NOT NULL,
    field       TEXT,         -- e.g., 650
    indicator2  TEXT,         -- thesaurus indicator (2nd indicator)
    subject     TEXT NOT NULL,
    source      TEXT,
    -- keep consistent with main: yyyymmdd int
    date_added  INTEGER NOT NULL,
    FOREIGN KEY (isbn) REFERENCES main(isbn) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_subjects_isbn ON subjects(isbn);
CREATE INDEX IF NOT EXISTS idx_subjects_field ON subjects(field);
