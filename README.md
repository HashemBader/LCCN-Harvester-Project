# LCCN Harvester

A desktop application for UPEI Library that automatically retrieves Library of Congress Call Numbers (LCCNs) and National Library of Medicine Call Numbers (NLMCNs) for large lists of ISBNs.

Instead of searching multiple library catalogues manually, cataloguers upload a single TSV file. The application queries multiple sources in priority order, caches results locally, and produces structured output files ready for import into the library management system.

---

## Features

- **Multi-source querying** — Library of Congress, Harvard LibraryCloud, OpenLibrary (REST APIs), and configurable Z39.50 catalog servers
- **Smart caching** — successful results are stored in a per-profile SQLite database; cached ISBNs are never re-queried
- **Edition linking** — sibling ISBNs of a cached edition are resolved locally without external queries
- **MARC import** — import call numbers directly from MARC files, bypassing API lookups
- **Named profiles** — separate source priorities, retry windows, and call number modes per cataloguing workflow
- **Dual call number modes** — harvest LCCN only, NLMCN only, or both in a single run
- **Structured output** — TSV and CSV output files (successful, failed, invalid, problems) after every run
- **Light and dark theme** — Catppuccin-inspired palette, persisted across sessions
- **Cross-platform** — macOS, Windows, Linux; distributable as a standalone executable via PyInstaller

---

## Quick Start

**macOS / Linux:**
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app_entry.py
```

**Windows (PowerShell):**
```powershell
py -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app_entry.py
```

See [docs/installation_guide.md](docs/installation_guide.md) for packaged executable installation and platform-specific notes.

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/user_guide.md](docs/user_guide.md) | Full user guide |
| [docs/installation_guide.md](docs/installation_guide.md) | Installation instructions |
| [docs/cli_reference.md](docs/cli_reference.md) | Command-line interface reference |
| [docs/technical_manual.md](docs/technical_manual.md) | Architecture and developer reference |
| [docs/contribution_guide.md](docs/contribution_guide.md) | Developer setup and contribution workflow |

---

## Repository Layout

```
src/
  gui/          PyQt6 interface (tabs, dialogs, theming)
  harvester/    Orchestrator, API/Z39.50 targets, MARC import, export
  database/     DatabaseManager, schema
  config/       ProfileManager
  utils/        ISBN/LCCN/NLMCN validators, MARC parser
  z3950/        Pure-Python Z39.50 client
tests/          pytest test suite
docs/           All project documentation
data/           Sample input files and per-profile output data
config/         Profile JSON files, targets configuration
```

---

## License

MIT — see [LICENSE](LICENSE).

UPEI Library · CS4820 / CS4810 Software Engineering Project
