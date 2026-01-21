PRAGMA foreign_keys = ON;

-- ==========================================================
-- MAIN: Successful results (matches planned export columns)
-- Columns: isbn (PK), lccn, nlmcn, loc_class, source, date_added
-- ==========================================================
CREATE TABLE IF NOT EXISTS main (
    isbn        TEXT PRIMARY KEY,      -- normalized ISBN-10/13 (no hyphens)
    lccn        TEXT,                  -- call number from MARC 050
    nlmcn       TEXT,                  -- call number from MARC 060 (optional)
    loc_class   TEXT,                  -- 1-3 letter class prefix (e.g., "HF")
    source      TEXT,                  -- API/Z39.50 target name
    date_added  INTEGER                -- yyyymmdd
);

-- ==========================================================
-- ATTEMPTED: Failed attempts (supports retry-days)
-- Columns: isbn, target_attempted, date_attempted
-- NOTE: no FK to main (an ISBN can fail before ever being found)
-- ==========================================================
CREATE TABLE IF NOT EXISTS attempted (
    isbn             TEXT NOT NULL,
    target_attempted TEXT NOT NULL,
    date_attempted   INTEGER NOT NULL,  -- yyyymmdd
    PRIMARY KEY (isbn, target_attempted)
);

-- Helpful index for retry checks
CREATE INDEX IF NOT EXISTS idx_attempted_isbn
ON attempted(isbn);

-- ==========================================================
-- STRETCH: Linked ISBNs (edition linking)
-- Columns: lowest_isbn, other_isbn
-- ==========================================================
CREATE TABLE IF NOT EXISTS linked_isbns (
    lowest_isbn TEXT NOT NULL,
    other_isbn  TEXT NOT NULL,
    PRIMARY KEY (lowest_isbn, other_isbn),
    CHECK (lowest_isbn <> other_isbn)
);

-- ==========================================================
-- STRETCH: Subjects
-- Columns: lowest_isbn, subject_phrase, source
-- ==========================================================
CREATE TABLE IF NOT EXISTS subjects (
    lowest_isbn    TEXT NOT NULL,
    subject_phrase TEXT NOT NULL,
    source         TEXT,
    PRIMARY KEY (lowest_isbn, subject_phrase, source)
);

CREATE INDEX IF NOT EXISTS idx_subjects_lowest_isbn
ON subjects(lowest_isbn);
