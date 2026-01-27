# Database Schema & Planned Pipeline (Architecture)

This project uses a small SQLite database (DB) as the “source of truth” for what we’ve already harvested successfully, what has failed (so we can retry later without wasting calls), and a couple of stretch features (edition linking + subjects).

This section documents the schema **and** the planned flow that writes to it. It also ties the docs to the actual initialization code so future changes stay consistent.

---

## The docs ↔ code link

- **Schema file:** `schema.sql`
- **Init code:** `db_manager.py` → `DatabaseManager.init_db()`
- **Default DB path:** `./data/lccn_harvester.db`

`DatabaseManager.init_db()` reads `schema.sql` and runs it via SQLite so the database can always be created the same way on any machine.

Note: SQLite foreign keys are enabled per-connection. This means the app ensures `PRAGMA foreign_keys = ON` is set when initializing the DB connection.

---

## Schema status

This document describes the **intended** schema and DB usage.

- `schema.sql` is owned/maintained by the DB implementation task owner.
- If `schema.sql` differs from this document, treat `schema.sql` as the executable source of truth and update this document accordingly.

---

## Tables

### 1) `main` — successful results (export-ready)
**Purpose:** One row per ISBN that we successfully classify. This table is shaped to match the planned export columns.

**Primary key:** `isbn`

**Columns**
- `isbn` *(TEXT, PK)* — normalized ISBN-10/13 (no hyphens/spaces)
- `lccn` *(TEXT)* — Library of Congress call number from MARC **050**
- `nlmcn` *(TEXT)* — National Library of Medicine call number from MARC **060** (optional)
- `loc_class` *(TEXT)* — LoC class prefix (1–3 letters, e.g., `HF`) derived from `lccn`
- `source` *(TEXT)* — where the record came from (API / Z39.50 target name)
- `date_added` *(INTEGER)* — stored as `yyyymmdd`

**Behavior**
- If an ISBN is in `main`, we treat it as “done” (unless a future “force refresh” feature is added).

---

### 2) `attempted` — failed attempts (retry support)
**Purpose:** Track that an ISBN was tried on a target and did not succeed, so we can skip wasting calls until a retry window passes.

**Primary key:** `(isbn, target_attempted)`

**Columns**
- `isbn` *(TEXT, NOT NULL)* — the ISBN that failed (may not exist in `main`)
- `target_attempted` *(TEXT, NOT NULL)* — the target/source we tried
- `date_attempted` *(INTEGER, NOT NULL)* — stored as `yyyymmdd`

**Index**
- `idx_attempted_isbn` on `(isbn)` for fast lookup

**Note on retries**
- With the current primary key, this table stores the **latest attempt per (isbn, target)**.
- If we later want full attempt history, we can expand the primary key to include `date_attempted`.

---

### 3) `linked_isbns` — stretch: edition linking
**Purpose:** Link “other ISBNs” (other editions) to a canonical ISBN (`lowest_isbn`) to reduce duplication.

**Primary key:** `(lowest_isbn, other_isbn)`

**Rules**
- `lowest_isbn` and `other_isbn` must be different (`CHECK (lowest_isbn <> other_isbn)`)

---

### 4) `subjects` — stretch: subject phrases
**Purpose:** Store subject phrases tied to a canonical ISBN.

**Primary key:** `(lowest_isbn, subject_phrase, source)`

**Columns**
- `lowest_isbn` *(TEXT, NOT NULL)*
- `subject_phrase` *(TEXT, NOT NULL)*
- `source` *(TEXT)* — optional; where we got the subject from

**Index**
- `idx_subjects_lowest_isbn` on `(lowest_isbn)` for fast lookup

---

## Planned pipeline (how data flows into the DB)

### Inputs
- A list of raw ISBNs (from file/UI)
- A configured list of targets (API and/or Z39.50 systems)

### Output
- Rows in `main` that are ready to export:
  - `isbn, lccn, nlmcn, loc_class, source, date_added`

### Steps

1) **Normalize the ISBN**
- Remove hyphens/spaces
- Validate 10/13 length where possible
- Use the normalized value everywhere (DB key + lookups)

2) **Skip ISBNs we already solved**
- If ISBN exists in `main`, skip (already harvested)

3) **Retry gate (avoid repeated failures)**
- Before querying a target, check `attempted`
- If `(isbn, target)` was attempted recently (within retry-days), skip that target

4) **Query targets in order**
For each target:
- Attempt lookup by ISBN
- If not found / error:
  - write/update `attempted` with today’s `date_attempted`
  - continue to next target
- If found:
  - parse classification data and proceed to success write

5) **Parse classification**
- Extract MARC fields:
  - `050` → `lccn`
  - `060` → `nlmcn` (optional)
- Derive `loc_class` from the alphabetic prefix of `lccn` (e.g., `HF`)

6) **Write success**
- Insert into `main`:
  - `isbn, lccn, nlmcn, loc_class, source, date_added=today`
- Stop trying other targets for that ISBN once successful

7) **Export**
- Export reads from `main` and writes columns in the planned order

---

## Stretch hooks (future)
- **Edition linking:** populate `linked_isbns` when we detect related ISBNs
- **Subjects:** populate `subjects` when subject phrases are available

---

## Implementation reference
- The schema is defined in `schema.sql`.
- The database is created/opened and initialized by `db_manager.py` (`DatabaseManager.init_db()`), which executes the schema script and ensures the DB file exists within the data folder.

---

## Verification checklist (for maintainers)
- [ ] `db_manager.py` enables `PRAGMA foreign_keys = ON` for each connection
- [ ] `schema.sql` creates tables: `main`, `attempted`, `linked_isbns`, `subjects`
- [ ] Primary keys match: `main(isbn)`, `attempted(isbn,target_attempted)`, etc.
- [ ] Indexes exist: `idx_attempted_isbn`, `idx_subjects_lowest_isbn`
- [ ] Export reads exactly: `isbn,lccn,nlmcn,loc_class,source,date_added`
