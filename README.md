# MT Desk — MT4/MT5 Trading Analytics Desktop

[![Build](https://github.com/saileri/mt-desk/actions/workflows/build.yml/badge.svg)](https://github.com/saileri/mt-desk/actions/workflows/build.yml)

Multi-account trading performance dashboard. Drag-drop MT4/MT5 HTML statements, get instant interactive ECharts reports — all in a single portable EXE.

## Architecture
```
MT Desk.exe
├── Python backend (streaming HTML parser + statistics engine)
├── Tkinter launcher (file picker, progress)
└── Browser-based report (ECharts interactive charts, dark/light theme)
```

## Features

- **Zero install** — single EXE, double-click to run
- **No file size limit** — Python streaming parser handles 500MB+ files
- **5-Tab Dashboard** — organized, insight-driven report layout
- **Interactive ECharts** — 15+ interactive chart types with dark/light theme
- **Monte Carlo simulation** — 1000-run random shuffle with P5~P95 confidence bands
- **MAE/MFE analysis** — Maximum Adverse/Favorable Excursion scatter plots
- **Leverage correlation** — volume bucket analysis with win rate overlay
- **CS Audit mode** — stop-out detection, scalp warnings, swap burden analysis
- **KPI dashboard** — 11 key metrics with hover tooltips and metric guide
- **Trade detail table** — sortable, searchable, paginated 12-column trade log
- **Date filtering** — quick filters (today/week/month/3m) + custom date range
- **Print-ready** — CSS print styles for PDF export
- **GitHub Actions CI/CD** — auto-build EXE on every `v*` tag

## Dashboard Tabs

| Tab | Charts |
|:--|:--|
| 📊 **Dashboard 總覽** | KPI cards, Equity curve + Drawdown subchart, Summary insights |
| 🛡️ **風險與權益** | Monthly waterfall, Long/Short bars, Quarterly symbols, Monte Carlo simulation, Leverage correlation, Volume-P&L scatter |
| 🧠 **交易習慣** | Heatmap, Session radar, Duration histogram, Holding P&L distribution, Symbol bubble matrix, Symbol P&L bar |
| 📐 **MAE/MFE 點陣** | MAE scatter, MFE scatter, MAE vs MFE bubble, Statistical summary |
| 🔍 **CS 風控審計** | Close reason donut, Holding time buckets, Swap burden, Cashflow waterfall, Scalp/Stop-out filters |

## Quick Start

```bash
pip install -e .
mt-desk
# Opens browser with interactive report
```

## Download

Get the latest EXE from [Releases](https://github.com/saileri/mt-desk/releases).
