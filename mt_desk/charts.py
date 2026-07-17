"""Matplotlib charts — Linear-inspired dashboard style.

Design principles (from frontend-design skill):
  - Monitor surface: dense, glanceable, restrained tinted neutrals + one accent
  - One signature: subtle gradient fill on equity curve
  - Remove junk: no spines, minimal gridlines, clean typography
  - Color: single accent (#2563eb) + semantic green/red for P&L signals
"""
from __future__ import annotations
import base64, io, os, sys, warnings
from typing import Any
import matplotlib
matplotlib.use("Agg")
warnings.filterwarnings("ignore", message="Glyph.*missing from font")
import matplotlib.ticker as mticker
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyBboxPatch
import numpy as np

# ─── Font ───────────────────────────────────────────────────────
_FONT_PATH = None
if sys.platform == "win32":
    windir = os.environ.get("WINDIR", "C:/Windows")
    for fn in ["msyh.ttc", "msyhbd.ttc", "simhei.ttf"]:
        fp = os.path.join(windir, "Fonts", fn)
        if os.path.isfile(fp): _FONT_PATH = fp; break

def _f(size=9, bold=False):
    return FontProperties(fname=_FONT_PATH, size=size, weight="bold" if bold else "normal") if _FONT_PATH else FontProperties(size=size)

# ─── Linear-inspired palette ────────────────────────────────────
ACCENT  = "#2563eb"   # primary blue
GREEN   = "#059669"   # profit
RED     = "#dc2626"   # loss
ORANGE  = "#d97706"   # warning/secondary
PURPLE  = "#7c3aed"   # tertiary
TEAL    = "#0d9488"   # quaternary
GRAY    = "#9ca3af"   # muted text
LIGHT   = "#f3f4f6"   # subtle bg
WHITE   = "#ffffff"   # card bg
DARK    = "#111827"   # text
PALETTE = [ACCENT, GREEN, ORANGE, RED, PURPLE, TEAL, "#be185d", "#4f46e5", "#0891b2", "#b45309"]

# ─── Helpers ────────────────────────────────────────────────────
def _fig(w, h):
    return Figure(figsize=(w, h), dpi=120, facecolor=LIGHT, edgecolor="none")

def _ax(fig, title=""):
    ax = fig.add_subplot(111)
    ax.set_facecolor("none")
    for s in ax.spines.values(): s.set_visible(False)
    ax.tick_params(labelsize=7, colors=GRAY, length=0, pad=4)
    ax.grid(axis="y", color="#e5e7eb", linewidth=0.4, alpha=0.6)
    if title:
        ax.set_title(title, fontproperties=_f(11, True), color=DARK, pad=12, loc="left")
    return ax

def _b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor=LIGHT, edgecolor="none")
    buf.seek(0); return base64.b64encode(buf.read()).decode()

def _usd(): return mticker.FuncFormatter(lambda v, _: f"${v/1000:.0f}k" if abs(v)>=1000 else f"${v:,.0f}")

# ─── Charts ─────────────────────────────────────────────────────

def chart_equity(stats):
    eq = stats["equity"]; n = len(eq)
    if not eq: return ""
    fig = _fig(8, 3.4)
    ax = _ax(fig, "Net Equity & Drawdown")
    x = np.arange(n)
    color = GREEN if stats["total_pl"] >= 0 else RED
    # Gradient fill — the signature element
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("eq", [(color, 0.0), (color, 0.08), (color, 0.02)])
    ax.fill_between(x, eq, 0, alpha=0.06, color=color)
    ax.plot(x, eq, color=color, linewidth=1.6, solid_capstyle="round")
    ax.axhline(y=0, color="#e5e7eb", linewidth=0.5, linestyle="--")
    ax.yaxis.set_major_formatter(_usd())
    # Annotate start/end
    if n > 1:
        for idx, ha in [(0, "left"), (n-1, "right")]:
            ax.annotate(_usd().format_data(eq[idx]), (idx, eq[idx]),
                        textcoords="offset points", xytext=(10 if ha=="left" else -10, 8),
                        fontsize=7, color=DARK, ha=ha, fontproperties=_f(7))
    return _b64(fig)

def chart_symbol(stats):
    syms = sorted(stats["sym_pl"].items(), key=lambda x: abs(x[1]), reverse=True)[:10]
    if not syms: return ""
    fig = _fig(5, 3.0)
    ax = _ax(fig, "P&L by Symbol")
    labels = [s[0][:6].upper() for s in syms]
    values = [s[1] for s in syms]
    colors = [GREEN if v>=0 else RED for v in values]
    bars = ax.barh(labels, values, color=colors, height=0.5, alpha=0.9)
    for bar, v in zip(bars, values):
        offset = abs(v)*0.005
        ax.text(bar.get_width() + offset, bar.get_y()+bar.get_height()/2,
                _usd().format_data(v), va="center", fontsize=7, color=DARK, fontproperties=_f(7))
    ax.axvline(x=0, color="#e5e7eb", linewidth=0.5)
    ax.xaxis.set_major_formatter(_usd())
    return _b64(fig)

def chart_monthly(stats):
    monthly = stats["monthly"]
    if not monthly: return ""
    fig = _fig(8, 3.0)
    ax = _ax(fig, "Monthly P&L")
    months = list(monthly.keys()); values = list(monthly.values())
    colors = [GREEN if v>=0 else RED for v in values]
    bars = ax.bar(range(len(months)), values, color=colors, width=0.5, alpha=0.9, edgecolor=WHITE, linewidth=0.3)
    ax.set_xticks(range(len(months)))
    ax.set_xticklabels([m[2:] for m in months], fontsize=7, color=GRAY, fontproperties=_f(7))
    ax.axhline(y=0, color="#e5e7eb", linewidth=0.5)
    ax.yaxis.set_major_formatter(_usd())
    return _b64(fig)

def chart_winloss(stats):
    fig = _fig(4, 3.0)
    ax = _ax(fig, "Win/Loss")
    sizes = [stats["wins"], stats["losses"]]
    wedges, texts = ax.pie(sizes, labels=None, colors=[GREEN, RED],
                           startangle=90, wedgeprops={"alpha":0.9, "edgecolor":WHITE, "linewidth":2})
    ax.text(0, 0.08, f"{stats['wr']:.0f}%", ha="center", va="center", fontproperties=_f(22, True), color=DARK)
    ax.text(0, -0.12, "Win Rate", ha="center", va="center", fontproperties=_f(8), color=GRAY)
    # Legend below
    ax.legend([f"Wins {stats['wins']}", f"Losses {stats['losses']}"], loc="lower center",
              prop=_f(8), frameon=False, ncol=2, bbox_to_anchor=(0.5, -0.15))
    ax.axis("equal")
    return _b64(fig)

def chart_hourly(stats):
    fig = _fig(6, 2.6)
    ax = _ax(fig, "Trading Hours (UTC)")
    hours = list(range(24))
    counts = [stats["hourly"].get(h, 0) for h in hours]
    ax.bar(hours, counts, color=ACCENT, alpha=0.75, width=0.7, edgecolor=WHITE, linewidth=0.2)
    ax.set_xticks([0, 6, 12, 18, 23])
    ax.set_xticklabels(["00:00", "06:00", "12:00", "18:00", "23:00"], fontsize=7, color=GRAY, fontproperties=_f(7))
    return _b64(fig)

def chart_streaks(stats):
    wd, ld = stats["win_dist"], stats["loss_dist"]
    if not wd and not ld: return ""
    max_len = max(len(wd), len(ld), 1)
    fig = _fig(5, 2.8)
    ax = _ax(fig, "Consecutive Streaks")
    x = np.arange(max_len)
    bar_w = 0.3
    ax.bar(x - bar_w/2, wd + [0]*(max_len-len(wd)), bar_w, color=GREEN, alpha=0.85, label="Win", edgecolor=WHITE, linewidth=0.2)
    ax.bar(x + bar_w/2, ld + [0]*(max_len-len(ld)), bar_w, color=RED, alpha=0.85, label="Loss", edgecolor=WHITE, linewidth=0.2)
    ax.set_xticks(x)
    ax.set_xticklabels([str(i+1) for i in range(max_len)], fontsize=7, color=GRAY)
    ax.legend(prop=_f(7), frameon=False, loc="upper right")
    return _b64(fig)

def chart_equity_overlay(accounts):
    if not accounts: return ""
    fig = _fig(8, 3.4)
    ax = _ax(fig, "Equity Comparison")
    for i, acc in enumerate(accounts):
        eq = acc.get("stats", {}).get("equity", [])
        if not eq: continue
        c = PALETTE[i % len(PALETTE)]
        ax.plot(np.arange(len(eq)), eq, color=c, linewidth=1.5, label=acc.get("account", f"Acc{i+1}"))
    ax.axhline(y=0, color="#e5e7eb", linewidth=0.5, linestyle="--")
    ax.legend(prop=_f(7), frameon=False, loc="upper left")
    ax.yaxis.set_major_formatter(_usd())
    return _b64(fig)

def chart_monthly_compare(accounts):
    if not accounts: return ""
    all_months = set()
    for a in accounts: all_months.update(a.get("stats", {}).get("monthly", {}).keys())
    months = sorted(all_months)
    if not months: return ""
    fig = _fig(8, 3.0)
    ax = _ax(fig, "Monthly P&L Comparison")
    n = len(accounts); bar_w = 0.65 / n
    for i, acc in enumerate(accounts):
        mv = [acc.get("stats", {}).get("monthly", {}).get(m, 0) for m in months]
        offset = (i - (n-1)/2) * bar_w
        ax.bar(np.arange(len(months)) + offset, mv, bar_w,
               color=PALETTE[i % len(PALETTE)], alpha=0.85, label=acc.get("account", f"Acc{i+1}"),
               edgecolor=WHITE, linewidth=0.2)
    ax.set_xticks(range(len(months)))
    ax.set_xticklabels([m[2:] for m in months], fontsize=7, color=GRAY, fontproperties=_f(7))
    ax.axhline(y=0, color="#e5e7eb", linewidth=0.5)
    ax.legend(prop=_f(7), frameon=False, ncol=min(n, 3), loc="upper left")
    ax.yaxis.set_major_formatter(_usd())
    return _b64(fig)
