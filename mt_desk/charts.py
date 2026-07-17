"""Matplotlib charts — focused, clean, intuitive. 150 DPI, Traditional Chinese, annotated values.

Only 6 chart types — each answers ONE question:
  1. 淨值曲線 & 回撤 — How did equity change over time?
  2. 月度盈虧 — Which months made/lost money?
  3. 盈虧分佈 — What's the spread of P&L per trade?
  4. 品種盈虧 — Which symbols perform best?
  5. 交易時段 — When do trades happen?
  6. 累計盈虧 — How does cumulative P&L build trade by trade?
"""
from __future__ import annotations
import base64,io,os,sys,warnings
from typing import Any
import matplotlib;matplotlib.use("Agg")
warnings.filterwarnings("ignore",message="Glyph.*missing from font")
import matplotlib.ticker as mticker
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
import numpy as np

# ─── Font ───────────────────────────────────────────────────────
_FONT=None
if sys.platform=="win32":
    for fn in["msyh.ttc","msyhbd.ttc","simhei.ttf"]:
        fp=os.path.join(os.environ.get("WINDIR","C:/Windows"),"Fonts",fn)
        if os.path.isfile(fp):_FONT=fp;break
def F(s=9,b=False):return FontProperties(fname=_FONT,size=s,weight="bold" if b else"normal") if _FONT else FontProperties(size=s)

# ─── Colors ─────────────────────────────────────────────────────
BLUE="#2563eb";GREEN="#059669";RED="#dc2626";GRAY="#9ca3af";LGRAY="#e5e7eb"
DARK="#111827";BG="#f0f2f5";WHITE="#ffffff"
PALETTE=[BLUE,GREEN,"#d97706",RED,"#7c3aed","#0891b2","#be185d","#4f46e5","#0d9488","#b45309"]

def _fig(w,h):return Figure(figsize=(w,h),dpi=150,facecolor=BG)
def _ax(fig,title=""):
    ax=fig.add_subplot(111);ax.set_facecolor("none")
    for s in ax.spines.values():s.set_visible(False)
    ax.tick_params(labelsize=8,colors=GRAY,length=0,pad=4)
    if title:ax.set_title(title,fontproperties=F(12,True),color=DARK,pad=14,loc="left")
    return ax
def _b64(fig):
    buf=io.BytesIO();fig.savefig(buf,format="png",dpi=150,bbox_inches="tight",facecolor=BG,edgecolor="none")
    buf.seek(0);return base64.b64encode(buf.read()).decode()
_fmt_usd=lambda:mticker.FuncFormatter(lambda v,_:f"${v/1000:.0f}k" if abs(v)>=10000 else f"${v:,.0f}")

# ─── 1. Equity & Drawdown ───────────────────────────────────────
def chart_equity(stats):
    eq=stats["equity"];n=len(eq)
    if n<2:return""
    fig=_fig(9,3.8);ax=_ax(fig,"淨值曲線 & 回撤")
    x=np.arange(n);color=GREEN if stats["total_pl"]>=0 else RED
    ax.fill_between(x,eq,0,alpha=0.06,color=color)
    ax.plot(x,eq,color=color,linewidth=1.8,solid_capstyle="round")
    ax.axhline(y=0,color=LGRAY,linewidth=0.5,linestyle="--")
    ax.set_ylabel("USD",fontproperties=F(8),color=GRAY)
    ax.set_xlabel("交易序號",fontproperties=F(8),color=GRAY)
    ax.yaxis.set_major_formatter(_fmt_usd())
    # Start/end annotations
    for idx,ha in[(0,"left"),(n-1,"right")]:
        ax.annotate(_fmt_usd().format_data(eq[idx]),(idx,eq[idx]),
            textcoords="offset points",xytext=(12 if ha=="left" else-12,8),
            fontsize=8,color=DARK,ha=ha,fontproperties=F(8))
    return _b64(fig)

# ─── 2. Monthly P&L ─────────────────────────────────────────────
def chart_monthly(stats):
    m=stats["monthly"]
    if not m:return""
    fig=_fig(9,3.4);ax=_ax(fig,"月度盈虧 (USD)")
    months=list(m.keys());vals=list(m.values())
    colors=[GREEN if v>=0 else RED for v in vals]
    bars=ax.bar(range(len(months)),vals,color=colors,width=0.5,alpha=0.9,edgecolor=WHITE,linewidth=0.3)
    ax.set_xticks(range(len(months)))
    ax.set_xticklabels([m[2:] for m in months],fontsize=7,color=GRAY,fontproperties=F(7))
    ax.axhline(y=0,color=LGRAY,linewidth=0.5)
    ax.set_ylabel("USD",fontproperties=F(8),color=GRAY)
    ax.yaxis.set_major_formatter(_fmt_usd())
    # Value labels on bars
    for bar,v in zip(bars,vals):
        y=v;offset=abs(v)*0.03+max(abs(min(vals)),abs(max(vals)))*0.01
        ax.text(bar.get_x()+bar.get_width()/2,y+offset if v>=0 else y-offset,
            _fmt_usd().format_data(v),ha="center",fontsize=7,color=DARK,fontproperties=F(7))
    return _b64(fig)

# ─── 3. P&L Distribution ────────────────────────────────────────
def chart_pnl_dist(stats,trades):
    """Histogram of trade P&L values."""
    pls=[t["profit"] for t in trades]
    if not pls:return""
    fig=_fig(7,3.2);ax=_ax(fig,"盈虧分佈 (USD)")
    # Auto-bin with Freedman-Diaconis or just 40 bins
    bins=min(50,max(15,int(len(pls)**0.5)))
    n,bins,patches=ax.hist(pls,bins=bins,color=BLUE,alpha=0.8,edgecolor=WHITE,linewidth=0.3)
    ax.axvline(x=0,color=LGRAY,linewidth=0.5,linestyle="--")
    ax.set_xlabel("USD",fontproperties=F(8),color=GRAY)
    ax.set_ylabel("交易筆數",fontproperties=F(8),color=GRAY)
    ax.xaxis.set_major_formatter(_fmt_usd())
    # Annotate mean
    mean_pl=np.mean(pls)
    ax.axvline(x=mean_pl,color=RED,linewidth=1,linestyle="-",alpha=0.6)
    ax.text(mean_pl,max(n)*0.95,f" 均值 ${mean_pl:,.0f}",fontsize=8,color=RED,fontproperties=F(8),va="top")
    return _b64(fig)

# ─── 4. Symbol P&L ──────────────────────────────────────────────
def chart_symbol(stats):
    syms=sorted(stats["sym_pl"].items(),key=lambda x:abs(x[1]),reverse=True)[:8]
    if not syms:return""
    fig=_fig(5,3);ax=_ax(fig,"品種盈虧 (USD)")
    labels=[s[0][:6].upper() for s in syms];vals=[s[1] for s in syms]
    colors=[GREEN if v>=0 else RED for v in vals]
    bars=ax.barh(labels,vals,color=colors,height=0.5,alpha=0.9)
    for bar,v in zip(bars,vals):
        ax.text(bar.get_width()+abs(v)*0.005,bar.get_y()+bar.get_height()/2,
            _fmt_usd().format_data(v),va="center",fontsize=8,color=DARK,fontproperties=F(8))
    ax.axvline(x=0,color=LGRAY,linewidth=0.5)
    ax.set_xlabel("USD",fontproperties=F(8),color=GRAY);ax.xaxis.set_major_formatter(_fmt_usd())
    return _b64(fig)

# ─── 5. Trading Hours ───────────────────────────────────────────
def chart_hourly(stats):
    fig=_fig(6,2.8);ax=_ax(fig,"交易時段分佈 (UTC)")
    hours=list(range(24));counts=[stats["hourly"].get(h,0) for h in hours]
    ax.bar(hours,counts,color=BLUE,alpha=0.75,width=0.7,edgecolor=WHITE,linewidth=0.2)
    ax.set_xticks([0,6,12,18,23])
    ax.set_xticklabels(["00:00","06:00","12:00","18:00","23:00"],fontsize=7,color=GRAY,fontproperties=F(7))
    ax.set_ylabel("交易筆數",fontproperties=F(8),color=GRAY)
    ax.set_xlabel("UTC 時段",fontproperties=F(8),color=GRAY)
    return _b64(fig)

# ─── 6. Cumulative P&L by Trade ─────────────────────────────────
def chart_cumulative(stats):
    """How cumulative P&L builds trade by trade."""
    eq=stats["equity"];n=len(eq)
    if n<2:return""
    fig=_fig(9,3.2);ax=_ax(fig,"累計盈虧走勢 (USD)")
    x=np.arange(n);color=GREEN if eq[-1]>=0 else RED
    ax.fill_between(x,eq,0,alpha=0.05,color=color)
    ax.plot(x,eq,color=color,linewidth=1.6)
    ax.axhline(y=0,color=LGRAY,linewidth=0.5,linestyle="--")
    ax.set_ylabel("USD",fontproperties=F(8),color=GRAY)
    ax.set_xlabel("交易序號",fontproperties=F(8),color=GRAY)
    ax.yaxis.set_major_formatter(_fmt_usd())
    # Final value annotation
    ax.annotate(_fmt_usd().format_data(eq[-1]),(n-1,eq[-1]),
        textcoords="offset points",xytext=(-8,10),fontsize=9,color=DARK,ha="right",fontproperties=F(9,True))
    return _b64(fig)

# ─── Comparison charts ──────────────────────────────────────────
def chart_equity_overlay(accounts):
    if not accounts:return""
    fig=_fig(9,3.8);ax=_ax(fig,"淨值曲線對比 (USD)")
    for i,a in enumerate(accounts):
        eq=a.get("stats",{}).get("equity",[])
        if not eq:continue
        ax.plot(np.arange(len(eq)),eq,color=PALETTE[i%10],linewidth=1.5,label=a.get("account",f"帳戶{i+1}"))
    ax.axhline(y=0,color=LGRAY,linewidth=0.5,linestyle="--")
    ax.set_ylabel("USD",fontproperties=F(8),color=GRAY)
    ax.legend(prop=F(8),frameon=False,loc="upper left");ax.yaxis.set_major_formatter(_fmt_usd())
    return _b64(fig)

def chart_monthly_compare(accounts):
    if not accounts:return""
    all_months=set()
    for a in accounts:all_months.update(a.get("stats",{}).get("monthly",{}).keys())
    months=sorted(all_months)
    if not months:return""
    fig=_fig(9,3.4);ax=_ax(fig,"月度盈虧對比 (USD)")
    n=len(accounts);bar_w=0.6/n
    for i,a in enumerate(accounts):
        mv=[a.get("stats",{}).get("monthly",{}).get(m,0) for m in months]
        ax.bar(np.arange(len(months))+(i-(n-1)/2)*bar_w,mv,bar_w,color=PALETTE[i%10],alpha=0.85,
            label=a.get("account",f"帳戶{i+1}"),edgecolor=WHITE,linewidth=0.2)
    ax.set_xticks(range(len(months)))
    ax.set_xticklabels([m[2:] for m in months],fontsize=7,color=GRAY,fontproperties=F(7))
    ax.axhline(y=0,color=LGRAY,linewidth=0.5)
    ax.set_ylabel("USD",fontproperties=F(8),color=GRAY)
    ax.legend(prop=F(7),frameon=False,ncol=min(n,3));ax.yaxis.set_major_formatter(_fmt_usd())
    return _b64(fig)
