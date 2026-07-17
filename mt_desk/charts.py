"""Matplotlib charts — dark professional theme, Bloomberg/TradingView inspired.

Dark backgrounds make data pop. Green=profit, Red=loss, White=neutral.
150 DPI, Traditional Chinese, annotated values, axis units.
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

# ─── Dark theme palette ─────────────────────────────────────────
BG="#1a1f2e";CARD="#222839";GREEN="#00c853";RED="#ff1744";BLUE="#448aff"
ORANGE="#ff9100";TEAL="#1de9b6";GRAY="#64748b";LIGHT="#94a3b8";WHITE="#e2e8f0"
PALETTE=[BLUE,GREEN,ORANGE,RED,"#7c4dff",TEAL,"#ff4081","#40c4ff","#69f0ae","#ff6e40"]

def _fig(w,h):return Figure(figsize=(w,h),dpi=150,facecolor=BG)
def _ax(fig,title=""):
    ax=fig.add_subplot(111);ax.set_facecolor(BG)
    for s in ax.spines.values():s.set_visible(False)
    ax.tick_params(labelsize=8,colors=GRAY,length=0,pad=6)
    ax.grid(axis="y",color="#2d3446",linewidth=0.5,alpha=0.6)
    if title:ax.set_title(title,fontproperties=F(12,True),color=WHITE,pad=14,loc="left")
    ax.xaxis.label.set_color(GRAY);ax.yaxis.label.set_color(GRAY)
    return ax
def _b64(fig):
    buf=io.BytesIO();fig.savefig(buf,format="png",dpi=150,bbox_inches="tight",facecolor=BG,edgecolor="none")
    buf.seek(0);return base64.b64encode(buf.read()).decode()
_fmt=lambda:mticker.FuncFormatter(lambda v,_:f"${v/1000:.1f}k" if abs(v)>=1000 else f"${v:,.0f}")

# ─── 1. 淨值曲線 & 回撤 ─────────────────────────────────────────
def chart_equity(stats):
    eq=stats["equity"];n=len(eq)
    if n<2:return""
    fig=_fig(10,3.8);ax=_ax(fig,"淨值曲線 & 回撤")
    color=GREEN if stats["total_pl"]>=0 else RED
    ax.fill_between(range(n),eq,0,alpha=0.08,color=color)
    ax.plot(range(n),eq,color=color,linewidth=2,solid_capstyle="round")
    ax.axhline(y=0,color="#2d3446",linewidth=0.8,linestyle="--")
    ax.set_ylabel("USD",fontproperties=F(8));ax.set_xlabel("交易序號",fontproperties=F(8))
    ax.yaxis.set_major_formatter(_fmt())
    for idx,ha in[(0,"left"),(n-1,"right")]:
        ax.annotate(_fmt().format_data(eq[idx]),(idx,eq[idx]),textcoords="offset points",
            xytext=(14 if ha=="left" else-14,10),fontsize=9,color=WHITE,ha=ha,fontproperties=F(9))
    return _b64(fig)

# ─── 2. 月度盈虧 ─────────────────────────────────────────────────
def chart_monthly(stats):
    m=stats["monthly"];months=list(m.keys());vals=list(m.values())
    if not m:return""
    fig=_fig(10,3.4);ax=_ax(fig,"月度盈虧 (USD)")
    colors=[GREEN if v>=0 else RED for v in vals]
    bars=ax.bar(range(len(months)),vals,color=colors,width=0.5,alpha=0.95)
    ax.set_xticks(range(len(months)))
    ax.set_xticklabels([m[2:] for m in months],fontsize=8,color=LIGHT,fontproperties=F(8))
    ax.axhline(y=0,color="#2d3446",linewidth=0.8)
    ax.set_ylabel("USD",fontproperties=F(8));ax.yaxis.set_major_formatter(_fmt())
    for bar,v in zip(bars,vals):
        o=max(abs(min(vals)),abs(max(vals)))*0.02
        ax.text(bar.get_x()+bar.get_width()/2,v+o if v>=0 else v-o,_fmt().format_data(v),
            ha="center",fontsize=8,color=WHITE,fontproperties=F(8))
    return _b64(fig)

# ─── 3. 盈虧分佈 ─────────────────────────────────────────────────
def chart_pnl_dist(stats,trades):
    pls=[t["profit"] for t in trades]
    if not pls:return""
    fig=_fig(7,3.2);ax=_ax(fig,"盈虧分佈 (USD)")
    bins=min(50,max(15,int(len(pls)**0.5)))
    n,bins,patches=ax.hist(pls,bins=bins,color=BLUE,alpha=0.85,edgecolor=BG,linewidth=0.5)
    ax.axvline(x=0,color="#2d3446",linewidth=0.8,linestyle="--")
    ax.set_xlabel("USD",fontproperties=F(8));ax.set_ylabel("交易筆數",fontproperties=F(8))
    ax.xaxis.set_major_formatter(_fmt())
    mean_pl=np.mean(pls)
    ax.axvline(x=mean_pl,color=ORANGE,linewidth=1.2,linestyle="-",alpha=0.8)
    ax.text(mean_pl,max(n)*0.95,f"  均值 ${mean_pl:,.0f}",fontsize=9,color=ORANGE,fontproperties=F(9),va="top")
    return _b64(fig)

# ─── 4. 品種盈虧 ─────────────────────────────────────────────────
def chart_symbol(stats):
    syms=sorted(stats["sym_pl"].items(),key=lambda x:abs(x[1]),reverse=True)[:8]
    if not syms:return""
    fig=_fig(6,3);ax=_ax(fig,"品種盈虧 (USD)")
    labels=[s[0][:6].upper() for s in syms];vals=[s[1] for s in syms]
    colors=[GREEN if v>=0 else RED for v in vals]
    bars=ax.barh(labels,vals,color=colors,height=0.5,alpha=0.95)
    for bar,v in zip(bars,vals):
        ax.text(bar.get_width()+abs(v)*0.005,bar.get_y()+bar.get_height()/2,
            _fmt().format_data(v),va="center",fontsize=9,color=WHITE,fontproperties=F(9))
    ax.axvline(x=0,color="#2d3446",linewidth=0.8)
    ax.set_xlabel("USD",fontproperties=F(8));ax.xaxis.set_major_formatter(_fmt())
    return _b64(fig)

# ─── 5. 交易時段 ─────────────────────────────────────────────────
def chart_hourly(stats):
    fig=_fig(7,2.8);ax=_ax(fig,"交易時段分佈 (UTC)")
    hours=list(range(24));counts=[stats["hourly"].get(h,0) for h in hours]
    ax.bar(hours,counts,color=BLUE,alpha=0.85,width=0.7)
    ax.set_xticks([0,6,12,18,23])
    ax.set_xticklabels(["00:00","06:00","12:00","18:00","23:00"],fontsize=8,color=LIGHT,fontproperties=F(8))
    ax.set_ylabel("交易筆數",fontproperties=F(8));ax.set_xlabel("UTC 時段",fontproperties=F(8))
    return _b64(fig)

# ─── 6. 累計盈虧走勢 ─────────────────────────────────────────────
def chart_cumulative(stats):
    eq=stats["equity"];n=len(eq)
    if n<2:return""
    fig=_fig(10,3.4);ax=_ax(fig,"累計盈虧走勢 (USD)")
    color=GREEN if eq[-1]>=0 else RED
    ax.fill_between(range(n),eq,0,alpha=0.1,color=color)
    ax.plot(range(n),eq,color=color,linewidth=2)
    ax.axhline(y=0,color="#2d3446",linewidth=0.8,linestyle="--")
    ax.set_ylabel("USD",fontproperties=F(8));ax.set_xlabel("交易序號",fontproperties=F(8))
    ax.yaxis.set_major_formatter(_fmt())
    ax.annotate(_fmt().format_data(eq[-1]),(n-1,eq[-1]),textcoords="offset points",
        xytext=(-8,12),fontsize=10,color=WHITE,ha="right",fontproperties=F(10,True))
    return _b64(fig)

# ─── Comparison charts ──────────────────────────────────────────
def chart_equity_overlay(accounts):
    if not accounts:return""
    fig=_fig(10,3.8);ax=_ax(fig,"淨值曲線對比 (USD)")
    for i,a in enumerate(accounts):
        eq=a.get("stats",{}).get("equity",[])
        if not eq:continue
        ax.plot(range(len(eq)),eq,color=PALETTE[i%10],linewidth=1.8,label=a.get("account",f"帳戶{i+1}"))
    ax.axhline(y=0,color="#2d3446",linewidth=0.8,linestyle="--")
    ax.set_ylabel("USD",fontproperties=F(8));ax.legend(prop=F(9),frameon=False,loc="upper left",labelcolor=WHITE)
    ax.yaxis.set_major_formatter(_fmt())
    return _b64(fig)

def chart_monthly_compare(accounts):
    if not accounts:return""
    all_months=set()
    for a in accounts:all_months.update(a.get("stats",{}).get("monthly",{}).keys())
    months=sorted(all_months)
    if not months:return""
    fig=_fig(10,3.4);ax=_ax(fig,"月度盈虧對比 (USD)")
    n=len(accounts);bar_w=0.6/n
    for i,a in enumerate(accounts):
        mv=[a.get("stats",{}).get("monthly",{}).get(m,0) for m in months]
        ax.bar(np.arange(len(months))+(i-(n-1)/2)*bar_w,mv,bar_w,color=PALETTE[i%10],alpha=0.9,
            label=a.get("account",f"帳戶{i+1}"))
    ax.set_xticks(range(len(months)));ax.set_xticklabels([m[2:] for m in months],fontsize=8,color=LIGHT,fontproperties=F(8))
    ax.axhline(y=0,color="#2d3446",linewidth=0.8)
    ax.set_ylabel("USD",fontproperties=F(8));ax.legend(prop=F(8),frameon=False,ncol=min(n,3),labelcolor=WHITE)
    ax.yaxis.set_major_formatter(_fmt())
    return _b64(fig)
