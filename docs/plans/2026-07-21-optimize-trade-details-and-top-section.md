# MT Desk 優化 — DeepSeek-Flash 執行手冊

> **給 AI 的指令：請嚴格按照以下每一步操作，不要跳步、不要自行發揮。每一步都有 EXACT 的檔案路徑、行號、和程式碼。用 `patch` 工具做修改。**

---

## 背景

專案位置：`/root/mt-desk`
虛擬環境：`source /root/mt-desk/.venv/bin/activate`
測試檔案：`/root/mt-desk/tests/test_statement.htm`

修改 2 個檔案：
- `/root/mt-desk/mt_desk/analysis.py`（新增 3 個統計欄位）
- `/root/mt-desk/mt_desk/main.py`（主要變更：HTML、JS、trade JSON）

---

## 步驟 1：修改 analysis.py — 新增 total_swap、total_volume、sym_volume

### 1a. 在 analysis.py 第 69-72 行之間插入 swap/volume 計算

用 `replace` mode 做 patch。找到以下程式碼（約第 67-70 行）：

```python
    for t in trades:
        sym = t["symbol"]
        sym_pl[sym] += t["profit"]
        sym_count[sym] += 1
        if t["profit"] > 0:
            sym_wins[sym] += 1
```

替換為（在 `if t["profit"] > 0:` 之後的那一行，即在 `sym_wins[sym] += 1` 之後插入新程式碼）：

```python
    for t in trades:
        sym = t["symbol"]
        sym_pl[sym] += t["profit"]
        sym_count[sym] += 1
        if t["profit"] > 0:
            sym_wins[sym] += 1

    # ── v5: swap & volume totals ──
    total_swap = sum(t.get("swap", 0) for t in trades)
    total_volume = sum(t.get("volume", 0) for t in trades)
    sym_volume: dict[str, float] = defaultdict(float)
    for t in trades:
        sym_volume[t["symbol"]] += t.get("volume", 0)
```

### 1b. 在 return dict 中新增 3 個 key

找到 return dict 的最後一行（約第 150-151 行）：

```python
        "daily_pl": dict(daily_pl),
    }
```

替換為：

```python
        "daily_pl": dict(daily_pl),
        "total_swap": round(total_swap, 2),
        "total_volume": round(total_volume, 2),
        "sym_volume": dict(sym_volume),
    }
```

### 1c. 驗證

```bash
cd /root/mt-desk && source .venv/bin/activate && python3 -c "
from mt_desk.parser import parse_statement
from mt_desk.analysis import analyze
r = parse_statement('tests/test_statement.htm')
s = analyze(r['trades'])
print('total_swap:', s.get('total_swap'))
print('total_volume:', s.get('total_volume'))
print('sym_volume:', s.get('sym_volume'))
"
```

預期輸出類似：
```
total_swap: -9.0
total_volume: 4.1
sym_volume: {'xauusd': 1.3, 'eurusd': 0.5, 'gbpusd': 2.0, 'usdjpy': 0.3}
```

---

## 步驟 2：修改 main.py — 擴充 all_trades JSON

### 2a. 找到 all_trades 建構程式碼

在 `main.py` 中，找這一行（約第 37-41 行）：

```python
    all_trades=[{"ticket":str(t["ticket"]),"open":t["open_time"].strftime("%Y-%m-%d %H:%M") if t["open_time"] else"-",
        "close":t["close_time"].strftime("%Y-%m-%d %H:%M") if t["close_time"] else"-","type":t["type"].upper(),
        "symbol":t["symbol"].upper(),"volume":t["volume"],"profit":round(t["profit"],2),
        "open_date":t["open_time"].strftime("%Y-%m-%d") if t["open_time"] else""} for t in trades]
```

替換為：

```python
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
```

### 2b. 驗證

```bash
cd /root/mt-desk && source .venv/bin/activate && python3 -c "
from mt_desk.parser import parse_statement
from mt_desk.analysis import analyze
from mt_desk.main import build_dashboard_html
r = parse_statement('tests/test_statement.htm')
s = analyze(r['trades'])
html = build_dashboard_html(r['account'], r['trades'], s)
import json, re
m = re.search(r'var ALL_TRADES=(\[.+?\]);', html, re.DOTALL)
data = json.loads(m.group(1))
t = data[0]
print('Fields:', sorted(t.keys()))
print('Has swap:', 'swap' in t)
print('Has commission:', 'commission' in t)
print('Has open_price:', 'open_price' in t)
print('Has close_price:', 'close_price' in t)
print('Has sl:', 'sl' in t)
print('Has tp:', 'tp' in t)
"
```

預期輸出：所有 Has xxx 都是 True。

---

## 步驟 3：修改 main.py — 移除 8 張圖表，換成頂部摘要區

這一步最複雜，分 4 個子步驟。

### 3a. 刪除 build_dashboard_html() 中的 charts 生成邏輯

找到以下程式碼區塊（約第 16-21 行）：

```python
    chart_configs={
        "equity":chart_equity(stats),"winloss":chart_winloss_count(stats),
        "pnl_stats":chart_pnl_stats(stats),"symbol":chart_symbol_table(stats),
        "profit_curve":chart_profit_curve(stats),"symbol_group":chart_symbol_grouped(stats),
        "pnl_hist":chart_pnl_histogram(stats,trades),"hourly":chart_hourly_area(stats),
    }
```

**刪除這整個區塊**（替換為空字串）。

### 3b. 刪除 chart_divs 生成邏輯，改用 summary_html

找到以下程式碼區塊（約第 30-36 行）：

```python
    chart_divs=[]
    chart_names={"equity":"權益曲線","winloss":"交易次數","pnl_stats":"盈虧統計","symbol":"品種盈虧",
                 "profit_curve":"盈利曲線","symbol_group":"品種盈虧統計","pnl_hist":"交易盈虧分佈","hourly":"交易時段分佈"}
    for key,h in[("equity","400px"),("winloss","280px"),("pnl_stats","300px"),("symbol","320px"),
                 ("profit_curve","320px"),("symbol_group","300px"),("pnl_hist","300px"),("hourly","280px")]:
        w="wide" if key in("equity","profit_curve") else""
        chart_divs.append(f'<div class="chart-card {w}"><div id="chart-{key}" style="width:100%;height:{h}"></div><div class="chart-label">{chart_names[key]}</div></div>')
```

替換為：

```python
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
```

### 3c. 更新 HTML 模板中的佔位符替換

找到以下程式碼（約第 49-54 行）：

```python
    html=html.replace("{PL}",f"${stats['total_pl']:+,.2f}").replace("{PL_COLOR}",pl_color)
    html=html.replace("{WR}",f"{stats['wr']:.0f}%").replace("{CARDS}",card_html)
    html=html.replace("{CHARTS}","".join(chart_divs)).replace("{TRADE_JSON}",trade_json)
    html=html.replace("{ECHART_CDN}",ECHARTS_CDN).replace("{CONFIGS}",configs_json)
    html=html.replace("{DATE_MIN}",date_min).replace("{DATE_MAX}",date_max)
```

替換為：

```python
    html=html.replace("{PL}",f"${stats['total_pl']:+,.2f}").replace("{PL_COLOR}",pl_color)
    html=html.replace("{WR}",f"{stats['wr']:.0f}%").replace("{CARDS}",card_html)
    html=html.replace("{CHARTS}",summary_html).replace("{TRADE_JSON}",trade_json)
    html=html.replace("{ECHART_CDN}",ECHARTS_CDN).replace("{SYM_PIE_DATA}",sym_pie_json)
    html=html.replace("{DATE_MIN}",date_min).replace("{DATE_MAX}",date_max)
```

### 3d. 修改 HTML 模板 `_HTML` — 三處變更

#### 3d-1. 新增 summary 區的 CSS

在 `_HTML` 的 `<style>` 區塊中，找到這一行（約第 94 行）：

```css
@media(max-width:768px){.charts{grid-template-columns:1fr}.kpi-row{grid-template-columns:repeat(3,1fr)}}
```

**在這一行「之前」**（即插入在 `@media` 之前），新增 summary CSS：

```css
.summary-row{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:10px;margin-bottom:16px}
.summary-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:16px;display:flex;flex-direction:column;justify-content:center;min-height:120px}
.summary-title{font-size:12px;color:var(--muted);margin-bottom:8px;font-weight:500}
.summary-val{font-size:28px;font-weight:700;color:var(--text)}
.summary-sub{font-size:11px;color:var(--muted);margin-top:4px}
@media(max-width:768px){.summary-row{grid-template-columns:1fr 1fr}.charts{grid-template-columns:1fr}.kpi-row{grid-template-columns:repeat(3,1fr)}}
```

#### 3d-2. 刪除 `.charts` div 區塊

找到這一行（約第 110 行）：

```html
<div class="charts">{CHARTS}</div>
```

替換為（`{CHARTS}` 現在渲染為 summary HTML，改放在 main 內部的最前面）：

```html
{CHARTS}
```

#### 3d-3. 更新 JS：刪除舊的 initCharts，換成只初始化品種餅圖

找到 `initCharts()` 函式（約第 141-158 行）：

```javascript
function initCharts(){
  var isDark=document.documentElement.getAttribute('data-theme')==='dark';
  var tc=isDark?'#e2e8f0':'#1f2937';var mc=isDark?'#64748b':'#6b7280';
  ['equity','winloss','pnl_stats','symbol','profit_curve','symbol_group','pnl_hist','hourly'].forEach(function(k){
    var el=document.getElementById('chart-'+k);if(!el||!CONFIGS[k]||CONFIGS[k]==='null')return;
    if(el._echart)el._echart.dispose();
    var opt=JSON.parse(CONFIGS[k]);
    if(opt.legend&&opt.legend.textStyle)opt.legend.textStyle.color=tc;
    if(opt.graphic)opt.graphic.forEach(function(g){if(g.style&&g.style.fill)g.style.fill=tc;});
    ['xAxis','yAxis'].forEach(function(a){
      var ax=opt[a];if(!ax)return;
      if(Array.isArray(ax))ax.forEach(function(x){if(x.axisLabel)x.axisLabel.color=mc;});
      else{if(ax.axisLabel)ax.axisLabel.color=mc;}
    });
    var chart=echarts.init(el,isDark?'dark':null);
    chart.setOption(opt);el._echart=chart;
  });
}
```

替換為：

```javascript
var SYM_PIE_DATA={SYM_PIE_DATA};
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
```

#### 3d-4. 更新 window resize 事件處理器

找到這一行（約第 159 行）：

```javascript
window.addEventListener('resize',function(){['equity','winloss','pnl_stats','symbol','profit_curve','symbol_group','pnl_hist','hourly'].forEach(function(k){var el=document.getElementById('chart-'+k);if(el&&el._echart)el._echart.resize();});});
```

替換為：

```javascript
window.addEventListener('resize',function(){var el=document.getElementById('chart-symbol-pie');if(el&&el._echart)el._echart.resize();});
```

#### 3d-5. 刪除 CONFIGS 變數宣告

找到這一行（約第 135 行）：

```javascript
var CONFIGS={CONFIGS};
```

替換為空（刪除這一行）。

#### 3d-6. theme 切換事件也更新

找到這一行（約第 139 行）：

```javascript
window.matchMedia('(prefers-color-scheme:dark)').addEventListener('change',function(e){if(!localStorage.getItem('mt-theme')){document.documentElement.setAttribute('data-theme',e.matches?'dark':'light');initCharts();}});
```

這個不用改 — `initCharts()` 已經被重新定義了，會自動只初始化品種餅圖。

### 3e. 驗證

```bash
cd /root/mt-desk && source .venv/bin/activate && python3 -c "
from mt_desk.parser import parse_statement
from mt_desk.analysis import analyze
from mt_desk.main import build_dashboard_html
r = parse_statement('tests/test_statement.htm')
s = analyze(r['trades'])
html = build_dashboard_html(r['account'], r['trades'], s)
# 確認舊圖表已刪除
for old in ['chart-equity','chart-winloss','chart-pnl_stats','chart-symbol','chart-profit_curve','chart-symbol_group','chart-pnl_hist','chart-hourly']:
    assert old not in html, f'{old} should be removed'
# 確認新元素存在
assert 'chart-symbol-pie' in html, 'symbol pie chart missing'
assert 'SYM_PIE_DATA' in html, 'SYM_PIE_DATA missing'
assert 'summary-row' in html, 'summary-row missing'
assert '交易量' in html, 'volume section missing'
assert 'Swap / 利息' in html, 'swap section missing'
print('All step 3 assertions passed')
"
```

---

## 步驟 4：修改 main.py — 擴充逐筆明細表格至 13 欄

### 4a. 替換 thead（表格標頭）

找到這個 `<thead>` 區塊（約第 119-127 行）：

```html
<thead><tr>
<th onclick="sortBy('ticket')">Ticket<span class="sort-arrow" id="sa-ticket"></span></th>
<th onclick="sortBy('open')">開倉<span class="sort-arrow" id="sa-open"></span></th>
<th onclick="sortBy('type')">方向<span class="sort-arrow" id="sa-type"></span></th>
<th onclick="sortBy('volume')">手數<span class="sort-arrow" id="sa-volume"></span></th>
<th onclick="sortBy('symbol')">品種<span class="sort-arrow" id="sa-symbol"></span></th>
<th onclick="sortBy('close')">平倉<span class="sort-arrow" id="sa-close"></span></th>
<th onclick="sortBy('profit')">盈虧<span class="sort-arrow" id="sa-profit"></span></th></tr></thead>
```

替換為：

```html
<thead><tr>
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
```

### 4b. 替換 renderTable() 函式

找到 `renderTable()` 函式（約第 200 行）：

```javascript
function renderTable(){totalPages=Math.ceil(data.length/pageSize)||1;if(currentPage>totalPages)currentPage=totalPages;var start=(currentPage-1)*pageSize;var page=data.slice(start,start+pageSize);var h='';page.forEach(function(t){h+='<tr class="'+(t.profit>0?'win':'loss')+'"><td>'+t.ticket+'</td><td>'+t.open+'</td><td>'+t.type+'</td><td>'+t.volume+'</td><td>'+t.symbol+'</td><td>'+t.close+'</td><td>$'+t.profit.toFixed(2)+'</td></tr>';});document.getElementById('tradeBody').innerHTML=h;var info=currentPage+'/'+totalPages+' ('+data.length+'筆)';document.getElementById('pageInfo').textContent=info;document.getElementById('pageInfo2').textContent=info;}
```

替換為：

```javascript
function renderTable(){totalPages=Math.ceil(data.length/pageSize)||1;if(currentPage>totalPages)currentPage=totalPages;var start=(currentPage-1)*pageSize;var page=data.slice(start,start+pageSize);var h='';page.forEach(function(t){var cls=t.profit>0?'win':'loss';h+='<tr class=\"'+cls+'\"><td>'+t.ticket+'</td><td>'+t.open+'</td><td>'+t.type+'</td><td>'+t.volume+'</td><td>'+t.symbol+'</td><td>'+(t.open_price||'-')+'</td><td>'+(t.sl||'-')+'</td><td>'+(t.tp||'-')+'</td><td>'+t.close+'</td><td>'+(t.close_price||'-')+'</td><td>$'+(t.commission||0).toFixed(2)+'</td><td>$'+(t.swap||0).toFixed(2)+'</td><td class=\"'+cls+'\">$'+t.profit.toFixed(2)+'</td></tr>';});document.getElementById('tradeBody').innerHTML=h;var info=currentPage+'/'+totalPages+' ('+data.length+'筆)';document.getElementById('pageInfo').textContent=info;document.getElementById('pageInfo2').textContent=info;}
```

### 4c. 確保 table-wrap 可以橫向滾動

找到這一行（約第 87 行）：

```css
.table-wrap{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
```

替換為：

```css
.table-wrap{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);overflow-x:auto}
```

### 4d. 驗證

```bash
cd /root/mt-desk && source .venv/bin/activate && python3 -c "
from mt_desk.parser import parse_statement
from mt_desk.analysis import analyze
from mt_desk.main import build_dashboard_html
r = parse_statement('tests/test_statement.htm')
s = analyze(r['trades'])
html = build_dashboard_html(r['account'], r['trades'], s)
# 確認 13 欄標頭
for hdr in ['開倉價','S/L','T/P','平倉價','佣金','Swap']:
    assert hdr in html, f'{hdr} header missing'
# 確認表格渲染包含新欄位
assert 't.open_price' in html or 'open_price' in html
assert 't.commission' in html or 'commission' in html
assert 't.swap' in html or 'swap' in html
print('All step 4 assertions passed')
"
```

---

## 步驟 5：最終端到端驗證

### 5a. 生成完整 HTML 輸出

```bash
cd /root/mt-desk && source .venv/bin/activate && python3 -c "
from mt_desk.parser import parse_statement
from mt_desk.analysis import analyze
from mt_desk.main import build_dashboard_html
import tempfile
from pathlib import Path
r = parse_statement('tests/test_statement.htm')
s = analyze(r['trades'])
html = build_dashboard_html(r['account'], r['trades'], s)
out = Path(tempfile.gettempdir()) / 'MT_Desk_v5_test.html'
out.write_text(html, encoding='utf-8')
print('Output:', out)
print('Account:', r['account'])
print('Trades:', len(r['trades']))
print('Total Swap:', s['total_swap'])
print('Total Volume:', s['total_volume'])
print('Sym counts:', s['sym_count'])
print('File size:', out.stat().st_size, 'bytes')
"
```

### 5b. 終極檢查清單

用 `grep` 快速確認 HTML：

```bash
cd /tmp
# 1. 確認舊圖表已全部刪除
grep -c 'chart-equity' MT_Desk_v5_test.html   # 預期 0
grep -c 'chart-winloss' MT_Desk_v5_test.html   # 預期 0
grep -c 'CONFIGS' MT_Desk_v5_test.html         # 預期 0
# 2. 確認新摘要區存在
grep -c 'chart-symbol-pie' MT_Desk_v5_test.html  # 預期 ≥1
grep -c 'SYM_PIE_DATA' MT_Desk_v5_test.html      # 預期 ≥1
grep -c 'summary-row' MT_Desk_v5_test.html        # 預期 ≥1
grep -c 'Swap / 利息' MT_Desk_v5_test.html        # 預期 1
# 3. 確認表格有 13 欄
grep -c '開倉價' MT_Desk_v5_test.html             # 預期 ≥1
grep -c '平倉價' MT_Desk_v5_test.html             # 預期 ≥1
grep -c '佣金' MT_Desk_v5_test.html               # 預期 ≥1
```

---

## 執行順序摘要

| 順序 | 檔案 | 做什麼 |
|:--|:--|:--|
| 1 | `analysis.py` | 2 處修改：插入 swap/volume 計算 + return dict 加 3 個 key |
| 2 | `main.py` | 擴充 all_trades JSON（1 處修改） |
| 3 | `main.py` | 移除 8 圖表 → 頂部摘要區（7 處修改：chart_configs 刪除、chart_divs 替換、html.replace 更新、CSS 新增、charts div 改 {CHARTS}、initCharts 替換、resize 簡化、CONFIGS 刪除） |
| 4 | `main.py` | 表格 7→13 欄（3 處修改：thead、renderTable、table-wrap CSS） |
| 5 | 驗證 | 跑 Python 驗證 + grep 檢查 |

每完成一步，就跑該步驟的驗證指令確認無誤後再繼續下一步。
