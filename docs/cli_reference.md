# CLI Reference — LCCN Harvester

The primary interface for LCCN Harvester is the desktop GUI. This reference covers the command-line interface, intended for scripting and headless use. The CLI works on macOS, Windows, and Linux.

---

## Quick Start

### Prepare an input TSV

- File type: `.tsv`
- One ISBN per line (first column)
- Hyphens and spaces are stripped automatically

Example `input.tsv`:

```text
978-0-13-110362-7
0131103628
9780306406157
```

### Run the CLI

```bash
python src/harvester_cli.py --input path/to/input.tsv
```

Short flag:

```bash
python src/harvester_cli.py -i path/to/input.tsv
```

Dry-run (no database writes):

```bash
python src/harvester_cli.py -i path/to/input.tsv --dry-run
```

---

## What the CLI Does

Given an input TSV, the CLI:

1. Validates that the input file exists and is a regular file.
2. Initializes the SQLite database (creates tables if needed).
3. Parses and normalizes ISBNs from the input file.
4. Runs the full harvest pipeline (cache check → retry gate → target queries → DB write).
5. Prints a summary of results.

### Console output

```text
LCCN Harvester
- Input TSV: /full/path/to/input.tsv
- Dry run:   False
- Database:  initialized (tables ready)
- ISBNs:     parsed 3 entries
- Preview:   9780131103627, 0131103628, 9780306406157

Harvest complete: 2 found, 1 failed
```

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success — harvest ran (some ISBNs may still have no result) |
| `1` | Input file error or database initialization failure |

---

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--input` / `-i` | Yes | Path to the TSV file containing ISBNs |
| `--dry-run` | No | Run without writing to the database (default: `False`) |
| `--stop-rule` | No | Stop behaviour in `both` mode — `stop_either` (default), `stop_lccn`, `stop_nlmcn`, `continue_both` |

---

## Output Files

The CLI writes the same output files as the GUI:

| File | Contents |
|------|---------|
| `*_successful.tsv` / `.csv` | ISBNs with call numbers found |
| `*_failed.tsv` / `.csv` | ISBNs with no call number found |
| `*_invalid.tsv` / `.csv` | ISBNs that failed format validation |
| `*_problems.tsv` / `.csv` | Per-target error summaries |

Output files are written to `data/` by default. The database is at `data/lccn_harvester.sqlite3`.

---

## Troubleshooting

### "Input file does not exist"

```
ERROR: Input file does not exist: /path/to/file.tsv
```

Check your path and ensure the file exists.

### "Input path is not a file"

```
ERROR: Input path is not a file: /path/to/folder
```

Provide a path to a `.tsv` file, not a directory.

### Module not found / import errors

- Ensure your virtual environment is activated.
- Ensure dependencies are installed: `pip install -r requirements.txt`
- Run from the project root so `src/` paths resolve correctly.

---

## See Also

- [user_guide.md](user_guide.md) — Full GUI user guide
- [installation_guide.md](installation_guide.md) — Installation instructions
