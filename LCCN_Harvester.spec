# -*- mode: python ; coding: utf-8 -*-
"""
LCCN_Harvester.spec
===================
PyInstaller build specification for the LCCN Harvester GUI.

Produces:
  macOS  → dist/LCCN Harvester.app   (self-contained .app bundle)
  Windows→ dist/LCCN_Harvester.exe   (single portable executable)

Run with:
  pyinstaller LCCN_Harvester.spec
"""

import platform
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SPEC_DIR    = Path(SPECPATH)          # project root (where this .spec lives)
SRC_DIR     = SPEC_DIR / "src"
CONFIG_DIR  = SPEC_DIR / "config"
DOCS_DIR    = SPEC_DIR / "docs"
ICONS_DIR   = SRC_DIR / "gui" / "icons"
DB_DIR      = SRC_DIR / "database"
DATA_DIR    = SPEC_DIR / "data"

IS_MAC     = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"

# ---------------------------------------------------------------------------
# Collect third-party packages that use dynamic imports / data files
# ---------------------------------------------------------------------------
pyz3950_d, pyz3950_b, pyz3950_h = collect_all("PyZ3950")
stdnum_d,  stdnum_b,  stdnum_h  = collect_all("stdnum")
certifi_d, certifi_b, certifi_h = collect_all("certifi")
pymarc_d,  pymarc_b,  pymarc_h  = collect_all("pymarc")
requests_d, requests_b, requests_h = collect_all("requests")


def add_data_if_exists(path: Path, target: str) -> tuple[str, str] | None:
    """Return a PyInstaller data tuple only when the source path exists."""
    if not path.exists():
        return None
    return (str(path), target)

# ---------------------------------------------------------------------------
# Data files bundled into the executable
# ---------------------------------------------------------------------------
datas = [
    # Application config defaults (profiles, active_profile.txt, etc.)
    (str(CONFIG_DIR),                   "config"),
    # Default writable data seeds used by the packaged app on first launch
    (str(DATA_DIR / "targets.tsv"),     "data"),
    (str(DATA_DIR / "targets.json"),    "data"),
    (str(DATA_DIR / "gui_settings.json"), "data"),
    # SVG icons used by the GUI
    (str(ICONS_DIR),                    "gui/icons"),
    # Database SQL schema (db_manager.py reads it at runtime)
    (str(DB_DIR / "schema.sql"),        "database"),
    (str(DB_DIR / "schema.sql"),        "src/database"),
    # Docs (help tab reads WCAG docs from here)
    (str(DOCS_DIR),                     "docs"),
    # The full src tree so that __file__-relative lookups work
    (str(SRC_DIR / "gui"),              "gui"),
    (str(SRC_DIR / "config"),           "config"),
    (str(SRC_DIR / "harvester"),        "harvester"),
    (str(SRC_DIR / "api"),              "api"),
    (str(SRC_DIR / "z3950"),            "z3950"),
    (str(SRC_DIR / "database"),         "database"),
    (str(SRC_DIR / "utils"),            "utils"),
]

optional_data = [
    add_data_if_exists(DATA_DIR / "sample", "data/sample"),
]

datas.extend(item for item in optional_data if item is not None)

datas += pyz3950_d + stdnum_d + certifi_d + pymarc_d + requests_d

# ---------------------------------------------------------------------------
# Hidden imports (dynamic imports PyInstaller cannot trace statically)
# ---------------------------------------------------------------------------
hiddenimports = [
    # PyQt6 modules
    "PyQt6",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtSvg",
    "PyQt6.QtSvgWidgets",
    "PyQt6.QtNetwork",
    "PyQt6.sip",
    # PyZ3950
    "PyZ3950",
    "PyZ3950.zoom",
    "PyZ3950.z3950",
    "PyZ3950.asn1",
    "PyZ3950.oids",
    "PyZ3950.zdefs",
    "PyZ3950.grs1",
    "PyZ3950.marc_to_unicode",
    "PyZ3950.zmarc",
    "PyZ3950.CQLParser",
    "PyZ3950.CQLUtils",
    "PyZ3950.bib1msg",
    "PyZ3950.charneg",
    "PyZ3950.ccl",
    "PyZ3950.pqf",
    "PyZ3950.c2query",
    "PyZ3950.SRWDiagnostics",
    # PLY (parser used by PyZ3950)
    "ply",
    "ply.lex",
    "ply.yacc",
    # Networking & SSL
    "requests",
    "certifi",
    "urllib3",
    "charset_normalizer",
    "idna",
    # MARC / ISBN
    "pymarc",
    "stdnum",
    "stdnum.isbn",
    "stdnum.issn",
    "stdnum.exceptions",
    # Standard library extras sometimes missed
    "sqlite3",
    "json",
    "csv",
    "email",
    "email.mime",
    "email.mime.text",
    # Internal packages
    "config",
    "config.profile_manager",
    "config.app_paths",
    "gui",
    "gui.modern_window",
    "gui.dashboard_v2",
    "gui.harvest_tab_v2",
    "gui.targets_config_tab",
    "gui.targets_tab_v2",
    "gui.config_tab_v2",
    "gui.results_tab_v2",
    "gui.ai_assistant_tab",
    "gui.help_tab",
    "gui.icons",
    "gui.notifications",
    "gui.styles_v2",
    "gui.theme_manager",
    "gui.shortcuts_dialog",
    "gui.accessibility_statement_dialog",
    "gui.animated_stat_card",
    "gui.input_tab",
    "harvester",
    "harvester.orchestrator",
    "harvester.targets",
    "harvester.z3950_targets",
    "harvester.export_manager",
    "harvester.export_main_tsv",
    "harvester.run_harvest",
    "harvester.api_targets",
    "api",
    "api.base_api",
    "api.loc_api",
    "api.harvard_api",
    "api.openlibrary_api",
    "api.http_utils",
    "z3950",
    "z3950.client",
    "z3950.marc_decoder",
    "z3950.pyz3950_compat",
    "z3950.session_manager",
    "database",
    "database.db_manager",
    "utils",
]

hiddenimports += (
    pyz3950_h + stdnum_h + certifi_h + pymarc_h + requests_h
    + collect_submodules("stdnum")
)

# ---------------------------------------------------------------------------
# Exclusions (reduce bundle size by dropping unused heavy packages)
# ---------------------------------------------------------------------------
excludes = [
    "tkinter",
    "matplotlib",
    "numpy",
    "pandas",
    "scipy",
    "PIL",
    "IPython",
    "jupyter",
    "notebook",
    "sphinx",
    "docutils",
]

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    [str(SPEC_DIR / "app_entry.py")],
    pathex=[str(SPEC_DIR), str(SRC_DIR)],
    binaries=[] + pyz3950_b + stdnum_b + certifi_b + pymarc_b + requests_b,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# ---------------------------------------------------------------------------
# macOS – .app bundle
# ---------------------------------------------------------------------------
if IS_MAC:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="LCCN Harvester",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,           # No terminal window
        argv_emulation=False,
        target_arch=None,        # Build for host arch; use --target-arch for universal
        codesign_identity=None,
        entitlements_file=None,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="LCCN_Harvester",
    )

    app = BUNDLE(
        coll,
        name="LCCN Harvester.app",
        # icon="assets/icon.icns",  # Uncomment and supply a .icns file to set a custom icon
        bundle_identifier="ca.upei.lccn-harvester",
        version="1.0.0",
        info_plist={
            "CFBundleName": "LCCN Harvester",
            "CFBundleDisplayName": "LCCN Harvester",
            "CFBundleVersion": "1.0.0",
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,   # Allows macOS dark mode
            "LSMinimumSystemVersion": "11.0",
            "NSHumanReadableCopyright": "© 2025 UPEI Library",
            "CFBundleDocumentTypes": [],
        },
    )

# ---------------------------------------------------------------------------
# Windows – single portable .exe
# ---------------------------------------------------------------------------
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="LCCN_Harvester",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,           # No console / cmd window
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        # icon="assets/icon.ico",  # Uncomment and supply a .ico file for a custom icon
    )
