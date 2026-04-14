# Contribution Guide

This guide covers the practical developer workflow for working on the current repository.

---

## Development Setup

Clone the repository and create a virtual environment.

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Launch the GUI:

```bash
python app_entry.py
```

Run the CLI:

```bash
python src/harvester_cli.py -i path/to/input.tsv
```

---

## Repository Layout

```text
src/
  api/          HTTP API clients
  config/       Profile and path management
  database/     SQLite schema and access layer
  gui/          Main window, tabs, dialogs, styles
  harvester/    Runtime pipeline, targets, MARC import
  utils/        Validators, parsers, target persistence helpers
  z3950/        Z39.50 support
docs/           Maintained project documentation
config/         Runtime profile configuration
data/           Runtime database, GUI settings, profile output folders
```

---

## Contribution Notes

- Keep generated files out of commits where possible.
- Do not commit runtime SQLite databases or harvest output files.
- Update documentation when user-facing behavior changes.
- If you change storage or schema behavior, update both `schema.sql` and the relevant migration logic in `db_manager.py`.

---

## Style Expectations

- Python is the primary implementation language.
- The GUI is built with PyQt6.
- SQLite is the storage layer.
- Z39.50 support is implemented in Python within this repository.

Try to keep new code aligned with the surrounding module style rather than introducing a second style within the same area.

---

## Recommended Git Workflow

The application itself does not enforce a branching model. Use the workflow your team prefers, but keep these basics in place:

1. Create a branch for your work.
2. Update docs when behavior changes.
3. Keep commits focused and reviewable.

---

## Packaging

Do not assume packaging assets exist on every branch.

For the `main` branch baseline used in this documentation pass, the reliable documented execution path is running from source.

---

## See Also

- [technical_manual.md](technical_manual.md)
- [installation_guide.md](installation_guide.md)
