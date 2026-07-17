"""Matplotlib charts — PPT-ready styling, Microsoft YaHei font.

Font loading: Uses FontProperties(fname=path) directly to bypass
matplotlib's font cache issues in PyInstaller builds.
"""
from __future__ import annotations
import base64, io, os, sys, warnings
from typing import Any
import matplotlib
matplotlib.use("Agg")
# Suppress CJK font warnings on Linux (fine on Windows with msyh.ttc)
warnings.filterwarnings("ignore", message="Glyph.*missing from font")
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter

# ─── Font ───────────────────────────────────────────────────────
_FONT_PATH = None
if sys.platform == "win32":
    windir = os.environ.get("WINDIR", "C:/Windows")
    for fn in ["msyh.ttc", "msyhbd.ttc", "simhei.ttf", "simsun.ttc"]:
        fp = os.path.join(windir, "Fonts", fn)
        if os.path.isfile(fp):
            _FONT_PATH = fp
            break

def _font(size: int = 9, bold: bool = False) -> FontProperties:
    if _FONT_PATH:
        return FontProperties(fname=_FONT_PATH, size=size, weight="bold" if bold else "normal")
    return FontProperties(size=size)

def _usd_fmt():
    return FuncFormatter(lambda v, _: f"${v:,.0f}")

# ─── PPT-ready colors ───────────────────────────────────────────
C = {
    "blue":   "#2563eb", "dblue":  "#1e40af",
    "green":  "#059669", "dgreen": "#065f46",
    "red":    "#dc2626", "dred":   "#991b1b",
    "orange": "#d97706", "cyan":   "#0891b2",
    "purple": "#7c3aed", "gray":   "#6b7280",
    "lgray":  "#e5e7eb", "bg":     "#fafafa",
    "text":   "#1f2937",
}
PALETTE = ["#2563eb","#059669","#d97706","#dc2626","#7c3aed","#0891b2","#be185d","#4f46e5","#0d9488","#b45309"]

def _fig(w: float, h: float) -> Figure:
    return Figure(figsize=(w, h), dpi=120, facecolor=C["bg"], edgecolor="none")

def _ax(fig: Figure, title: str = ""):
    ax = fig.add_subplot(111)
    ax.set_facecolor(C["bg"])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(labelsize=7, colors=C["gray"])
    ax.grid(axis="y", color=C["lgray"], linewidth=0.5, alpha=0.7)
    if title:
        ax.set_title(title, fontproperties=_font(12, True), color=C["text"], pad=10)
    return ax

def _b64(fig: Figure) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor=C["bg"])
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()

# ─── Charts ─────────────────────────────────────────────────────

def chart_equity(stats: dict[str, Any]) -> str:
    eq = stats["equity"]
    if not eq: return ""
    fig = _fig(8, 3.2)
    ax = _ax(fig, "净值曲线 & 回撤")
    x = range(len(eq))
    color = C["green"] if stats["total_pl"] >= 0 else C["red"]
    ax.fill_between(x, eq, 0, alpha=0.08, color=color)
    ax.plot(x, eq, color=color, linewidth=1.5)
    ax.axhline(y=0, color=C["lgray"], linewidth=0.5, linestyle="--")
    ax.yaxis.set_major_formatter(_usd_fmt())
    # Annotate start & end
    if len(eq) > 1:
        ax.annotate(f"${eq[0]:,.0f}", (0, eq[0]), textcoords="offset points",
                    xytext=(8, 6), fontsize=7, color=C["gray"])
        ax.annotate(f"${eq[-1]:,.0f}", (len(eq)-1, eq[-1]), textcoords="offset points",
                    xytext=(-8, 6), fontsize=7, color=C["gray"], ha="right")
    return _b64(fig)

def chart_symbol(stats: dict[str, Any]) -> str:
    syms = sorted(stats["sym_pl"].items(), key=lambda x: x[1], reverse=True)[-10:]
    if not syms: return ""
    fig = _fig(5, 3)
    ax = _ax(fig, "品种盈亏 (Top 10)")
    labels = [s[0][:6].upper() for s in syms]
    values = [s[1] for s in syms]
    colors = [C["green"] if v >= 0 else C["red"] for v in values]
    bars = ax.barh(labels, values, color=colors, height=0.55, alpha=0.9)
    for bar, v in zip(bars, values):
        ax.text(bar.get_width() + (max(values)-min(values))*0.01, bar.get_y()+bar.get_height()/2,
                f"${v:+,.0f}", va="center", fontsize=7, color=C["gray"])
    ax.axvline(x=0, color=C["lgray"], linewidth=0.5)
    ax.xaxis.set_major_formatter(_usd_fmt())
    return _b64(fig)

def chart_monthly(stats: dict[str, Any]) -> str:
    monthly = stats["monthly"]
    if not monthly: return ""
    fig = _fig(8, 2.8)
    ax = _ax(fig, "月度盈亏")
    months = list(monthly.keys())
    values = list(monthly.values())
    colors = [C["green"] if v >= 0 else C["red"] for v in values]
    bars = ax.bar(range(len(months)), values, color=colors, width=0.55, alpha=0.9, edgecolor="white", linewidth=0.5)
    ax.set_xticks(range(len(months)))
    ax.set_xticklabels([m[2:] for m in months], rotation=0, fontsize=7, color=C["gray"])
    ax.axhline(y=0, color=C["lgray"], linewidth=0.5)
    ax.yaxis.set_major_formatter(_usd_fmt())
    for bar, v in zip(bars, values):
        y = bar.get_height()
        ax.text(bar.get_x()+bar.get_width()/2, y+(max(abs(min(values)),abs(max(values)))*0.03),
                f"${v:+,.0f}", ha="center", fontsize=6, color=C["gray"])
    return _b64(fig)

def chart_winloss(stats: dict[str, Any]) -> str:
    fig = _fig(4, 3)
    ax = _ax(fig, "盈亏分布")
    sizes = [stats["wins"], stats["losses"]]
    labels = [f"盈利 {stats['wins']}笔", f"亏损 {stats['losses']}笔"]
    wedges, texts = ax.pie(sizes, labels=labels, colors=[C["green"],C["red"]],
                           startangle=90, wedgeprops={"alpha":0.9,"edgecolor":"white","linewidth":1.5})
    for t in texts:
        t.set_fontproperties(_font(9))
    # Center text
    ax.text(0, 0, f"{stats['wr']:.0f}%", ha="center", va="center",
            fontproperties=_font(18, True), color=C["text"])
    ax.text(0, -0.18, "胜率", ha="center", va="center",
            fontproperties=_font(8), color=C["gray"])
    ax.axis("equal")
    return _b64(fig)

def chart_hourly(stats: dict[str, Any]) -> str:
    fig = _fig(6, 2.5)
    ax = _ax(fig, "交易时段分布 (UTC)")
    hours = list(range(24))
    counts = [stats["hourly"].get(h, 0) for h in hours]
    ax.bar(hours, counts, color=C["blue"], alpha=0.75, width=0.7, edgecolor="white", linewidth=0.3)
    ax.set_xticks([0, 6, 12, 18, 23])
    ax.set_xticklabels(["00:00", "06:00", "12:00", "18:00", "23:00"], fontsize=7, color=C["gray"])
    return _b64(fig)

def chart_streaks(stats: dict[str, Any]) -> str:
    wd, ld = stats["win_dist"], stats["loss_dist"]
    if not wd and not ld: return ""
    max_len = max(len(wd), len(ld), 1)
    fig = _fig(5, 2.8)
    ax = _ax(fig, "连续盈利/亏损")
    x = range(1, max_len+1)
    bar_w = 0.3
    ax.bar([i-bar_w/2 for i in x], wd+[0]*(max_len-len(wd)), bar_w, color=C["green"], alpha=0.85, label="盈利")
    ax.bar([i+bar_w/2 for i in x], ld+[0]*(max_len-len(ld)), bar_w, color=C["red"], alpha=0.85, label="亏损")
    ax.set_xticks(list(x))
    ax.legend(prop=_font(8), frameon=False)
    return _b64(fig)

def chart_equity_overlay(accounts: list[dict]) -> str:
    if not accounts: return ""
    fig = _fig(8, 3.2)
    ax = _ax(fig, "净值曲线对比")
    for i, acc in enumerate(accounts):
        eq = acc.get("stats", {}).get("equity", [])
        if not eq: continue
        label = acc.get("account", f"Acc{i+1}")
        ax.plot(range(len(eq)), eq, color=PALETTE[i%len(PALETTE)], linewidth=1.5, label=label)
    ax.axhline(y=0, color=C["lgray"], linewidth=0.5, linestyle="--")
    ax.legend(prop=_font(8), frameon=False)
    ax.yaxis.set_major_formatter(_usd_fmt())
    return _b64(fig)

def chart_monthly_compare(accounts: list[dict]) -> str:
    if not accounts: return ""
    all_months = set()
    for acc in accounts:
        all_months.update(acc.get("stats", {}).get("monthly", {}).keys())
    months = sorted(all_months)
    if not months: return ""
    fig = _fig(8, 3)
    ax = _ax(fig, "月度盈亏对比")
    n = len(accounts)
    bar_w = 0.7 / n
    for i, acc in enumerate(accounts):
        monthly = acc.get("stats", {}).get("monthly", {})
        vals = [monthly.get(m, 0) for m in months]
        offset = (i-(n-1)/2)*bar_w
        ax.bar([j+offset for j in range(len(months))], vals, bar_w,
               color=PALETTE[i%len(PALETTE)], alpha=0.85,
               label=acc.get("account", f"Acc{i+1}"))
    ax.set_xticks(range(len(months)))
    ax.set_xticklabels([m[2:] for m in months], fontsize=7, color=C["gray"])
    ax.axhline(y=0, color=C["lgray"], linewidth=0.5)
    ax.legend(prop=_font(7), frameon=False, ncol=min(n, 3))
    ax.yaxis.set_major_formatter(_usd_fmt())
    return _b64(fig)
