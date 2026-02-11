# Configuration Tab User Guide

Last updated: 2026-02-10
Applies to: `src/gui/config_tab.py`

## Purpose
Use the Configuration tab to manage reusable settings profiles and control harvest behavior (collection options, retry policy, and output toggles).

## What Is In This Tab
The tab has two sections:

1. `Configuration Profile`
2. `Settings`

## Configuration Profile Section

### Active profile selector
- The dropdown at the top shows all available profiles.
- Selecting a different profile loads its settings into the tab.
- If there are unsaved edits, the tab asks for confirmation before switching profiles.

### Unsaved changes indicator
- `Unsaved changes` appears when any setting is modified.
- The `Save` button is enabled only when there are unsaved edits.

### Save
- Saves the current settings to the currently active profile.
- If the active profile is `Default Settings`, direct overwrite is blocked.
- For default profile edits, use `Save As`.

### Save As
- Saves current settings to a new profile name.
- If the name already exists, overwrite confirmation is required.
- Duplicate-settings warning:
  - If another profile already has identical settings, the tab warns you and asks whether to continue.

### Use Session Only
- Applies current tab settings for this run/session only.
- Does not write changes to profile files.

### Manage menu
The `Manage` button opens:
- `Rename Profile`
- `Delete Profile`
- `Reset to Default Settings`

Behavior notes:
- `Default Settings` cannot be renamed or deleted.
- Delete asks for confirmation.
- Reset loads values from `Default Settings`.

## Settings Section

### Call Number Collection
- `Collect Library of Congress Call Numbers (LCCN)` (`collect_lccn`)
- `Collect NLM Call Numbers (NLMCN)` (`collect_nlmcn`)

### Retry Settings
- `Days before retrying failed ISBNs` (`retry_days`)
- Range: `0` to `365`

### Output Settings
- `Generate TSV output file` (`output_tsv`)
- `Generate invalid ISBN file` (`output_invalid_isbn_file`)

## How To Use

1. Open `Configuration`.
2. Select an existing profile or keep the current one.
3. Change settings.
4. Choose one of:
   - `Save` to current profile
   - `Save As` to create/update another profile
   - `Use Session Only` to avoid persisting changes

## Data And Persistence

- Active profile name is managed by `ProfileManager`.
- Profile settings are loaded/saved via `config/profile_manager.py`.
- `get_config()` returns the currently visible settings from the tab, whether or not they are saved.

## Current Limits

- The tab does not configure API target order/enabled state directly; target selection is handled in the Targets tab.
- Advanced mode currently does not reveal additional Configuration-tab-only controls.

## Troubleshooting

### Save button stays disabled
- No setting has changed since the profile load.
- Modify any checkbox/spinbox value to mark changes.

### Profile switch is blocked
- You likely declined the unsaved-changes confirmation prompt.

### Cannot edit default profile
- This is expected. Use `Save As` to create a custom profile.
