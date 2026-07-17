#!/usr/bin/env python3
"""MT Desk v4 — Apache ECharts (66.8k stars), date axes, native browser fonts"""
import json,io,os,sys,tempfile,tkinter as tk,threading,webbrowser
from tkinter import filedialog,messagebox
from datetime import datetime
from pathlib import Path
from mt_desk.parser import parse_statement
from mt_desk.analysis import analyze
from mt_desk.charts import *

if sys.stdout is None:sys.stdout=io.StringIO()
if sys.stderr is None:sys.stderr=sys.stdout

ECHARTS_CDN="https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js"

def build_dashboard_html(account,trades,stats,date_from=None,date_to=None):
    chart_configs={
        "equity":chart_equity(stats),"symbol":chart_symbol(stats),
        "monthly":chart_monthly(stats),"pnl_dist":chart_pnl_dist(stats,trades),
        "hourly":chart_hourly(stats),"rolling_wr":chart_rolling_wr(stats,trades),
        "drawdown":chart_drawdown(stats),"volume_dist":chart_volume_dist(stats,trades),
    }
    cards=[
        ("總交易",str(stats["count"]),""),("總盈虧",f"${stats['total_pl']:+,.2f}","--green" if stats["total_pl"]>=0 else"--red"),
        ("勝率",f"{stats['wr']:.0f}%","--green"),("盈利因子",f"{stats['pf']:.2f}" if stats["pf"]!=float("inf") else"∞","--muted"),
        ("最大回撤",f"${stats['max_dd']:,.2f}","--red"),("夏普比率",f"{stats['sharpe']:.2f}","--muted"),
        ("最佳",f"+${stats['best']:,.2f}","--green"),("最差",f"-${abs(stats['worst']):,.2f}","--red"),
        ("連續盈利",f"{stats['max_win_streak']}筆","--muted"),("連續虧損",f"{stats['max_loss_streak']}筆","--muted"),
    ]
    card_html="".join(f'<div class="kpi"><span class="lbl">{l}</span><span class="val" style="color:var({c})">{v}</span></div>' for l,v,c in cards)
    chart_divs=[]
    chart_names={"equity":"淨值曲線 & 回撤","drawdown":"回撤走勢","monthly":"月度盈虧",
                 "pnl_dist":"盈虧分佈","symbol":"品種盈虧","rolling_wr":"滾動勝率 (30筆)",
                 "hourly":"交易時段","volume_dist":"手數分佈"}
    for key,w,h in[("equity","100%","400px"),("drawdown","100%","320px"),("monthly","100%","360px"),
                    ("pnl_dist","100%","300px"),("symbol","100%","320px"),("rolling_wr","100%","320px"),
                    ("hourly","100%","260px"),("volume_dist","100%","280px")]:
        label = chart_names.get(key, key)
        chart_divs.append(f'<div class="chart-card {"wide" if key in("equity","drawdown","monthly") else ""}"><div id="chart-{key}" style="width:100%;height:{h}"></div><div class="chart-label">{label}</div></div>')
    trade_data=[{"ticket":str(t["ticket"]),"open":t["open_time"].strftime("%Y-%m-%d %H:%M") if t["open_time"] else"-",
        "close":t["close_time"].strftime("%Y-%m-%d %H:%M") if t["close_time"] else"-","type":t["type"].upper(),
        "symbol":t["symbol"].upper(),"volume":t["volume"],"profit":round(t["profit"],2)} for t in trades]
    trade_json=json.dumps(trade_data,ensure_ascii=False)
    configs_json=json.dumps(chart_configs,ensure_ascii=False)
    date_info=f'<span class="filter-tag">📅 {date_from} ~ {date_to}</span>' if date_from or date_to else""
    pl_color="#69f0ae" if stats["total_pl"]>=0 else"#ff8a80"
    
    # Build HTML with string replacement (avoid .format() conflicts with JS braces)
    html=_HTML.replace("{ACCOUNT}",account).replace("{COUNT}",str(stats["count"]))
    html=html.replace("{PL}",f"${stats['total_pl']:+,.2f}").replace("{PL_COLOR}",pl_color)
    html=html.replace("{WR}",f"{stats['wr']:.0f}%").replace("{CARDS}",card_html)
    html=html.replace("{CHARTS}","".join(chart_divs)).replace("{TRADE_JSON}",trade_json)
    html=html.replace("{ECHART_CDN}",ECHARTS_CDN).replace("{CONFIGS}",configs_json)
    html=html.replace("{DATE_INFO}",date_info)
    return html

_HTML=r"""<!DOCTYPE html><html lang="zh-HK"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MT Desk — {ACCOUNT}</title>
<style>
:root,[data-theme="dark"]{--bg:#0f1119;--surface:#1a1f2e;--card:#1e2433;--border:#2d3446;--text:#e2e8f0;--muted:#64748b;--blue:#448aff;--green:#00e676;--red:#ff5252;--radius:8px}
[data-theme="light"]{--bg:#f0f2f5;--surface:#ffffff;--card:#ffffff;--border:#d1d5db;--text:#1f2937;--muted:#6b7280;--blue:#2563eb;--green:#059669;--red:#dc2626}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei','Helvetica Neue',sans-serif;background:var(--bg);color:var(--text);font-size:clamp(12px,1vw,15px);line-height:1.5;-webkit-font-smoothing:antialiased}
.header{background:var(--surface);border-bottom:1px solid var(--border);padding:clamp(10px,1vw,18px) clamp(14px,1.4vw,28px);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px}
.header h1{font-size:clamp(15px,1.3vw,20px);font-weight:600;color:var(--blue);display:flex;align-items:center;gap:8px}
.header .meta{font-size:clamp(10px,0.8vw,13px);color:var(--muted)}.header .meta b{color:var(--text)}
.theme-btn{background:var(--surface);border:1px solid var(--border);color:var(--muted);padding:4px 10px;border-radius:6px;cursor:pointer;font-size:clamp(10px,0.8vw,13px);font-family:inherit}.theme-btn:hover{border-color:var(--blue);color:var(--text)}
.filter-tag{display:inline-block;background:var(--surface);border:1px solid var(--border);border-radius:4px;padding:2px 8px;margin-left:8px;font-size:11px;color:var(--muted)}
.main{max-width:1440px;margin:0 auto;padding:clamp(10px,1vw,20px)}
.kpi-row{display:grid;grid-template-columns:repeat(auto-fill,minmax(clamp(110px,12vw,140px),1fr));gap:clamp(5px,0.5vw,8px);margin-bottom:clamp(10px,1vw,16px)}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:clamp(10px,0.9vw,14px);text-align:center}
.kpi .lbl{display:block;font-size:clamp(9px,0.7vw,11px);color:var(--muted);margin-bottom:4px}
.kpi .val{display:block;font-size:clamp(15px,1.3vw,20px);font-weight:700}
.section{margin-bottom:clamp(10px,1vw,16px)}
.section-title{font-size:clamp(11px,0.9vw,14px);color:var(--blue);font-weight:600;margin-bottom:clamp(5px,0.5vw,10px);padding-left:clamp(8px,0.7vw,14px);border-left:3px solid var(--blue)}
.charts{display:grid;grid-template-columns:1fr 1fr;gap:clamp(6px,0.6vw,10px)}
.chart-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;padding:8px}
.chart-card.wide{grid-column:1/-1}
.chart-label{text-align:center;font-size:clamp(10px,0.8vw,12px);color:var(--muted);padding:4px 0 2px;font-weight:500}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:8px}
.toolbar input{padding:6px 12px;border:1px solid var(--border);border-radius:6px;font-size:clamp(10px,0.8vw,13px);outline:none;background:var(--surface);color:var(--text);font-family:inherit;transition:border-color .2s;width:clamp(140px,18vw,200px)}
.toolbar input:focus{border-color:var(--blue)}.toolbar input::placeholder{color:var(--muted)}
.toolbar button,.toolbar select{padding:5px 12px;border:1px solid var(--border);border-radius:6px;background:var(--surface);color:var(--muted);cursor:pointer;font-size:clamp(10px,0.8vw,13px);font-family:inherit}
.toolbar button:hover{background:var(--card);border-color:var(--blue);color:var(--text)}
.toolbar .nav-btn{min-width:30px;text-align:center}.toolbar .page-info{font-size:clamp(10px,0.8vw,13px);color:var(--muted);margin:0 3px}
.table-wrap{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
table{width:100%;border-collapse:collapse;font-size:clamp(10px,0.8vw,13px)}
th{background:var(--surface);padding:clamp(6px,0.5vw,8px) clamp(8px,0.7vw,12px);text-align:left;font-weight:600;border-bottom:1px solid var(--border);cursor:pointer;user-select:none;white-space:nowrap;color:var(--muted);font-size:clamp(9px,0.7vw,11px)}
th:hover{color:var(--text)}th .sort-arrow{font-size:8px;margin-left:3px;color:var(--blue)}
td{padding:clamp(4px,0.4vw,6px) clamp(8px,0.7vw,12px);border-bottom:1px solid var(--border);color:var(--text)}
tr:hover td{background:var(--surface)}.win{color:var(--green)!important;font-weight:500}.loss{color:var(--red)!important;font-weight:500}
tr.highlight td{outline:2px solid #ff9100;outline-offset:-1px}
@media(max-width:768px){.charts{grid-template-columns:1fr}.kpi-row{grid-template-columns:repeat(3,1fr)}}
</style></head><body>
<div class="header"><div><h1>MT Desk <span style="font-weight:300;font-size:clamp(10px,0.8vw,13px);color:var(--muted);margin-left:4px">— {ACCOUNT}</span></h1></div>
<div style="display:flex;align-items:center;gap:12px">
  <div class="meta">{COUNT} 筆交易 · P/L: <b style="color:{PL_COLOR}">{PL}</b> · 勝率: <b>{WR}</b>{DATE_INFO}</div>
  <button class="theme-btn" onclick="toggleTheme()" id="themeBtn">🌓</button>
</div></div>
<div class="main"><div class="kpi-row">{CARDS}</div>
<div class="section"><div class="section-title">權益與統計</div><div class="charts">{CHARTS}</div></div>
<div class="section"><div class="section-title">逐筆明細</div>
<div class="toolbar"><input type="text" id="searchBox" placeholder="搜尋 Ticket..." oninput="doSearch()">
<span id="searchInfo" style="font-size:clamp(10px,0.8vw,13px);color:var(--muted)"></span><span style="flex:1"></span>
<span class="page-info">每頁</span><select id="pageSize" onchange="pageSize=+this.value;currentPage=1;renderTable()">
<option value="15" selected>15</option><option value="30">30</option><option value="50">50</option><option value="100">100</option></select><span class="page-info">筆</span>
<button class="nav-btn" onclick="currentPage=1;renderTable()">«</button><button class="nav-btn" onclick="if(currentPage>1){currentPage--;renderTable()}">‹</button>
<span class="page-info" id="pageInfo"></span><button class="nav-btn" onclick="if(currentPage<totalPages){currentPage++;renderTable()}">›</button>
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
<button class="nav-btn" onclick="currentPage=1;renderTable()">«</button><button class="nav-btn" onclick="if(currentPage>1){currentPage--;renderTable()}">‹</button>
<button class="nav-btn" onclick="if(currentPage<totalPages){currentPage++;renderTable()}">›</button>
<button class="nav-btn" onclick="currentPage=totalPages;renderTable()">»</button></div></div></div>
<script src="{ECHART_CDN}"></script>
<script>
var CONFIGS={CONFIGS};
(function(){var s=localStorage.getItem('mt-theme');var m=window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light';document.documentElement.setAttribute('data-theme',s||m);})();
window.matchMedia('(prefers-color-scheme:dark)').addEventListener('change',function(e){if(!localStorage.getItem('mt-theme')){document.documentElement.setAttribute('data-theme',e.matches?'dark':'light');initCharts();}});
function toggleTheme(){var c=document.documentElement.getAttribute('data-theme');var n=c==='dark'?'light':'dark';document.documentElement.setAttribute('data-theme',n);localStorage.setItem('mt-theme',n);initCharts();}
function initCharts(){
  var isDark=document.documentElement.getAttribute('data-theme')==='dark';
  var tc=isDark?'#e2e8f0':'#1f2937';var mc=isDark?'#64748b':'#6b7280';
  ['equity','drawdown','monthly','pnl_dist','symbol','rolling_wr','hourly','volume_dist'].forEach(function(k){
    var el=document.getElementById('chart-'+k);if(!el||!CONFIGS[k]||CONFIGS[k]==='null')return;
    if(el._echart)el._echart.dispose();
    var opt=JSON.parse(CONFIGS[k]);
    if(opt.legend&&opt.legend.textStyle)opt.legend.textStyle.color=tc;
    ['xAxis','yAxis'].forEach(function(a){
      var ax=opt[a];if(!ax)return;
      if(Array.isArray(ax))ax.forEach(function(x){if(x.axisLabel)x.axisLabel.color=mc;if(x.nameTextStyle)x.nameTextStyle.color=mc;});
      else{if(ax.axisLabel)ax.axisLabel.color=mc;if(ax.nameTextStyle)ax.nameTextStyle.color=mc;}
    });
    var chart=echarts.init(el,isDark?'dark':null);
    chart.setOption(opt);el._echart=chart;
  });
}
window.addEventListener('resize',function(){['equity','drawdown','monthly','pnl_dist','symbol','rolling_wr','hourly','volume_dist'].forEach(function(k){var el=document.getElementById('chart-'+k);if(el&&el._echart)el._echart.resize();});});
initCharts();

var ALL={TRADE_JSON};var data=ALL.slice();var sortCol='profit',sortDir=-1;var currentPage=1,pageSize=15,totalPages=1;var searchIdx=-1,searchMatches=[];
function sortBy(col){if(sortCol===col)sortDir*=-1;else{sortCol=col;sortDir=-1;}data.sort(function(a,b){var va=a[col],vb=b[col];if(typeof va==='number')return(va-vb)*sortDir;return String(va).localeCompare(String(vb))*sortDir;});currentPage=1;renderTable();document.querySelectorAll('.sort-arrow').forEach(function(el){el.textContent='';});var arrow=document.getElementById('sa-'+col);if(arrow)arrow.textContent=sortDir>0?'▲':'▼';}
function doSearch(){var q=document.getElementById('searchBox').value.trim().toLowerCase();searchMatches=[];searchIdx=-1;if(!q){data=ALL.slice();document.getElementById('searchInfo').textContent='';}else{data=ALL.filter(function(t){return String(t.ticket).toLowerCase().indexOf(q)>=0;});document.getElementById('searchInfo').textContent=data.length+' 條匹配';ALL.forEach(function(t,i){if(String(t.ticket).toLowerCase().indexOf(q)>=0)searchMatches.push(i);});}currentPage=1;renderTable();}
document.getElementById('searchBox').addEventListener('keydown',function(e){if(e.key==='Enter'&&searchMatches.length>0){e.preventDefault();searchIdx=(searchIdx+1)%searchMatches.length;var gi=searchMatches[searchIdx];currentPage=Math.floor(gi/pageSize)+1;renderTable();setTimeout(function(){var rows=document.querySelectorAll('#tradeBody tr');rows.forEach(function(r){r.classList.remove('highlight');});var li=gi%pageSize;if(rows[li]){rows[li].classList.add('highlight');rows[li].scrollIntoView({behavior:'smooth',block:'center'});}document.getElementById('searchInfo').textContent=(searchIdx+1)+'/'+searchMatches.length+' 條匹配';},30);}});
function renderTable(){totalPages=Math.ceil(data.length/pageSize)||1;if(currentPage>totalPages)currentPage=totalPages;var start=(currentPage-1)*pageSize;var page=data.slice(start,start+pageSize);var h='';page.forEach(function(t){h+='<tr class="'+(t.profit>0?'win':'loss')+'"><td>'+t.ticket+'</td><td>'+t.open+'</td><td>'+t.type+'</td><td>'+t.volume+'</td><td>'+t.symbol+'</td><td>'+t.close+'</td><td>$'+t.profit.toFixed(2)+'</td></tr>';});document.getElementById('tradeBody').innerHTML=h;var info=currentPage+'/'+totalPages+' ('+data.length+'筆)';document.getElementById('pageInfo').textContent=info;document.getElementById('pageInfo2').textContent=info;}
renderTable();document.getElementById('sa-profit').textContent='▼';</script></body></html>"""

def process_file(path,date_from=None,date_to=None):
    result=parse_statement(path);trades=result["trades"]
    if not trades:messagebox.showerror("失敗","未找到交易記錄");return
    if date_from or date_to:
        trades=[t for t in trades if t.get("open_time") and (not date_from or t["open_time"].date()>=date_from) and (not date_to or t["open_time"].date()<=date_to)]
        if not trades:messagebox.showerror("失敗","篩選後無交易記錄");return
    stats=analyze(trades)
    html=build_dashboard_html(result["account"],trades,stats,date_from,date_to)
    out=Path(tempfile.gettempdir())/f"MT_Desk_{result['account']}.html"
    out.write_text(html,encoding="utf-8")
    threading.Timer(0.3,lambda:webbrowser.open(out.as_uri())).start()
    return result,len(trades)

def main():
    root=tk.Tk();root.title("MT Desk");root.geometry("440x350")
    root.configure(bg="#f0f2f5");root.resizable(False,False)
    tk.Label(root,text="MT Desk",font=("Segoe UI",22,"bold"),fg="#2563eb",bg="#f0f2f5").pack(pady=(20,4))
    tk.Label(root,text="ECharts · 瀏覽器原生渲染 · 時間軸",font=("Segoe UI",10),fg="#6b7280",bg="#f0f2f5").pack(pady=(0,14))
    dframe=tk.Frame(root,bg="#f0f2f5")
    tk.Label(dframe,text="篩選日期:",font=("Segoe UI",9),fg="#6b7280",bg="#f0f2f5").pack(side=tk.LEFT,padx=(0,6))
    dfrom_var=tk.StringVar();dto_var=tk.StringVar()
    for v in[dfrom_var,dto_var]:tk.Entry(dframe,textvariable=v,width=12,font=("Segoe UI",9)).pack(side=tk.LEFT,padx=2)
    tk.Label(dframe,text="~",font=("Segoe UI",9),fg="#6b7280",bg="#f0f2f5").pack(side=tk.LEFT,padx=2)
    tk.Label(dframe,text="YYYY-MM-DD",font=("Segoe UI",8),fg="#9ca3af",bg="#f0f2f5").pack(side=tk.LEFT,padx=(4,0))
    dframe.pack(pady=(0,14))
    status_var=tk.StringVar(value="選擇 HTML 報表檔案")
    status=tk.Label(root,textvariable=status_var,font=("Segoe UI",9),fg="#6b7280",bg="#f0f2f5");status.pack(pady=(0,12))
    def open_file():
        paths=filedialog.askopenfilenames(title="選擇 MT4/MT5 報表",filetypes=[("HTML","*.htm *.html")])
        if not paths:return
        df=dt=None
        try:
            s=dfrom_var.get().strip()
            if s:df=datetime.strptime(s,"%Y-%m-%d").date()
            s=dto_var.get().strip()
            if s:dt=datetime.strptime(s,"%Y-%m-%d").date()
        except:pass
        total=len(paths)
        for i,path in enumerate(paths,1):
            fname=Path(path).name;status_var.set(f"⏳ ({i}/{total}): {fname}");root.update()
            try:process_file(path,df,dt)
            except Exception as e:messagebox.showerror("錯誤",str(e))
        status_var.set(f"✅ 完成 — {total} 個檔案")
    tk.Button(root,text="📂 選擇 MT4/MT5 HTML 報表",font=("Segoe UI",12),bg="#2563eb",fg="white",
        relief="flat",padx=24,pady=10,command=open_file,cursor="hand2").pack(pady=(0,8))
    root.mainloop()

if __name__=="__main__":main()
