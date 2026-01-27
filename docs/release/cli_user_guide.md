# User Guide — LCCN Harvester

This guide explains how to use **LCCN Harvester** from the command line with an input TSV of ISBNs, what outputs to expect, and how the system is intended to behave as features are completed.

---

## Quick Start (CLI)

### 1) Prepare an input TSV
- File type: `.tsv`
- Recommended: **one ISBN per line** (first column)
- ISBNs may contain hyphens/spaces (normalization/validation will be added in later sprints)

Example `input.tsv`:
```text
978-0-13-110362-7
0131103628
9780306406157
```

### 2) Run the CLI
The CLI accepts a required input path and an optional dry-run flag.

Basic run:
```bash
python src/harvester_cli.py --input path/to/input.tsv
```

Short flag:
```bash
python src/harvester_cli.py -i path/to/input.tsv
```

Dry-run flag (reserved; currently no behavior change):
```bash
python src/harvester_cli.py -i path/to/input.tsv --dry-run
```

---

## What the CLI does (current)

Given an input TSV path, the CLI:
- checks that the input path exists
- checks that the input path is a regular file (not a folder)
- prints a summary of the selected options (`--input`, `--dry-run`)

### Output (current)
On success, the CLI prints a short summary including:
- the resolved input file path
- whether dry-run was set

Example:
```text
LCCN Harvester (CLI skeleton)
- Input TSV: /full/path/to/input.tsv
- Dry run:   False

No harvesting is performed yet. This CLI only validates the file path and confirms the options.
```

### Exit codes
- `0` = success
- `1` = input file error (missing file, or path is not a file)

---

## Arguments

### `--input` / `-i` (required)
Path to the TSV file containing ISBNs.

If the file does not exist, the CLI exits with an error.

### `--dry-run` (optional)
Boolean flag reserved for later use.
- Default: `False`
- Current behavior: no functional change (still only validates and prints summary)

---

## Outputs (planned)

As harvesting features are implemented, the system will produce:

### 1) SQLite database (local)
- Default path (planned): `./data/lccn_harvester.db`
- Tables (planned):
  - `main` — successful results (export-ready)
  - `attempted` — failed attempts (retry support)
  - `linked_isbns` — (stretch) edition linking
  - `subjects` — (stretch) subject phrases

### 2) Results TSV export (from `main`)
Export column order:
1. ISBN
2. LCCN
3. NLMCN
4. Classification (loc_class)
5. Source
6. Date Added

Overwrite behavior (planned): if a file with the same name already exists, the exporter should create a unique name (example: timestamp suffix) rather than overwrite.

### 3) Invalid ISBN log (optional)
If invalid ISBNs are found:
- they are written to `invalid_isbns.txt` (or similar)
- logged immediately when detected

---

## Planned harvesting behavior (pipeline integration)

Future sprints will extend the CLI to:

1) **Normalize the ISBN**
- remove hyphens/spaces
- validate 10/13 length and check digit where possible
- use the normalized value everywhere (DB key + lookups)

2) **Skip ISBNs already solved**
- if ISBN exists in `main`, skip (already harvested)

3) **Retry gate**
- before querying a target, check `attempted`
- if `(isbn, target)` was attempted recently (within retry-days), skip that target

4) **Query targets in order**
For each target:
- attempt lookup by ISBN
- if not found / error:
  - write/update `attempted` with today’s `date_attempted`
  - continue to next target
- if found:
  - parse classification data and proceed to success write

5) **Parse classification**
- extract MARC fields:
  - `050` → LCCN
  - `060` → NLMCN (optional)
- derive `loc_class` from the alphabetic prefix of `lccn` (1–3 letters, e.g., `HF`)

6) **Write success**
- insert into `main`:
  - `isbn, lccn, nlmcn, loc_class, source, date_added=today`
- stop trying other targets for that ISBN once successful

7) **Export**
- export reads from `main` and writes columns in the planned order

---

## Troubleshooting

### “Input file does not exist”
Check your path and ensure the file exists:
```text
ERROR: Input file does not exist: /path/to/file.tsv
```

### “Input path is not a file”
You likely passed a folder instead of a `.tsv` file:
```text
ERROR: Input path is not a file: /path/to/folder
```

### “Module not found” / import errors
- Ensure your virtual environment is activated
- Ensure dependencies are installed
- Ensure you’re running from the project root (so `src/` paths resolve)

---

## Notes for maintainers (doc → code alignment)
- This guide reflects the current CLI interface in `src/harvester_cli.py`.
- As the pipeline is implemented, update this guide with:
  - the real “run” entrypoint (module/package command, if changed)
  - the final output filenames/locations
  - the final behavior of `--dry-run`
