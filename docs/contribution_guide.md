# Contribution Guide — LCCN Harvester

Developer guide covering environment setup, repository layout, coding standards, and the branch/commit workflow.

---

## Prerequisites

| Tool | Required |
|------|---------|
| Git | Any recent version |
| Python | 3.10 or later |
| Terminal | macOS Terminal, Linux shell, or Windows PowerShell |

Quick check:

```bash
# macOS / Linux
git --version && python3 --version

# Windows (PowerShell)
git --version && py --version
```

---

## Environment Setup

### Clone and create a virtual environment

```bash
git clone <REPO_URL>
cd LCCN-Harvester-Project

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Verify PyQt6

```bash
python -c "import PyQt6; print('PyQt6 OK')"
```

### Launch the app

```bash
python app_entry.py
```

### Run tests

```bash
pytest               # all tests
pytest -v            # verbose
pytest tests/test_isbn.py   # single file
pytest -k "isbn"     # by name pattern
```

### Clean reset

**macOS / Linux:**
```bash
deactivate 2>/dev/null || true
rm -rf .venv
```

**Windows (PowerShell):**
```powershell
deactivate
Remove-Item -Recurse -Force .venv
```

Then repeat the setup steps above.

---

## Repository Layout

```
LCCN-Harvester-Project/
├── src/
│   ├── gui/            # PyQt6 GUI (tabs, dialogs, styles)
│   ├── harvester/      # Orchestrator, targets, MARC import, export
│   ├── database/       # DatabaseManager, schema.sql
│   ├── config/         # ProfileManager
│   ├── utils/          # ISBN/LCCN/NLMCN validators, MARC parser
│   └── z3950/          # Pure-Python Z39.50 client
├── tests/              # pytest test suite (mirrors src/ structure)
├── docs/               # All project documentation (this folder)
├── data/               # Sample input files, per-profile output data
├── config/             # Profile JSON files, targets.json
├── app_entry.py        # Main entry point (GUI)
├── requirements.txt    # Python dependencies
├── README.md           # Project overview
└── LICENSE             # MIT license
```

**Guidelines:**

- New modules go in the most relevant `src/` subfolder.
- Shared helpers that don't belong to a subsystem go in `src/utils/`.
- Never commit `.db` or `.sqlite3` files — databases are gitignored.
- Never commit generated output files from harvest runs.

---

## Coding Standards

### Core constraints

- **Python only** — Python 3.x exclusively. No C/C++ extensions or compiled binaries.
- **GUI framework** — PyQt6. Do not introduce other GUI toolkits.
- **Z39.50** — Pure-Python implementation only. Do not use compiled YAZ binaries.
- **License** — All code must be MIT-compatible.

### Naming conventions

| Scope | Convention | Example |
|-------|-----------|---------|
| Variables & functions | `snake_case` | `search_isbn`, `parse_response` |
| Classes | `PascalCase` | `DatabaseManager`, `LOCTarget` |
| Constants | `UPPER_CASE` | `DEFAULT_RETRY_DAYS`, `MAX_TIMEOUT` |
| Files & directories | `snake_case` | `db_manager.py`, `src/utils/` |

### Data handling rules

- **ISBNs are always strings.** Never cast to int — leading zeros would be lost.
- **LCCN parsing:** extract first `$a` subfield, replace `$b` with a space, strip trailing periods unless part of the classification.
- **Dates** are stored as `yyyymmdd` integers (e.g., `20260404`). Use `today_yyyymmdd()` and `yyyymmdd_to_iso_date()` from `db_manager.py`.
- **SQLite** is the only database. Use parameterised queries — no ORM.

### Code quality

- All classes and public functions require a docstring (purpose, args, return value).
- Remove all `print()` debug statements before pushing. Use the logging module if output is needed.
- Keep inline comments for non-obvious logic only.

---

## Branch Workflow

| Branch | Purpose |
|--------|---------|
| `main` | Always stable and deployable. Tagged at each sprint close. |
| `develop` | Integration branch. Feature branches merge here. Must always build and pass tests. |
| `feature/*` | One branch per sprint task. Created from `develop`, deleted after merge. |

### Naming

```
feature/<sprint>-<task-id>-short-name

Examples:
  feature/S1-T01-contribution-workflow
  feature/S3-T10-dashboard-kpi-cards
```

### Step-by-step workflow

1. **Sync and branch**

   ```bash
   git checkout develop && git pull
   git checkout -b feature/S3-T10-dashboard-kpi-cards
   ```

2. **Implement** — restrict changes to the task in scope.

3. **Commit** with the sprint-task prefix:

   ```bash
   git add <files>
   git commit -m "S3-T10: add KPI cards to dashboard tab"
   ```

4. **Run tests** before pushing.

5. **Push and open a PR** from your feature branch into `develop`.

6. **PR review** — at least one teammate checks that:
   - Tests pass.
   - Docstrings and comments are present where needed.
   - No debug prints remain.

7. **Merge** into `develop`. Delete the feature branch after merge.

### Sprint close → `main`

At the end of each sprint the Version Manager merges `develop` into `main` and tags it:

```bash
git tag sprint-<N>
git push origin sprint-<N>
```

### Hotfixes

For critical bugs found in `main`:

```bash
git checkout main && git pull
git checkout -b hotfix/short-description
# fix, test, commit
# merge into both main and develop via PRs
```

---

## Commit Message Format

```
<sprint-task-id>: short description of change

Examples:
  S1-T03: add docs/contribution_guide.md
  S5-T07: implement profile CRUD in config_tab_v2
```

Keep messages short and meaningful. The sprint-task ID makes it easy to trace commits back to the sprint log.

---

## See Also

- [technical_manual.md](technical_manual.md) — Architecture, database schema, and maintenance
- [installation_guide.md](installation_guide.md) — Installation and first-run instructions
