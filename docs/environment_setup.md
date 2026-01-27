<!--
Developer Environment Setup (LCCN Harvester)
Keep this file up to date as the repo evolves (Python version, run command, dependency file, packaging, tests).
-->

# Developer Environment Setup

This guide shows how to set up the project from scratch on macOS / Windows / Linux. It’s meant to be the one place a developer can follow to get running quickly, and it will be updated as the codebase grows.

What you need

Required
Git
Python 3.x (team version)
A terminal (and optionally VS Code)

Recommended
VS Code + Python extension
A GUI diff tool (optional)

Quick checks

macOS / Linux
```bash
git --version
python3 --version
```

Windows (PowerShell)
```powershell
git --version
py --version
```

1) Get the code
```bash
git clone <REPO_URL>
cd <REPO_FOLDER>
```

Replace <REPO_URL> with the repo clone URL and <REPO_FOLDER> with the folder created by Git.

2) Create + activate a virtual environment

macOS / Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
python --version
```

Windows (PowerShell)
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
```

Windows (CMD)
```bat
py -m venv .venv
.\.venv\Scripts\activate.bat
python --version
```

If PowerShell blocks activation, run:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

3) Upgrade pip
```bash
python -m pip install --upgrade pip
```

4) Install dependencies

One of these will be used (keep the one that matches the repo).

Option A — requirements.txt (common early stage)
```bash
pip install -r requirements.txt
```

Option B — pyproject.toml (packaged project)
```bash
pip install -e .
```

Option C — requirements-dev.txt (if used)
```bash
pip install -r requirements-dev.txt
```

5) Confirm PyQt6 works

Run this quick import test:
```bash
python -c "import PyQt6; print('PyQt6 OK')"
```

6) Run the CLI

The harvester provides a command-line interface for processing ISBN files.

Basic usage:
```bash
python src/harvester_cli.py --input path/to/input.tsv
```

Short flag:
```bash
python src/harvester_cli.py -i path/to/input.tsv
```

Dry-run mode (reserved for future use):
```bash
python src/harvester_cli.py -i path/to/input.tsv --dry-run
```

Example with sample data:
```bash
python src/harvester_cli.py -i data/sample/sample_isbns.tsv
```

The CLI currently validates the input file and prints a summary. Full harvesting will be added in later sprints.

7) Configuration & local files

Where settings live
Local dev settings should live in a non-committed location where possible (or in a config file that’s gitignored).
If the repo uses a config folder, it should be documented here.

Targets file (if present)
If the system uses targets.tsv, keep a dev copy locally and ensure it’s gitignored if it contains private hosts.

Example:
```text
config/targets.tsv
```

8) Run tests

The project uses pytest for testing.

Run all tests:
```bash
pytest
```

Run tests with verbose output:
```bash
pytest -v
```

Run a specific test file:
```bash
pytest tests/test_isbn.py
```

Run tests matching a pattern:
```bash
pytest -k "isbn"
```

Test files are located in `tests/` and mirror the `src/` structure:
- `tests/test_db.py` — Database tests
- `tests/test_isbn.py` — ISBN validation tests

9) Common problems & fixes

python / pip not found
macOS/Linux: use python3 / pip3
Windows: use py launcher

Permission denied activating venv (Windows)
PowerShell:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

ModuleNotFoundError: PyQt6
Make sure:
1. the venv is activated
2. you installed dependencies inside the venv
3. pip list shows PyQt6

10) Updating this guide over time

As the codebase grows, update:
Python version requirement (pin exact version if needed)
Dependency install method (requirements vs pyproject)
Run command (entrypoint)
Config locations
Testing commands
Packaging / release instructions (move to release docs later)

Appendix: Clean reset

If you want to rebuild your environment from scratch:
```bash
deactivate 2>/dev/null || true
rm -rf .venv
```

Then repeat steps 2 → 6.
