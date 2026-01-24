# CLI User Guide (Skeleton)

This guide explains how to run the **LCCN Harvester** from the command line using an input TSV of ISBNs, and how to understand the outputs.

---

## What the CLI does
Given a TSV input file of ISBNs, the CLI:
- normalizes + validates ISBNs
- checks the local SQLite DB to reuse existing results
- queries configured targets in order until a classification is found
- writes successes to the `main` table (export-ready)
- tracks failures in `attempted` to avoid repeated calls
- exports a TSV from `main`

---

## Input format (TSV)
- File type: `.tsv`
- Recommended: **one ISBN per line** (first column)
- ISBNs may contain hyphens/spaces (they’ll be normalized)

Example:
```text
978-0-13-110362-7
0131103628
9780306406157