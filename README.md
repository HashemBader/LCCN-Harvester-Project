# LCCN Harvester

LCCN Harvester is a PyQt6 desktop application for looking up Library of Congress and National Library of Medicine call numbers from lists of ISBNs.

It supports API and Z39.50 targets, local caching in SQLite, linked ISBN handling, MARC import, named profiles, and timestamped TSV/CSV exports for each run.

---

## Features

- Desktop GUI with four primary pages: `Dashboard`, `Configure`, `Harvest`, and `Help`
- Built-in API targets for Library of Congress, Harvard LibraryCloud, and OpenLibrary
- Configurable Z39.50 targets stored per profile
- Shared SQLite cache with linked-ISBN support
- Profile-specific settings and output folders
- Harvest modes for `LCCN only`, `NLMCN only`, or `Both`
- Per-run `Database only for this run` option
- MARC import from binary MARC21 (`.mrc`, `.marc`) and MARCXML (`.xml`)
- Timestamped TSV exports plus UTF-8-BOM CSV copies
- Light and dark themes, persisted in `data/gui_settings.json`
- Cross-platform source execution with Python

---

## Quick Start

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app_entry.py
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app_entry.py
```

---

## Documentation

Start with [docs/README.md](docs/README.md) for the documentation landing page.

| Document | Purpose |
|----------|---------|
| [docs/user_guide.md](docs/user_guide.md) | How to use the GUI, profiles, targets, harvest runs, outputs, and MARC import |
| [docs/concepts.md](docs/concepts.md) | Plain-language glossary for ISBNs, call numbers, caching, linked ISBNs, and MARC |
| [docs/installation_guide.md](docs/installation_guide.md) | Installation and source-run guidance |
| [docs/local_app_build_guide.md](docs/local_app_build_guide.md) | Packaging notes and current `main`-branch limitations |
| [docs/cli_reference.md](docs/cli_reference.md) | Command-line utility reference |
| [docs/technical_manual.md](docs/technical_manual.md) | Architecture, storage layout, pipeline, and internal reference |
| [docs/contribution_guide.md](docs/contribution_guide.md) | Developer setup and contribution notes |
| [docs/WCAG_ACCESSIBILITY.md](docs/WCAG_ACCESSIBILITY.md) | Accessibility notes and self-assessment context |

---

## Repository Layout

```text
src/
  api/          HTTP API clients
  config/       Path helpers, profile manager, help-link config
  database/     SQLite schema and database access layer
  gui/          Main window, tabs, dialogs, styles, notifications
  harvester/    Orchestrator, targets, MARC import, run pipeline
  utils/        Validators, parsers, target persistence helpers
  z3950/        Z39.50 compatibility and client code
docs/           Project documentation
config/         Active-profile file, default profile, saved profile folders
data/           GUI settings, runtime database, profile output folders
```

---

## License

MIT. See [LICENSE](LICENSE).

## Contributors:

- Ahmed Abdelmagid: ahmedmkabdelmagid@gmail.com - www.linkedin.com/in/ahmed-abdelmagid-84007236a
- Abdel Rahman Alashal: abd.alashel@gmail.com - https://www.linkedin.com/in/abdel-rahman-alashel-883a30271/
- Eyad Mansour - Eyad-mansour@hotmail.com - https://www.linkedin.com/in/eyadmansour1
- Hashem Bader - https://www.linkedin.com/in/hashem-bader-7b25092b7/
- Karim Khalil: karimelsadek@live.com - https://www.linkedin.com/in/karim-khalil-404074242?
