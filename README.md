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
- **Interactive ECharts** — 12 interactive chart types with dark/light theme
- **Insight-driven** — radar charts, bubble matrix, drawdown subchart, waterfall with cumulative line
- **KPI dashboard** — 11 key metrics with hover tooltips and metric guide
- **Trade detail table** — sortable, searchable, paginated 12-column trade log
- **Date filtering** — quick filters (today/week/month/3m) + custom date range
- **Print-ready** — CSS print styles for PDF export
- **GitHub Actions CI/CD** — auto-build EXE on every `v*` tag

## Charts

| Chart | Type | Description |
|:--|:--|:--|
| Symbol Preference | Donut | Trade count share by instrument |
| Symbol P&L | Horizontal Bar | Profit/loss contribution per symbol |
| Volume / Swap | Donut + Bar | Trading volume & overnight interest |
| Monthly P&L | Waterfall + Cumulative Line | Monthly gain/loss breakdown |
| Long/Short P&L | Stacked Bar + Line | Directional P&L with win ratio |
| Quarterly Symbols | 100% Stacked Bar | Symbol preference evolution |
| Holding Duration | Histogram | Fixed-bucket trade duration distribution |
| Equity Curve | Line + Drawdown Subchart | Cumulative P&L with drawdown overlay |
| Trading Heatmap | Heatmap | Weekday × hour trade activity |
| Session Radar | Radar | Asia vs London vs NY performance |
| Symbol Matrix | Bubble Scatter | Count × win rate × P&L matrix |

## Key Dependencies

| Component | Role |
|:--|:--|
| ECharts 5.6 | Interactive chart rendering (CDN) |
| Tkinter | File picker launcher (stdlib) |
| PyInstaller | EXE packaging |

## Quick Start

```bash
pip install -e .
mt-desk
# Opens browser with interactive report
```

## Download

Get the latest EXE from [Releases](https://github.com/saileri/mt-desk/releases).
