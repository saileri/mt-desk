"""Matplotlib chart generation — server-side rendering to base64 PNG.

Browser only displays <img> tags — no Chart.js / JS rendering.
"""
from __future__ import annotations

import base64
import glob
import io
import os
import sys
from typing import Any

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend

import matplotlib.font_manager as fm
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

# ─── CJK Font Setup ─────────────────────────────────────────────
def _setup_cjk():
    """Configure CJK fonts for Chinese chart labels."""
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", "C:/Windows")
        font_dir = os.path.join(windir, "Fonts")
        if os.path.isdir(font_dir):
            for fn in ["msyh.ttc", "msyhbd.ttc", "simsun.ttc", "simhei.ttf"]:
                fp = os.path.join(font_dir, fn)
                if os.path.isfile(fp):
                    try:
                        fm.fontManager.addfont(fp)
                    except Exception:
                        pass

    # Clear font cache (matplotlib >=3.10 removed get_cachedir)
    try:
        cache_dir = matplotlib.get_cachedir()
    except AttributeError:
        cache_dir = os.path.join(matplotlib.get_configdir(), "fontlist-v330.json")
        if not os.path.exists(cache_dir):
            cache_dir = None
    if cache_dir and os.path.isdir(cache_dir):
        for f in glob.glob(os.path.join(cache_dir, "fontlist*")):
            try:
                os.remove(f)
            except OSError:
                pass

    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = [
        "Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
        "WenQuanYi Micro Hei", "DejaVu Sans", "Arial", "sans-serif",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False

_setup_cjk()

# Brand colors
BLUE = "#2563eb"
GREEN = "#10b981"
RED = "#ef4444"
ORANGE = "#f59e0b"
TEXT = "#1f2937"
MUTED = "#6b7280"
BG = "#f8fafc"
COLORS_10 = [
    "#1e40af", "#047857", "#b45309", "#b91c1c", "#6d28d9",
    "#0f766e", "#9d174d", "#c2410c", "#4338ca", "#4d7c0f",
]


def _fig_to_b64(fig: Figure) -> str:
    """Convert matplotlib Figure to base64 PNG string."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def _usd_fmt():
    return FuncFormatter(lambda v, _: f"${v:,.0f}")


def _setup_ax(ax, title: str):
    """Common axis setup."""
    ax.set_title(title, fontsize=11, fontweight="bold", color=TEXT, pad=8)
    ax.tick_params(labelsize=7, colors=MUTED)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_facecolor(BG)


def chart_equity(stats: dict[str, Any]) -> str:
    """Equity curve with drawdown overlay."""
    eq = stats["equity"]
    if not eq:
        return ""

    fig = Figure(figsize=(8, 3.2), dpi=100, facecolor=BG)
    ax = fig.add_subplot(111)

    x = range(len(eq))
    color = GREEN if stats["total_pl"] >= 0 else RED
    ax.fill_between(x, eq, 0, alpha=0.08, color=color)
    ax.plot(x, eq, color=color, linewidth=1.2, label="Equity")
    ax.axhline(y=0, color="#e5e7eb", linewidth=0.5, linestyle="--")

    # Drawdown
    peak = 0.0
    dd = [0.0] * len(eq)
    for i, v in enumerate(eq):
        if v > peak:
            peak = v
        dd[i] = peak - v
    ax_dd = ax.twinx()
    ax_dd.fill_between(x, dd, 0, alpha=0.12, color=RED, label="DD")
    ax_dd.set_ylabel("DD ($)", fontsize=8, color=MUTED)
    ax_dd.tick_params(labelsize=7, colors=MUTED)
    ax_dd.spines["top"].set_visible(False)

    _setup_ax(ax, "净值曲线 & 回撤")
    ax.yaxis.set_major_formatter(_usd_fmt())
    return _fig_to_b64(fig)


def chart_symbol(stats: dict[str, Any]) -> str:
    """Horizontal bar chart of symbol P&L."""
    syms = sorted(stats["sym_pl"].items(), key=lambda x: x[1], reverse=True)[-12:]
    if not syms:
        return ""

    fig = Figure(figsize=(5, 3), dpi=100, facecolor=BG)
    ax = fig.add_subplot(111)
    labels = [s[0].upper()[:8] for s in syms]
    values = [s[1] for s in syms]
    colors = [GREEN if v >= 0 else RED for v in values]
    ax.barh(labels, values, color=colors, height=0.6, alpha=0.85)
    ax.axvline(x=0, color="#e5e7eb", linewidth=0.5)
    ax.xaxis.set_major_formatter(_usd_fmt())
    _setup_ax(ax, "品种盈亏")
    return _fig_to_b64(fig)


def chart_monthly(stats: dict[str, Any]) -> str:
    """Monthly P&L bar chart."""
    monthly = stats["monthly"]
    if not monthly:
        return ""

    fig = Figure(figsize=(8, 2.8), dpi=100, facecolor=BG)
    ax = fig.add_subplot(111)
    months = list(monthly.keys())
    values = list(monthly.values())
    colors = [GREEN if v >= 0 else RED for v in values]
    ax.bar(range(len(months)), values, color=colors, width=0.6, alpha=0.85)
    ax.set_xticks(range(len(months)))
    ax.set_xticklabels(months, rotation=45, ha="right", fontsize=7, color=MUTED)
    ax.axhline(y=0, color="#e5e7eb", linewidth=0.5)
    ax.yaxis.set_major_formatter(_usd_fmt())
    _setup_ax(ax, "月度盈亏")
    return _fig_to_b64(fig)


def chart_winloss(stats: dict[str, Any]) -> str:
    """Win/Loss pie chart."""
    fig = Figure(figsize=(4, 3), dpi=100, facecolor=BG)
    ax = fig.add_subplot(111)
    sizes = [stats["wins"], stats["losses"]]
    labels = [f'Wins ({stats["wins"]})', f'Losses ({stats["losses"]})']
    ax.pie(sizes, labels=labels, colors=[GREEN, RED], autopct="%1.0f%%",
           startangle=90, textprops={"fontsize": 9, "color": TEXT},
           wedgeprops={"alpha": 0.85, "edgecolor": "white", "linewidth": 1})
    _setup_ax(ax, "盈亏分布")
    ax.axis("equal")
    return _fig_to_b64(fig)


def chart_hourly(stats: dict[str, Any]) -> str:
    """Trading hour distribution."""
    fig = Figure(figsize=(6, 2.5), dpi=100, facecolor=BG)
    ax = fig.add_subplot(111)
    hours = list(range(24))
    counts = [stats["hourly"].get(h, 0) for h in hours]
    ax.bar(hours, counts, color=BLUE, alpha=0.7, width=0.7)
    ax.set_xlabel("Hour (UTC)", fontsize=8, color=MUTED)
    ax.set_ylabel("Trades", fontsize=8, color=MUTED)
    _setup_ax(ax, "交易时段分布")
    return _fig_to_b64(fig)


def chart_streaks(stats: dict[str, Any]) -> str:
    """Consecutive win/loss streak distribution."""
    wd = stats["win_dist"]
    ld = stats["loss_dist"]
    if not wd and not ld:
        return ""

    max_len = max(len(wd), len(ld), 1)
    fig = Figure(figsize=(5, 2.8), dpi=100, facecolor=BG)
    ax = fig.add_subplot(111)

    x = range(1, max_len + 1)
    wd_padded = wd + [0] * (max_len - len(wd))
    ld_padded = ld + [0] * (max_len - len(ld))

    bar_w = 0.35
    ax.bar([i - bar_w / 2 for i in x], wd_padded, bar_w,
           color=GREEN, alpha=0.75, label="连续盈利")
    ax.bar([i + bar_w / 2 for i in x], ld_padded, bar_w,
           color=RED, alpha=0.75, label="连续亏损")
    ax.set_xticks(list(x))
    ax.legend(fontsize=8, loc="upper right")
    _setup_ax(ax, "连续盈利/亏损分布")
    ax.set_ylabel("次数", fontsize=8, color=MUTED)
    return _fig_to_b64(fig)


def chart_equity_overlay(accounts: list[dict]) -> str:
    """Overlay equity curves from multiple accounts."""
    if not accounts:
        return ""

    fig = Figure(figsize=(8, 3.2), dpi=100, facecolor=BG)
    ax = fig.add_subplot(111)

    for i, acc in enumerate(accounts):
        label = acc.get("account", f"Acc {i + 1}")
        eq = acc.get("stats", {}).get("equity", [])
        if not eq:
            continue
        color = COLORS_10[i % len(COLORS_10)]
        x = range(len(eq))
        ax.plot(x, eq, color=color, linewidth=1.2, label=label, alpha=0.85)

    ax.axhline(y=0, color="#e5e7eb", linewidth=0.5, linestyle="--")
    _setup_ax(ax, "净值曲线对比")
    ax.legend(fontsize=8, loc="upper left")
    ax.yaxis.set_major_formatter(_usd_fmt())
    return _fig_to_b64(fig)


def chart_monthly_compare(accounts: list[dict]) -> str:
    """Grouped bar chart of monthly P&L across accounts."""
    if not accounts:
        return ""

    # Collect all months
    all_months: set[str] = set()
    for acc in accounts:
        m = acc.get("stats", {}).get("monthly", {})
        all_months.update(m.keys())
    months = sorted(all_months)
    if not months:
        return ""

    fig = Figure(figsize=(8, 3), dpi=100, facecolor=BG)
    ax = fig.add_subplot(111)

    n_acc = len(accounts)
    bar_w = 0.8 / n_acc
    for i, acc in enumerate(accounts):
        label = acc.get("account", f"Acc {i + 1}")
        monthly = acc.get("stats", {}).get("monthly", {})
        values = [monthly.get(m, 0) for m in months]
        offset = (i - (n_acc - 1) / 2) * bar_w
        x = [j + offset for j in range(len(months))]
        ax.bar(x, values, bar_w, color=COLORS_10[i % len(COLORS_10)],
               alpha=0.8, label=label)

    ax.set_xticks(range(len(months)))
    ax.set_xticklabels(months, rotation=45, ha="right", fontsize=7, color=MUTED)
    ax.axhline(y=0, color="#e5e7eb", linewidth=0.5)
    _setup_ax(ax, "月度盈亏对比")
    ax.legend(fontsize=7, loc="upper left", ncol=min(n_acc, 3))
    ax.yaxis.set_major_formatter(_usd_fmt())
    return _fig_to_b64(fig)
