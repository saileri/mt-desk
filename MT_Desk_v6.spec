# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for MT Desk — single-file EXE build.

Usage:
  pyinstaller MT_Desk_v5.spec    # Build using this spec (recommended)
  pyinstaller --onefile --noconsole --name MT_Desk mt_desk/main.py  # CLI build
"""

import sys
import os

# ── Platform-specific settings ──────────────────────────────────
is_windows = sys.platform == "win32"

# Base hidden imports — required for tkinter GUI on Windows
hiddenimports = [
    "tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "mt_desk",
    "mt_desk.parser",
    "mt_desk.analysis",
]

# On Windows, add Tcl/Tk related imports
if is_windows:
    hiddenimports += [
        "_tkinter",
        "tkinter.ttk",
    ]

a = Analysis(
    ["mt_desk/main.py"],
    pathex=[os.path.abspath(".")],  # Ensure mt_desk package can be found
    binaries=[],
    datas=[],
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
    console=False,  # No console window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
