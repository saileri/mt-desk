"""Matplotlib charts — 150 DPI, Traditional Chinese, axis units, multiple chart types.

New charts: heatmap (hour×weekday), combo (bar+line monthly cumulative), duration histogram.
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
import numpy as np
from collections import defaultdict
from datetime import datetime

# ─── Font ───────────────────────────────────────────────────────
_FONT_PATH = None
if sys.platform == "win32":
    windir = os.environ.get("WINDIR", "C:/Windows")
    for fn in ["msyh.ttc", "msyhbd.ttc", "simhei.ttf"]:
        fp = os.path.join(windir, "Fonts", fn)
        if os.path.isfile(fp): _FONT_PATH = fp; break

def _f(size=10, bold=False):
    return FontProperties(fname=_FONT_PATH, size=size, weight="bold" if bold else "normal") if _FONT_PATH else FontProperties(size=size)

# ─── Palette ────────────────────────────────────────────────────
ACCENT="#2563eb";GREEN="#059669";RED="#dc2626";ORANGE="#d97706";PURPLE="#7c3aed"
TEAL="#0d9488";GRAY="#9ca3af";LIGHT="#f0f2f5";WHITE="#ffffff";DARK="#111827"
PALETTE=[ACCENT,GREEN,ORANGE,RED,PURPLE,TEAL,"#be185d","#4f46e5","#0891b2","#b45309"]

def _fig(w,h): return Figure(figsize=(w,h),dpi=150,facecolor=LIGHT)
def _ax(fig,title=""):
    ax=fig.add_subplot(111);ax.set_facecolor("none")
    for s in ax.spines.values():s.set_visible(False)
    ax.tick_params(labelsize=8,colors=GRAY,length=0,pad=4)
    ax.grid(axis="y",color="#e5e7eb",linewidth=0.4,alpha=0.5)
    if title:ax.set_title(title,fontproperties=_f(12,True),color=DARK,pad=14,loc="left")
    return ax
def _b64(fig):
    buf=io.BytesIO();fig.savefig(buf,format="png",dpi=150,bbox_inches="tight",facecolor=LIGHT)
    buf.seek(0);return base64.b64encode(buf.read()).decode()
_usd=lambda:mticker.FuncFormatter(lambda v,_:f"${v/1000:.0f}k" if abs(v)>=10000 else f"${v:,.0f}")

# ─── Charts ─────────────────────────────────────────────────────

def chart_equity(stats):
    eq=stats["equity"];n=len(eq)
    if not eq:return""
    fig=_fig(8,3.6);ax=_ax(fig,"淨值曲線 & 回撤")
    x=np.arange(n);color=GREEN if stats["total_pl"]>=0 else RED
    ax.fill_between(x,eq,0,alpha=0.05,color=color)
    ax.plot(x,eq,color=color,linewidth=1.8,solid_capstyle="round")
    ax.axhline(y=0,color="#e5e7eb",linewidth=0.5,linestyle="--")
    ax.set_ylabel("USD",fontproperties=_f(8),color=GRAY)
    ax.set_xlabel("交易序號",fontproperties=_f(8),color=GRAY)
    ax.yaxis.set_major_formatter(_usd())
    if n>1:
        for idx,ha in[(0,"left"),(n-1,"right")]:
            ax.annotate(_usd().format_data(eq[idx]),(idx,eq[idx]),
                textcoords="offset points",xytext=(10 if ha=="left" else-10,8),
                fontsize=8,color=DARK,ha=ha,fontproperties=_f(8))
    return _b64(fig)

def chart_symbol(stats):
    syms=sorted(stats["sym_pl"].items(),key=lambda x:abs(x[1]),reverse=True)[:10]
    if not syms:return""
    fig=_fig(5,3.2);ax=_ax(fig,"品種盈虧 (USD)")
    labels=[s[0][:6].upper() for s in syms];values=[s[1] for s in syms]
    colors=[GREEN if v>=0 else RED for v in values]
    bars=ax.barh(labels,values,color=colors,height=0.5,alpha=0.9)
    for bar,v in zip(bars,values):
        ax.text(bar.get_width()+abs(v)*0.005,bar.get_y()+bar.get_height()/2,
            _usd().format_data(v),va="center",fontsize=8,color=DARK,fontproperties=_f(8))
    ax.axvline(x=0,color="#e5e7eb",linewidth=0.5)
    ax.set_xlabel("USD",fontproperties=_f(8),color=GRAY)
    ax.xaxis.set_major_formatter(_usd())
    return _b64(fig)

def chart_monthly(stats):
    monthly=stats["monthly"]
    if not monthly:return""
    fig=_fig(8,3.2);ax=_ax(fig,"月度盈虧 & 累計")
    months=list(monthly.keys());values=list(monthly.values())
    colors=[GREEN if v>=0 else RED for v in values]
    bars=ax.bar(range(len(months)),values,color=colors,width=0.45,alpha=0.85,edgecolor=WHITE,linewidth=0.3)
    # Cumulative line overlay
    cum=np.cumsum(values)
    ax2=ax.twinx()
    ax2.plot(range(len(months)),cum,color=ACCENT,linewidth=2,marker="o",markersize=4,markerfacecolor=WHITE,markeredgecolor=ACCENT)
    ax2.set_ylabel("累計 (USD)",fontproperties=_f(8),color=ACCENT)
    ax2.tick_params(labelsize=7,colors=ACCENT,length=0)
    for s in ax2.spines.values():s.set_visible(False)
    ax.set_xticks(range(len(months)))
    ax.set_xticklabels([m[2:] for m in months],fontsize=7,color=GRAY,fontproperties=_f(7))
    ax.axhline(y=0,color="#e5e7eb",linewidth=0.5)
    ax.set_ylabel("USD",fontproperties=_f(8),color=GRAY)
    ax.yaxis.set_major_formatter(_usd())
    return _b64(fig)

def chart_winloss(stats):
    fig=_fig(4,3.2);ax=_ax(fig,"盈虧分佈")
    wedges,_=ax.pie([stats["wins"],stats["losses"]],labels=None,colors=[GREEN,RED],
        startangle=90,wedgeprops={"alpha":0.9,"edgecolor":WHITE,"linewidth":2})
    ax.text(0,0.08,f"{stats['wr']:.0f}%",ha="center",va="center",fontproperties=_f(24,True),color=DARK)
    ax.text(0,-0.14,"勝率",ha="center",va="center",fontproperties=_f(9),color=GRAY)
    ax.legend([f"盈利 {stats['wins']}",f"虧損 {stats['losses']}"],loc="lower center",
        prop=_f(9),frameon=False,ncol=2,bbox_to_anchor=(0.5,-0.18))
    ax.axis("equal")
    return _b64(fig)

def chart_hourly(stats):
    fig=_fig(6,2.8);ax=_ax(fig,"交易時段分佈 (UTC)")
    hours=list(range(24));counts=[stats["hourly"].get(h,0) for h in hours]
    ax.bar(hours,counts,color=ACCENT,alpha=0.75,width=0.7,edgecolor=WHITE,linewidth=0.2)
    ax.set_xticks([0,6,12,18,23])
    ax.set_xticklabels(["00:00","06:00","12:00","18:00","23:00"],fontsize=7,color=GRAY,fontproperties=_f(7))
    ax.set_ylabel("交易筆數",fontproperties=_f(8),color=GRAY)
    ax.set_xlabel("UTC 時段",fontproperties=_f(8),color=GRAY)
    return _b64(fig)

def chart_streaks(stats):
    wd,ld=stats["win_dist"],stats["loss_dist"]
    if not wd and not ld:return""
    max_len=max(len(wd),len(ld),1)
    fig=_fig(5,3);ax=_ax(fig,"連續盈利/虧損分佈")
    x=np.arange(max_len);bar_w=0.3
    ax.bar(x-bar_w/2,wd+[0]*(max_len-len(wd)),bar_w,color=GREEN,alpha=0.85,label="盈利",edgecolor=WHITE,linewidth=0.2)
    ax.bar(x+bar_w/2,ld+[0]*(max_len-len(ld)),bar_w,color=RED,alpha=0.85,label="虧損",edgecolor=WHITE,linewidth=0.2)
    ax.set_xticks(x);ax.set_xticklabels([str(i+1) for i in range(max_len)],fontsize=7,color=GRAY)
    ax.set_xlabel("連續筆數",fontproperties=_f(8),color=GRAY)
    ax.set_ylabel("出現次數",fontproperties=_f(8),color=GRAY)
    ax.legend(prop=_f(8),frameon=False,loc="upper right")
    return _b64(fig)

def chart_heatmap(stats, trades):
    """Trading activity heatmap: hour × weekday."""
    from matplotlib.colors import LinearSegmentedColormap
    matrix=np.zeros((7,24))
    for t in trades:
        if t["open_time"]:
            matrix[t["open_time"].weekday(),t["open_time"].hour]+=1
    fig=_fig(8,3.2);ax=_ax(fig,"交易熱力圖 (時段 × 週日)")
    cmap=LinearSegmentedColormap.from_list("hm",["#f0f2f5","#dbeafe","#93c5fd","#3b82f6","#1e40af"])
    im=ax.imshow(matrix,aspect="auto",cmap=cmap,origin="lower")
    days=["一","二","三","四","五","六","日"]
    ax.set_yticks(range(7));ax.set_yticklabels(days,fontsize=8,fontproperties=_f(8))
    ax.set_xticks([0,6,12,18,23])
    ax.set_xticklabels(["00","06","12","18","23"],fontsize=7,color=GRAY)
    ax.set_xlabel("UTC 時段",fontproperties=_f(8),color=GRAY)
    ax.set_ylabel("週日",fontproperties=_f(8),color=GRAY)
    cbar=fig.colorbar(im,ax=ax,shrink=0.8,pad=0.02)
    cbar.ax.tick_params(labelsize=7,colors=GRAY,length=0)
    cbar.outline.set_visible(False)
    return _b64(fig)

def chart_duration(stats, trades):
    """Trade duration distribution histogram."""
    durs=[]
    for t in trades:
        if t["open_time"] and t["close_time"]:
            h=(t["close_time"]-t["open_time"]).total_seconds()/3600
            if h>0:durs.append(h)
    if not durs:return""
    fig=_fig(5,3);ax=_ax(fig,"持倉時長分佈")
    bins=[0,0.25,1,4,12,24,72,168,720,9999]
    labels=["<15m","15m-1h","1-4h","4-12h","12h-1d","1-3d","3d-1w","1w-1m",">1m"]
    counts,_=np.histogram(durs,bins=bins)
    colors=[ACCENT]*len(labels)
    bars=ax.bar(range(len(labels)),counts,color=colors,alpha=0.8,width=0.6,edgecolor=WHITE,linewidth=0.2)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels,rotation=30,fontsize=7,color=GRAY,fontproperties=_f(7))
    ax.set_ylabel("交易筆數",fontproperties=_f(8),color=GRAY)
    ax.set_xlabel("持倉時長",fontproperties=_f(8),color=GRAY)
    for bar,c in zip(bars,counts):
        if c>0:ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+max(counts)*0.02,
            str(c),ha="center",fontsize=7,color=GRAY,fontproperties=_f(7))
    return _b64(fig)

def chart_equity_overlay(accounts):
    if not accounts:return""
    fig=_fig(8,3.6);ax=_ax(fig,"淨值曲線對比")
    for i,acc in enumerate(accounts):
        eq=acc.get("stats",{}).get("equity",[])
        if not eq:continue
        ax.plot(np.arange(len(eq)),eq,color=PALETTE[i%10],linewidth=1.5,label=acc.get("account",f"帳戶{i+1}"))
    ax.axhline(y=0,color="#e5e7eb",linewidth=0.5,linestyle="--")
    ax.set_ylabel("USD",fontproperties=_f(8),color=GRAY)
    ax.legend(prop=_f(8),frameon=False,loc="upper left")
    ax.yaxis.set_major_formatter(_usd())
    return _b64(fig)

def chart_monthly_compare(accounts):
    if not accounts:return""
    all_months=set()
    for a in accounts:all_months.update(a.get("stats",{}).get("monthly",{}).keys())
    months=sorted(all_months)
    if not months:return""
    fig=_fig(8,3.2);ax=_ax(fig,"月度盈虧對比")
    n=len(accounts);bar_w=0.6/n
    for i,acc in enumerate(accounts):
        mv=[acc.get("stats",{}).get("monthly",{}).get(m,0) for m in months]
        ax.bar(np.arange(len(months))+(i-(n-1)/2)*bar_w,mv,bar_w,color=PALETTE[i%10],alpha=0.85,
            label=acc.get("account",f"帳戶{i+1}"),edgecolor=WHITE,linewidth=0.2)
    ax.set_xticks(range(len(months)))
    ax.set_xticklabels([m[2:] for m in months],fontsize=7,color=GRAY,fontproperties=_f(7))
    ax.axhline(y=0,color="#e5e7eb",linewidth=0.5)
    ax.set_ylabel("USD",fontproperties=_f(8),color=GRAY)
    ax.legend(prop=_f(7),frameon=False,ncol=min(n,3),loc="upper left")
    ax.yaxis.set_major_formatter(_usd())
    return _b64(fig)
