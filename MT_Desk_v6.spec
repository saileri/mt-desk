# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for MT Desk v6.2.2 — CSV import + R-Multiple analysis.

Usage:
  pyinstaller MT_Desk_v6.spec    # Build using this spec (recommended)
"""

import sys
import os

# ── Platform-specific settings ──────────────────────────────────
is_windows = sys.platform == "win32"

# Resolve the project root (where this .spec file lives)
ROOT = os.path.dirname(os.path.abspath(__file__))

hiddenimports = [
    "tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "mt_desk",
    "mt_desk.parser",
    "mt_desk.analysis",
    "mt_desk.csv_import",
    "yaml",
]

if is_windows:
    hiddenimports += [
        "_tkinter",
        "tkinter.ttk",
    ]

a = Analysis(
    ["mt_desk/main.py"],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "mt_desk", "config", "mt_column_map.yaml"), "mt_desk/config"),
        (os.path.join(ROOT, "mt_desk", "config", "app_config.yaml"), "mt_desk/config"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MT_Desk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
