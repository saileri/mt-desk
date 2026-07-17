#!/usr/bin/env python3
"""MT Desk v2 — Python pre-processor + browser dashboard.

Pipeline:
  Large MT4/MT5 HTML (500MB+) → Python streaming parser → Slim HTML
  → Auto-opens in browser → Chart.js renders all charts client-side
  Zero file upload limits (native file dialog). Zero server needed after generation.
"""
import base64, io, os, sys, tempfile, tkinter as tk, json, threading, webbrowser
from tkinter import filedialog, messagebox
from pathlib import Path
from mt_desk.parser import parse_statement
from mt_desk.analysis import analyze
from mt_desk.charts import *

if sys.stdout is None: sys.stdout = io.StringIO()
if sys.stderr is None: sys.stderr = sys.stdout

THRESHOLD = 50 * 1024 * 1024  # 50MB — above this, slim mode only

def build_slim_html(account: str, trades: list) -> str:
    rows = []
    for t in sorted(trades, key=lambda x: x["profit"], reverse=True):
        ot = t["open_time"].strftime("%Y-%m-%d %H:%M") if t["open_time"] else "-"
        ct = t["close_time"].strftime("%Y-%m-%d %H:%M") if t["close_time"] else "-"
        pl, sw, cm = t["profit"], t.get("swap",0), t.get("commission",0)
        cl = "pos" if pl > 0 else "neg"
        rows.append(f'<tr class="{cl}"><td>{t["ticket"]}</td><td>{ot}</td><td>{t["type"]}</td>'
                    f'<td>{t["volume"]}</td><td>{t["symbol"].upper()}</td><td>{ct}</td>'
                    f'<td>${pl:+,.2f}</td><td>${sw:+,.2f}</td><td>${cm:+,.2f}</td></tr>')
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8">
<title>MT4/MT5 Slim — {account}</title>
<style>body{{font-family:monospace;font-size:11px;margin:8px;background:#f8fafc}}
h2{{color:#2563eb}}p{{color:#6b7280;font-size:10px}}
table{{border-collapse:collapse;width:100%;font-size:10px}}
th{{background:#f1f5f9;padding:4px 6px;text-align:left;font-weight:600;border-bottom:2px solid #2563eb;position:sticky;top:0}}
td{{padding:2px 6px;border-bottom:1px solid #e5e7eb}}
tr:hover td{{background:#f0f4ff}}.pos{{color:#10b981}}.neg{{color:#ef4444}}
</style></head><body><h2>MT4/MT5 Slim — Account {account}</h2>
<p>{len(trades)} trades</p><div style="max-height:90vh;overflow:auto">
<table><thead><tr><th>Ticket</th><th>Open</th><th>Type</th><th>Vol</th><th>Symbol</th><th>Close</th><th>P/L</th><th>Swap</th><th>Comm</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div></body></html>"""


def build_dashboard_html(account: str, trades: list, stats: dict) -> str:
    charts = {k: fn(stats) for k, fn in [
        ("equity", chart_equity), ("symbol", chart_symbol), ("monthly", chart_monthly),
        ("winloss", chart_winloss), ("hourly", chart_hourly), ("streaks", chart_streaks)]}
    cards = [
        ("总交易", str(stats["count"])), ("总盈亏", f"${stats['total_pl']:+,.2f}", "#10b981" if stats["total_pl"]>=0 else "#ef4444"),
        ("胜率", f"{stats['wr']:.0f}%", "#10b981"), ("盈利因子", f"{stats['pf']:.2f}" if stats["pf"]!=float("inf") else "∞"),
        ("最大回撤", f"${stats['max_dd']:,.2f}", "#ef4444"), ("夏普比率", f"{stats['sharpe']:.2f}"),
        ("最佳", f"+${stats['best']:,.2f}", "#10b981"), ("最差", f"-${abs(stats['worst']):,.2f}", "#ef4444"),
        ("连续盈利", f"{stats['max_win_streak']}笔"), ("连续亏损", f"{stats['max_loss_streak']}笔")]
    card_html = "".join(f'<div class="card"><div class="cl">{l}</div><div class="cv" style="color:{c}">{v}</div></div>'
                        for l, v, c in [(it[0], it[1], it[2] if len(it)>2 else "#1f2937") for it in cards])
    chart_blocks = []
    for key, cls in [("equity","chart-wide"),("symbol",""),("winloss",""),("monthly","chart-wide"),("streaks",""),("hourly","")]:
        if charts.get(key):
            chart_blocks.append(f'<div class="{cls}"><img src="data:image/png;base64,{charts[key]}"></div>')
    trade_data = [{"ticket": str(t["ticket"]),
        "open": t["open_time"].strftime("%Y-%m-%d %H:%M") if t["open_time"] else "-",
        "close": t["close_time"].strftime("%Y-%m-%d %H:%M") if t["close_time"] else "-",
        "type": t["type"].upper(), "symbol": t["symbol"].upper(),
        "volume": t["volume"], "profit": round(t["profit"],2)} for t in trades]
    trade_json = json.dumps(trade_data, ensure_ascii=False)
    return _HTML_TEMPLATE.format(account=account, count=stats["count"],
        pl=f"${stats['total_pl']:+,.2f}", wr=f"{stats['wr']:.0f}%",
        cards=card_html, charts="".join(chart_blocks), trade_json=trade_json)

_HTML_TEMPLATE = r"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8">
<title>MT Desk — {account}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI','Microsoft YaHei',system-ui;background:#f8fafc;color:#1f2937;font-size:clamp(11px,1.1vw,14px);padding:clamp(8px,1vw,16px);max-width:1300px;margin:0 auto}}
h1{{font-size:clamp(15px,1.5vw,20px);color:#2563eb;margin-bottom:2px}}
.sub{{font-size:clamp(10px,0.9vw,12px);color:#6b7280;margin-bottom:12px}}
.cards{{display:flex;flex-wrap:wrap;gap:clamp(3px,0.4vw,6px);margin-bottom:12px}}
.card{{flex:1;min-width:clamp(70px,8vw,95px);background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:clamp(5px,0.6vw,8px) clamp(6px,0.8vw,10px);text-align:center}}
.card .cl{{font-size:clamp(7px,0.7vw,9px);color:#6b7280}}
.card .cv{{font-size:clamp(11px,1.1vw,15px);font-weight:700}}
.charts{{display:grid;grid-template-columns:1fr 1fr;gap:clamp(6px,0.8vw,10px);margin-bottom:12px}}
.charts img{{width:100%;display:block;border-radius:6px}}
.chart-wide{{grid-column:1/-1}}
h3{{font-size:clamp(11px,1vw,14px);color:#2563eb;margin:8px 0 4px}}
.toolbar{{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:8px}}
.toolbar input{{padding:4px 8px;border:1px solid #d1d5db;border-radius:4px;font-size:clamp(9px,0.8vw,11px);width:clamp(120px,16vw,180px)}}
.toolbar button,.toolbar select{{padding:3px 8px;border:1px solid #d1d5db;border-radius:4px;background:#fff;cursor:pointer;font-size:clamp(9px,0.8vw,11px)}}
.toolbar button:hover{{background:#f0f4ff;border-color:#2563eb}}
.toolbar .active{{background:#2563eb;color:#fff;border-color:#2563eb}}
.toolbar .page-info{{font-size:clamp(9px,0.8vw,11px);color:#6b7280;margin:0 4px}}
table{{width:100%;border-collapse:collapse;font-size:clamp(8px,0.8vw,11px)}}
th{{background:#f1f5f9;padding:clamp(4px,0.5vw,6px) clamp(5px,0.6vw,8px);text-align:left;font-weight:600;border-bottom:2px solid #2563eb;cursor:pointer;user-select:none;white-space:nowrap;position:sticky;top:0;z-index:1}}
th:hover{{background:#dbeafe}}
th .sort-arrow{{font-size:9px;margin-left:2px;color:#9ca3af}}
td{{padding:clamp(2px,0.3vw,4px) clamp(5px,0.6vw,8px);border-bottom:1px solid #e5e7eb}}
tr:hover td{{background:#f0f4ff}}.win{{color:#10b981}}.loss{{color:#ef4444}}
tr.highlight td{{background:#fef3c7!important;outline:2px solid #f59e0b}}
@media(max-width:768px){{.charts{{grid-template-columns:1fr}}.cards{{grid-template-columns:repeat(3,1fr)}}}}
</style></head><body>
<h1>📊 MT Desk — {account}</h1>
<div class="sub">{count} trades · P/L: {pl} · 胜率: {wr}</div>
<div class="cards">{cards}</div>
<div class="charts">{charts}</div>
<h3>📋 逐笔明细</h3>
<div class="toolbar">
  <input type="text" id="searchBox" placeholder="🔍 搜索 Ticket..." oninput="doSearch()">
  <span id="searchInfo" style="font-size:clamp(9px,0.8vw,11px);color:#6b7280"></span>
  <span style="flex:1"></span>
  <span class="page-info">每页</span>
  <select id="pageSize" onchange="pageSize=+this.value;currentPage=1;renderTable()">
    <option value="15" selected>15</option><option value="30">30</option><option value="50">50</option><option value="100">100</option>
  </select>
  <span class="page-info">笔</span>
  <button onclick="currentPage=1;renderTable()">«</button>
  <button onclick="if(currentPage>1){{currentPage--;renderTable()}}">‹</button>
  <span class="page-info" id="pageInfo"></span>
  <button onclick="if(currentPage<totalPages){{currentPage++;renderTable()}}">›</button>
  <button onclick="currentPage=totalPages;renderTable()">»</button>
</div>
<table><thead><tr>
  <th onclick="sortBy('ticket')">Ticket<span class="sort-arrow" id="sa-ticket"></span></th>
  <th onclick="sortBy('open')">开仓<span class="sort-arrow" id="sa-open"></span></th>
  <th onclick="sortBy('type')">方向<span class="sort-arrow" id="sa-type"></span></th>
  <th onclick="sortBy('volume')">手数<span class="sort-arrow" id="sa-volume"></span></th>
  <th onclick="sortBy('symbol')">品种<span class="sort-arrow" id="sa-symbol"></span></th>
  <th onclick="sortBy('close')">平仓<span class="sort-arrow" id="sa-close"></span></th>
  <th onclick="sortBy('profit')">盈亏<span class="sort-arrow" id="sa-profit"></span></th>
</tr></thead>
<tbody id="tradeBody"></tbody></table>
<div class="toolbar" style="justify-content:flex-end;margin-top:6px">
  <span class="page-info" id="pageInfo2"></span>
  <button onclick="currentPage=1;renderTable()">«</button>
  <button onclick="if(currentPage>1){{currentPage--;renderTable()}}">‹</button>
  <button onclick="if(currentPage<totalPages){{currentPage++;renderTable()}}">›</button>
  <button onclick="currentPage=totalPages;renderTable()">»</button>
</div>
<script>
var ALL={trade_json};
var data=ALL.slice();
var sortCol='profit',sortDir=-1;
var currentPage=1,pageSize=15,totalPages=1;
var searchIdx=-1,searchMatches=[];

function sortBy(col){{
  if(sortCol===col)sortDir*=-1;else{{sortCol=col;sortDir=-1;}}
  data.sort(function(a,b){{var va=a[col],vb=b[col];
    if(typeof va==='number')return(va-vb)*sortDir;
    return String(va).localeCompare(String(vb))*sortDir;}});
  currentPage=1;renderTable();
  document.querySelectorAll('.sort-arrow').forEach(function(el){{el.textContent='';}});
  var arrow=document.getElementById('sa-'+col);
  if(arrow)arrow.textContent=sortDir>0?'▲':'▼';
}}

function doSearch(){{
  var q=document.getElementById('searchBox').value.trim().toLowerCase();
  searchMatches=[];searchIdx=-1;
  if(!q){{data=ALL.slice();document.getElementById('searchInfo').textContent='';}}
  else{{
    data=ALL.filter(function(t){{return String(t.ticket).toLowerCase().indexOf(q)>=0;}});
    document.getElementById('searchInfo').textContent=data.length+' 条匹配';
    ALL.forEach(function(t,i){{if(String(t.ticket).toLowerCase().indexOf(q)>=0)searchMatches.push(i);}});
  }}
  currentPage=1;renderTable();
}}

document.getElementById('searchBox').addEventListener('keydown',function(e){{
  if(e.key==='Enter'&&searchMatches.length>0){{
    e.preventDefault();
    searchIdx=(searchIdx+1)%searchMatches.length;
    var globalIdx=searchMatches[searchIdx];
    var page=Math.floor(globalIdx/pageSize)+1;
    currentPage=page;renderTable();
    setTimeout(function(){{
      var rows=document.querySelectorAll('#tradeBody tr');
      rows.forEach(function(r){{r.classList.remove('highlight');}});
      var localIdx=globalIdx%pageSize;
      if(rows[localIdx]){{rows[localIdx].classList.add('highlight');rows[localIdx].scrollIntoView({{behavior:'smooth',block:'center'}});}}
      document.getElementById('searchInfo').textContent=(searchIdx+1)+'/'+searchMatches.length+' 条匹配';
    }},30);
  }}
}});

function renderTable(){{
  totalPages=Math.ceil(data.length/pageSize)||1;
  if(currentPage>totalPages)currentPage=totalPages;
  var start=(currentPage-1)*pageSize;
  var page=data.slice(start,start+pageSize);
  var h='';
  page.forEach(function(t){{
    h+='<tr class="'+(t.profit>0?'win':'loss')+'"><td>'+t.ticket+'</td><td>'+t.open+'</td><td>'+t.type+'</td><td>'+t.volume+'</td><td>'+t.symbol+'</td><td>'+t.close+'</td><td>$'+t.profit.toFixed(2)+'</td></tr>';
  }});
  document.getElementById('tradeBody').innerHTML=h;
  var info=currentPage+'/'+totalPages+' ('+data.length+'笔)';
  document.getElementById('pageInfo').textContent=info;
  document.getElementById('pageInfo2').textContent=info;
}}

renderTable();
document.getElementById('sa-profit').textContent='▼';
</script></body></html>"""


def process_file(path: str):
    filepath = Path(path)
    size = filepath.stat().st_size
    if size > THRESHOLD:
        result = parse_statement(path)
        trades = result["trades"]
        if not trades: messagebox.showerror("失败", "未找到交易记录"); return
        html = build_slim_html(result["account"], trades); kind = "Slim"
    else:
        result = parse_statement(path)
        trades = result["trades"]
        if not trades: messagebox.showerror("失败", "未找到交易记录"); return
        stats = analyze(trades)
        html = build_dashboard_html(result["account"], trades, stats); kind = "Dashboard"
    out = Path(tempfile.gettempdir()) / f"MT_Desk_{result['account']}.html"
    out.write_text(html, encoding="utf-8")
    threading.Timer(0.3, lambda: webbrowser.open(out.as_uri())).start()
    return result, kind


def main():
    root = tk.Tk()
    root.title("MT Desk v2")
    root.geometry("440x280")
    root.configure(bg="#f8fafc"); root.resizable(False, False)
    tk.Label(root, text="📊 MT Desk", font=("Segoe UI", 18, "bold"), fg="#2563eb", bg="#f8fafc").pack(pady=(24,4))
    tk.Label(root, text="MT4/MT5 → 自动解析 → 浏览器图表", font=("Segoe UI", 10), fg="#6b7280", bg="#f8fafc").pack(pady=(0,16))
    status_var = tk.StringVar(value="选择 HTML 报表文件")
    status = tk.Label(root, textvariable=status_var, font=("Segoe UI", 9), fg="#6b7280", bg="#f8fafc")
    status.pack(pady=(0,12))
    def open_file():
        path = filedialog.askopenfilename(title="选择 MT4/MT5 报表", filetypes=[("HTML", "*.htm *.html"), ("All", "*.*")])
        if not path: return
        fname = Path(path).name; size_mb = Path(path).stat().st_size / 1024 / 1024
        status_var.set(f"⏳ 解析中: {fname} ({size_mb:.1f}MB)..."); root.update()
        try:
            res, kind = process_file(path)
            status_var.set(f"✅ {kind} — {res['account']} — {len(res['trades'])}笔")
        except Exception as e:
            status_var.set(f"❌ {e}"); messagebox.showerror("错误", str(e))
    btn = tk.Button(root, text="📂 选择 MT4/MT5 HTML 报表", font=("Segoe UI", 12), bg="#2563eb", fg="white",
                    relief="flat", padx=24, pady=10, command=open_file, cursor="hand2")
    btn.pack(pady=(0,6))
    tk.Label(root, text="小文件→完整图表  ·  超大文件(>50MB)→精简表格", font=("Segoe UI", 9), fg="#6b7280", bg="#f8fafc").pack()
    tk.Label(root, text="浏览器只显示不计算 · 零上传限制", font=("Segoe UI", 9), fg="#6b7280", bg="#f8fafc").pack()
    root.mainloop()

if __name__ == "__main__":
    main()
