# Technical Manual

This document is the developer-facing reference for the current LCCN Harvester codebase.

## Table Of Contents

- [Architecture Overview](#architecture-overview)
- [Entry Points](#entry-points)
- [Runtime Paths](#runtime-paths)
- [GUI Layer](#gui-layer)
  - [Pages](#pages)
  - [Notable GUI behavior](#notable-gui-behavior)
- [Profiles And Targets](#profiles-and-targets)
- [Input Parsing](#input-parsing)
- [Harvest Pipeline](#harvest-pipeline)
- [MARC Import](#marc-import)
- [Output Files](#output-files)
- [Database Schema](#database-schema)
  - [`main`](#main)
  - [`attempted`](#attempted)
  - [`linked_isbns`](#linked_isbns)
  - [`marc_imports`](#marc_imports)
- [Database Browser](#database-browser)
- [Notifications And Accessibility](#notifications-and-accessibility)
- [Build And Packaging](#build-and-packaging)
- [See Also](#see-also)

---

## Architecture Overview

LCCN Harvester is a layered Python application built around a PyQt6 GUI and a shared SQLite database.

```text
GUI (src/gui/)
  ModernMainWindow
  Dashboard / Configure / Harvest / Help

Harvest Runtime (src/harvester/)
  run_harvest.py
  orchestrator.py
  targets.py
  marc_import.py

Storage (src/database/)
  db_manager.py
  schema.sql

Configuration (src/config/)
  profile_manager.py
  app_paths.py

Utilities (src/utils/, src/z3950/, src/api/)
  validators, parsers, target persistence, API clients, Z39.50 support
```

---

## Entry Points

| File | Purpose |
|------|---------|
| `app_entry.py` | Primary GUI entry point for source and frozen runs |
| `src/gui_launcher.py` | Alternate development launcher |
| `src/harvester_cli.py` | Command-line harvest utility |
| `src/main.py` | `python -m src` shim for the CLI |

---

## Runtime Paths

In development, runtime files live beside the repository. In frozen builds, `src/config/app_paths.py` redirects writable data to the platform-specific user-data directory unless the app is being run from a local build inside the workspace.

Current layout:

```text
config/
  active_profile.txt
  default_profile.json
  profiles/
    <slug>/
      <slug>.json
      <slug>_targets.tsv

data/
  gui_settings.json
  targets.tsv
  lccn_harvester.sqlite3
  <slug>/
    <profile>-success-<timestamp>.tsv / .csv
    <profile>-failed-<timestamp>.tsv / .csv
    <profile>-invalid-<timestamp>.tsv / .csv
    <profile>-problems-<timestamp>.tsv / .csv
    <profile>-linked-isbns-<timestamp>.tsv / .csv
    <profile>-marc-import-<timestamp>.tsv / .csv
```

Key points:

- The database is shared across profiles.
- Profiles separate settings, targets, and output folders.
- `gui_settings.json` stores theme and related GUI preferences.
- Output files are timestamped, so runs do not overwrite one another.

---

## GUI Layer

`src/gui/modern_window.py` builds the main window and wires together the four primary pages.

### Pages

| Module | Primary responsibility |
|--------|------------------------|
| `dashboard.py` | Run status, KPI cards, recent results, result-file access, linked-ISBN tools |
| `targets_config_tab.py` | Combined `Configure` page container |
| `targets_tab.py` | Target list editing and connectivity checks |
| `config_tab.py` | Profile selection and harvest settings |
| `harvest_tab.py` | Input preview, harvest controls, MARC import |
| `help_tab.py` | Help links, shortcuts, and accessibility links |

### Notable GUI behavior

- The app opens on the `Configure` page.
- Theme selection is loaded from `ThemeManager`.
- The system tray menu exposes `Show Window`, `Enable Notifications`, and `Quit`.
- The dashboard database browser is read-only and supports search, source filtering, and pagination.

---

## Profiles And Targets

`ProfileManager` stores:

- The active profile name in `config/active_profile.txt`
- Profile settings in `config/profiles/<slug>/<slug>.json`
- The built-in default targets in `data/targets.tsv`
- User-profile targets in `config/profiles/<slug>/<slug>_targets.tsv`

`TargetsManager` persists the target list as TSV and ensures the built-in API targets are present.

The GUI target editor is the main source of truth for target configuration. Built-in API targets and user-added Z39.50 targets are shown together in the same table.

---

## Input Parsing

`src/harvester/run_harvest.py` provides `parse_isbn_file()`.

Supported formats:

- `.tsv`
- `.txt`
- `.csv`
- `.xlsx`
- `.xls`

Parsing rules:

- Column 0 is the primary ISBN.
- Columns 1+ are linked ISBN variants.
- Blank rows are skipped.
- Rows beginning with `#` are skipped.
- The first row is treated as a header when the first cell matches known ISBN labels.
- Excel numeric ISBNs ending in `.0` are normalized before validation.

The parser returns:

- Deduplicated valid ISBNs
- Invalid ISBNs
- Duplicate counts
- Linked-ISBN mappings

---

## Harvest Pipeline

`run_harvest()` coordinates input parsing, database initialization, target creation, and orchestration.

`HarvestOrchestrator` performs the per-ISBN runtime flow:

1. Resolve the canonical ISBN if the input is already linked.
2. Check the shared SQLite cache.
3. In `db_only` mode, stop here if no cached result is available.
4. Walk enabled targets in rank order.
5. Apply call-number mode and stop-rule logic.
6. Record successes in `main` and failed attempts in `attempted`.
7. Record linked-ISBN relationships in `linked_isbns`.

Progress events include:

- `isbn_start`
- `cached`
- `linked_cached`
- `target_start`
- `success`
- `linked_success`
- `failed`
- `skip_retry`
- `attempt_failed`
- `not_in_local_catalog`
- `stats`
- `db_flush`

---

## MARC Import

`src/harvester/marc_import.py` persists MARC-derived records directly into the same database used by normal harvest runs.

Current GUI-supported import formats:

- Binary MARC21: `.mrc`, `.marc`
- MARCXML: `.xml`

Import behavior:

- The GUI asks for a source name.
- The active call-number mode determines which fields are kept.
- Records with call numbers are written to `main`.
- Records with ISBNs but no call numbers are written to `attempted`.
- Records with no usable ISBN are skipped.
- Linked ISBNs discovered during import are merged into the canonical ISBN structure.

---

## Output Files

Normal harvests write live TSV files during execution and generate CSV copies at the end.

Output groups:

- success
- failed
- invalid
- problems
- linked-isbns

Successful output columns vary by mode:

| Mode | Columns |
|------|---------|
| `lccn` | `ISBN`, `LCCN`, `LCCN Source`, `Classification`, `Date` |
| `nlmcn` | `ISBN`, `NLM`, `NLM Source`, `Date` |
| `both` | `ISBN`, `LCCN`, `LCCN Source`, `Classification`, `NLM`, `NLM Source`, `Date` |

The MARC import path writes a separate timestamped export file in the active profile folder.

---

## Database Schema

`src/database/schema.sql` currently defines four tables:

| Table | Purpose |
|-------|---------|
| `main` | Successful call-number rows |
| `attempted` | Failed lookups, retry tracking, invalid ISBN tracking |
| `linked_isbns` | Canonical ISBN mapping |
| `marc_imports` | MARC import file metadata |

### `main`

Physical storage is one row per `(isbn, call_number_type, source)` combination.

Key columns:

- `isbn`
- `call_number`
- `call_number_type`
- `classification`
- `source`
- `date_added`

### `attempted`

Tracks retry state and failures by:

- `isbn`
- `last_target`
- `attempt_type`
- `last_attempted`
- `fail_count`
- `last_error`

### `linked_isbns`

Maps non-canonical ISBNs to a canonical lowest ISBN.

### `marc_imports`

Tracks import-source metadata such as source name, file name, file hash, and import date.

---

## Database Browser

`src/gui/database_browser_dialog.py` exposes a read-only browser for:

- `main`
- `attempted`
- `linked_isbns`

It loads tables lazily and supports:

- Search
- Source filtering where applicable
- Pagination
- Refresh

It does not execute arbitrary SQL.

---

## Notifications And Accessibility

`NotificationManager` supports tray or native notifications depending on platform availability.

Accessibility-related notes live in:

- `docs/WCAG_ACCESSIBILITY.md`

---

## Build And Packaging

For the `main` branch baseline, the reliable documented execution path is running from source.

Packaging instructions should only claim script-based build support when the branch actually contains the corresponding packaging assets.

---

## See Also

- [user_guide.md](user_guide.md)
- [cli_reference.md](cli_reference.md)
- [contribution_guide.md](contribution_guide.md)
