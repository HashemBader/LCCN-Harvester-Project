# Results Tab User Guide

Last updated: 2026-02-10
Applies to: `src/gui/results_tab.py`, `src/gui/export_dialog.py`, `src/harvester/export_manager.py`

## Purpose
Use the Results tab to inspect harvested data in the local database, search records, clear data when needed, and export records to files.

## What Is In This Tab

1. `Search & Filter` controls
2. `Records` table
3. Export actions

## Search And Filter

### Table selector
- `Successful Records`: reads from `main` table.
- `Failed Attempts`: reads from `attempted` table.

### ISBN search
- Enter full or partial ISBN.
- Press `Enter` or click `Search`.
- Clearing the field reloads the full selected table.

### Refresh
- Reloads current selected table from database.

### Clear Database
- Deletes all rows from both `main` and `attempted`.
- Confirmation is required.

## Records Table

### Successful Records columns
- `ISBN`
- `LCCN`
- `NLMCN`
- `Classification`
- `Source`
- `Date Added`
- `Age (days)` (derived in UI)

### Failed Attempts columns
- `ISBN`
- `Last Target`
- `Last Attempted`
- `Fail Count`
- `Last Error`
- `Age (days)` (derived in UI)

### Automatic fallback
- If `Successful Records` is empty but `Failed Attempts` has rows, the tab auto-switches to Failed Attempts and shows a status note.

### Row limit
- The UI loads up to the most recent `1000` rows per view.

## Export

## Export Results dialog
Click `Export Results...` to open the advanced export dialog.

### Supported formats
- `TSV` (default)
- `CSV`
- `JSON`

### Source options
- `Main Results`
- `Failed Attempts`
- `Both` (writes two files with `_success` and `_failed` suffixes)

### Save location behavior
- When you click `OK`, the dialog always prompts for save location.
- Export runs only after a location is selected.
- If canceled, no export is performed.
- File extension is normalized to selected format.

### Column selection
- For `Main Results`, selected columns are used.
- For `Failed Attempts`, fixed attempted columns are exported.

### Additional options
- `Include column headers`
- `Open file after export`

## Quick Export

- Available only in Advanced Mode.
- Button: `Quick Export TSV`.
- Exports `main` table to `data/exports/quick_export_<timestamp>.tsv`.

## File Format Notes

### TSV
- Tab-delimited rows.
- Optional header row.

### CSV
- Comma-delimited rows.
- Optional header row.

### JSON
- Array of objects.
- Keys use displayed header names.

## Typical Workflows

### Review successful harvests
1. Open Results tab.
2. Keep `Successful Records`.
3. Search by ISBN as needed.

### Investigate failures
1. Switch table to `Failed Attempts`.
2. Review `Last Error` and `Fail Count`.
3. Re-run harvest later based on retry policy.

### Export to chosen location and format
1. Click `Export Results...`.
2. Select source + format + columns.
3. Click `OK`.
4. Pick save path in system save dialog.

## Troubleshooting

### Export dialog opens but no file appears
- Ensure you selected a save location after pressing `OK`.
- Verify folder write permissions.

### Search returns no rows
- Check current table selector (`Successful` vs `Failed`).
- Search is performed only in the active table.

### Table shows fewer records than expected
- UI view is capped at 1000 rows by design.
