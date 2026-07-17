#!/usr/bin/env python3
"""MT Desk v3 — 繁體中文 · 150DPI 高清 · 熱力圖/組合圖 · 自訂日期範圍"""
import base64,io,os,sys,tempfile,tkinter as tk,json,threading,webbrowser
from tkinter import filedialog,messagebox
from datetime import datetime,date
from pathlib import Path
from mt_desk.parser import parse_statement
from mt_desk.analysis import analyze
from mt_desk.charts import *

if sys.stdout is None:sys.stdout=io.StringIO()
if sys.stderr is None:sys.stderr=sys.stdout

THRESHOLD=50*1024*1024

def build_dashboard_html(account,trades,stats,date_from=None,date_to=None):
    charts={
        "equity":chart_equity(stats),"symbol":chart_symbol(stats),
        "monthly":chart_monthly(stats),"pnl_dist":chart_pnl_dist(stats,trades),
        "hourly":chart_hourly(stats),"cumulative":chart_cumulative(stats),
    }
    cards=[
        ("總交易",str(stats["count"])),
        ("總盈虧",f"${stats['total_pl']:+,.2f}","#059669" if stats["total_pl"]>=0 else"#dc2626"),
        ("勝率",f"{stats['wr']:.0f}%","#059669"),
        ("盈利因子",f"{stats['pf']:.2f}" if stats["pf"]!=float("inf") else"∞"),
        ("最大回撤",f"${stats['max_dd']:,.2f}","#dc2626"),
        ("夏普比率",f"{stats['sharpe']:.2f}"),
        ("最佳",f"+${stats['best']:,.2f}","#059669"),
        ("最差",f"-${abs(stats['worst']):,.2f}","#dc2626"),
        ("連續盈利",f"{stats['max_win_streak']}筆"),
        ("連續虧損",f"{stats['max_loss_streak']}筆"),
    ]
    card_html="".join(f'<div class="kpi"><div class="lbl">{l}</div><div class="val" style="color:{c}">{v}</div></div>'
        for l,v,c in[(it[0],it[1],it[2] if len(it)>2 else"#1f2937") for it in cards])
    chart_blocks=[]
    for key,cls in [("equity","wide"),("symbol",""),("pnl_dist",""),("monthly","wide"),
                     ("hourly",""),("cumulative","wide")]:
        if charts.get(key):
            chart_blocks.append(f'<div class="chart-card {"wide" if cls=="wide" else ""}">'
                f'<img src="data:image/png;base64,{charts[key]}"></div>')
    trade_data=[{"ticket":str(t["ticket"]),
        "open":t["open_time"].strftime("%Y-%m-%d %H:%M") if t["open_time"] else"-",
        "close":t["close_time"].strftime("%Y-%m-%d %H:%M") if t["close_time"] else"-",
        "type":t["type"].upper(),"symbol":t["symbol"].upper(),
        "volume":t["volume"],"profit":round(t["profit"],2)} for t in trades]
    trade_json=json.dumps(trade_data,ensure_ascii=False)
    date_info=""
    if date_from or date_to:
        df=date_from.strftime("%Y-%m-%d") if date_from else"不限"
        dt=date_to.strftime("%Y-%m-%d") if date_to else"不限"
        date_info=f' · 篩選: {df} ~ {dt}'
    return _HTML_TEMPLATE.format(account=account,count=stats["count"],
        pl=f"${stats['total_pl']:+,.2f}",pl_color="#86efac" if stats["total_pl"]>=0 else"#fca5a5",
        wr=f"{stats['wr']:.0f}%",cards=card_html,charts="".join(chart_blocks),
        trade_json=trade_json,date_info=date_info)

_HTML_TEMPLATE=r"""<!DOCTYPE html><html lang="zh-HK"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MT Desk — {account}</title>
<style>
:root{{--bg:#f0f2f5;--card:#fff;--text:#1f2937;--muted:#6b7280;--blue:#2563eb;--dblue:#1e40af;--green:#059669;--red:#dc2626;--border:#e5e7eb;--radius:10px;--shadow:0 1px 3px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04)}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI','Microsoft YaHei',system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);font-size:clamp(12px,1.1vw,14px);line-height:1.5}}
.header{{background:linear-gradient(135deg,var(--blue),var(--dblue));color:#fff;padding:clamp(10px,1.2vw,16px) clamp(14px,1.6vw,24px);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px}}
.header h1{{font-size:clamp(14px,1.4vw,18px);font-weight:700;display:flex;align-items:center;gap:8px}}
.header .meta{{font-size:clamp(9px,0.8vw,11px);opacity:.85}}
.main{{max-width:1400px;margin:0 auto;padding:clamp(8px,1vw,16px)}}
.kpi-row{{display:grid;grid-template-columns:repeat(auto-fill,minmax(clamp(100px,12vw,130px),1fr));gap:clamp(4px,0.5vw,8px);margin-bottom:clamp(8px,1vw,14px)}}
.kpi{{background:var(--card);border-radius:var(--radius);padding:clamp(8px,0.8vw,12px);box-shadow:var(--shadow);text-align:center;border:1px solid var(--border);transition:transform .15s}}
.kpi:hover{{transform:translateY(-1px);box-shadow:0 4px 8px rgba(0,0,0,.08)}}
.kpi .lbl{{font-size:clamp(8px,0.7vw,10px);color:var(--muted);margin-bottom:2px;font-weight:500}}
.kpi .val{{font-size:clamp(14px,1.3vw,18px);font-weight:700;line-height:1.2}}
.chart-section{{margin-bottom:clamp(8px,1vw,14px)}}
.chart-section h3{{font-size:clamp(11px,1vw,13px);color:var(--dblue);margin-bottom:clamp(4px,0.5vw,8px);padding-left:clamp(6px,0.6vw,10px);border-left:3px solid var(--blue);font-weight:600}}
.charts{{display:grid;grid-template-columns:1fr 1fr;gap:clamp(6px,0.8vw,10px)}}
.chart-card{{background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);border:1px solid var(--border);overflow:hidden}}
.chart-card.wide{{grid-column:1/-1}}
.chart-card img{{width:100%;display:block}}
.toolbar{{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:8px;padding:clamp(4px,0.5vw,8px) 0}}
.toolbar input{{padding:4px 10px;border:1px solid #d1d5db;border-radius:6px;font-size:clamp(9px,0.8vw,11px);outline:none;transition:border-color .2s}}
.toolbar input:focus{{border-color:var(--blue);box-shadow:0 0 0 2px rgba(37,99,235,.15)}}
.toolbar button,.toolbar select{{padding:4px 10px;border:1px solid #d1d5db;border-radius:6px;background:#fff;cursor:pointer;font-size:clamp(9px,0.8vw,11px);font-family:inherit;transition:all .15s}}
.toolbar button:hover{{background:#eff6ff;border-color:var(--blue);color:var(--blue)}}
.toolbar .nav-btn{{min-width:28px;text-align:center}}
.toolbar .page-info{{font-size:clamp(9px,0.8vw,11px);color:var(--muted);margin:0 2px}}
.table-wrap{{background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);border:1px solid var(--border);overflow:hidden}}
table{{width:100%;border-collapse:collapse;font-size:clamp(8px,0.8vw,11px)}}
th{{background:#f8fafc;padding:clamp(5px,0.5vw,7px) clamp(7px,0.7vw,10px);text-align:left;font-weight:600;border-bottom:2px solid var(--blue);cursor:pointer;user-select:none;white-space:nowrap;font-size:clamp(8px,0.8vw,11px);color:var(--dblue)}}
th:hover{{background:#eff6ff}}
th .sort-arrow{{font-size:8px;margin-left:2px;color:#93c5fd}}
td{{padding:clamp(3px,0.4vw,5px) clamp(7px,0.7vw,10px);border-bottom:1px solid #f3f4f6}}
tr:hover td{{background:#f8fafc}}.win{{color:var(--green);font-weight:500}}.loss{{color:var(--red);font-weight:500}}
tr.highlight td{{background:#fef3c7!important;outline:2px solid #f59e0b;outline-offset:-1px}}
@media(max-width:768px){{.charts{{grid-template-columns:1fr}}.kpi-row{{grid-template-columns:repeat(3,1fr)}}}}
</style></head><body>
<div class="header"><div><h1>📊 MT Desk <span style="font-weight:400;font-size:clamp(10px,0.9vw,13px);opacity:.7">— {account}</span></h1></div>
<div class="meta">{count} 筆交易 · P/L: <span style="color:{pl_color};font-weight:600">{pl}</span> · 勝率: <span style="color:#86efac;font-weight:600">{wr}</span>{date_info}</div></div>
<div class="main"><div class="kpi-row">{cards}</div>
<div class="chart-section"><h3>📈 權益與統計</h3><div class="charts">{charts}</div></div>
<div class="chart-section"><h3>📋 逐筆明細</h3>
<div class="toolbar"><input type="text" id="searchBox" placeholder="🔍 搜尋 Ticket..." oninput="doSearch()">
<span id="searchInfo" style="font-size:clamp(9px,0.8vw,11px);color:var(--muted)"></span><span style="flex:1"></span>
<span class="page-info">每頁</span><select id="pageSize" onchange="pageSize=+this.value;currentPage=1;renderTable()">
<option value="15" selected>15</option><option value="30">30</option><option value="50">50</option><option value="100">100</option></select><span class="page-info">筆</span>
<button class="nav-btn" onclick="currentPage=1;renderTable()">«</button>
<button class="nav-btn" onclick="if(currentPage>1){{currentPage--;renderTable()}}">‹</button>
<span class="page-info" id="pageInfo"></span>
<button class="nav-btn" onclick="if(currentPage<totalPages){{currentPage++;renderTable()}}">›</button>
<button class="nav-btn" onclick="currentPage=totalPages;renderTable()">»</button></div>
<div class="table-wrap"><table><thead><tr>
<th onclick="sortBy('ticket')">Ticket<span class="sort-arrow" id="sa-ticket"></span></th>
<th onclick="sortBy('open')">開倉<span class="sort-arrow" id="sa-open"></span></th>
<th onclick="sortBy('type')">方向<span class="sort-arrow" id="sa-type"></span></th>
<th onclick="sortBy('volume')">手數<span class="sort-arrow" id="sa-volume"></span></th>
<th onclick="sortBy('symbol')">品種<span class="sort-arrow" id="sa-symbol"></span></th>
<th onclick="sortBy('close')">平倉<span class="sort-arrow" id="sa-close"></span></th>
<th onclick="sortBy('profit')">盈虧<span class="sort-arrow" id="sa-profit"></span></th></tr></thead>
<tbody id="tradeBody"></tbody></table></div>
<div class="toolbar" style="justify-content:flex-end;margin-top:6px">
<span class="page-info" id="pageInfo2"></span>
<button class="nav-btn" onclick="currentPage=1;renderTable()">«</button>
<button class="nav-btn" onclick="if(currentPage>1){{currentPage--;renderTable()}}">‹</button>
<button class="nav-btn" onclick="if(currentPage<totalPages){{currentPage++;renderTable()}}">›</button>
<button class="nav-btn" onclick="currentPage=totalPages;renderTable()">»</button></div></div></div>
<script>var ALL={trade_json};var data=ALL.slice();var sortCol='profit',sortDir=-1;var currentPage=1,pageSize=15,totalPages=1;var searchIdx=-1,searchMatches=[];
function sortBy(col){{if(sortCol===col)sortDir*=-1;else{{sortCol=col;sortDir=-1;}}data.sort(function(a,b){{var va=a[col],vb=b[col];if(typeof va==='number')return(va-vb)*sortDir;return String(va).localeCompare(String(vb))*sortDir;}});currentPage=1;renderTable();document.querySelectorAll('.sort-arrow').forEach(function(el){{el.textContent='';}});var arrow=document.getElementById('sa-'+col);if(arrow)arrow.textContent=sortDir>0?'▲':'▼';}}
function doSearch(){{var q=document.getElementById('searchBox').value.trim().toLowerCase();searchMatches=[];searchIdx=-1;if(!q){{data=ALL.slice();document.getElementById('searchInfo').textContent='';}}else{{data=ALL.filter(function(t){{return String(t.ticket).toLowerCase().indexOf(q)>=0;}});document.getElementById('searchInfo').textContent=data.length+' 條匹配';ALL.forEach(function(t,i){{if(String(t.ticket).toLowerCase().indexOf(q)>=0)searchMatches.push(i);}});}}currentPage=1;renderTable();}}
document.getElementById('searchBox').addEventListener('keydown',function(e){{if(e.key==='Enter'&&searchMatches.length>0){{e.preventDefault();searchIdx=(searchIdx+1)%searchMatches.length;var globalIdx=searchMatches[searchIdx];var page=Math.floor(globalIdx/pageSize)+1;currentPage=page;renderTable();setTimeout(function(){{var rows=document.querySelectorAll('#tradeBody tr');rows.forEach(function(r){{r.classList.remove('highlight');}});var localIdx=globalIdx%pageSize;if(rows[localIdx]){{rows[localIdx].classList.add('highlight');rows[localIdx].scrollIntoView({{behavior:'smooth',block:'center'}});}}document.getElementById('searchInfo').textContent=(searchIdx+1)+'/'+searchMatches.length+' 條匹配';}},30);}}}});
function renderTable(){{totalPages=Math.ceil(data.length/pageSize)||1;if(currentPage>totalPages)currentPage=totalPages;var start=(currentPage-1)*pageSize;var page=data.slice(start,start+pageSize);var h='';page.forEach(function(t){{h+='<tr class="'+(t.profit>0?'win':'loss')+'"><td>'+t.ticket+'</td><td>'+t.open+'</td><td>'+t.type+'</td><td>'+t.volume+'</td><td>'+t.symbol+'</td><td>'+t.close+'</td><td>$'+t.profit.toFixed(2)+'</td></tr>';}});document.getElementById('tradeBody').innerHTML=h;var info=currentPage+'/'+totalPages+' ('+data.length+'筆)';document.getElementById('pageInfo').textContent=info;document.getElementById('pageInfo2').textContent=info;}}
renderTable();document.getElementById('sa-profit').textContent='▼';</script></body></html>"""


def process_file(path,date_from=None,date_to=None):
    filepath=Path(path);size=filepath.stat().st_size
    result=parse_statement(path);trades=result["trades"]
    if not trades:messagebox.showerror("失敗","未找到交易記錄");return
    # Filter by date range
    if date_from or date_to:
        filtered=[]
        for t in trades:
            ot=t.get("open_time")
            if not ot:continue
            if date_from and ot.date()<date_from:continue
            if date_to and ot.date()>date_to:continue
            filtered.append(t)
        trades=filtered
        if not trades:messagebox.showerror("失敗","篩選後無交易記錄");return
    stats=analyze(trades)
    html=build_dashboard_html(result["account"],trades,stats,date_from,date_to)
    out=Path(tempfile.gettempdir())/f"MT_Desk_{result['account']}.html"
    out.write_text(html,encoding="utf-8")
    threading.Timer(0.3,lambda:webbrowser.open(out.as_uri())).start()
    return result,len(trades)


def main():
    root=tk.Tk();root.title("MT Desk v3");root.geometry("460x380")
    root.configure(bg="#f0f2f5");root.resizable(False,False)
    tk.Label(root,text="📊 MT Desk",font=("Segoe UI",20,"bold"),fg="#2563eb",bg="#f0f2f5").pack(pady=(20,4))
    tk.Label(root,text="MT4/MT5 → 自動解析 → 瀏覽器圖表",font=("Segoe UI",10),fg="#6b7280",bg="#f0f2f5").pack(pady=(0,12))
    # Date range
    dframe=tk.Frame(root,bg="#f0f2f5")
    tk.Label(dframe,text="篩選日期 (可選):",font=("Segoe UI",9),fg="#6b7280",bg="#f0f2f5").pack(side=tk.LEFT,padx=(0,6))
    dfrom_var=tk.StringVar();dto_var=tk.StringVar()
    tk.Entry(dframe,textvariable=dfrom_var,width=12,font=("Segoe UI",9)).pack(side=tk.LEFT,padx=2)
    tk.Label(dframe,text="~",font=("Segoe UI",9),fg="#6b7280",bg="#f0f2f5").pack(side=tk.LEFT,padx=2)
    tk.Entry(dframe,textvariable=dto_var,width=12,font=("Segoe UI",9)).pack(side=tk.LEFT,padx=2)
    tk.Label(dframe,text="(YYYY-MM-DD)",font=("Segoe UI",8),fg="#9ca3af",bg="#f0f2f5").pack(side=tk.LEFT,padx=(4,0))
    dframe.pack(pady=(0,10))
    status_var=tk.StringVar(value="選擇 HTML 報表檔案")
    status=tk.Label(root,textvariable=status_var,font=("Segoe UI",9),fg="#6b7280",bg="#f0f2f5")
    status.pack(pady=(0,10))
    def open_file():
        path=filedialog.askopenfilename(title="選擇 MT4/MT5 報表",filetypes=[("HTML","*.htm *.html"),("All","*.*")])
        if not path:return
        fname=Path(path).name;size_mb=Path(path).stat().st_size/1024/1024
        # Parse date range
        df=None;dt=None
        try:
            s=dfrom_var.get().strip()
            if s:df=datetime.strptime(s,"%Y-%m-%d").date()
            s=dto_var.get().strip()
            if s:dt=datetime.strptime(s,"%Y-%m-%d").date()
        except:pass
        status_var.set(f"⏳ 解析中: {fname} ({size_mb:.1f}MB)...");root.update()
        try:
            res,count=process_file(path,df,dt)
            status_var.set(f"✅ {res['account']} — {count} 筆")
        except Exception as e:
            status_var.set(f"❌ {e}");messagebox.showerror("錯誤",str(e))
    btn=tk.Button(root,text="📂 選擇 MT4/MT5 HTML 報表",font=("Segoe UI",12),bg="#2563eb",fg="white",
        relief="flat",padx=24,pady=10,command=open_file,cursor="hand2")
    btn.pack(pady=(0,8))
    root.mainloop()

if __name__=="__main__":main()
