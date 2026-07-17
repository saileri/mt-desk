"""ECharts configs — 8 useful, non-redundant trading charts. Zero deps, pure Python."""
from __future__ import annotations
import json,math
from collections import defaultdict

def _j(obj): return json.dumps(obj, ensure_ascii=False, default=str)

# ─── 1. 淨值曲線 & 回撤 ─────────────────────────────────────────
def chart_equity(stats):
    eq = stats["equity"]; dates = stats.get("equity_dates", [])
    n = len(eq)
    if n < 2: return "null"
    labels = dates if dates else list(range(n))
    # Compute drawdown
    peak = 0; dd = []
    for v in eq:
        if v > peak: peak = v
        dd.append(round(peak - v, 2))
    color = "#059669" if stats["total_pl"] >= 0 else "#dc2626"
    return _j({
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["淨值", "回撤"], "top": 0, "textStyle": {"fontSize": 11}},
        "grid": {"left": 60, "right": 60, "top": 40, "bottom": 30},
        "xAxis": {"type": "category", "data": labels, "axisLabel": {"fontSize": 9, "rotate": 30, "interval": max(1, n//8)}},
        "yAxis": [
            {"type": "value", "name": "淨值 USD", "axisLabel": {"formatter": "${{value}}"}},
            {"type": "value", "name": "回撤 USD", "axisLabel": {"formatter": "${{value}}"}},
        ],
        "series": [
            {"name": "淨值", "type": "line", "data": eq, "yAxisIndex": 0,
             "smooth": True, "symbol": "none", "lineStyle": {"color": color, "width": 2},
             "areaStyle": {"color": "rgba(5,150,105,0.08)" if stats["total_pl"]>=0 else "rgba(220,38,38,0.08)"}},
            {"name": "回撤", "type": "line", "data": dd, "yAxisIndex": 1,
             "smooth": True, "symbol": "none", "lineStyle": {"color": "#f59e0b", "width": 1.5, "type": "dashed"},
             "areaStyle": {"color": "rgba(245,158,11,0.06)"}},
        ]
    })

# ─── 2. 月度盈虧 ─────────────────────────────────────────────────
def chart_monthly(stats):
    m = stats["monthly"]; months = list(m.keys()); vals = list(m.values())
    if not m: return "null"
    cum = []; running = 0
    for v in vals: running += v; cum.append(running)
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
             "label": {"show": True, "position": "top", "fontSize": 8, "formatter": "{c}", "color": "#64748b"}},
            {"name": "累計", "type": "line", "data": cum, "yAxisIndex": 1,
             "smooth": True, "symbol": "circle", "symbolSize": 4, "lineStyle": {"color": "#2563eb", "width": 2}},
        ]
    })

# ─── 3. 盈虧分佈 ─────────────────────────────────────────────────
def chart_pnl_dist(stats, trades):
    pls = [t["profit"] for t in trades]
    if not pls: return "null"
    bins = min(50, max(20, int(len(pls)**0.5)))
    pl_min, pl_max = min(pls), max(pls)
    if pl_min == pl_max: pl_max = pl_min + 1
    bin_w = (pl_max - pl_min) / bins
    hist = [0] * bins
    edges = [pl_min + i * bin_w for i in range(bins + 1)]
    for v in pls:
        idx = min(int((v - pl_min) / bin_w), bins - 1)
        hist[idx] += 1
    mean_pl = sum(pls) / len(pls)
    categories = [f"${edges[i]:.0f}" for i in range(bins)]
    return _j({
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 50, "right": 20, "top": 30, "bottom": 45},
        "xAxis": {"type": "category", "data": categories, "axisLabel": {"fontSize": 8, "rotate": 45, "interval": max(1, bins//6)}},
        "yAxis": {"type": "value", "name": "筆數", "axisLabel": {"fontSize": 10}},
        "series": [{"type": "bar", "data": [int(h) for h in hist],
                    "itemStyle": {"color": "#2563eb"}, "barWidth": "90%"}],
        "markLine": {"data": [{"xAxis": f"${mean_pl:.0f}", "label": {"formatter": f"均值 ${mean_pl:.0f}", "fontSize": 10}}],
                     "lineStyle": {"color": "#f59e0b", "type": "dashed"}}
    })

# ─── 4. 品種盈虧 ─────────────────────────────────────────────────
def chart_symbol(stats):
    syms = sorted(stats["sym_pl"].items(), key=lambda x: abs(x[1]), reverse=True)[:10]
    if not syms: return "null"
    return _j({
        "tooltip": {"trigger": "axis", "formatter": "{b}: ${c}"},
        "grid": {"left": 80, "right": 80, "top": 20, "bottom": 20},
        "xAxis": {"type": "value", "axisLabel": {"formatter": "${{value}}"}},
        "yAxis": {"type": "category", "data": [s[0][:8].upper() for s in syms], "axisLabel": {"fontSize": 10}},
        "series": [{"type": "bar", "data": [{"value": s[1], "itemStyle": {"color": "#059669" if s[1]>=0 else "#dc2626"}} for s in syms],
                    "label": {"show": True, "position": "right", "fontSize": 9, "formatter": "${{c}}", "color": "#64748b"}}]
    })

# ─── 5. 交易時段 ─────────────────────────────────────────────────
def chart_hourly(stats):
    hours = list(range(24)); counts = [stats["hourly"].get(h, 0) for h in hours]
    return _j({
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 45, "right": 10, "top": 20, "bottom": 25},
        "xAxis": {"type": "category", "data": [f"{h:02d}:00" for h in hours], "axisLabel": {"fontSize": 9, "interval": 5}},
        "yAxis": {"type": "value", "name": "筆數", "axisLabel": {"fontSize": 10}},
        "series": [{"type": "bar", "data": counts, "itemStyle": {"color": "#2563eb"}}]
    })

# ─── 6. 滾動勝率 (30-trade rolling) ─────────────────────────────
def chart_rolling_wr(stats, trades):
    """30-trade rolling win rate."""
    sorted_trades = sorted(trades, key=lambda t: t.get("open_time") or datetime.min)
    window = min(30, len(sorted_trades))
    if len(sorted_trades) < window: return "null"
    wr = []
    for i in range(window - 1, len(sorted_trades)):
        wins = sum(1 for j in range(i - window + 1, i + 1) if sorted_trades[j]["profit"] > 0)
        wr.append(round(wins / window * 100, 1))
    labels = [sorted_trades[i]["open_time"].strftime("%Y-%m-%d") if sorted_trades[i]["open_time"] else "" for i in range(window-1, len(sorted_trades))]
    return _j({
        "tooltip": {"trigger": "axis", "formatter": "{b}<br/>勝率: {c}%"},
        "legend": {"data": ["滾動勝率"], "top": 0},
        "grid": {"left": 55, "right": 20, "top": 35, "bottom": 30},
        "xAxis": {"type": "category", "data": labels, "axisLabel": {"fontSize": 9, "rotate": 30, "interval": max(1, len(labels)//6)}},
        "yAxis": {"type": "value", "name": "%", "min": 0, "max": 100, "axisLabel": {"formatter": "{value}%"}},
        "series": [{"name": "滾動勝率", "type": "line", "data": wr,
                    "smooth": True, "symbol": "none", "lineStyle": {"color": "#2563eb", "width": 2},
                    "areaStyle": {"color": "rgba(37,99,235,0.1)"},
                    "markLine": {"data": [{"yAxis": 50, "label": {"formatter": "50%", "fontSize": 9}}],
                                 "lineStyle": {"color": "#e5e7eb", "type": "dashed"}}}]
    })

# ─── 7. 最大回撤走勢 ─────────────────────────────────────────────
def chart_drawdown(stats):
    """How drawdown evolved over time."""
    eq = stats["equity"]; dates = stats.get("equity_dates", [])
    n = len(eq)
    if n < 2: return "null"
    peak = 0; dd_pct = []
    for v in eq:
        if v > peak: peak = v
        pct = round((peak - v) / peak * 100, 2) if peak > 0 else 0
        dd_pct.append(pct)
    labels = dates if dates else list(range(n))
    return _j({
        "tooltip": {"trigger": "axis", "formatter": "{b}<br/>回撤: {c}%"},
        "legend": {"data": ["回撤%"], "top": 0},
        "grid": {"left": 50, "right": 20, "top": 35, "bottom": 30},
        "xAxis": {"type": "category", "data": labels, "axisLabel": {"fontSize": 9, "rotate": 30, "interval": max(1, n//8)}},
        "yAxis": {"type": "value", "name": "%", "axisLabel": {"formatter": "{value}%"}, "inverse": True},
        "series": [{"name": "回撤%", "type": "line", "data": dd_pct,
                    "smooth": True, "symbol": "none",
                    "lineStyle": {"color": "#dc2626", "width": 2},
                    "areaStyle": {"color": "rgba(220,38,38,0.08)"}}]
    })

# ─── 8. 手數分佈 ─────────────────────────────────────────────────
def chart_volume_dist(stats, trades):
    """Distribution of trade volumes/lots."""
    vols = [t["volume"] for t in trades]
    if not vols: return "null"
    bins = min(20, max(8, int(len(set(vols))**0.5 * 2)))
    v_min, v_max = min(vols), max(vols)
    if v_min == v_max: v_max = v_min + 0.01
    bin_w = (v_max - v_min) / bins
    hist = [0] * bins
    labels = [f"{v_min + i*bin_w:.2f}" for i in range(bins)]
    for v in vols:
        idx = min(int((v - v_min) / bin_w), bins - 1)
        hist[idx] += 1
    return _j({
        "tooltip": {"trigger": "axis", "formatter": "手數 {b}: {c} 筆"},
        "grid": {"left": 45, "right": 10, "top": 30, "bottom": 45},
        "xAxis": {"type": "category", "data": labels, "axisLabel": {"fontSize": 8, "rotate": 30}},
        "yAxis": {"type": "value", "name": "筆數", "axisLabel": {"fontSize": 10}},
        "series": [{"type": "bar", "data": [int(h) for h in hist],
                    "itemStyle": {"color": "#7c3aed"}, "barWidth": "85%"}]
    })

# ─── Imports ─────────────────────────────────────────────────────
from datetime import datetime
