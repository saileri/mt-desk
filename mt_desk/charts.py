"""ECharts configs — 8 charts matching professional trading dashboard. Zero deps."""
from __future__ import annotations
import json
from datetime import datetime

def _j(obj): return json.dumps(obj, ensure_ascii=False, default=str)

# ─── 1. 權益曲線 (Equity area chart) ────────────────────────────
def chart_equity(stats):
    eq = stats["equity"]; dates = stats.get("equity_dates", [])
    n = len(eq)
    if n < 2: return "null"
    labels = dates if dates else list(range(n))
    color = "#059669" if stats["total_pl"] >= 0 else "#dc2626"
    return _j({
        "tooltip": {"trigger": "axis", "formatter": "{b}<br/>權益: ${c}"},
        "grid": {"left": 65, "right": 15, "top": 15, "bottom": 30},
        "xAxis": {"type": "category", "data": labels, "axisLabel": {"fontSize": 9, "rotate": 30, "interval": max(1, n//8)}},
        "yAxis": {"type": "value", "axisLabel": {"formatter": "${{value}}"}},
        "series": [{"type": "line", "data": eq, "smooth": True, "symbol": "none",
                    "lineStyle": {"color": color, "width": 2},
                    "areaStyle": {"color": {"type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                        "colorStops": [{"offset": 0, "color": "rgba(5,150,105,0.2)" if stats["total_pl"]>=0 else "rgba(220,38,38,0.2)"},
                                       {"offset": 1, "color": "rgba(5,150,105,0)" if stats["total_pl"]>=0 else "rgba(220,38,38,0)"}]}}}]
    })

# ─── 2. 交易次數 (Win/Loss count bar) ───────────────────────────
def chart_winloss_count(stats):
    return _j({
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 50, "right": 10, "top": 15, "bottom": 25},
        "xAxis": {"type": "category", "data": ["盈利", "虧損"], "axisLabel": {"fontSize": 10}},
        "yAxis": {"type": "value", "name": "筆數", "axisLabel": {"fontSize": 10}},
        "series": [{"type": "bar", "data": [
            {"value": stats["wins"], "itemStyle": {"color": "#059669"}},
            {"value": stats["losses"], "itemStyle": {"color": "#dc2626"}},
        ], "barWidth": "50%", "label": {"show": True, "position": "top", "fontSize": 11, "fontWeight": "bold"}}]
    })

# ─── 3. 盈虧統計 (Donut + center stats) ─────────────────────────
def chart_pnl_stats(stats):
    return _j({
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} 筆 ({d}%)"},
        "legend": {"bottom": 0, "textStyle": {"fontSize": 10}},
        "series": [{"type": "pie", "radius": ["55%", "75%"], "center": ["50%", "45%"],
                    "avoidLabelOverlap": False, "label": {"show": False},
                    "data": [{"value": stats["wins"], "name": "盈利", "itemStyle": {"color": "#059669"}},
                             {"value": stats["losses"], "name": "虧損", "itemStyle": {"color": "#dc2626"}}],
                    "emphasis": {"scale": False}}],
        "graphic": [{"type": "text", "left": "center", "top": "38%",
                     "style": {"text": f"{stats['wr']:.0f}%", "fontSize": 22, "fontWeight": "bold", "fill": "#1f2937"}},
                    {"type": "text", "left": "center", "top": "52%",
                     "style": {"text": "勝率", "fontSize": 11, "fill": "#6b7280"}}]
    })

# ─── 4. 品種盈虧表 (Table) ──────────────────────────────────────
def chart_symbol_table(stats):
    syms = sorted(stats["sym_pl"].items(), key=lambda x: abs(x[1]), reverse=True)[:12]
    if not syms: return "null"
    return _j({
        "tooltip": {"trigger": "axis", "formatter": "{b}: ${c}"},
        "grid": {"left": 80, "right": 80, "top": 15, "bottom": 20},
        "xAxis": {"type": "value", "axisLabel": {"formatter": "${{value}}"}},
        "yAxis": {"type": "category", "data": [s[0][:8].upper() for s in syms], "axisLabel": {"fontSize": 10}},
        "series": [{"type": "bar", "data": [{"value": s[1], "itemStyle": {"color": "#059669" if s[1]>=0 else "#dc2626"}} for s in syms],
                    "label": {"show": True, "position": "right", "fontSize": 9, "formatter": "${{c}}"}}]
    })

# ─── 5. 盈利曲線 (Per-trade profit scatter/line) ────────────────
def chart_profit_curve(stats):
    eq = stats["equity"]; dates = stats.get("equity_dates", [])
    n = len(eq)
    if n < 2: return "null"
    # Per-trade profit (diff of equity)
    profits = [eq[0]] + [eq[i] - eq[i-1] for i in range(1, n)]
    labels = dates if dates else list(range(n))
    return _j({
        "tooltip": {"trigger": "axis", "formatter": "{b}<br/>盈虧: ${c}"},
        "grid": {"left": 65, "right": 15, "top": 15, "bottom": 30},
        "xAxis": {"type": "category", "data": labels, "axisLabel": {"fontSize": 9, "rotate": 30, "interval": max(1, n//8)}},
        "yAxis": {"type": "value", "axisLabel": {"formatter": "${{value}}"}},
        "series": [{"type": "bar", "data": [{"value": v, "itemStyle": {"color": "#059669" if v>=0 else "#dc2626"}} for v in profits],
                    "barWidth": "60%"}]
    })

# ─── 6. 品種盈虧統計 (Symbol P&L grouped bar) ───────────────────
def chart_symbol_grouped(stats):
    syms = sorted(stats["sym_pl"].items(), key=lambda x: abs(x[1]), reverse=True)[:6]
    if not syms: return "null"
    names = [s[0][:6].upper() for s in syms]
    gains = [max(0, s[1]) for s in syms]
    losses = [min(0, s[1]) for s in syms]
    return _j({
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["盈利", "虧損"], "bottom": 0, "textStyle": {"fontSize": 10}},
        "grid": {"left": 50, "right": 10, "top": 15, "bottom": 35},
        "xAxis": {"type": "category", "data": names, "axisLabel": {"fontSize": 9}},
        "yAxis": {"type": "value", "axisLabel": {"formatter": "${{value}}"}},
        "series": [
            {"name": "盈利", "type": "bar", "stack": "total", "data": gains, "itemStyle": {"color": "#059669"}, "barWidth": "50%"},
            {"name": "虧損", "type": "bar", "stack": "total", "data": losses, "itemStyle": {"color": "#dc2626"}},
        ]
    })

# ─── 7. 盈虧分佈直方圖 ───────────────────────────────────────────
def chart_pnl_histogram(stats, trades):
    pls = [t["profit"] for t in trades]
    if not pls: return "null"
    bins = min(40, max(15, int(len(pls)**0.5)))
    pl_min, pl_max = min(pls), max(pls)
    if pl_min == pl_max: pl_max = pl_min + 1
    bin_w = (pl_max - pl_min) / bins
    hist = [0] * bins
    edges = [pl_min + i * bin_w for i in range(bins + 1)]
    for v in pls:
        idx = min(int((v - pl_min) / bin_w), bins - 1)
        hist[idx] += 1
    categories = [f"${edges[i]:.0f}" for i in range(bins)]
    return _j({
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 50, "right": 10, "top": 10, "bottom": 45},
        "xAxis": {"type": "category", "data": categories, "axisLabel": {"fontSize": 8, "rotate": 45, "interval": max(1, bins//6)}},
        "yAxis": {"type": "value", "name": "筆數", "axisLabel": {"fontSize": 10}},
        "series": [{"type": "bar", "data": [int(h) for h in hist], "itemStyle": {"color": "#2563eb"}, "barWidth": "90%"}]
    })

# ─── 8. 交易時段分佈 (Area) ─────────────────────────────────────
def chart_hourly_area(stats):
    hours = list(range(24)); counts = [stats["hourly"].get(h, 0) for h in hours]
    return _j({
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 45, "right": 10, "top": 15, "bottom": 25},
        "xAxis": {"type": "category", "data": [f"{h:02d}:00" for h in hours], "axisLabel": {"fontSize": 9, "interval": 5}},
        "yAxis": {"type": "value", "name": "筆數", "axisLabel": {"fontSize": 10}},
        "series": [{"type": "line", "data": counts, "smooth": True, "symbol": "none",
                    "lineStyle": {"color": "#2563eb", "width": 2},
                    "areaStyle": {"color": "rgba(37,99,235,0.15)"}}]
    })
