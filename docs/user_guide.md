# User Guide — LCCN Harvester

**Version 1.0.0 · UPEI Library**

This guide explains how to use the LCCN Harvester desktop application to look up Library of Congress Call Numbers (LCCNs) and National Library of Medicine Call Numbers (NLMCNs) for a list of ISBNs.

---

## Overview

The LCCN Harvester takes a TSV file of ISBNs, queries multiple library sources (API targets and Z39.50 servers) in priority order, and saves results to a local database and output files. Results are immediately available on the Dashboard during and after each run.

---

## Launching the Application

LCCN Harvester runs on **macOS, Windows, and Linux**.

- **Packaged executable** — double-click the app file for your platform. No setup required.
- **From source** — run the following from the project root:

```bash
python app_entry.py
```

The application opens to the **Dashboard** tab. A collapsible sidebar on the left provides navigation.

---

## Interface Overview

The application has four tabs, accessible from the left sidebar:

| Tab | Purpose |
|-----|---------|
| **Dashboard** | Harvest statistics, live activity monitor, and recent results |
| **Configure** | Target list and per-profile settings |
| **Harvest** | Run and monitor harvests; import MARC records |
| **Help** | Keyboard shortcuts, accessibility info, and this user manual |

The sidebar also shows a **status pill** (Idle / Running / Paused / Completed / Cancelled / Error) reflecting the current harvester state.

---

## Profiles

Profiles let you maintain separate configurations (targets, retry interval, call number mode) for different cataloguing workflows.

### Switching profiles
- Use the profile selector on the **Dashboard** or in **Configure → Settings**.
- The active profile name is displayed at the top of the Dashboard.

### Creating a profile
1. Go to **Configure → Settings**.
2. Click **New Profile**.
3. Enter a name and choose starting settings.
4. Click **OK**.

### Deleting a profile
Select the profile in **Configure → Settings** and click **Delete**. The default profile cannot be deleted.

> **Note:** Switching profiles resets the Harvest tab. Any in-progress harvest must be stopped first.

---

## Configuring Targets (Configure → Targets)

Targets are the library sources the harvester queries. They are tried in rank order — the harvester stops at the first successful match for each ISBN ("stop on find").

### Target types
- **API targets** — Library of Congress (LOC), Harvard LibraryCloud, OpenLibrary
- **Z39.50 targets** — library catalog servers using the Z39.50 protocol

### Managing targets
- **Enable / Disable** — check or uncheck a target to include or exclude it from harvests.
- **Priority (Rank)** — lower rank number = tried first. Use the up/down controls to reorder.
- Changes are saved per profile.

---

## Settings (Configure → Settings)

| Setting | Description | Default |
|---------|-------------|---------|
| **Retry Interval** | Days before retrying an ISBN that previously failed on all targets | 7 days |
| **Call Number Selection** | Which call number type(s) to harvest | LCCN only |

### Call Number Selection modes

| Mode | Behaviour |
|------|-----------|
| **LCCN only** | Harvest Library of Congress call numbers (MARC 050) |
| **NLMCN only** | Harvest National Library of Medicine call numbers (MARC 060) |
| **Both** | Harvest both LCCN and NLMCN; stop once either is found (configurable) |

Click **Save** to persist any changes to the active profile.

---

## Preparing Input

### File format
- Type: `.tsv` (tab-separated values)
- One ISBN per line (first column)
- Hyphens and spaces are stripped automatically

### Supported ISBN formats
- ISBN-10 (10 digits, may end in `X`)
- ISBN-13 (13 digits, starts with `978` or `979`)

### Example `input.tsv`
```
978-0-13-110362-7
0131103628
9780306406157
```

---

## Running a Harvest (Harvest Tab)

### Steps
1. Go to the **Harvest** tab.
2. Select an input file by dragging and dropping it onto the drop zone, or clicking **Choose File**.
3. Click **Start Harvest**.
4. Monitor progress in the progress bar and activity log.
5. When complete, output files are listed in the Harvest tab. Results also appear live on the **Dashboard**.

### Harvest controls

| Control | Action |
|---------|--------|
| **Start Harvest** | Begin processing the input file |
| **Pause** | Suspend processing (resume with the same button) |
| **Stop / Cancel** | Stop the current run. Results collected so far are saved. |
| **New Harvest** | Reset the tab for a new input file |

### Retry bypass
If some ISBNs were recently skipped due to the retry window, you can check **Bypass retry for this run** before starting to force a fresh attempt on all ISBNs in the file.

---

## Understanding Outputs

All output files are written to the active profile's data directory. Each run overwrites the previous run's files.

### Successful results (`*_successful.tsv` / `.csv`)

Columns vary by call number mode:

**LCCN only:**
`ISBN · LCCN · LCCN Source · Classification · Date`

**NLMCN only:**
`ISBN · NLM · NLM Source · Date`

**Both:**
`ISBN · LCCN · LCCN Source · Classification · NLM · NLM Source · Date`

- **Classification** — the LoC class prefix derived from the LCCN (e.g., `QA`, `HF`)
- **Date** — the date the record was harvested (ISO format)
- A `.csv` copy is generated automatically for use in Excel and Google Sheets

### Failed (`*_failed.tsv` / `.csv`)
ISBNs for which no call number was found. Columns: `Call Number Type · ISBN · Target · Date Attempted · Reason`

### Invalid (`*_invalid.tsv` / `.csv`)
ISBNs that failed format validation (wrong length, bad check digit, etc.). Column: `ISBN`

### Problems (`*_problems.tsv` / `.csv`)
Per-target error summaries: `Target · Problem`

### Local database
All successful results are cached in a per-profile SQLite database. On subsequent runs, cached ISBNs are served from the database without re-querying external sources, saving time and API calls.

---

## MARC Import (Harvest Tab)

You can import call numbers directly from a MARC file instead of (or in addition to) querying external sources.

### Steps
1. In the **Harvest** tab, click **Import MARC**.
2. Select a MARC file.
3. Choose the call number mode (LCCN, NLMCN, or Both).
4. Confirm. Records are imported into the database and written to the results files.

---

## Dashboard

The Dashboard provides an at-a-glance view of the current profile's harvest data.

| Section | Shows |
|---------|-------|
| **KPI cards** | Total ISBNs in database, Found, Failed, and Cached counts |
| **Live Activity** | Real-time per-ISBN status during a running harvest |
| **Recent Results** | A scrollable table of the most recent ISBN outcomes (ISBN, status, source) |
| **Last Run** | Timestamp and outcome of the last completed harvest |

The Dashboard refreshes automatically when a harvest completes or when you switch to it.

---

## Keyboard Shortcuts

| Action | macOS | Windows / Linux |
|--------|-------|-----------------|
| Toggle sidebar | Control+B | Ctrl+B |
| Quit | Control+Q | Ctrl+Q |
| Refresh Dashboard | Control+R | Ctrl+R |
| Open Dashboard | Control+1 | Ctrl+1 |
| Open Configure | Control+2 | Ctrl+2 |
| Open Harvest | Control+3 | Ctrl+3 |
| Open Help | Control+4 | Ctrl+4 |
| Start harvest | Control+H | Ctrl+H |
| Stop harvest | Esc | Esc |
| Cancel harvest | Control+. | Ctrl+. |

---

## Troubleshooting

### No results for an ISBN
Possible causes:
- The ISBN is invalid or has a typo.
- No configured target has a record for this ISBN.
- All targets timed out — check your network connection.
- The ISBN was recently attempted and is within the retry window. Use **Bypass retry** to force a retry.

### ISBN shows as invalid
- Verify the ISBN length (10 or 13 digits) and check digit.
- Remove any leading/trailing spaces in your input file.

### Harvest stops immediately with "No valid ISBNs"
- Ensure the input file is a `.tsv` file with ISBNs in the first column.
- Confirm the file is not empty.

### SSL / certificate errors
If you see `CERTIFICATE_VERIFY_FAILED`:
```bash
python3 -m pip install --upgrade pip certifi
```

### Target shows as offline / unavailable
- Check your internet connection.
- If a target returns `403 Forbidden`, it may be blocking your IP or network. Try a different network or temporarily disable that target in **Configure → Targets**.

### Profile settings not saving
- Click **Save** after making changes in **Configure → Settings**.
- Ensure you have write access to the application's data directory.

---

## See Also

- [installation_guide.md](installation_guide.md) — Installation and setup instructions
- [cli_reference.md](cli_reference.md) — Command-line interface reference (advanced / scripting use)
