# Installation Guide

## Purpose
Client-facing installation instructions (packaged release or from source).

## Supported OS
- macOS 13+
- Windows 10/11
- Linux (Ubuntu 22.04+ recommended)

## Install Steps (Source)
1. Install Python 3.10+.
2. Open terminal in project root.
3. Install dependencies:
```bash
python3 -m pip install -r requirements.txt
```
4. Launch GUI:
```bash
python3 src/gui_launcher.py
```

## First Run Checklist
1. Confirm internet access.
2. Open `2. Targets` and ensure desired APIs are enabled.
3. Open `🌐 API Monitor` and click `Check Now`.

## Common Issues

### SSL certificate verify failed
If HTTPS requests fail with `CERTIFICATE_VERIFY_FAILED`:
```bash
python3 -m pip install --upgrade pip certifi
```

### API returns 403 Forbidden
This is usually external access policy (network/VPN/IP), not an app bug.
- test on another network
- disable VPN/proxy
- temporarily disable blocked API target
