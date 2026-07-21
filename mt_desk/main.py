#!/usr/bin/env python3
"""MT Desk v5 — Symbol preference pie, volume, swap summary. 13-column trade table."""
import json,io,os,sys,tempfile,tkinter as tk,threading,webbrowser
from tkinter import filedialog,messagebox
from datetime import datetime
from pathlib import Path
from mt_desk.parser import parse_statement
from mt_desk.analysis import analyze
# charts module no longer used (v5 replaced charts with summary section)

if sys.stdout is None:sys.stdout=io.StringIO()
if sys.stderr is None:sys.stderr=sys.stdout
ECHARTS_CDN="https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js"

def build_dashboard_html(account,trades,stats):
    avg_w=stats["avg_win"];avg_l=abs(stats["avg_loss"]);plr=avg_w/avg_l if avg_l>0 else 0
    cards=[
        ("總交易",str(stats["count"]),"總交易筆數",""),
        ("總盈虧",f"${stats['total_pl']:+,.2f}","所有交易的淨盈虧金額總和","--green" if stats["total_pl"]>=0 else"--red"),
        ("勝率",f"{stats['wr']:.0f}%","盈利交易數 ÷ 總交易數 × 100%","--green"),
        ("平均盈利",f"+${avg_w:,.2f}","盈利交易的平均獲利金額","--green"),
        ("平均虧損",f"-${avg_l:,.2f}","虧損交易的平均損失金額","--red"),
        ("盈虧比",f"{plr:.2f}","平均盈利 ÷ 平均虧損，<1 表示每賺 1 元要賠更多元，即使勝率高也會虧損","--muted" if plr<1 else"--green"),
        ("盈利因子",f"{stats['pf']:.2f}" if stats["pf"]!=float("inf") else"∞","總盈利 ÷ 總虧損絕對值，<1 代表虧損策略","--muted"),
        ("最大回撤",f"${stats['max_dd']:,.2f}","權益曲線從最高點到最低點的最大跌幅","--red"),
        ("夏普比率",f"{stats['sharpe']:.2f}","風險調整後報酬，<0 表示平均每日回報為負","--muted"),
        ("最佳",f"+${stats['best']:,.2f}","單筆最大盈利","--green"),
        ("最差",f"-${abs(stats['worst']):,.2f}","單筆最大虧損","--red"),
    ]
    card_html="".join(f'<div class="kpi has-tip"><span class="lbl">{l}</span><span class="val" style="color:var({c})">{v}</span><span class="tip">{tip}</span></div>' for l,v,tip,c in cards)
    # ── v5 top section: symbol pie, volume, swap ──
    sym_pie_data=[{"name":s.upper(),"value":c} for s,c in stats["sym_count"].items()]
    sym_pie_json=json.dumps(sym_pie_data,ensure_ascii=False)
    total_swap_val=stats["total_swap"]
    total_volume_val=stats["total_volume"]
    swap_color="#00e676" if total_swap_val>=0 else"#ff5252"
    summary_html=f'''<div class="summary-row">
  <div class="summary-card" style="grid-column:span 2">
    <div class="summary-title">品種偏好（交易次數佔比）</div>
    <div id="chart-symbol-pie" style="width:100%;height:300px"></div>
  </div>
  <div class="summary-card">
    <div class="summary-title">交易量</div>
    <div class="summary-val">{total_volume_val:.2f} 手</div>
    <div class="summary-sub">總交易手數</div>
  </div>
  <div class="summary-card">
    <div class="summary-title">Swap / 利息</div>
    <div class="summary-val" style="color:{swap_color}">${total_swap_val:+,.2f}</div>
    <div class="summary-sub">累計隔夜利息</div>
  </div>
</div>'''
    # All trades as JSON (for client-side date filtering)
    all_trades=[{
        "ticket":str(t["ticket"]),
        "open":t["open_time"].strftime("%Y-%m-%d %H:%M") if t["open_time"] else"-",
        "close":t["close_time"].strftime("%Y-%m-%d %H:%M") if t["close_time"] else"-",
        "type":t["type"].upper(),
        "volume":t["volume"],
        "symbol":t["symbol"].upper(),
        "open_price":round(t.get("open_price",0),5),
        "close_price":round(t.get("close_price",0),5),
        "sl":round(t.get("sl",0),5),
        "tp":round(t.get("tp",0),5),
        "commission":round(t.get("commission",0),2),
        "swap":round(t.get("swap",0),2),
        "profit":round(t["profit"],2),
        "open_date":t["open_time"].strftime("%Y-%m-%d") if t["open_time"] else"",
    } for t in trades]
    trade_json=json.dumps(all_trades,ensure_ascii=False)
    pl_color="#69f0ae" if stats["total_pl"]>=0 else"#ff8a80"
    # Date range for the full data
    all_dates=sorted(set(t["open_date"] for t in all_trades if t["open_date"]))
    date_min=all_dates[0] if all_dates else""
    date_max=all_dates[-1] if all_dates else""
    html=_HTML.replace("{ACCOUNT}",account).replace("{COUNT}",str(stats["count"]))
    html=html.replace("{PL}",f"${stats['total_pl']:+,.2f}").replace("{PL_COLOR}",pl_color)
    html=html.replace("{WR}",f"{stats['wr']:.0f}%").replace("{CARDS}",card_html)
    html=html.replace("{CHARTS}",summary_html).replace("{TRADE_JSON}",trade_json)
    html=html.replace("{ECHART_CDN}",ECHARTS_CDN).replace("{SYM_PIE_DATA}",sym_pie_json)
    html=html.replace("{DATE_MIN}",date_min).replace("{DATE_MAX}",date_max)
    return html

_HTML=r"""<!DOCTYPE html><html lang="zh-HK"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MT Desk — {ACCOUNT}</title>
<style>
:root,[data-theme="dark"]{--bg:#0f1119;--surface:#1a1f2e;--card:#1e2433;--border:#2d3446;--text:#e2e8f0;--muted:#64748b;--blue:#448aff;--green:#00e676;--red:#ff5252;--radius:8px}
[data-theme="light"]{--bg:#f0f2f5;--surface:#ffffff;--card:#ffffff;--border:#d1d5db;--text:#1f2937;--muted:#6b7280;--blue:#2563eb;--green:#059669;--red:#dc2626}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei','Helvetica Neue',sans-serif;background:var(--bg);color:var(--text);font-size:clamp(12px,1vw,15px);line-height:1.5;-webkit-font-smoothing:antialiased}
.header{background:var(--surface);border-bottom:1px solid var(--border);padding:clamp(10px,1vw,18px) clamp(14px,1.4vw,28px);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px}
.header h1{font-size:clamp(15px,1.3vw,20px);font-weight:600;color:var(--blue)}
.header .meta{font-size:clamp(10px,0.8vw,13px);color:var(--muted)}.header .meta b{color:var(--text)}
.theme-btn{background:var(--surface);border:1px solid var(--border);color:var(--muted);padding:4px 10px;border-radius:6px;cursor:pointer;font-size:clamp(10px,0.8vw,13px);font-family:inherit}.theme-btn:hover{border-color:var(--blue);color:var(--text)}
.date-bar{display:flex;align-items:center;gap:8px;padding:8px clamp(14px,1.4vw,28px);background:var(--surface);border-bottom:1px solid var(--border)}
.date-bar input{padding:4px 8px;border:1px solid var(--border);border-radius:4px;font-size:clamp(10px,0.8vw,12px);background:var(--bg);color:var(--text);font-family:inherit}
.date-bar button{padding:4px 12px;border:1px solid var(--border);border-radius:4px;background:var(--card);color:var(--text);cursor:pointer;font-size:clamp(10px,0.8vw,12px);font-family:inherit}.date-bar button:hover{border-color:var(--blue)}
.date-bar .lbl{font-size:clamp(9px,0.7vw,11px);color:var(--muted)}
.main{max-width:1440px;margin:0 auto;padding:clamp(10px,1vw,20px)}
.kpi-row{display:grid;grid-template-columns:repeat(auto-fill,minmax(clamp(110px,12vw,140px),1fr));gap:clamp(5px,0.5vw,8px);margin-bottom:clamp(10px,1vw,16px)}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:clamp(10px,0.9vw,14px);text-align:center}
.kpi .lbl{display:block;font-size:clamp(9px,0.7vw,11px);color:var(--muted);margin-bottom:4px}
.kpi .val{display:block;font-size:clamp(15px,1.3vw,20px);font-weight:700}
.kpi.has-tip{position:relative;cursor:help}
.kpi .tip{display:none;position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:11px;line-height:1.4;white-space:normal;max-width:220px;text-align:left;z-index:100;box-shadow:0 4px 12px rgba(0,0,0,.15);pointer-events:none}
.kpi.has-tip .tip::after{content:'';position:absolute;top:100%;left:50%;transform:translateX(-50%);border:6px solid transparent;border-top-color:var(--border)}
.kpi.has-tip:hover .tip{display:block}
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
.table-wrap{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:clamp(10px,0.8vw,13px)}
th{background:var(--surface);padding:clamp(6px,0.5vw,8px) clamp(8px,0.7vw,12px);text-align:left;font-weight:600;border-bottom:1px solid var(--border);cursor:pointer;user-select:none;white-space:nowrap;color:var(--muted);font-size:clamp(9px,0.7vw,11px)}
th:hover{color:var(--text)}th .sort-arrow{font-size:8px;margin-left:3px;color:var(--blue)}
td{padding:clamp(4px,0.4vw,6px) clamp(8px,0.7vw,12px);border-bottom:1px solid var(--border);color:var(--text)}
tr:hover td{background:var(--surface)}.win{color:var(--green)!important}.loss{color:var(--red)!important}
tr.highlight td{outline:2px solid #ff9100;outline-offset:-1px}
.summary-row{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:10px;margin-bottom:16px}
.summary-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:16px;display:flex;flex-direction:column;justify-content:center;min-height:120px}
.summary-title{font-size:12px;color:var(--muted);margin-bottom:8px;font-weight:500}
.summary-val{font-size:28px;font-weight:700;color:var(--text)}
.summary-sub{font-size:11px;color:var(--muted);margin-top:4px}
@media(max-width:768px){.summary-row{grid-template-columns:1fr 1fr}.charts{grid-template-columns:1fr}.kpi-row{grid-template-columns:repeat(3,1fr)}}
</style></head><body>
<div class="header"><h1>MT Desk — {ACCOUNT}</h1>
<div style="display:flex;align-items:center;gap:12px">
  <div class="meta"><span id="headerCount">{COUNT}</span> 筆交易 · P/L: <b id="headerPL" style="color:{PL_COLOR}">{PL}</b> · 勝率: <b id="headerWR">{WR}</b></div>
  <button class="theme-btn" onclick="toggleTheme()" id="themeBtn">🌓</button>
</div></div>
<div class="date-bar">
  <span class="lbl">📅 篩選日期:</span>
  <input type="date" id="dateFrom" value="{DATE_MIN}" onchange="applyDateFilter()">
  <span class="lbl">至</span>
  <input type="date" id="dateTo" value="{DATE_MAX}" onchange="applyDateFilter()">
  <button onclick="resetDateFilter()">重置</button>
  <span class="lbl" id="filterInfo"></span>
</div>
<div class="main"><div class="kpi-row" id="kpiRow">{CARDS}</div>
{CHARTS}
<div class="section-title" style="margin:12px 0 6px">逐筆明細</div>
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
<th onclick="sortBy('open_price')">開倉價<span class="sort-arrow" id="sa-open_price"></span></th>
<th onclick="sortBy('sl')">S/L<span class="sort-arrow" id="sa-sl"></span></th>
<th onclick="sortBy('tp')">T/P<span class="sort-arrow" id="sa-tp"></span></th>
<th onclick="sortBy('close')">平倉<span class="sort-arrow" id="sa-close"></span></th>
<th onclick="sortBy('close_price')">平倉價<span class="sort-arrow" id="sa-close_price"></span></th>
<th onclick="sortBy('commission')">佣金<span class="sort-arrow" id="sa-commission"></span></th>
<th onclick="sortBy('swap')">Swap<span class="sort-arrow" id="sa-swap"></span></th>
<th onclick="sortBy('profit')">盈虧<span class="sort-arrow" id="sa-profit"></span></th>
</tr></thead>
<tbody id="tradeBody"></tbody></table></div>
<div class="toolbar" style="justify-content:flex-end;margin-top:6px">
<span class="page-info" id="pageInfo2"></span>
<button class="nav-btn" onclick="currentPage=1;renderTable()">«</button><button class="nav-btn" onclick="if(currentPage>1){currentPage--;renderTable()}">‹</button>
<button class="nav-btn" onclick="if(currentPage<totalPages){currentPage++;renderTable()}">›</button>
<button class="nav-btn" onclick="currentPage=totalPages;renderTable()">»</button></div></div>
<script src="{ECHART_CDN}"></script>
<script>
var ALL_TRADES={TRADE_JSON};
var SYM_PIE_DATA={SYM_PIE_DATA};
var data=ALL_TRADES.slice();
(function(){var s=localStorage.getItem('mt-theme');var m=window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light';document.documentElement.setAttribute('data-theme',s||m);})();
window.matchMedia('(prefers-color-scheme:dark)').addEventListener('change',function(e){if(!localStorage.getItem('mt-theme')){document.documentElement.setAttribute('data-theme',e.matches?'dark':'light');initCharts();}});
function toggleTheme(){var c=document.documentElement.getAttribute('data-theme');var n=c==='dark'?'light':'dark';document.documentElement.setAttribute('data-theme',n);localStorage.setItem('mt-theme',n);initCharts();}
function initCharts(){
  var isDark=document.documentElement.getAttribute('data-theme')==='dark';
  var tc=isDark?'#e2e8f0':'#1f2937';
  var el=document.getElementById('chart-symbol-pie');
  if(!el)return;
  if(el._echart)el._echart.dispose();
  var colors=['#5470c6','#91cc75','#fac858','#ee6666','#73c0de','#3ba272','#fc8452','#9a60b4','#ea7ccc','#48b8d0'];
  var opt={
    tooltip:{trigger:'item',formatter:'{b}: {c} 筆 ({d}%)'},
    legend:{bottom:0,textStyle:{color:tc,fontSize:10}},
    color:colors,
    series:[{
      type:'pie',radius:['45%','75%'],center:['50%','48%'],
      avoidLabelOverlap:false,
      label:{show:true,formatter:'{b} {d}%',fontSize:10,color:tc},
      data:SYM_PIE_DATA,
      emphasis:{scale:false}
    }]
  };
  var chart=echarts.init(el,isDark?'dark':null);
  chart.setOption(opt);el._echart=chart;
}
window.addEventListener('resize',function(){var el=document.getElementById('chart-symbol-pie');if(el&&el._echart)el._echart.resize();});
initCharts();

// Date filter
function applyDateFilter(){
  var df=document.getElementById('dateFrom').value;
  var dt=document.getElementById('dateTo').value;
  if(!df&&!dt){resetDateFilter();return;}
  data=ALL_TRADES.filter(function(t){
    if(df&&t.open_date<df)return false;
    if(dt&&t.open_date>dt)return false;
    return true;
  });
  updateKPIs();currentPage=1;renderTable();
  document.getElementById('filterInfo').textContent=' ('+data.length+' 筆)';
}
function resetDateFilter(){
  document.getElementById('dateFrom').value='{DATE_MIN}';
  document.getElementById('dateTo').value='{DATE_MAX}';
  data=ALL_TRADES.slice();
  updateKPIs();currentPage=1;renderTable();
  document.getElementById('filterInfo').textContent='';
}
function updateKPIs(){
  var total=data.length;
  var pl=0,wins=0,losses=0,totalW=0,totalL=0,best=-Infinity,worst=Infinity;
  data.forEach(function(t){pl+=t.profit;if(t.profit>0){wins++;totalW+=t.profit;}else{losses++;totalL+=t.profit;}if(t.profit>best)best=t.profit;if(t.profit<worst)worst=t.profit;});
  var avgW=wins?(totalW/wins):0,avgL=losses?Math.abs(totalL/losses):0,plr=avgL?avgW/avgL:0;
  var pf=totalL?Math.abs(totalW/totalL):0;
  document.getElementById('headerCount').textContent=total;
  document.getElementById('headerPL').textContent='$'+(pl>=0?'+':'')+pl.toFixed(2);
  document.getElementById('headerWR').textContent=(total?(wins/total*100).toFixed(0):0)+'%';
  var vals=[total,'$'+(pl>=0?'+':'')+pl.toFixed(2),(total?(wins/total*100).toFixed(0):0)+'%',
    '+$'+avgW.toFixed(2),'-$'+avgL.toFixed(2),plr.toFixed(2),pf.toFixed(2),
    'N/A','N/A','$'+(best!==-Infinity?'+':'')+best.toFixed(2),'$-'+Math.abs(worst).toFixed(2)];
  var kpiVals=document.querySelectorAll('.kpi .val');
  for(var i=0;i<Math.min(vals.length,kpiVals.length);i++){kpiVals[i].textContent=vals[i];}
}

var sortCol='profit',sortDir=-1;var currentPage=1,pageSize=15,totalPages=1;var searchIdx=-1,searchMatches=[];
function sortBy(col){if(sortCol===col)sortDir*=-1;else{sortCol=col;sortDir=-1;}data.sort(function(a,b){var va=a[col],vb=b[col];if(typeof va==='number')return(va-vb)*sortDir;return String(va).localeCompare(String(vb))*sortDir;});currentPage=1;renderTable();document.querySelectorAll('.sort-arrow').forEach(function(el){el.textContent='';});var arrow=document.getElementById('sa-'+col);if(arrow)arrow.textContent=sortDir>0?'▲':'▼';}
function doSearch(){var q=document.getElementById('searchBox').value.trim().toLowerCase();searchMatches=[];searchIdx=-1;if(!q){data=applyCurrentFilter();document.getElementById('searchInfo').textContent='';}else{data=applyCurrentFilter().filter(function(t){return String(t.ticket).toLowerCase().indexOf(q)>=0;});document.getElementById('searchInfo').textContent=data.length+' 條匹配';ALL_TRADES.forEach(function(t,i){if(String(t.ticket).toLowerCase().indexOf(q)>=0)searchMatches.push(i);});}currentPage=1;renderTable();}
function applyCurrentFilter(){var df=document.getElementById('dateFrom').value;var dt=document.getElementById('dateTo').value;if(!df&&!dt)return ALL_TRADES.slice();return ALL_TRADES.filter(function(t){if(df&&t.open_date<df)return false;if(dt&&t.open_date>dt)return false;return true;});}
document.getElementById('searchBox').addEventListener('keydown',function(e){if(e.key==='Enter'&&searchMatches.length>0){e.preventDefault();searchIdx=(searchIdx+1)%searchMatches.length;var gi=searchMatches[searchIdx];currentPage=Math.floor(gi/pageSize)+1;renderTable();setTimeout(function(){var rows=document.querySelectorAll('#tradeBody tr');rows.forEach(function(r){r.classList.remove('highlight');});var li=gi%pageSize;if(rows[li]){rows[li].classList.add('highlight');rows[li].scrollIntoView({behavior:'smooth',block:'center'});}document.getElementById('searchInfo').textContent=(searchIdx+1)+'/'+searchMatches.length+' 條匹配';},30);}});
function renderTable(){totalPages=Math.ceil(data.length/pageSize)||1;if(currentPage>totalPages)currentPage=totalPages;var start=(currentPage-1)*pageSize;var page=data.slice(start,start+pageSize);var h='';page.forEach(function(t){var cls=t.profit>0?'win':'loss';h+='<tr class="'+cls+'"><td>'+t.ticket+'</td><td>'+t.open+'</td><td>'+t.type+'</td><td>'+t.volume+'</td><td>'+t.symbol+'</td><td>'+(t.open_price||'-')+'</td><td>'+(t.sl||'-')+'</td><td>'+(t.tp||'-')+'</td><td>'+t.close+'</td><td>'+(t.close_price||'-')+'</td><td>$'+(t.commission||0).toFixed(2)+'</td><td>$'+(t.swap||0).toFixed(2)+'</td><td class="'+cls+'">$'+t.profit.toFixed(2)+'</td></tr>';});document.getElementById('tradeBody').innerHTML=h;var info=currentPage+'/'+totalPages+' ('+data.length+'筆)';document.getElementById('pageInfo').textContent=info;document.getElementById('pageInfo2').textContent=info;}
renderTable();document.getElementById('sa-profit').textContent='▼';</script>
<div class="metric-guide" style="max-width:1440px;margin:20px auto 0;padding:0 clamp(10px,1vw,20px) 20px">
<details style="background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:14px 18px;cursor:pointer">
<summary style="font-size:13px;font-weight:600;color:var(--text);outline:none">📖 指標說明與計算公式</summary>
<div style="margin-top:10px;font-size:12px;color:var(--muted);line-height:1.8">
<p><b>總交易</b>：報表中所有已平倉交易的總筆數。</p>
<p><b>總盈虧</b>：所有交易 profit 欄位的代數和（盈利 − 虧損 − 佣金 − Swap）。</p>
<p><b>勝率</b>：盈利筆數 ÷ 總筆數 × 100%。高勝率不等於賺錢 — 如果平均虧損遠大於平均盈利，仍然會虧損。</p>
<p><b>平均盈利</b>：所有盈利交易 profit 的平均值。這個值小 + 平均虧損大 = 高勝率但虧錢。</p>
<p><b>平均虧損</b>：所有虧損交易 profit 絕對值的平均值。</p>
<p><b>盈虧比</b>：平均盈利 ÷ 平均虧損。<b style="color:var(--green)">≥1</b> 表示盈利時賺的比虧損時賠的多；<b style="color:var(--red)">&lt;1</b> 表示虧損時賠的比盈利時賺的多。這是判斷策略品質的核心指標。</p>
<p><b>盈利因子</b>：總盈利 ÷ 總虧損絕對值。<b style="color:var(--red)">&lt;1</b> 是虧損策略。</p>
<p><b>最大回撤</b>：權益曲線從歷史最高點到之後最低點的跌幅（美元）。衡量最壞情況下虧了多少。公式：max(0, max(peak − equity))。</p>
<p><b>夏普比率</b>：風險調整後報酬 = 日均盈虧均值 ÷ 日均盈虧標準差 × √252。<b style="color:var(--red)">&lt;0</b> 表示平均每日回報為負。</p>
<p><b>最佳／最差</b>：單筆交易的最大盈利與最大虧損金額。</p>
</div></details></div>
</body></html>"""

def process_file(path):
    result=parse_statement(path);trades=result["trades"]
    if not trades:messagebox.showerror("失敗","未找到交易記錄");return
    stats=analyze(trades)
    html=build_dashboard_html(result["account"],trades,stats)
    out=Path(tempfile.gettempdir())/f"MT_Desk_{result['account']}.html"
    out.write_text(html,encoding="utf-8")
    threading.Timer(0.3,lambda:webbrowser.open(out.as_uri())).start()
    return result,len(trades)

def main():
    root=tk.Tk();root.title("MT Desk");root.geometry("400x260")
    root.configure(bg="#f0f2f5");root.resizable(False,False)
    tk.Label(root,text="MT Desk",font=("Segoe UI",22,"bold"),fg="#2563eb",bg="#f0f2f5").pack(pady=(24,4))
    tk.Label(root,text="ECharts · 瀏覽器篩選日期 · 8 張圖表",font=("Segoe UI",10),fg="#6b7280",bg="#f0f2f5").pack(pady=(0,20))
    status_var=tk.StringVar(value="選擇 HTML 報表檔案")
    status=tk.Label(root,textvariable=status_var,font=("Segoe UI",9),fg="#6b7280",bg="#f0f2f5");status.pack(pady=(0,14))
    def open_file():
        paths=filedialog.askopenfilenames(title="選擇 MT4/MT5 報表",filetypes=[("HTML","*.htm *.html")])
        if not paths:return
        total=len(paths)
        for i,path in enumerate(paths,1):
            fname=Path(path).name;status_var.set(f"⏳ ({i}/{total}): {fname}");root.update()
            try:process_file(path)
            except Exception as e:messagebox.showerror("錯誤",str(e))
        status_var.set(f"✅ 完成 — {total} 個檔案")
    tk.Button(root,text="📂 選擇 MT4/MT5 HTML 報表",font=("Segoe UI",12),bg="#2563eb",fg="white",
        relief="flat",padx=24,pady=10,command=open_file,cursor="hand2").pack()
    root.mainloop()

if __name__=="__main__":main()
