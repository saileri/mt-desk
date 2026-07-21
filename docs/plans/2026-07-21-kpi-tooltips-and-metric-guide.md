# MT Desk v5.1 — KPI 工具提示 + 反誤導 + 公式說明

> **給 deepseek-flash：嚴格按照以下每一步的 EXACT old_string/new_string 執行，不要跳步、不要自行發揮。**

專案位置：`/root/mt-desk`
虛擬環境：`source /root/mt-desk/.venv/bin/activate`

只改 1 個檔案：`/root/mt-desk/mt_desk/main.py`，共 4 處 patch。

---

## 背景

目前 KPI 卡片有 10 個，但組合容易造成誤解：

| KPI | 值 | 誤解風險 |
|:--|:--|:--|
| 勝率 86% | 綠色 | 看起來很好，但總盈虧是負的 |
| 盈利因子 0.77 | 灰色 | 一般人不知道 <1 代表虧損策略 |
| 最大回撤 | 紅色 | 不知道回撤是什麼 |
| 夏普比率 -5.08 | 灰色 | 極技術性 |
| 連續盈利 112筆 | 灰色 | 非交易人會誤會"全部連續" |

### 解決方案
1. **新增 3 張 KPI 卡片**：平均盈利、平均虧損、盈虧比 — 直接解釋 86% 勝率但虧錢的原因
2. **所有 KPI 加 hover 工具提示**（用 CSS tooltip，不用 JS）
3. **底部新增摺疊式「指標說明」區塊**（用 HTML `<details>` 標籤）

---

## 步驟 1：新增 3 張 KPI 卡片 + 所有卡片加 tooltip

### 1a. 修改 KPI 卡片列表（`build_dashboard_html` 函式，約第 16-23 行）

用 `patch` 工具，`mode=replace`，`path=/root/mt-desk/mt_desk/main.py`

**old_string:**
```python
    cards=[
        ("總交易",str(stats["count"]),""),("總盈虧",f"${stats['total_pl']:+,.2f}","--green" if stats["total_pl"]>=0 else"--red"),
        ("勝率",f"{stats['wr']:.0f}%","--green"),("盈利因子",f"{stats['pf']:.2f}" if stats["pf"]!=float("inf") else"∞","--muted"),
        ("最大回撤",f"${stats['max_dd']:,.2f}","--red"),("夏普比率",f"{stats['sharpe']:.2f}","--muted"),
        ("最佳",f"+${stats['best']:,.2f}","--green"),("最差",f"-${abs(stats['worst']):,.2f}","--red"),
        ("連續盈利",f"{stats['max_win_streak']}筆","--muted"),("連續虧損",f"{stats['max_loss_streak']}筆","--muted"),
    ]
    card_html="".join(f'<div class="kpi"><span class="lbl">{l}</span><span class="val" style="color:var({c})">{v}</span></div>' for l,v,c in cards)
```

**new_string:**
```python
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
        ("最長連勝",f"{stats['max_win_streak']}筆","按時間順序連續盈利的最長筆數（非全部連續）","--muted"),
        ("最長連敗",f"{stats['max_loss_streak']}筆","按時間順序連續虧損的最長筆數（非全部連續）","--muted"),
    ]
    card_html="".join(f'<div class="kpi has-tip"><span class="lbl">{l}</span><span class="val" style="color:var({c})">{v}</span><span class="tip">{tip}</span></div>' for l,v,tip,c in cards)
```

### 1b. 驗證

```bash
cd /root/mt-desk && source .venv/bin/activate && python3 -c "
from mt_desk.parser import parse_statement
from mt_desk.analysis import analyze
from mt_desk.main import build_dashboard_html
r = parse_statement('tests/test_statement.htm')
s = analyze(r['trades'])
html = build_dashboard_html(r['account'], r['trades'], s)
for k in ['平均盈利','平均虧損','盈虧比','最長連勝','最長連敗','class=\"tip\"']:
    assert k in html, f'{k} missing'
print('All step 1 assertions passed')
"
```

預期輸出：All step 1 assertions passed

---

## 步驟 2：新增 tooltip CSS（`.kpi.has-tip` 樣式）

### 2a. 在 KPI CSS 後插入 tooltip 樣式

用 `patch` 工具，`mode=replace`，`path=/root/mt-desk/mt_desk/main.py`

**old_string:**
```css
.kpi .val{display:block;font-size:clamp(15px,1.3vw,20px);font-weight:700}
```

**new_string:**
```css
.kpi .val{display:block;font-size:clamp(15px,1.3vw,20px);font-weight:700}
.kpi.has-tip{position:relative;cursor:help}
.kpi .tip{display:none;position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:11px;line-height:1.4;white-space:normal;max-width:220px;text-align:left;z-index:100;box-shadow:0 4px 12px rgba(0,0,0,.15);pointer-events:none}
.kpi.has-tip .tip::after{content:'';position:absolute;top:100%;left:50%;transform:translateX(-50%);border:6px solid transparent;border-top-color:var(--border)}
.kpi.has-tip:hover .tip{display:block}
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
assert 'has-tip' in html
assert '.tip{display:none' in html
print('CSS tooltip styles verified')
"
```

預期輸出：CSS tooltip styles verified

---

## 步驟 3：底部新增摺疊式「指標說明」區塊

### 3a. 在 `</script></body></html>` 之前插入 details 區塊

用 `patch` 工具，`mode=replace`，`path=/root/mt-desk/mt_desk/main.py`

**old_string:**
```html
renderTable();document.getElementById('sa-profit').textContent='▼';</script></body></html>"""
```

**new_string:**
```html
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
<p><b>最長連勝／連敗</b>：按開倉時間排序後，profit > 0（或 ≤0）連續出現的最長筆數。</p>
</div></details></div>
</body></html>"""
```

### 3b. 驗證

```bash
cd /root/mt-desk && source .venv/bin/activate && python3 -c "
from mt_desk.parser import parse_statement
from mt_desk.analysis import analyze
from mt_desk.main import build_dashboard_html
r = parse_statement('tests/test_statement.htm')
s = analyze(r['trades'])
html = build_dashboard_html(r['account'], r['trades'], s)
assert '指標說明' in html
assert '盈虧比' in html
assert '<details' in html
print('Metric guide section verified')
"
```

預期輸出：Metric guide section verified

---

## 步驟 4：修正日期篩選後的 KPI 更新邏輯

### 4a. 更新 `updateKPIs()` 函式讓它能更新所有 13 個 KPI（含新增的 3 個）

用 `patch` 工具，`mode=replace`，`path=/root/mt-desk/mt_desk/main.py`

搜尋 `function updateKPIs()` 開頭的那幾行，找到後整段替換。

**old_string:**
```javascript
function updateKPIs(){
  var total=data.length;
  var pl=0,wins=0,losses=0,best=-Infinity,worst=Infinity;
  data.forEach(function(t){pl+=t.profit;if(t.profit>0)wins++;else losses++;if(t.profit>best)best=t.profit;if(t.profit<worst)worst=t.profit;});
  document.getElementById('headerCount').textContent=total;
  document.getElementById('headerPL').textContent='$'+(pl>=0?'+':'')+pl.toFixed(2);
  document.getElementById('headerWR').textContent=(total?(wins/total*100).toFixed(0):0)+'%';
  var vals=[total,'$'+(pl>=0?'+':'')+pl.toFixed(2),(total?(wins/total*100).toFixed(0):0)+'%',
    'N/A','N/A','N/A','$'+(best!==-Infinity?'+':'')+best.toFixed(2),'$-'+Math.abs(worst).toFixed(2),'N/A','N/A'];
  var kpiVals=document.querySelectorAll('.kpi .val');
  for(var i=0;i<Math.min(vals.length,kpiVals.length);i++)kpiVals[i].textContent=vals[i];
}
```

**new_string:**
```javascript
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
    'N/A','N/A','$'+(best!==-Infinity?'+':'')+best.toFixed(2),'$-'+Math.abs(worst).toFixed(2),'N/A','N/A'];
  var kpiVals=document.querySelectorAll('.kpi .val');
  for(var i=0;i<Math.min(vals.length,kpiVals.length);i++){kpiVals[i].textContent=vals[i];}
}
```

### 4b. 驗證

```bash
cd /root/mt-desk && source .venv/bin/activate && python3 -c "
from mt_desk.parser import parse_statement
from mt_desk.analysis import analyze
from mt_desk.main import build_dashboard_html
r = parse_statement('tests/test_statement.htm')
s = analyze(r['trades'])
html = build_dashboard_html(r['account'], r['trades'], s)
assert 'totalW' in html, 'updateKPIs totalW missing'
assert 'avgW' in html, 'updateKPIs avgW missing'
assert 'plr' in html, 'updateKPIs plr missing'
print('updateKPIs fix verified')
"
```

預期輸出：updateKPIs fix verified

---

## 步驟 5：最終端到端驗證

### 5a. 生成 HTML 並檢查所有功能

```bash
cd /root/mt-desk && source .venv/bin/activate && python3 -c "
from mt_desk.parser import parse_statement
from mt_desk.analysis import analyze
from mt_desk.main import build_dashboard_html
from pathlib import Path
import tempfile
r = parse_statement('tests/test_statement.htm')
s = analyze(r['trades'])
html = build_dashboard_html(r['account'], r['trades'], s)
out = Path(tempfile.gettempdir()) / 'MT_Desk_v51_test.html'
out.write_text(html, encoding='utf-8')
print('Output:', out)
print('File size:', out.stat().st_size, 'bytes')
# Check all critical elements
checks = [
    'has-tip', '平均盈利', '平均虧損', '盈虧比', '最長連勝', '最長連敗',
    '指標說明', '<details', '<summary',
    'class=\"tip\"', '.tip{display:none',
]
all_ok = True
for c in checks:
    ok = c in html
    print(f'  {c}: {\"OK\" if ok else \"MISSING!\"}')
    if not ok: all_ok = False
print('ALL CHECKS PASSED' if all_ok else 'SOME CHECKS FAILED')
"
```

### 5b. grep 快速檢查

```bash
grep -c '平均盈利' /tmp/MT_Desk_v51_test.html      # 預期 ≥1
grep -c '平均虧損' /tmp/MT_Desk_v51_test.html      # 預期 ≥1
grep -c '指標說明' /tmp/MT_Desk_v51_test.html      # 預期 ≥1
grep -c 'has-tip' /tmp/MT_Desk_v51_test.html      # 預期 ≥1
```

---

## 變更摘要

| # | 檔案 | 改什麼 |
|:--|:--|:--|
| 1 | `main.py` | KPI 10→13 張 + 每個加 tooltip |
| 2 | `main.py` | 新增 CSS tooltip 樣式 |
| 3 | `main.py` | 底部摺疊式指標說明 |
| 4 | `main.py` | updateKPIs() 支援 13 張 KPI |

執行順序：1 → 2 → 3 → 4 → 5（驗證）
