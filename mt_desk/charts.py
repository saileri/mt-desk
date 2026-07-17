"""ECharts config generator — browser-native rendering, no matplotlib.

Apache ECharts (66.8k stars) — enterprise-grade interactive charts.
X-axis uses real dates. Fonts rendered by browser (crisp, native).
"""
from __future__ import annotations
import json
from collections import defaultdict
from typing import Any
from datetime import datetime
import numpy as np

def _j(obj): return json.dumps(obj, ensure_ascii=False, default=str)

# ─── 1. 淨值曲線 & 回撤 ─────────────────────────────────────────
def chart_equity(stats):
    eq = stats["equity"]; dates = stats.get("equity_dates", [])
    n = len(eq)
    if n < 2: return "null"
    # Build date labels or use indices
    labels = dates if dates else list(range(n))
    # Max drawdown
    peak = 0; dd = []
    for v in eq:
        if v > peak: peak = v
        dd.append(peak - v)
    return _j({
        "tooltip": {"trigger": "axis", "formatter": "{b}<br/>淨值: ${c}"},
        "legend": {"data": ["淨值"], "top": 0, "textStyle": {"fontSize": 11}},
        "grid": {"left": 60, "right": 20, "top": 40, "bottom": 30},
        "xAxis": {"type": "category", "data": labels, "axisLabel": {"fontSize": 10, "rotate": 30}},
        "yAxis": {"type": "value", "axisLabel": {"formatter": "${{value}}"}},
        "series": [{
            "name": "淨值", "type": "line", "data": eq,
            "smooth": True, "symbol": "none",
            "lineStyle": {"color": "#059669" if stats["total_pl"] >= 0 else "#dc2626", "width": 2},
            "areaStyle": {"color": {"type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                "colorStops": [{"offset": 0, "color": "rgba(5,150,105,0.15)" if stats["total_pl"] >= 0 else "rgba(220,38,38,0.15)"},
                               {"offset": 1, "color": "rgba(5,150,105,0)" if stats["total_pl"] >= 0 else "rgba(220,38,38,0)"}]}},
        }]
    })

# ─── 2. 月度盈虧 ─────────────────────────────────────────────────
def chart_monthly(stats):
    m = stats["monthly"]; months = list(m.keys()); vals = list(m.values())
    if not m: return "null"
    cum = list(np.cumsum(vals))
    return _j({
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["月度盈虧", "累計"], "top": 0, "textStyle": {"fontSize": 11}},
        "grid": {"left": 60, "right": 60, "top": 40, "bottom": 30},
        "xAxis": {"type": "category", "data": [m[2:] for m in months], "axisLabel": {"fontSize": 10}},
        "yAxis": [
            {"type": "value", "name": "USD", "axisLabel": {"formatter": "${{value}}"}},
            {"type": "value", "name": "累計 USD", "axisLabel": {"formatter": "${{value}}"}},
        ],
        "series": [
            {"name": "月度盈虧", "type": "bar", "data": vals, "yAxisIndex": 0,
             "itemStyle": {"color": {"type": "piecewise",
                "pieces": [{"lt": 0, "color": "#dc2626"}, {"gte": 0, "color": "#059669"}]}},
             "label": {"show": True, "position": "top", "fontSize": 9,
                       "formatter": "{c}", "color": "#64748b"}},
            {"name": "累計", "type": "line", "data": cum, "yAxisIndex": 1,
             "smooth": True, "symbol": "circle", "symbolSize": 4,
             "lineStyle": {"color": "#2563eb", "width": 2}},
        ]
    })

# ─── 3. 盈虧分佈 ─────────────────────────────────────────────────
def chart_pnl_dist(stats, trades):
    pls = [t["profit"] for t in trades]
    if not pls: return "null"
    bins = min(50, max(20, int(len(pls)**0.5)))
    hist, edges = np.histogram(pls, bins=bins)
    mean_pl = np.mean(pls)
    categories = [f"${edges[i]:.0f}" for i in range(len(edges)-1)]
    return _j({
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 50, "right": 20, "top": 30, "bottom": 40},
        "xAxis": {"type": "category", "data": categories, "axisLabel": {"fontSize": 8, "rotate": 45, "interval": max(1, bins//6)}},
        "yAxis": {"type": "value", "name": "筆數", "axisLabel": {"fontSize": 10}},
        "series": [{
            "type": "bar", "data": [int(h) for h in hist],
            "itemStyle": {"color": "#2563eb", "borderRadius": [2, 2, 0, 0]},
        }],
        "markLine": {"data": [{"xAxis": f"${mean_pl:.0f}", "label": {"formatter": f"均值 ${mean_pl:.0f}", "fontSize": 10}}],
                     "lineStyle": {"color": "#f59e0b", "type": "dashed"}}
    })

# ─── 4. 品種盈虧 ─────────────────────────────────────────────────
def chart_symbol(stats):
    syms = sorted(stats["sym_pl"].items(), key=lambda x: abs(x[1]), reverse=True)[:10]
    if not syms: return "null"
    return _j({
        "tooltip": {"trigger": "axis", "formatter": "{b}: ${c}"},
        "grid": {"left": 80, "right": 20, "top": 20, "bottom": 20},
        "xAxis": {"type": "value", "axisLabel": {"formatter": "${{value}}"}},
        "yAxis": {"type": "category", "data": [s[0][:8].upper() for s in syms], "axisLabel": {"fontSize": 10}},
        "series": [{
            "type": "bar", "data": [{"value": s[1], "itemStyle": {"color": "#059669" if s[1]>=0 else "#dc2626"}} for s in syms],
            "label": {"show": True, "position": "right", "fontSize": 9, "formatter": "${{c}}", "color": "#64748b"},
        }]
    })

# ─── 5. 交易時段 ─────────────────────────────────────────────────
def chart_hourly(stats):
    hours = list(range(24)); counts = [stats["hourly"].get(h, 0) for h in hours]
    return _j({
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 45, "right": 10, "top": 20, "bottom": 25},
        "xAxis": {"type": "category", "data": [f"{h:02d}:00" for h in hours], "axisLabel": {"fontSize": 9, "interval": 5}},
        "yAxis": {"type": "value", "name": "筆數", "axisLabel": {"fontSize": 10}},
        "series": [{"type": "bar", "data": counts, "itemStyle": {"color": "#2563eb", "borderRadius": [3, 3, 0, 0]}}]
    })

# ─── 6. 累計盈虧走勢 ─────────────────────────────────────────────
def chart_cumulative(stats):
    eq = stats["equity"]; dates = stats.get("equity_dates", [])
    n = len(eq)
    if n < 2: return "null"
    labels = dates if dates else list(range(n))
    color = "#059669" if eq[-1] >= 0 else "#dc2626"
    return _j({
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["累計盈虧"], "top": 0},
        "grid": {"left": 60, "right": 20, "top": 35, "bottom": 30},
        "xAxis": {"type": "category", "data": labels, "axisLabel": {"fontSize": 10, "rotate": 30}},
        "yAxis": {"type": "value", "axisLabel": {"formatter": "${{value}}"}},
        "series": [{
            "name": "累計盈虧", "type": "line", "data": eq,
            "smooth": True, "symbol": "none",
            "lineStyle": {"color": color, "width": 2},
            "areaStyle": {"color": "rgba(5,150,105,0.12)" if eq[-1]>=0 else "rgba(220,38,38,0.12)"},
        }]
    })
