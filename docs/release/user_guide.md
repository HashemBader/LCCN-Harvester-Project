# User Guide — LCCN Harvester

This guide explains how to use the LCCN Harvester to look up Library of Congress call numbers (LCCNs) and National Library of Medicine call numbers (NLMCNs) for a list of ISBNs.

---

## Overview

The LCCN Harvester takes a TSV file of ISBNs, queries multiple library sources (APIs and Z39.50 servers), and produces a results file with call numbers for cataloging purposes.

**Current status:** CLI-only. See [cli_user_guide.md](cli_user_guide.md) for detailed CLI usage.

---

## Preparing Input

### Input file format
- File type: `.tsv` (tab-separated values)
- One ISBN per line (first column)
- ISBNs may include hyphens or spaces (they will be normalized)

Example `input.tsv`:
```
978-0-13-110362-7
0131103628
9780306406157
```

### ISBN formats supported
- ISBN-10 (10 digits, may end in X)
- ISBN-13 (13 digits, starts with 978 or 979)

---

## Running a Harvest

### CLI (current)
```bash
python src/harvester_cli.py --input path/to/input.tsv
```

See [cli_user_guide.md](cli_user_guide.md) for full CLI documentation.

### GUI (planned)
A graphical interface will be added in future sprints with:
- File selection dialog
- Target configuration panel
- Progress display
- Export options

---

## Configuring Targets

Targets are the library sources the harvester queries for call numbers.

### Target types
- **API targets:** Library of Congress, Harvard LibraryCloud, OpenLibrary
- **Z39.50 targets:** Library catalog servers using the Z39.50 protocol

### Target priority
Targets are queried in rank order. The harvester stops at the first successful match ("stop on find").

### Configuration file (planned)
Target settings will be stored in `config/targets.tsv`.

---

## Understanding Outputs

### Results TSV
Export columns:
1. ISBN — normalized ISBN
2. LCCN — Library of Congress call number (MARC 050)
3. NLMCN — National Library of Medicine call number (MARC 060)
4. Classification — LoC class prefix (e.g., HF, QA)
5. Source — which target provided the result
6. Date Added — when the record was harvested

### Local database
Results are cached in a local SQLite database (`data/lccn_harvester.db`) to avoid re-querying ISBNs that have already been resolved.

### Invalid ISBNs
ISBNs that fail validation are logged to `invalid_isbns.txt`.

---

## Troubleshooting

### Input file not found
```
ERROR: Input file does not exist: /path/to/file.tsv
```
Check that the file path is correct and the file exists.

### Input path is a directory
```
ERROR: Input path is not a file: /path/to/folder
```
Provide a path to a `.tsv` file, not a folder.

### No results for an ISBN
Possible causes:
- ISBN is invalid or has a typo
- No library source has a record for this ISBN
- All targets timed out (check network connection)

### Module not found errors
Ensure your virtual environment is activated and dependencies are installed:
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Run harvest | `python src/harvester_cli.py -i input.tsv` |
| Dry run | `python src/harvester_cli.py -i input.tsv --dry-run` |
| Run tests | `pytest` |

---

## See Also

- [cli_user_guide.md](cli_user_guide.md) — Detailed CLI documentation
- [installation_guide.md](installation_guide.md) — Installation instructions
- [../environment_setup.md](../environment_setup.md) — Developer environment setup
