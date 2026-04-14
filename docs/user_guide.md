# User Guide

This guide covers the current GUI workflow for LCCN Harvester.

For plain-language definitions of ISBNs, call numbers, MARC, caching, and linked ISBNs, see [concepts.md](concepts.md).

## Table Of Contents

- [Overview](#overview)
- [Launching the App](#launching-the-app)
- [Profiles](#profiles)
  - [Important profile behavior](#important-profile-behavior)
  - [Create a profile](#create-a-profile)
  - [Switch profiles](#switch-profiles)
- [Configure: Targets](#configure-targets)
- [Configure: Harvest Settings](#configure-harvest-settings)
- [Preparing Input Files](#preparing-input-files)
- [Harvest Page](#harvest-page)
  - [Run setup controls](#run-setup-controls)
  - [Stop Rule options](#stop-rule-options)
  - [Running a harvest](#running-a-harvest)
- [Harvest Outputs](#harvest-outputs)
  - [Successful results](#successful-results)
  - [Failed results](#failed-results)
  - [Invalid results](#invalid-results)
  - [Problems results](#problems-results)
  - [Linked ISBNs snapshot](#linked-isbns-snapshot)
- [MARC Import](#marc-import)
  - [MARC import flow](#marc-import-flow)
- [Dashboard](#dashboard)
- [Help And Accessibility](#help-and-accessibility)
- [Troubleshooting](#troubleshooting)
  - [No results returned](#no-results-returned)
  - [File preview shows no valid rows](#file-preview-shows-no-valid-rows)
  - [SSL or certificate problems](#ssl-or-certificate-problems)
  - [Database locked](#database-locked)
  - [Target unavailable](#target-unavailable)
- [See Also](#see-also)

---

## Overview

LCCN Harvester reads a list of ISBNs, checks the local SQLite cache, queries enabled targets when needed, and writes timestamped result files in the active profile's output folder.

The application has four main pages:

| Page | Purpose |
|------|---------|
| `Dashboard` | Run status, KPI cards, recent results, result-file buttons, linked-ISBN tools |
| `Configure` | Profile settings and target management |
| `Harvest` | Input-file preview, harvest controls, and MARC import |
| `Help` | Keyboard shortcuts, accessibility links, and documentation links |

The app currently opens on the `Configure` page.

---

## Launching the App

From source:

```bash
python app_entry.py
```

---

## Profiles

Profiles keep settings and targets separate for different workflows.

Each profile has:

- Its own settings JSON under `config/profiles/<slug>/`
- Its own targets TSV under `config/profiles/<slug>/` if it is a user-created profile
- Its own output folder under `data/<slug>/`

All profiles share the same SQLite database file at `data/lccn_harvester.sqlite3`.

### Important profile behavior

- `Default Settings` is built in and read-only.
- `Default Settings` uses the shared targets file at `data/targets.tsv`.
- To keep changes, create a new profile and save there.
- Deleting a profile removes its saved configuration files, but its existing output folder is left in place.

### Create a profile

1. Open `Configure`.
2. In `Profile Settings`, click `New Profile`.
3. Choose the source profile to copy from.
4. Enter a new name and confirm.

### Switch profiles

Use the profile selector on the `Configure` page. Switching profiles reloads both settings and targets.

---

## Configure: Targets

The targets table contains both built-in API targets and any Z39.50 targets for the active profile.

Supported target types:

- API targets
- Z39.50 targets

From this page you can:

- Enable or disable targets
- Change rank order
- Add or edit Z39.50 targets
- Search the target list
- Run connectivity checks

Lower rank numbers are tried first during a harvest.

---

## Configure: Harvest Settings

The `Harvest Settings` card stores the profile defaults used when a run begins.

| Setting | Meaning |
|---------|---------|
| `Retry Interval` | Days to wait before retrying a failed lookup |
| `Call Number Selection` | `LCCN only`, `NLMCN only`, or `Both` |

When a harvest run starts from the `Harvest` page, the run controls can override parts of this configuration for that run.

---

## Preparing Input Files

Accepted input formats:

| Format | Extensions |
|--------|------------|
| Tab-separated text | `.tsv`, `.txt` |
| Comma-separated text | `.csv` |
| Excel | `.xlsx`, `.xls` |

Input rules:

- Column 1 is the primary ISBN.
- Columns 2 and later are treated as linked ISBN variants for the same row.
- Blank rows are ignored.
- Rows beginning with `#` are treated as comments.
- Duplicate valid ISBNs are processed once.
- Hyphens and spaces are stripped before validation.

Recognized first-column header values include:

- `ISBN`
- `ISBNs`
- `ISBN10`
- `ISBN13`

Example:

```text
ISBN
978-0-13-110362-7	0131103628
9780306406157
```

---

## Harvest Page

The `Harvest` page has three main areas:

- Run setup
- File statistics and preview
- MARC import

### Run setup controls

| Control | Meaning |
|---------|---------|
| `Input file` | Select or drag in the harvest input file |
| `Run Mode` | `LCCN Only`, `NLM Only`, `Both (LCCN & NLM)`, or `MARC Import Only` |
| `Stop Rule` | Active only when run mode is `Both` and DB-only is off |
| `Database only for this run` | Skip external targets and search the local database only |

`MARC Import Only` sets the run to use the local database only, which is useful after seeding records through the MARC Import section.

### Stop Rule options

| Option | Meaning |
|--------|---------|
| `Stop if either found` | Stop when either an LCCN or NLMCN is found |
| `Stop if LCCN found` | Stop once an LCCN is found |
| `Stop if NLMCN found` | Stop once an NLMCN is found |
| `Continue until both found` | Keep querying until both types are found or targets are exhausted |

### Running a harvest

1. Open `Harvest`.
2. Select or drag in an input file.
3. Review the file statistics and preview.
4. Adjust run mode if needed.
5. Click `Start Harvest`.

During a run you can:

- Pause and resume
- Cancel the run
- Watch live status updates on the `Dashboard`

---

## Harvest Outputs

Harvest output files are written into the active profile folder under `data/<profile-slug>/`.

Each harvest creates timestamped files with names like:

- `<profile>-success-<timestamp>.tsv`
- `<profile>-failed-<timestamp>.tsv`
- `<profile>-invalid-<timestamp>.tsv`
- `<profile>-problems-<timestamp>.tsv`
- `<profile>-linked-isbns-<timestamp>.tsv`

Each TSV also gets a CSV copy with UTF-8 BOM for spreadsheet compatibility.

### Successful results

Columns depend on the active mode:

| Mode | Columns |
|------|---------|
| `LCCN only` | `ISBN`, `LCCN`, `LCCN Source`, `Classification`, `Date` |
| `NLMCN only` | `ISBN`, `NLM`, `NLM Source`, `Date` |
| `Both` | `ISBN`, `LCCN`, `LCCN Source`, `Classification`, `NLM`, `NLM Source`, `Date` |

### Failed results

Columns:

`Call Number Type`, `ISBN`, `Target`, `Date Attempted`, `Reason`

In `Both` mode, a single ISBN can produce more than one failed row because LCCN and NLMCN failures are tracked separately.

### Invalid results

Columns:

`ISBN`

### Problems results

Columns:

`Target`, `Problem`

This file is for target or connectivity problems, not normal "not found" results.

### Linked ISBNs snapshot

Columns:

`ISBN`, `Canonical ISBN`

This file is a snapshot of the current linked-ISBN mappings in the database at the time of the run.

---

## MARC Import

The `MARC Import` section is separate from the standard harvest run.

Supported file types:

- Binary MARC21: `.mrc`, `.marc`
- MARCXML: `.xml`

### MARC import flow

1. Select or drag in a MARC file.
2. Click `Run`.
3. Enter a source name when prompted.
4. The import uses the current call-number mode from the active configuration.
5. Matching records are saved into the shared SQLite database.
6. A timestamped export is written to the active profile folder:
   `data/<profile-slug>/<profile>-marc-import-<timestamp>.tsv`

Records with ISBNs but no call number are recorded in the database as attempted rows. Records with no usable ISBN are skipped.

---

## Dashboard

The `Dashboard` summarizes the current session and gives quick access to outputs and maintenance tools.

Main sections:

- Run status pill
- Pause and cancel buttons during active runs
- KPI cards for processed, successful, failed, and invalid rows
- Result-file buttons for the most recent run
- Recent results list
- `Browse Database`
- `Linked ISBNs`
- `Reset Dashboard Stats`

`Browse Database` is a read-only viewer for the `main`, `attempted`, and `linked_isbns` tables with search, filtering, and pagination.

---

## Help And Accessibility

The `Help` page provides:

- Keyboard shortcut reference
- Accessibility statement link
- Support and guidance link
- User guide link
- App version and platform summary

The application also creates a system tray icon when the platform supports it. From the tray menu you can show the window, toggle notifications, or quit.

---

## Troubleshooting

### No results returned

- Check that at least one target is enabled.
- Verify your network connection.
- Confirm the ISBN is valid and present in column 1.
- If you expect a cached result, try `Database only for this run`.

### File preview shows no valid rows

- Confirm the file format is supported.
- Make sure ISBNs are in the first column.
- Check that the first row is either real data or a recognized header.

### SSL or certificate problems

```bash
python3 -m pip install --upgrade pip certifi
```

### Database locked

Another process may still have the SQLite database open. Close other app instances and try again.

### Target unavailable

Use `Check Servers` on the `Configure` page. A normal "not found" response is different from a target problem and will not appear in the problems file.

---

## See Also

- [concepts.md](concepts.md)
- [installation_guide.md](installation_guide.md)
- [cli_reference.md](cli_reference.md)
