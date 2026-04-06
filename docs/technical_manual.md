# Technical Manual — LCCN Harvester

Developer-facing reference covering architecture, source groups, pipeline flow, database schema, configuration, utilities, and maintenance.

---

## Architecture Overview

LCCN Harvester is a Python desktop application built with **PyQt6**. It follows a layered architecture:

```
┌─────────────────────────────────────────────┐
│                 GUI Layer                   │
│  ModernMainWindow → Dashboard / Configure / │
│  Harvest / Help  (src/gui/)                 │
├─────────────────────────────────────────────┤
│             Harvester Layer                 │
│  HarvestOrchestrator → Targets → APIs/Z39.50│
│  (src/harvester/)                           │
├─────────────────────────────────────────────┤
│             Database Layer                  │
│  DatabaseManager → SQLite per profile       │
│  (src/database/)                            │
├─────────────────────────────────────────────┤
│             Utilities                       │
│  ISBN / LCCN / NLMCN validators, MARC parser│
│  (src/utils/)                               │
└─────────────────────────────────────────────┘
```

### Entry Points

| File | Purpose |
|------|---------|
| `app_entry.py` | Main entry point — handles PyInstaller frozen builds and development mode |
| `src/gui_launcher.py` | Alternative IDE launch entry |
| `src/harvester_cli.py` | Command-line interface (scripting / headless use) |

---

## GUI Layer (`src/gui/`)

The GUI is built with PyQt6. The main window class is `ModernMainWindow` in `modern_window.py`.

### Main Window (`modern_window.py`)

- Renders a collapsible left sidebar (240 px expanded, 72 px collapsed) with animated transition.
- Hosts a `QStackedWidget` with four pages: Dashboard, Configure, Harvest, Help.
- Manages cross-tab signal wiring (harvest events → dashboard updates).
- Handles keyboard shortcuts, theme switching, system-tray notifications, and profile management.
- Minimum window size: 900 × 660 px.

### Tab Modules

| File | Class | Responsibility |
|------|-------|---------------|
| `dashboard_v2.py` | `DashboardTabV2` | KPI cards, live activity monitor, recent results table, profile selector |
| `targets_config_tab.py` | `TargetsConfigTab` | Container for Targets and Settings sub-tabs; profile change signals |
| `targets_tab_v2.py` | `TargetsTab` | Editable target list with enable/disable and priority reordering |
| `config_tab_v2.py` | `ConfigTabV2` | Profile CRUD, retry interval spinbox, call number mode selector |
| `harvest_tab_v2.py` | `HarvestTabV2` | File input drop zone, harvest controls, MARC import, output file links |
| `help_tab.py` | `HelpTab` | Keyboard shortcut reference, accessibility info, about section |

### Theming

- Two palettes: `CATPPUCCIN_DARK` and `CATPPUCCIN_LIGHT` (defined in `styles_v2.py`).
- `ThemeManager` (`theme_manager.py`) persists the selected theme across sessions.
- `generate_stylesheet(colors)` produces a full Qt stylesheet from a palette dict.
- All tabs that use inline styles implement `refresh_theme(colors)` for live switching.

### Icons

`icons.py` provides all SVG icons as string constants and caches rendered `QIcon` / `QPixmap` objects by `(svg, color, size)`.

---

## Harvester Layer (`src/harvester/`)

### Orchestrator (`orchestrator.py`)

`HarvestOrchestrator` manages the per-ISBN harvest pipeline:

1. **Cache check** — if the ISBN is already in `main`, emit `cached` and skip.
2. **Linked ISBN check** — if a sibling ISBN is in `main`, reuse its result (`linked_cached`).
3. **Retry gate** — for each target, skip if `(isbn, target)` was attempted within the retry window.
4. **Target loop** — query each enabled target in rank order; stop on first success.
5. **Success write** — insert into `main`; emit `success`.
6. **Failure write** — all targets failed; insert into `attempted`; emit `failed`.

Supports parallel ISBN processing via `ThreadPoolExecutor`. Raises `HarvestCancelled` when the caller's cancel check returns `True`.

### Run Harvest (`run_harvest.py`)

`run_harvest()` is the top-level function called by `HarvestWorkerV2`. It:

- Reads and validates ISBNs from the input file via `parse_isbn_file()`.
- Creates a `DatabaseManager` for the active profile.
- Instantiates enabled targets from configuration.
- Delegates per-ISBN work to `HarvestOrchestrator`.
- Returns a `HarvestSummary` with aggregate counts.

### Targets (`targets.py`, `api_targets.py`, `z3950_targets.py`)

Each target implements the `HarvestTarget` protocol:

```python
class HarvestTarget(Protocol):
    name: str
    def lookup(self, isbn: str) -> TargetResult: ...
```

`TargetResult` carries: `success`, `lccn`, `nlmcn`, `source`, `isbns`, `error`.

**API Targets** (`api_targets.py`):
- `LOCTarget` — queries `https://www.loc.gov/search/?q=<isbn>&fo=json`
- `HarvardTarget` — queries `https://api.lib.harvard.edu/`
- `OpenLibraryTarget` — queries `https://openlibrary.org/`

**Z39.50 Targets** (`z3950_targets.py`): connect to library catalog servers using the Z39.50 protocol via a pure-Python client (`src/z3950/`).

`create_target_from_config(config_dict)` in `targets.py` instantiates the correct target class from a configuration dictionary.

### MARC Import (`marc_import.py`)

`MarcImportService` parses MARC records from files and returns `ParsedMarcImportRecord` objects. These are persisted to the database and written to the output TSV files, bypassing external target lookups.

---

## Database Layer (`src/database/`)

SQLite — one database file per profile:

```
data/<profile_name>/lccn_harvester.sqlite3
```

### DatabaseManager Key Methods (`db_manager.py`)

| Method | Purpose |
|--------|---------|
| `init_db()` | Creates tables from `schema.sql`; enables `PRAGMA foreign_keys = ON` |
| `get_main_record(isbn)` | Look up a successfully harvested ISBN |
| `insert_main(record)` | Write a successful result |
| `get_attempted(isbn, target)` | Retry gate read |
| `insert_attempted(...)` | Retry gate write |
| `get_linked_isbn(isbn)` | Linked ISBN lookup for edition deduplication |
| `query_stats()` | Aggregate counts for Dashboard KPI cards |

### Schema

#### `main` — successful results

| Column | Type | Notes |
|--------|------|-------|
| `isbn` | TEXT (PK) | Normalized, no hyphens |
| `lccn` | TEXT | MARC 050 |
| `lccn_source` | TEXT | Target that provided LCCN |
| `nlmcn` | TEXT | MARC 060 (optional) |
| `nlmcn_source` | TEXT | Target that provided NLMCN |
| `loc_class` | TEXT | LoC class prefix, e.g. `QA` |
| `source` | TEXT | Winning target name |
| `date_added` | INTEGER | `yyyymmdd` integer |

#### `attempted` — failed attempts (retry support)

| Column | Type | Notes |
|--------|------|-------|
| `isbn` | TEXT | |
| `target_attempted` | TEXT | |
| `date_attempted` | INTEGER | `yyyymmdd` |

Primary key: `(isbn, target_attempted)` — stores the latest attempt per pair.

#### `linked_isbns` — edition linking

| Column | Type | Notes |
|--------|------|-------|
| `lowest_isbn` | TEXT | Canonical ISBN |
| `other_isbn` | TEXT | Sibling edition ISBN |

Primary key: `(lowest_isbn, other_isbn)`.

#### `subjects` — subject phrases (schema-ready; not populated by pipeline)

| Column | Type |
|--------|------|
| `lowest_isbn` | TEXT |
| `subject_phrase` | TEXT |
| `source` | TEXT |

### Date Storage

All dates are stored as `yyyymmdd` integers (e.g., `20260404`). Helpers in `db_manager.py`:

- `today_yyyymmdd()` — returns today as int.
- `yyyymmdd_to_iso_date(value)` — converts to `YYYY-MM-DD` string for display.

---

## Configuration System (`src/config/`)

### ProfileManager (`profile_manager.py`)

Manages named profiles stored as JSON files under `data/profiles/`. Each profile file:

```json
{
  "retry_days": 7,
  "call_number_mode": "lccn",
  "stop_rule": "stop_either",
  "both_stop_policy": "both",
  "db_only": false
}
```

Key methods: `get_active_profile()`, `set_active_profile(name)`, `get_db_path(profile)`, `list_profiles()`, `save_profile(name, settings)`, `load_profile(name)`.

### Profile Settings Reference

| Key | Type | Values | Default |
|-----|------|--------|---------|
| `retry_days` | int | 0–365 | 7 |
| `call_number_mode` | str | `lccn` / `nlmcn` / `both` | `lccn` |
| `stop_rule` | str | `stop_either` / `stop_lccn` / `stop_nlmcn` | `stop_either` |
| `both_stop_policy` | str | `both` / `either` | `both` |
| `db_only` | bool | `true` / `false` | `false` |

---

## Utilities (`src/utils/`)

| File | Responsibility |
|------|---------------|
| `isbn_validator.py` | `normalize_isbn()`, `validate_isbn()`, `pick_lowest_isbn()` |
| `lccn_validator.py` | Validates call numbers against MARC 050 formatting |
| `nlmcn_validator.py` | Validates call numbers against MARC 060 formatting |
| `call_number_normalizer.py` | Strips non-standard characters from API-returned call numbers |
| `marc_parser.py` | Reads XML/JSON responses; extracts MARC fields 050 and 060 |
| `messages.py` | Centralises all user-facing status and error strings |

---

## Source Groups (SG1 – SG5)

The harvester assigns every target to a source group. The group is recorded in result metadata and used to route `db_only` mode.

| Group | Protocol | Status | Targets |
|-------|----------|--------|---------|
| **SG1** | REST APIs | Implemented | LOC, Harvard LibraryCloud, OpenLibrary |
| **SG2** | Z39.50 | Implemented | Any configured Z39.50 catalog server |
| **SG3** | SRU | Not implemented | — |
| **SG4** | Other protocols | Not implemented | — |
| **SG5** | Local DB (db_only) | Implemented | Shared SQLite database |

### Why SG3 and SG4 Were Not Implemented

SG3 (Search/Retrieve via URL — SRU) and SG4 (future protocols such as OAI-PMH or GraphQL) were reserved in the design but not built within the project scope. The architecture supports adding them without changes to the orchestrator or database layers.

### Implementing SG3 — SRU Protocol

SRU is a REST-based search protocol that returns MARCXML. Adding it follows the same pattern as SG1 API targets:

1. Create a new class in `src/harvester/api_targets.py` (or a new `sru_targets.py`):

   ```python
   class SRUTarget:
       name: str
       source_group = "SG3"

       def __init__(self, name: str, base_url: str):
           self.name = name
           self._base_url = base_url

       def lookup(self, isbn: str) -> TargetResult:
           url = f"{self._base_url}?operation=searchRetrieve&query=isbn={isbn}&recordSchema=marcxml"
           # fetch URL, parse MARCXML using marc_parser.parse_marcxml_response()
           # return TargetResult(success=..., lccn=..., nlmcn=..., source=self.name)
   ```

2. Register the new type in `create_target_from_config()` in `src/harvester/targets.py`:

   ```python
   if config["type"] == "sru":
       return SRUTarget(name=config["name"], base_url=config["base_url"])
   ```

3. Add SRU entries to `data/targets.json` with `"type": "sru"`.

4. `marc_parser.parse_marcxml_response()` already handles MARCXML — no parser changes are needed.

### Implementing SG4 — Additional Protocols

SG4 follows the same extension pattern. For any new protocol:

1. Implement the `HarvestTarget` protocol in a new file under `src/harvester/`.
2. Register it in `create_target_from_config()`.
3. Assign `source_group = "SG4"` on the class.
4. Add target entries to `data/targets.json`.

No changes to `HarvestOrchestrator`, `DatabaseManager`, or the export layer are required.

---

## Harvest Pipeline — Full Flow

```
Input TSV
    │
    ▼
parse_isbn_file()
    ├─ normalize ISBNs
    ├─ deduplicate
    └─ flag invalid → invalid output file
    │
    ▼
For each unique valid ISBN:
    │
    ├─[cached?]──────────────────────────────► emit "cached"; write success row
    │
    ├─[linked_isbn cached?]──────────────────► emit "linked_cached"; write success row
    │
    └─[new / retry eligible]
         │
         For each target (in rank order):
         │
         ├─[retry gate: attempted within window?]─► skip this target → try next
         │
         ├─ target.lookup(isbn)
         │      ├─[success]──────────────────────► parse MARC fields
         │      │                                   insert main
         │      │                                   emit "success"
         │      │                                   stop target loop
         │      └─[failure]──────────────────────► insert/update attempted
         │                                          emit "attempt_failed"
         │                                          continue to next target
         │
         └─[all targets failed]────────────────► emit "failed"
    │
    ▼
HarvestSummary returned
    │
    ▼
Write output files:
    ├─ *_successful.tsv / .csv
    ├─ *_failed.tsv / .csv
    ├─ *_invalid.tsv / .csv
    └─ *_problems.tsv / .csv
```

---

## Output Files

Each run overwrites the previous run's files. A `.csv` copy (UTF-8 with BOM, for Excel compatibility) is generated alongside each `.tsv`.

| Mode | Successful TSV Columns |
|------|----------------------|
| LCCN only | ISBN · LCCN · LCCN Source · Classification · Date |
| NLMCN only | ISBN · NLM · NLM Source · Date |
| Both | ISBN · LCCN · LCCN Source · Classification · NLM · NLM Source · Date |

Failed: `Call Number Type · ISBN · Target · Date Attempted · Reason`

Invalid: `ISBN`

Problems: `Target · Problem`

---

## Build and Run

### Development Setup

```bash
python3 -m venv .venv
source .venv/bin/activate    # macOS/Linux
pip install -r requirements.txt
python app_entry.py
```

### Running Tests

```bash
pytest          # all tests
pytest -v       # verbose output
pytest -k "db"  # run tests matching a pattern
```

### Packaging (PyInstaller)

The build spec is in `.pyinstaller/`. To build on macOS:

```bash
bash build_mac.sh
```

To build on Windows:

```bat
build_windows.bat
```

---

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `PyQt6` | Desktop GUI framework |
| `requests` | HTTP client for SG1 API targets |
| `pymarc` | MARC record parsing |
| `pytest` | Test runner |

---

## Extending the System

### Adding a New API or Protocol Target

1. Create a class implementing the `HarvestTarget` protocol in `src/harvester/`.
2. Register it in `create_target_from_config()` in `targets.py`.
3. Add entries to `data/targets.json`.

### Extending the Database Schema

1. Edit `src/database/schema.sql`.
2. Add migration logic to `init_db()` in `db_manager.py` (use `ALTER TABLE` or recreate the table as needed).
3. Update `DatabaseManager` methods to read/write the new columns.
4. Add corresponding tests in `tests/test_db.py`.

---

## Maintenance Guide

### Routine Dependency Updates

```bash
pip list --outdated
pip install --upgrade <package>
pytest   # verify nothing broke
```

Pin versions in `requirements.txt` after confirming tests pass.

### Running the Test Suite

```bash
pytest -v
```

Key test files:

| File | Covers |
|------|--------|
| `tests/test_isbn.py` | ISBN normalization and validation |
| `tests/test_db.py` | Database operations |
| `tests/test_orchestrator.py` | Harvest pipeline logic |
| `tests/test_marc_import.py` | MARC import |
| `tests/test_run_harvest_smoke.py` | End-to-end harvest smoke test |
| `tests/test_profile_manager.py` | Profile CRUD |

### Debugging API Target Issues

1. Enable logging in `src/harvester/api_targets.py` to print raw responses.
2. Test the endpoint URL directly in a browser or with `curl`.
3. Check for `403 Forbidden` — usually a network/IP policy issue, not a bug.
4. If a target consistently fails, disable it in **Configure → Targets** and investigate separately.

### Debugging Z39.50 Connectivity

1. Confirm the server hostname and port in `data/targets.json`.
2. Test TCP connectivity: `nc -zv <host> <port>` (macOS/Linux).
3. Check `src/z3950/client.py` logs for the raw APDU exchange.
4. Increase the timeout value in the target configuration if the server is slow to respond.

### Database Maintenance

```bash
# Open the database in the SQLite CLI
sqlite3 data/<profile_name>/lccn_harvester.sqlite3

# Reclaim space after large deletes
VACUUM;

# Check row counts
SELECT COUNT(*) FROM main;
SELECT COUNT(*) FROM attempted;

# Backup
cp data/<profile>/lccn_harvester.sqlite3 backup_$(date +%Y%m%d).sqlite3
```

Never commit `.sqlite3` files to the repository.

### Adding or Updating a Z39.50 Target

Edit `data/targets.json`. Each Z39.50 entry requires:

```json
{
  "name": "My Library Z39.50",
  "type": "z3950",
  "host": "z3950.example.org",
  "port": 210,
  "db": "VOYAGER",
  "enabled": true,
  "rank": 10
}
```

Restart the application for changes to take effect.

### Packaging a New Release

1. Run the full test suite: `pytest -v`
2. Update the version string in `app_entry.py` and `docs/user_guide.md`.
3. Build executables: `bash build_mac.sh` / `build_windows.bat`
4. Smoke-test the built executable on a clean machine.
5. Tag the release: `git tag v<version> && git push origin v<version>`

### Common Issues and Resolutions

| Issue | Likely Cause | Resolution |
|-------|-------------|------------|
| No results for any ISBN | All targets disabled or unreachable | Check **Configure → Targets**; verify network |
| `CERTIFICATE_VERIFY_FAILED` | Outdated certifi | `pip install --upgrade certifi` |
| Harvest stops at 0 ISBNs | Input file not TSV or ISBNs not in column 1 | Check file format |
| Z39.50 target times out | Server slow or unreachable | Increase timeout; check host/port |
| Database locked error | Another process has the DB open | Close other instances of the app |

---

## Known Limitations

- Subject phrases (`subjects` table) — schema exists but the pipeline does not populate it.
- Internationalization (French UI) — not implemented; UI strings are English-only.
- SG3 (SRU) and SG4 (additional protocols) — reserved but not built; see the Source Groups section above for implementation guidance.

---

## See Also

- [user_guide.md](user_guide.md) — How to use the application
- [installation_guide.md](installation_guide.md) — Installation instructions
- [contribution_guide.md](contribution_guide.md) — Developer setup and workflow
