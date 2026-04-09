# Installation Guide — LCCN Harvester

**Version 1.0.0 · UPEI Library**

How to install and run LCCN Harvester on macOS, Windows, or Linux — either as a packaged executable or directly from source.

---

## Supported Platforms

| Platform | Minimum Version |
|----------|----------------|
| macOS | 13 (Ventura) or later |
| Windows | 10 or 11 |
| Linux | Ubuntu 22.04+ (or equivalent) |

---

## Option A — Packaged Executable (Recommended)

Download the pre-built executable for your platform from the project releases page and run it directly. No Python installation required.

- **macOS:** double-click `LCCN Harvester.app`
- **Windows:** double-click `LCCN_Harvester.exe`
- **Linux:** run `./LCCN_Harvester` from a terminal

---

## Option B — Run from Source

### 1. Install Python 3.10+

Download from [python.org](https://python.org) or use your system package manager.

### 2. Clone the repository

```bash
git clone <REPO_URL>
cd LCCN-Harvester-Project
```

### 3. Create and activate a virtual environment

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 4. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Launch the application

```bash
python app_entry.py
```

---

## First Run Checklist

1. Confirm you have a working internet connection.
2. Go to **Configure → Targets** and verify at least one target is enabled.
3. Prepare a `.tsv` input file with one ISBN per line.
4. Go to **Harvest**, load the file, and click **Start Harvest**.

---

## Troubleshooting

### SSL certificate verify failed

```bash
python3 -m pip install --upgrade pip certifi
```

### API returns 403 Forbidden

This is usually a network policy issue, not an application bug:
- Try from a different network or disable VPN/proxy.
- Temporarily disable the affected target in **Configure → Targets**.

### `ModuleNotFoundError: PyQt6`

Ensure your virtual environment is activated and dependencies are installed inside it:

```bash
pip install -r requirements.txt
pip list | grep PyQt6
```

### Application does not open on macOS

If macOS blocks the app with "unidentified developer":
- Right-click the app → Open → confirm.
- Or: System Settings → Privacy & Security → allow the app.

---

## See Also

- [user_guide.md](user_guide.md) — How to use the application
- [cli_reference.md](cli_reference.md) — Command-line interface
- [contribution_guide.md](contribution_guide.md) — Developer setup and workflow
