# Installation Guide

This guide covers the supported ways to run LCCN Harvester.

---

## Run From Source

### Requirements

- Python 3.10 or newer
- A working internet connection for dependency installation

### Setup

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app_entry.py
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app_entry.py
```

This is the documented launch path that is fully represented in the `main` branch.

---

## Packaged Builds

The `main` branch does not currently contain committed local packaging scripts or a checked-in build pipeline for platform executables.

If your team distributes packaged builds separately, follow the release process that belongs to the branch or repository where those packaging assets actually live.

---

## First Run Checklist

1. Open `Configure`.
2. Confirm the active profile and target list look correct.
3. Go to `Harvest`.
4. Load a test input file and verify the preview.
5. Start a small harvest run.

---

## Troubleshooting

### `ModuleNotFoundError` or missing dependency errors

Make sure the virtual environment is active and reinstall dependencies:

```bash
pip install -r requirements.txt
```

### Certificate or SSL errors

```bash
python3 -m pip install --upgrade pip certifi
```

### PowerShell blocks virtual-environment activation

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### PyZ3950 install problems

The project depends on `PyZ3950` from GitHub. If dependency installation fails, retry with network access available and then rerun `pip install -r requirements.txt`.

---

## See Also

- [user_guide.md](user_guide.md)
- [local_app_build_guide.md](local_app_build_guide.md)
- [contribution_guide.md](contribution_guide.md)
