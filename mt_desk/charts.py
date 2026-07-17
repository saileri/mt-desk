"""Matplotlib charts — 200 DPI, thick lines, high contrast.
Dark & light theme compatible — renders against transparent bg.
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

_FONT=None
if sys.platform=="win32":
    for fn in["msyh.ttc","msyhbd.ttc","simhei.ttf"]:
        fp=os.path.join(os.environ.get("WINDIR","C:/Windows"),"Fonts",fn)
        if os.path.isfile(fp):_FONT=fp;break
def F(s=11,b=False):return FontProperties(fname=_FONT,size=s,weight="bold" if b else"normal") if _FONT else FontProperties(size=s)

# Dark palette
BG="#1a1f2e";GREEN="#00e676";RED="#ff5252";BLUE="#448aff";ORANGE="#ff9100"
GRAY="#5c6b80";LIGHT="#8899aa";WHITE="#e8ecf1";GRID="#252d3f"
PALETTE=[BLUE,GREEN,ORANGE,RED,"#7c4dff","#1de9b6","#ff4081","#40c4ff"]

def _fig(w,h):return Figure(figsize=(w,h),dpi=200,facecolor=BG)
def _ax(fig,title=""):
    ax=fig.add_subplot(111);ax.set_facecolor(BG)
    for s in ax.spines.values():s.set_visible(False)
    ax.tick_params(labelsize=10,colors=GRAY,length=0,pad=6)
    ax.grid(axis="y",color=GRID,linewidth=0.6,alpha=0.7)
    if title:ax.set_title(title,fontproperties=F(14,True),color=WHITE,pad=18,loc="left")
    ax.xaxis.label.set_color(GRAY);ax.yaxis.label.set_color(GRAY)
    return ax
def _b64(fig):
    buf=io.BytesIO();fig.savefig(buf,format="png",dpi=200,bbox_inches="tight",facecolor=BG,edgecolor="none")
    buf.seek(0);return base64.b64encode(buf.read()).decode()
FMT=lambda:mticker.FuncFormatter(lambda v,_:f"${v/1000:.1f}k" if abs(v)>=1000 else f"${v:,.0f}")

# ─── Charts ─────────────────────────────────────────────────────
def chart_equity(stats):
    eq=stats["equity"];n=len(eq)
    if n<2:return""
    fig=_fig(10,4.2);ax=_ax(fig,"淨值曲線 & 回撤")
    c=GREEN if stats["total_pl"]>=0 else RED
    ax.fill_between(range(n),eq,0,alpha=0.1,color=c)
    ax.plot(range(n),eq,color=c,linewidth=2.5,solid_capstyle="round")
    ax.axhline(y=0,color=GRID,linewidth=1,linestyle="--")
    ax.set_ylabel("USD",fontproperties=F(10));ax.set_xlabel("交易序號",fontproperties=F(10))
    ax.yaxis.set_major_formatter(FMT())
    for idx,ha in[(0,"left"),(n-1,"right")]:
        ax.annotate(FMT().format_data(eq[idx]),(idx,eq[idx]),textcoords="offset points",
            xytext=(16 if ha=="left" else-16,12),fontsize=10,color=WHITE,ha=ha,fontproperties=F(10))
    return _b64(fig)

def chart_monthly(stats):
    m=stats["monthly"];months=list(m.keys());vals=list(m.values())
    if not m:return""
    fig=_fig(10,3.8);ax=_ax(fig,"月度盈虧 (USD)")
    colors=[GREEN if v>=0 else RED for v in vals]
    bars=ax.bar(range(len(months)),vals,color=colors,width=0.55,alpha=0.95)
    ax.set_xticks(range(len(months)))
    ax.set_xticklabels([m[2:] for m in months],fontsize=10,color=LIGHT,fontproperties=F(10))
    ax.axhline(y=0,color=GRID,linewidth=1)
    ax.set_ylabel("USD",fontproperties=F(10));ax.yaxis.set_major_formatter(FMT())
    mx=max(abs(min(vals)),abs(max(vals)))*0.025
    for bar,v in zip(bars,vals):
        ax.text(bar.get_x()+bar.get_width()/2,v+mx if v>=0 else v-mx,FMT().format_data(v),
            ha="center",fontsize=9,color=WHITE,fontproperties=F(9))
    return _b64(fig)

def chart_pnl_dist(stats,trades):
    pls=[t["profit"] for t in trades]
    if not pls:return""
    fig=_fig(7,3.6);ax=_ax(fig,"盈虧分佈 (USD)")
    bins=min(50,max(20,int(len(pls)**0.5)))
    n,bins,patches=ax.hist(pls,bins=bins,color=BLUE,alpha=0.85,edgecolor=BG,linewidth=0.5)
    ax.axvline(x=0,color=GRID,linewidth=1,linestyle="--")
    ax.set_xlabel("USD",fontproperties=F(10));ax.set_ylabel("交易筆數",fontproperties=F(10));ax.xaxis.set_major_formatter(FMT())
    mean_pl=np.mean(pls)
    ax.axvline(x=mean_pl,color=ORANGE,linewidth=1.5,linestyle="-",alpha=0.9)
    ax.text(mean_pl,max(n)*0.95,f"  均值 ${mean_pl:,.0f}",fontsize=10,color=ORANGE,fontproperties=F(10),va="top")
    return _b64(fig)

def chart_symbol(stats):
    syms=sorted(stats["sym_pl"].items(),key=lambda x:abs(x[1]),reverse=True)[:8]
    if not syms:return""
    fig=_fig(6,3.4);ax=_ax(fig,"品種盈虧 (USD)")
    labels=[s[0][:6].upper() for s in syms];vals=[s[1] for s in syms]
    colors=[GREEN if v>=0 else RED for v in vals]
    bars=ax.barh(labels,vals,color=colors,height=0.55,alpha=0.95)
    for bar,v in zip(bars,vals):
        ax.text(bar.get_width()+abs(v)*0.005,bar.get_y()+bar.get_height()/2,
            FMT().format_data(v),va="center",fontsize=10,color=WHITE,fontproperties=F(10))
    ax.axvline(x=0,color=GRID,linewidth=1)
    ax.set_xlabel("USD",fontproperties=F(10));ax.xaxis.set_major_formatter(FMT())
    return _b64(fig)

def chart_hourly(stats):
    fig=_fig(7,3);ax=_ax(fig,"交易時段分佈 (UTC)")
    hours=list(range(24));counts=[stats["hourly"].get(h,0) for h in hours]
    ax.bar(hours,counts,color=BLUE,alpha=0.85,width=0.75)
    ax.set_xticks([0,6,12,18,23])
    ax.set_xticklabels(["00:00","06:00","12:00","18:00","23:00"],fontsize=10,color=LIGHT,fontproperties=F(10))
    ax.set_ylabel("交易筆數",fontproperties=F(10));ax.set_xlabel("UTC 時段",fontproperties=F(10))
    return _b64(fig)

def chart_cumulative(stats):
    eq=stats["equity"];n=len(eq)
    if n<2:return""
    fig=_fig(10,3.6);ax=_ax(fig,"累計盈虧走勢 (USD)")
    c=GREEN if eq[-1]>=0 else RED
    ax.fill_between(range(n),eq,0,alpha=0.12,color=c)
    ax.plot(range(n),eq,color=c,linewidth=2.5)
    ax.axhline(y=0,color=GRID,linewidth=1,linestyle="--")
    ax.set_ylabel("USD",fontproperties=F(10));ax.set_xlabel("交易序號",fontproperties=F(10));ax.yaxis.set_major_formatter(FMT())
    ax.annotate(FMT().format_data(eq[-1]),(n-1,eq[-1]),textcoords="offset points",
        xytext=(-10,14),fontsize=12,color=WHITE,ha="right",fontproperties=F(12,True))
    return _b64(fig)

def chart_equity_overlay(accounts):
    if not accounts:return""
    fig=_fig(10,4.2);ax=_ax(fig,"淨值曲線對比 (USD)")
    for i,a in enumerate(accounts):
        eq=a.get("stats",{}).get("equity",[])
        if not eq:continue
        ax.plot(range(len(eq)),eq,color=PALETTE[i%8],linewidth=2,label=a.get("account",f"帳戶{i+1}"))
    ax.axhline(y=0,color=GRID,linewidth=1,linestyle="--")
    ax.set_ylabel("USD",fontproperties=F(10));ax.legend(prop=F(10),frameon=False,loc="upper left",labelcolor=WHITE)
    ax.yaxis.set_major_formatter(FMT());return _b64(fig)

def chart_monthly_compare(accounts):
    if not accounts:return""
    all_months=set()
    for a in accounts:all_months.update(a.get("stats",{}).get("monthly",{}).keys())
    months=sorted(all_months)
    if not months:return""
    fig=_fig(10,3.8);ax=_ax(fig,"月度盈虧對比 (USD)")
    n=len(accounts);bar_w=0.65/n
    for i,a in enumerate(accounts):
        mv=[a.get("stats",{}).get("monthly",{}).get(m,0) for m in months]
        ax.bar(np.arange(len(months))+(i-(n-1)/2)*bar_w,mv,bar_w,color=PALETTE[i%8],alpha=0.9,
            label=a.get("account",f"帳戶{i+1}"))
    ax.set_xticks(range(len(months)));ax.set_xticklabels([m[2:] for m in months],fontsize=10,color=LIGHT,fontproperties=F(10))
    ax.axhline(y=0,color=GRID,linewidth=1)
    ax.set_ylabel("USD",fontproperties=F(10));ax.legend(prop=F(9),frameon=False,ncol=min(n,3),labelcolor=WHITE)
    ax.yaxis.set_major_formatter(FMT());return _b64(fig)
