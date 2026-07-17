# MT Desk — MT4/MT5 Trading Analytics Desktop

[![Build](https://github.com/saileri/mt-desk/actions/workflows/build.yml/badge.svg)](https://github.com/saileri/mt-desk/actions/workflows/build.yml)

Multi-account trading performance dashboard. Drag-drop MT4/MT5 HTML statements, get instant charts and side-by-side comparison — all in a single portable EXE.

## Architecture

```
MT Desk.exe
├── Python backend (streaming parser + matplotlib charts → base64 PNG)
├── NiceGUI web UI (tabs, cards, tables)
└── Browser display (no JS charting — just <img> tags)
```

## Features

- **Zero install** — single EXE, double-click to run
- **No file size limit** — Python streaming parser handles 500MB+ files
- **Server-side charts** — matplotlib renders all charts as PNG, browser only displays
- **Multi-account comparison** — overlay equity curves, side-by-side stats, correlation matrix
- **GitHub Actions CI/CD** — auto-build EXE on every `v*` tag

## Key Dependencies

| Component | Repo | Stars | Role |
|:---|:---|:---:|:---|
| NiceGUI | [zauberzeug/nicegui](https://github.com/zauberzeug/nicegui) | 16k | Web UI framework |
| Matplotlib | [matplotlib/matplotlib](https://github.com/matplotlib/matplotlib) | 20k | Chart rendering |
| PyInstaller | [pyinstaller/pyinstaller](https://github.com/pyinstaller/pyinstaller) | 12k | EXE packaging |

## Quick Start

```bash
pip install -e .
mt-desk
# Opens browser at http://127.0.0.1:19799
```

## Download

Get the latest EXE from [Releases](https://github.com/saileri/mt-desk/releases).
