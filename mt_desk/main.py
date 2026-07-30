#!/usr/bin/env python3
"""MT Desk — Insight-driven trading dashboard with advanced charts."""
import json, io, os, sys, tempfile, tkinter as tk, threading, webbrowser
from tkinter import filedialog, messagebox
from datetime import datetime
from pathlib import Path
from mt_desk.parser import parse_statement
from mt_desk.analysis import analyze

if sys.stdout is None: sys.stdout = io.StringIO()
if sys.stderr is None: sys.stderr = sys.stdout
ECHARTS_CDN = "https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js"


def _j(obj): return json.dumps(obj, ensure_ascii=False, default=str)


def _fmt_hours(h):
    if h < 1:
        return f"{int(h * 60)}分鐘"
    if h < 24:
        s = f"{h:.1f}".rstrip("0").rstrip(".")
        return f"{s}小時"
    d = h / 24
    s = f"{d:.1f}".rstrip("0").rstrip(".")
    return f"{s}天"


def build_dashboard_html(account, trades, stats, cash_flows=None):
    if cash_flows is None:
        cash_flows = []
    avg_w = stats["avg_win"]
    avg_l = abs(stats["avg_loss"])
    plr = avg_w / avg_l if avg_l > 0 else 0
    wr_val = stats["wr"]
    wr_c = "--green" if wr_val >= 50 else "--muted" if wr_val >= 30 else "--red"
    pf_val = stats["pf"]
    pf_c = "--red" if pf_val < 1 else "--muted" if pf_val < 2 else "--green"
    core_cards = [
        ("總淨盈利", f"${stats['total_pl']:+,.2f}", "所有交易的淨盈虧金額總和", "--green" if stats["total_pl"] >= 0 else "--red"),
        ("獲利佔比", f"{wr_val:.0f}%", "盈利交易數 ÷ 總交易數 × 100%", wr_c),
        ("盈虧比", f"{plr:.2f}", "平均盈利 ÷ 平均虧損，≥1 表示賺多賠少", "--green" if plr >= 1 else "--red"),
        ("最大回撤", f"${stats['max_dd']:,.2f}", "權益曲線從最高點到最低點的最大跌幅", "--red" if stats['max_dd'] > abs(stats['total_pl'])*0.5 else "--muted"),
    ]
    core_html = "".join(
        f'<div class="kpi kpi-core has-tip"><span class="lbl">{l}</span><span class="val" style="color:var({c})">{v}</span><span class="tip">{tip}</span></div>'
        for l, v, tip, c in core_cards
    )
    sec_cards = [
        ("總交易", str(stats["count"]), "總交易筆數", ""),
        ("平均盈利", f"+${avg_w:,.2f}", "盈利交易的平均獲利金額", "--green"),
        ("平均虧損", f"-${avg_l:,.2f}", "虧損交易的平均損失金額", "--red"),
        ("盈利因子", f"{pf_val:.2f}" if pf_val != float("inf") else "∞", "總盈利 ÷ 總虧損，<1 代表虧損策略", pf_c),
        ("夏普比率", f"{stats['sharpe']:.2f}", "風險調整後報酬，<0 為負報酬", "--muted" if stats['sharpe'] < 0 else ""),
        ("最佳", f"+${stats['best']:,.2f}", "單筆最大盈利", "--green"),
        ("最差", f"-${abs(stats['worst']):,.2f}", "單筆最大虧損", "--red"),
    ]
    sec_html = "".join(
        f'<div class="kpi kpi-sec has-tip"><span class="lbl">{l}</span><span class="val" style="color:var({c})">{v}</span><span class="tip">{tip}</span></div>'
        for l, v, tip, c in sec_cards
    )

    # ── Top summary section ──
    sym_pie_data = [{"name": s.upper(), "value": c} for s, c in stats["sym_count"].items()]
    sym_pie_json = json.dumps(sym_pie_data, ensure_ascii=False)
    total_swap_val = stats["total_swap"]
    total_volume_val = stats["total_volume"]
    swap_color = "#00e676" if total_swap_val >= 0 else "#ff5252"

    vol_data = [{"name": s.upper(), "value": round(v, 2)} for s, v in stats["sym_volume"].items()]
    vol_json = json.dumps(sorted(vol_data, key=lambda x: x["value"], reverse=True), ensure_ascii=False)

    sw_data = [{"name": s.upper(), "value": round(v, 2)} for s, v in stats["sym_swap"].items()]
    sw_json = json.dumps(sorted(sw_data, key=lambda x: x["value"]), ensure_ascii=False)

    # Symbol P&L bar (top performers / losers)
    sym_pl_data = [{"name": s.upper(), "value": round(v, 2)} for s, v in stats["sym_pl"].items()]
    sym_pl_json = json.dumps(sorted(sym_pl_data, key=lambda x: x["value"]), ensure_ascii=False)

    # Determine if pie should be collapsed (single symbol > 90%)
    sym_count_items = sorted(stats["sym_count"].items(), key=lambda x: x[1], reverse=True)
    top_sym = sym_count_items[0] if sym_count_items else None
    top_pct = top_sym[1] / max(stats["count"], 1) * 100 if top_sym else 0
    single_sym = top_pct > 90

    # ── Session P&L breakdown (replaces pie for single-symbol accounts) ──
    session_pnl = {"asia": 0, "london": 0, "ny": 0}
    session_counts = {"asia": 0, "london": 0, "ny": 0}
    for t in trades:
        ot = t.get("open_time")
        if not ot:
            continue
        h = ot.hour
        pl = t.get("profit", 0)
        if 0 <= h < 8:
            session_pnl["asia"] += pl
            session_counts["asia"] += 1
        elif 8 <= h < 14:
            session_pnl["london"] += pl
            session_counts["london"] += 1
        else:
            session_pnl["ny"] += pl
            session_counts["ny"] += 1
    session_data = [
        {"name": "亞洲盤", "pl": round(session_pnl["asia"], 2), "count": session_counts["asia"]},
        {"name": "倫敦盤", "pl": round(session_pnl["london"], 2), "count": session_counts["london"]},
        {"name": "紐約盤", "pl": round(session_pnl["ny"], 2), "count": session_counts["ny"]},
    ]
    session_json = json.dumps(session_data, ensure_ascii=False)

    # Determine date span for smart chart aggregation
    open_dates = sorted(set(t["open_time"].strftime("%Y-%m-%d") for t in trades if t.get("open_time")))
    date_span_days = 0
    if len(open_dates) >= 2:
        try:
            from datetime import date as dt_date
            d1 = dt_date.fromisoformat(open_dates[0])
            d2 = dt_date.fromisoformat(open_dates[-1])
            date_span_days = (d2 - d1).days
        except: pass
    # Granularity hint: < 7 days -> daily, < 60 days -> weekly, else monthly
    if date_span_days <= 7: gran = "daily"
    elif date_span_days <= 60: gran = "weekly"
    else: gran = "monthly"

    summary_html = f'''<div class="quick-insights" id="quickInsights">
  <span class="qi-icon">💡</span>
  <span class="qi-text" id="qiText"></span>
</div>
<div class="summary-row compact">
  <div class="summary-card">
    <div class="summary-title">品種盈虧貢獻</div>
    <div id="chart-symbol-pl" style="width:100%;height:280px"></div>
  </div>
  <div class="summary-card" id="symbolPieBox">
    <div class="summary-title">品種偏好</div>
    <div id="chart-symbol-pie" style="width:100%;height:280px"></div>
    <div id="sessionPnlBox" style="display:none;padding:12px 0">
      <div style="font-size:13px;font-weight:600;margin-bottom:10px;color:var(--text)">⚡ 交易時段盈虧分佈</div>
      <div id="sessionPnlList"></div>
    </div>
    <div id="symbolPieText" style="display:none;text-align:center;padding:20px;font-size:14px;color:var(--muted);line-height:1.6"></div>
  </div>
  <div class="summary-card">
    <div class="summary-title">洞察</div>
    <ul class="insight-list" id="insightList"></ul>
  </div>
</div>
<div class="summary-row compact" style="grid-template-columns:1fr 1fr">
  <div class="summary-card">
    <div class="summary-title">交易量 <span class="hint">{total_volume_val:.2f} 手</span></div>
    <div id="chart-volume-donut" style="width:100%;height:150px"></div>
  </div>
  <div class="summary-card">
    <div class="summary-title">Swap / 利息 <span class="hint" style="color:{swap_color}">${total_swap_val:+,.2f}</span></div>
    <div id="chart-swap-bar" style="width:100%;height:150px"></div>
  </div>
</div>'''

    # ── v7.0: Insight-driven habit charts ──
    # 1. Monthly P&L waterfall
    monthly = sorted(stats["monthly"].items())
    m_labels = [m[0] for m in monthly]
    m_data = [round(m[1], 2) for m in monthly]
    waterfall_json = _j({"labels": m_labels, "data": m_data})

    # 2. Long/Short monthly grouped bar + win-rate line
    ls = sorted(stats["ls_monthly"].items())
    ls_labels = [m[0] for m in ls]
    ls_long = [m[1]["long"] for m in ls]
    ls_short = [m[1]["short"] for m in ls]
    # Compute monthly win rate for line overlay
    ls_wr = []
    for m in ls:
        month_key = m[0]
        month_pl = stats["monthly"].get(month_key, {})
        # Approximate: use daily pl dict to count wins per month
        month_wins = sum(1 for d, p in stats["daily_pl"].items() if d.startswith(month_key) and p > 0)
        month_days = sum(1 for d in stats["daily_pl"] if d.startswith(month_key))
        ls_wr.append(round(month_wins / month_days * 100, 1) if month_days else 0)
    ls_monthly_json = _j({"labels": ls_labels, "long": ls_long, "short": ls_short, "wr": ls_wr})

    # 3. Quarterly symbol preference: 100% stacked bar
    qs = sorted(stats["quarterly_sym"].items())
    qs_labels = [q[0] for q in qs]
    all_syms = set()
    for q in qs:
        all_syms.update(q[1].keys())
    top_syms = sorted(all_syms, key=lambda s: sum(stats["sym_count"].get(s.lower(), 0) for _ in [1]), reverse=True)[:6]
    qs_series = [{"name": s, "data": [q[1].get(s, 0) for q in qs]} for s in top_syms]
    quarterly_sym_json = _j({"labels": qs_labels, "series": qs_series})

    # 4. Equity curve with max drawdown markers
    eq = stats["equity"]
    eq_dates = stats["equity_dates"]
    equity_json = _j({
        "dates": eq_dates,
        "equity": eq,
        "pl": stats["total_pl"],
        "dd_peak_idx": stats.get("dd_peak_idx", 0),
        "dd_trough_idx": stats.get("dd_trough_idx", 0),
        "max_dd": stats["max_dd"],
    })

    # 5. Holding duration histogram with finer buckets
    durations = stats.get("durations", [])
    if durations:
        max_h = max(durations) * 1.05
        bucket_size = max(0.5, max_h / 12)
        hist_buckets = []
        hist_labels = []
        cur = 0.0
        while cur < max_h:
            nxt = cur + bucket_size
            cnt = sum(1 for d in durations if cur <= d < nxt)
            hist_buckets.append(cnt)
            if nxt < 1:
                hist_labels.append(f"{int(nxt * 60)}m")
            else:
                hist_labels.append(f"{nxt:.1f}h".rstrip("0").rstrip("."))
            cur = nxt
    else:
        hist_buckets = [0] * 6
        hist_labels = ["1h", "2h", "3h", "4h", "5h", "6h"]
    duration_json = _j({
        "labels": hist_labels,
        "data": hist_buckets,
        "buckets": stats.get("dur_buckets", {}),
        "avg": stats.get("avg_duration", 0),
        "median": stats.get("median_duration", 0),
    })

    # 6. Weekday × hour heatmap
    wd_names = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
    heatmap_data = []
    for key, v in stats.get("wd_hour", {}).items():
        wd, h = map(int, key.split("-"))
        heatmap_data.append([wd, h, v["cnt"], round(v["pl"], 2), round(v["wins"] / v["cnt"] * 100, 1) if v["cnt"] else 0])
    heatmap_json = _j({"data": heatmap_data, "weekdays": wd_names})

    # 7. Session radar chart (Asia/London/NY)
    session_data = stats.get("session", {})
    ses_names = {"亞洲盤 00~07": "亞洲盤", "倫敦盤 08~15": "倫敦盤", "紐約盤 16~23": "紐約盤"}
    ses_order = ["亞洲盤 00~07", "倫敦盤 08~15", "紐約盤 16~23"]
    ses_radar = []
    for ses_k in ses_order:
        v = session_data.get(ses_k, {})
        ses_radar.append({
            "name": ses_names.get(ses_k, ses_k),
            "cnt": int(v.get("cnt", 0)),
            "pl": round(v.get("pl", 0), 2),
            "wr": round(v.get("wins", 0) / v.get("cnt", 1) * 100, 1) if v.get("cnt", 0) else 0,
        })
    session_radar_json = _j(ses_radar)

    # 8. Symbol matrix bubble chart (count × win rate × P&L)
    sym_bubble = []
    for s in stats.get("sym_stats", []):
        if s["count"] >= 2:
            sym_bubble.append({
                "name": s["symbol"],
                "count": s["count"],
                "pl": s["pl"],
                "wr": s["wr"],
            })
    sym_bubble_json = _j(sym_bubble)

    # All trades as JSON (with derived fields)
    # Filter out only rows that are truly open/pending: missing close_time or identical to open_time.
    # close_price may legitimately be 0 for stop-out / malformed rows; keep those trades.
    all_trades = []
    skipped_open = 0
    for t in trades:
        # Skip open/pending: no close_time or close_time equals open_time
        if not t.get("close_time") or t["close_time"] == t.get("open_time"):
            skipped_open += 1
            continue
        dur_h = None
        if t["open_time"] and t["close_time"]:
            dur_h = round((t["close_time"] - t["open_time"]).total_seconds() / 3600, 2)
        vol = t.get("volume", 0) or 0
        profit_per_lot = round(t["profit"] / vol, 2) if vol else 0
        all_trades.append({
            "ticket": str(t["ticket"]),
            "open": t["open_time"].strftime("%Y-%m-%d %H:%M") if t["open_time"] else "-",
            "close": t["close_time"].strftime("%Y-%m-%d %H:%M") if t["close_time"] else "-",
            "type": t["type"].upper(),
            "volume": t["volume"],
            "symbol": t["symbol"].upper(),
            "open_price": round(t.get("open_price", 0), 5),
            "close_price": round(t.get("close_price", 0), 5),
            "sl": round(t.get("sl", 0), 5),
            "tp": round(t.get("tp", 0), 5),
            "commission": round(t.get("commission", 0), 2),
            "swap": round(t.get("swap", 0), 2),
            "profit": round(t["profit"], 2),
            "open_date": t["open_time"].strftime("%Y-%m-%d") if t["open_time"] else "",
            "duration_h": dur_h,
            "duration_str": _fmt_hours(dur_h) if dur_h is not None else "-",
            "profit_per_lot": profit_per_lot,
            "comment": t.get("comment", ""),
            "duration_s": round((t["close_time"] - t["open_time"]).total_seconds(), 2) if t["close_time"] and t["open_time"] else 0,
        })
    trade_json = json.dumps(all_trades, ensure_ascii=False)

    pl_color = "#69f0ae" if stats["total_pl"] >= 0 else "#ff8a80"
    all_dates = sorted(set(t["open_date"] for t in all_trades if t["open_date"]))
    date_min = all_dates[0] if all_dates else ""
    date_max = all_dates[-1] if all_dates else ""

    html = _HTML.replace("{ACCOUNT}", account).replace("{COUNT}", str(stats["count"]))
    html = html.replace("{PL}", f"${stats['total_pl']:+,.2f}").replace("{PL_COLOR}", pl_color)
    html = html.replace("{WR}", f"{stats['wr']:.0f}%").replace("{CORE_CARDS}", core_html).replace("{SEC_CARDS}", sec_html)

    # ── Risk Banner: auto-detect risk warnings ──
    risk_tags = []
    risk_msgs = []
    if stats["wr"] < 30:
        risk_tags.append(f"勝率 {stats['wr']:.0f}%")
    # Count trades with duration < 10 seconds
    scalp_count = sum(1 for t in trades if t.get("duration_h", 0) and t["duration_h"] < 10/3600)
    scalp_pct = scalp_count / max(stats["count"], 1) * 100
    if scalp_pct > 20:
        risk_tags.append(f"持倉 < 10秒 {scalp_pct:.0f}%")
    # Count trades with no SL
    no_sl = sum(1 for t in trades if not t.get("sl"))
    no_sl_pct = no_sl / max(stats["count"], 1) * 100
    if no_sl_pct > 80:
        risk_tags.append(f"SL未設置 {no_sl_pct:.0f}%")
    # Swap burden
    total_swap_abs = abs(stats.get("total_swap", 0))
    total_pl_abs = abs(stats.get("total_pl", 1))
    if total_pl_abs > 0 and total_swap_abs / total_pl_abs > 0.03:
        risk_tags.append(f"Swap佔比 {total_swap_abs/total_pl_abs*100:.1f}%")

    if risk_tags:
        banner_level = "warn"
        banner_icon = "⚠️"
        banner_text = f"檢測到 {stats['count']} 筆交易存在以下風險特徵："
        tags_html = '<div class="rb-tags">' + "".join(f'<span class="rb-tag">{t}</span>' for t in risk_tags) + '</div>'
        banner_html = f'<span class="rb-icon">{banner_icon}</span><div><strong>交易健康度預警：</strong> {banner_text}{tags_html}</div>'
    elif stats["total_pl"] > 0 and stats["wr"] >= 50:
        banner_level = "good"
        banner_icon = "✅"
        banner_html = f'<span class="rb-icon">{banner_icon}</span><div><strong>交易健康度良好：</strong>獲利 {stats["wr"]:.0f}% 勝率，淨盈利 ${stats["total_pl"]:+,.2f}</div>'
    else:
        banner_level = "info"
        banner_icon = "ℹ️"
        banner_html = f'<span class="rb-icon">{banner_icon}</span><div><strong>交易概覽：</strong>{stats["count"]} 筆交易，淨盈虧 ${stats["total_pl"]:+,.2f}，勝率 {stats["wr"]:.0f}%</div>'
    html = html.replace("{RISK_BANNER_LEVEL}", banner_level)
    html = html.replace("{RISK_BANNER_HTML}", banner_html)

    # Theme icon
    html = html.replace("{THEME_ICON}", "🌙")
    html = html.replace("{SUMMARY}", summary_html).replace("{TRADE_JSON}", trade_json)
    html = html.replace("{ECHART_CDN}", ECHARTS_CDN).replace("{SYM_PIE_DATA}", sym_pie_json)
    html = html.replace("{SYM_PL_JSON}", sym_pl_json)
    html = html.replace("{SESSION_PNL_JSON}", session_json)
    html = html.replace("{VOL_JSON}", vol_json).replace("{SWAP_JSON}", sw_json)
    html = html.replace("{DATE_MIN}", date_min).replace("{DATE_MAX}", date_max)

    # v7.0 chart JSON
    html = html.replace("{WATERFALL_JSON}", waterfall_json)
    html = html.replace("{LS_MONTHLY_JSON}", ls_monthly_json)
    html = html.replace("{QUARTERLY_SYM_JSON}", quarterly_sym_json)
    html = html.replace("{EQUITY_JSON}", equity_json)
    html = html.replace("{DURATION_JSON}", duration_json)
    html = html.replace("{SESSION_RADAR_JSON}", session_radar_json)
    html = html.replace("{SYM_BUBBLE_JSON}", sym_bubble_json)
    html = html.replace("{HEATMAP_JSON}", heatmap_json)
    html = html.replace("{GRAN}", gran).replace("{DATE_SPAN}", str(date_span_days))

    # ── v8.0 CS Audit data ──
    close_reason_json = json.dumps(stats.get("close_reason_distribution", {}), ensure_ascii=False)
    holding_time_json = json.dumps(stats.get("holding_time_buckets", {}), ensure_ascii=False)
    cs_timeline_json = json.dumps(stats.get("cs_timeline", []), ensure_ascii=False)

    # CS KPI cards
    nd_val = stats.get("net_deposit", 0)
    nd_color = "--green" if nd_val >= 0 else "--red"
    net_profit = stats.get("total_pl", 0)
    np_color = "--green" if net_profit >= 0 else "--red"
    so_cnt = stats.get("stop_out_count", 0)
    so_style = "color:var(--red);font-weight:900" if so_cnt > 0 else ""
    scalp_r = stats.get("scalp_ratio", 0)
    scalp_warn = '<span style="color:var(--red);font-size:10px;margin-left:4px">⚠️ 高頻/剥头皮预警</span>' if scalp_r > 20 else ""
    fee_r = stats.get("fee_ratio", 0)
    fee_s = stats.get("total_swap", 0)
    fee_c = stats.get("total_commission", 0)

    # Win/loss avg duration
    win_durs = []
    loss_durs = []
    for t in trades:
        if t.get("open_time") and t.get("close_time"):
            dur_s = (t["close_time"] - t["open_time"]).total_seconds()
            if t["profit"] > 0:
                win_durs.append(dur_s)
            else:
                loss_durs.append(dur_s)
    avg_win_dur = (sum(win_durs) / len(win_durs) / 3600) if win_durs else 0
    avg_loss_dur = (sum(loss_durs) / len(loss_durs) / 3600) if loss_durs else 0
    dur_ratio = (avg_win_dur / max(avg_loss_dur, 0.01)) if avg_loss_dur > 0 else 0

    def _fh(h):
        if h < 1: return f"{int(h*60)}分钟"
        if h < 24:
            s = f"{h:.1f}".rstrip("0").rstrip(".")
            return f"{s}小时"
        s = f"{h/24:.1f}".rstrip("0").rstrip(".")
        return f"{s}天"

    scalp_warn_html = scalp_warn
    so_html = f'<b style="{so_style}">{so_cnt} 次</b>'
    dur_html = f"赢单 {_fh(avg_win_dur)} / 亏单 {_fh(avg_loss_dur)} (比 {dur_ratio:.1f})"

    cs_cards_html = f"""<div class="cs-kpi-row">
  <div class="kpi kpi-cs{' cs-warn' if scalp_r > 20 else ''}"><span class="lbl">净入金</span><span class="val" style="color:var({nd_color})">${nd_val:+,.2f}</span><span class="sub">总入金 ${stats.get('total_deposit',0):,.2f} / 总出金 ${stats.get('total_withdrawal',0):,.2f}</span></div>
  <div class="kpi kpi-cs"><span class="lbl">净盈亏</span><span class="val" style="color:var({np_color})">${net_profit:+,.2f}</span><span class="sub">净利润总额</span></div>
  <div class="kpi kpi-cs"><span class="lbl">强平/爆仓</span><span class="val">{so_html if so_cnt > 0 else f'{so_cnt} 次'}</span><span class="sub">Stop Out 次数</span></div>
  <div class="kpi kpi-cs"><span class="lbl">SWAP & 佣金</span><span class="val" style="color:var(--muted)">${fee_s:+,.2f} / ${fee_c:+,.2f}</span><span class="sub">占盈亏 {fee_r:.1f}%</span></div>
  <div class="kpi kpi-cs"><span class="lbl">超短线 (<1m)</span><span class="val">{scalp_r:.1f}% {scalp_warn_html}</span><span class="sub">{stats.get('scalp_count',0)} 笔持仓不足60秒</span></div>
  <div class="kpi kpi-cs"><span class="lbl">平均持仓时长</span><span class="val" style="font-size:11px">{dur_html}</span><span class="sub">赢单 vs 亏单平均持仓比</span></div>
</div>"""

    # CS Filter toolbar
    cs_filter_toolbar = """<div class="cs-toolbar">
  <button class="cs-btn active" onclick="csFilter('all')">📋 全部订单</button>
  <button class="cs-btn" style="border-color:var(--red)" onclick="csFilter('stopout')">🔴 爆仓单 (Stop Out)</button>
  <button class="cs-btn" style="border-color:var(--yellow)" onclick="csFilter('scalp')">⚡ 超短线 (<1m)</button>
  <button class="cs-btn" style="border-color:var(--blue)" onclick="csFilter('swap')">🌙 隔夜 Swap 单</button>
  <span style="flex:1"></span>
  <span id="csFilterInfo" style="font-size:11px;color:var(--muted)"></span>
</div>"""

    # Swap burden data by symbol (top 10)
    sym_pl_raw = stats.get("sym_pl", {})
    sym_swap_raw = stats.get("sym_swap", {})
    all_syms_set = set(list(sym_pl_raw.keys())[:10]) | set(list(sym_swap_raw.keys())[:10])
    swap_burden_data = []
    for s in sorted(all_syms_set, key=lambda x: abs(sym_pl_raw.get(x, 0)) + abs(sym_swap_raw.get(x, 0)), reverse=True)[:10]:
        swap_burden_data.append({
            "name": s.upper(),
            "profit": round(sym_pl_raw.get(s, 0), 2),
            "swap": round(sym_swap_raw.get(s, 0), 2),
            "commission": 0,  # commission not tracked per-symbol currently
        })
    swap_burden_json = json.dumps(swap_burden_data, ensure_ascii=False)

    # Cashflow waterfall data
    total_dep = stats.get("total_deposit", 0)
    total_wd = stats.get("total_withdrawal", 0)
    total_sw = stats.get("total_swap", 0)
    total_com = stats.get("total_commission", 0)
    final_bal = net_profit + nd_val  # not perfectly accurate but close

    cf_waterfall_data = {
        "labels": ["初始资金", "+总入金", "-总出金", "±交易盈亏", "-总Swap", "-总佣金", "=最终余额"],
        "values": [
            0,
            total_dep,
            -total_wd,
            net_profit,
            total_sw,
            -total_com,
            round(net_profit + total_dep - total_wd + total_sw - total_com, 2),
        ]
    }
    cf_waterfall_json = json.dumps(cf_waterfall_data, ensure_ascii=False)

    html = html.replace("{CS_KPI_CARDS}", cs_cards_html)
    html = html.replace("{CS_FILTER_TOOLBAR}", cs_filter_toolbar)
    html = html.replace("{CS_TIMELINE_JSON}", cs_timeline_json)
    html = html.replace("{CS_CLOSE_REASON_JSON}", close_reason_json)
    html = html.replace("{CS_HOLDING_TIME_JSON}", holding_time_json)
    html = html.replace("{CS_SWAP_BURDEN_JSON}", swap_burden_json)
    html = html.replace("{CS_CASHFLOW_WATERFALL_JSON}", cf_waterfall_json)

    # ── v9.0 data ──
    html = html.replace("{MAE_MFE_JSON}", json.dumps(stats.get("mae_mfe_data", []), ensure_ascii=False))
    html = html.replace("{LEVERAGE_JSON}", json.dumps(stats.get("leverage_data", []), ensure_ascii=False))
    html = html.replace("{VOL_PL_SCATTER_JSON}", json.dumps(stats.get("vol_pl_scatter", []), ensure_ascii=False))
    html = html.replace("{HOLDING_PL_DIST_JSON}", json.dumps(stats.get("holding_pl_dist", []), ensure_ascii=False))
    return html


_HTML = r"""<!DOCTYPE html><html lang="zh-HK"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MT Desk — {ACCOUNT}</title>
<style>
:root,[data-theme="dark"]{--bg:#0b0e14;--surface:#151a23;--card:#1c2331;--border:#2e374a;--text:#e6edf3;--muted:#8b949e;--blue:#3b82f6;--green:#10b981;--red:#f43f5e;--yellow:#f59e0b;--purple:#8b5cf6;--radius:12px}
[data-theme="light"]{--bg:#f4f6f9;--surface:#ffffff;--card:#ffffff;--border:#e2e8f0;--text:#1e293b;--muted:#64748b;--blue:#2563eb;--green:#16a34a;--red:#e11d48;--yellow:#d97706;--purple:#7c3aed}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei','Helvetica Neue',sans-serif;background:var(--bg);color:var(--text);font-size:clamp(12px,1vw,15px);line-height:1.55;-webkit-font-smoothing:antialiased}
.header{background:var(--surface);border-bottom:1px solid var(--border);padding:clamp(12px,1vw,20px) clamp(14px,1.4vw,28px);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px}
.header h1{font-size:clamp(17px,1.5vw,23px);font-weight:800;color:var(--text);letter-spacing:-.5px;display:flex;align-items:center;gap:10px}
.header h1 span{font-size:clamp(11px,1vw,14px);font-weight:500;color:var(--muted);margin-left:4px}
.header .meta{font-size:clamp(10px,0.8vw,13px);color:var(--muted)}.header .meta b{color:var(--text)}
.theme-btn{background:var(--card);border:1px solid var(--border);color:var(--muted);padding:5px 11px;border-radius:7px;cursor:pointer;font-size:clamp(10px,0.8vw,13px);font-family:inherit}.theme-btn:hover{border-color:var(--blue);color:var(--text)}
.date-bar{display:flex;align-items:center;gap:8px;padding:8px clamp(14px,1.4vw,28px);background:var(--surface);border-bottom:1px solid var(--border);flex-wrap:wrap}
.date-bar input{padding:4px 8px;border:1px solid var(--border);border-radius:4px;font-size:clamp(10px,0.8vw,12px);background:var(--bg);color:var(--text);font-family:inherit}
.date-bar button{padding:4px 12px;border:1px solid var(--border);border-radius:4px;background:var(--card);color:var(--text);cursor:pointer;font-size:clamp(10px,0.8vw,12px);font-family:inherit}.date-bar button:hover{border-color:var(--blue)}
.date-bar .lbl{font-size:clamp(9px,0.7vw,11px);color:var(--muted)}
.main{max-width:1500px;margin:0 auto;padding:clamp(10px,1vw,20px)}
.kpi-row{display:grid;grid-template-columns:repeat(auto-fill,minmax(clamp(115px,11vw,150px),1fr));gap:clamp(6px,0.6vw,10px);margin-bottom:clamp(12px,1.1vw,18px)}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:clamp(12px,0.9vw,16px);text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.1);transition:border-color .2s,box-shadow .2s}
.kpi:hover{border-color:rgba(59,130,246,0.3);box-shadow:0 4px 16px rgba(0,0,0,.15)}
.kpi .lbl{display:block;font-size:clamp(9px,0.7vw,11px);color:var(--muted);margin-bottom:5px}
.kpi .val{display:block;font-size:clamp(16px,1.4vw,22px);font-weight:800;letter-spacing:-.5px}
.kpi.has-tip{position:relative;cursor:help}
.kpi .tip{display:none;position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:11px;line-height:1.4;white-space:normal;max-width:230px;text-align:left;z-index:100;box-shadow:0 4px 12px rgba(0,0,0,.2);pointer-events:none}
.kpi.has-tip .tip::after{content:'';position:absolute;top:100%;left:50%;transform:translateX(-50%);border:6px solid transparent;border-top-color:var(--border)}
.kpi.has-tip:hover .tip{display:block}
.summary-line{font-size:clamp(11px,0.9vw,14px);color:var(--text);margin-bottom:clamp(10px,1vw,16px);padding:10px 14px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius);line-height:1.6}
.summary-line b{color:var(--blue)}.summary-line .pos{color:var(--green)}.summary-line .neg{color:var(--red)}
.summary-row{display:grid;grid-template-columns:repeat(3,1fr);gap:clamp(8px,0.8vw,12px);margin-bottom:clamp(10px,1vw,16px)}
.summary-row.compact{grid-template-columns:1.1fr 1.1fr 1.3fr}
.summary-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:clamp(12px,1vw,16px);display:flex;flex-direction:column;justify-content:center;min-height:120px;box-shadow:0 1px 2px rgba(0,0,0,.05)}
.summary-card.wide{grid-column:span 1}
.summary-title{font-size:clamp(11px,0.85vw,13px);color:var(--muted);margin-bottom:8px;font-weight:600;display:flex;align-items:center;gap:6px}
.summary-title .hint{font-size:10px;color:var(--muted);font-weight:400}
.summary-val{font-size:28px;font-weight:700;color:var(--text)}
.summary-sub{font-size:11px;color:var(--muted);margin-top:4px}
.insight-list{list-style:none;font-size:11px;color:var(--text);line-height:1.7;padding:0;margin:0}
.insight-list li{padding-left:16px;position:relative}
.insight-list li::before{content:'→';position:absolute;left:0;color:var(--blue);font-weight:700}
.section-title{font-size:clamp(15px,1.2vw,19px);font-weight:700;color:var(--text);margin:24px 0 12px;padding-bottom:8px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px}
.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:clamp(10px,1vw,14px);margin-bottom:16px}
.chart-box{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);overflow:visible;padding:14px 16px 8px;box-shadow:0 2px 8px rgba(0,0,0,.1);transition:border-color .2s,box-shadow .2s}
.chart-box:hover{border-color:rgba(59,130,246,0.2);box-shadow:0 4px 16px rgba(0,0,0,.15)}
.chart-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.chart-title{font-size:clamp(13px,1vw,15px);font-weight:700;color:var(--text);display:flex;align-items:center;gap:6px;cursor:help;position:relative}
.chart-title .ct-info{font-size:12px;color:var(--muted);font-weight:400;cursor:help}
.chart-title .ct-tip{display:none;position:absolute;bottom:calc(100% + 8px);left:0;background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:8px 12px;font-size:12px;font-weight:400;line-height:1.5;white-space:normal;max-width:320px;text-align:left;z-index:200;box-shadow:0 4px 16px rgba(0,0,0,.25);pointer-events:none}
.chart-title:hover .ct-tip{display:block}
.chart-sub{font-size:10px;color:var(--muted);font-weight:400}
#chart-symbol-pie{cursor:pointer}
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
tr:hover td{background:var(--surface)}.win,.win td{color:var(--green)!important}.loss,.loss td{color:var(--red)!important}.win td{background:rgba(34,197,94,0.08)}.loss td{background:rgba(239,68,68,0.08)}
tr.highlight td{outline:2px solid #f59e0b;outline-offset:-1px}
.quick-btn{padding:3px 10px;border:1px solid var(--border);border-radius:4px;background:var(--card);color:var(--muted);cursor:pointer;font-size:clamp(9px,0.7vw,11px);font-family:inherit}.quick-btn:hover{border-color:var(--blue);color:var(--text)}.quick-btn.active{border-color:var(--blue);color:var(--blue);background:rgba(59,130,246,0.1)}
@media(max-width:900px){.summary-row,.summary-row.compact{grid-template-columns:1fr 1fr}.chart-grid{grid-template-columns:1fr}.kpi-row{grid-template-columns:repeat(3,1fr)}}
@media(max-width:600px){.summary-row,.summary-row.compact{grid-template-columns:1fr}.kpi-row{grid-template-columns:repeat(2,1fr)}.equity-section .chart-box-full{padding:10px}}
.kpi-core-row{grid-template-columns:repeat(4,1fr);gap:clamp(10px,1vw,16px)}
.kpi-core-row .kpi-core{padding:clamp(14px,1.2vw,20px)}
.kpi-core-row .kpi-core .lbl{font-size:clamp(10px,0.8vw,12px);letter-spacing:.5px;text-transform:uppercase}
.kpi-core-row .kpi-core .val{font-size:clamp(20px,2vw,30px);font-weight:800;margin-top:4px}
.kpi-sec-row{grid-template-columns:repeat(auto-fill,minmax(clamp(90px,9vw,120px),1fr));gap:clamp(4px,0.4vw,8px);margin-bottom:clamp(10px,1vw,16px)}
.kpi-sec-row .kpi-sec{padding:clamp(6px,0.5vw,10px)}
.kpi-sec-row .kpi-sec .lbl{font-size:clamp(8px,0.6vw,10px);margin-bottom:2px}
.kpi-sec-row .kpi-sec .val{font-size:clamp(13px,1.1vw,16px)}
/* Equity section full width */
.equity-section{margin-bottom:clamp(12px,1.2vw,20px)}
.chart-box-full{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);overflow:visible;padding:14px 18px 8px;box-shadow:0 1px 2px rgba(0,0,0,.05)}
/* Quick insights bar */
.quick-insights{display:flex;align-items:center;gap:10px;background:linear-gradient(135deg,var(--surface),var(--card));border:1px solid var(--border);border-radius:var(--radius);padding:10px 16px;margin-bottom:12px;font-size:12px;color:var(--text)}
.qi-icon{font-size:18px}
.qi-text{line-height:1.5}
/* Zebra table rows */
#tradeBody tr:nth-child(even){background:rgba(127,127,127,0.04)}
#tradeBody tr:nth-child(even):hover td{background:var(--surface)}
/* Direction & profit badges */
.dir-badge{display:inline-block;padding:2px 8px;border-radius:4px;font-weight:700;font-size:10px}
.dir-badge.buy{background:rgba(34,197,94,0.15);color:var(--green)}
.dir-badge.sell{background:rgba(239,68,68,0.15);color:var(--red)}
.pl-badge{display:inline-block;padding:2px 8px;border-radius:4px;font-weight:600;font-size:10px}
.pl-badge.win{background:rgba(34,197,94,0.12);color:var(--green)}
.pl-badge.loss{background:rgba(239,68,68,0.12);color:var(--red)}
/* Column toggle */
.col-toggle{display:inline-flex;align-items:center;gap:4px;font-size:10px;color:var(--muted);cursor:pointer;padding:3px 8px;border:1px solid var(--border);border-radius:4px;background:var(--card);margin-left:6px}
.col-toggle:hover{border-color:var(--blue)}
.col-hidden{display:none!important}
/* Volume formatting */
.vol-num{font-family:'SF Mono','Fira Code',monospace;font-variant-numeric:tabular-nums}
@media print{@page{margin:12mm}.header,.date-bar,.toolbar,.theme-btn,.metric-guide,.col-toggle{display:none!important}.chart-box{break-inside:avoid;page-break-inside:avoid}.table-wrap{overflow-x:visible}body{font-size:10pt;background:#fff!important;color:#000!important}.kpi{border:1px solid #ccc!important;background:#fff!important;box-shadow:none}.kpi .val{font-size:14pt}.kpi .lbl,.kpi .tip{color:#666!important}.chart-grid{grid-template-columns:1fr}.section-title{color:#000!important;border-bottom:1px solid #999}.summary-line{background:#f5f5f5!important;border:1px solid #ccc}.summary-card{background:#fff!important;border:1px solid #ccc}.equity-section{margin-bottom:16px}.cs-section,.cs-kpi-row,.cs-toolbar{display:none!important}.cs-kpi-row .kpi{display:none!important}}
/* CS Audit Mode */
.cs-section{margin-bottom:18px}.cs-kpi-row{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:10px 0 12px;padding:0 clamp(14px,1.4vw,28px)}.kpi-cs{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:10px 14px;text-align:left;box-shadow:0 1px 2px rgba(0,0,0,.05);position:relative}.kpi-cs .lbl{display:block;font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px}.kpi-cs .val{display:block;font-size:16px;font-weight:700;color:var(--text)}.kpi-cs .sub{display:block;font-size:10px;color:var(--muted);margin-top:2px}.kpi-cs.cs-warn{border-left:3px solid var(--red)}.cs-toolbar{display:flex;align-items:center;gap:6px;padding:6px clamp(14px,1.4vw,28px);background:var(--surface);border-bottom:1px solid var(--border);flex-wrap:wrap}.cs-btn{padding:3px 10px;border:1px solid var(--border);border-radius:4px;background:var(--card);color:var(--muted);cursor:pointer;font-size:10px;font-family:inherit}.cs-btn:hover{border-color:var(--blue);color:var(--text)}.cs-btn.active{border-color:var(--blue);color:var(--blue);background:rgba(59,130,246,0.1)}.cs-chart-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin:12px 0}.cs-chart-box{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);overflow:visible;padding:10px 12px 6px;box-shadow:0 1px 2px rgba(0,0,0,.05)}.cs-chart-box-wide{grid-column:span 2}@media(max-width:900px){.cs-kpi-row{grid-template-columns:1fr 1fr}.cs-chart-grid{grid-template-columns:1fr}.cs-chart-box-wide{grid-column:span 1}}@media(max-width:600px){.cs-kpi-row{grid-template-columns:1fr}}
/* ═══ Tab Navigation ═══ */
.tab-nav{display:flex;gap:0;padding:0 clamp(14px,1.4vw,28px);background:var(--surface);border-bottom:2px solid var(--border);overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none}
.tab-nav::-webkit-scrollbar{display:none}
.tab-btn{padding:10px 18px;border:none;border-bottom:3px solid transparent;background:transparent;color:var(--muted);font-size:clamp(11px,0.9vw,13px);font-weight:600;cursor:pointer;white-space:nowrap;transition:all .2s;font-family:inherit;position:relative}
.tab-btn:hover{color:var(--text);background:rgba(59,130,246,0.05)}
.tab-btn.active{color:var(--blue);border-bottom-color:var(--blue);background:rgba(59,130,246,0.08)}
.tab-btn .tab-icon{margin-right:6px;font-size:14px}
.tab-panel{display:none;animation:tabFadeIn .3s ease}
.tab-panel.active{display:block}
@keyframes tabFadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.tab-panel .chart-grid,.tab-panel .summary-row{margin-bottom:clamp(10px,1vw,16px)}
/* ═══ MAE/MFE Scatter ═══ */
.scatter-grid{display:grid;grid-template-columns:1fr 1fr;gap:clamp(10px,1vw,14px);margin-bottom:16px}
@media(max-width:900px){.scatter-grid{grid-template-columns:1fr}}
/* ═══ Risk Banner ═══ */
.risk-banner{border-radius:var(--radius);padding:12px 18px;margin:0 clamp(14px,1.4vw,28px) 16px;display:flex;align-items:center;gap:12px;font-size:13px;line-height:1.6;animation:tabFadeIn .4s ease}
.risk-banner.warn{background:rgba(244,63,94,0.1);border:1px solid rgba(244,63,94,0.3);color:#fda4af}
.risk-banner.info{background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.2);color:var(--blue)}
.risk-banner.good{background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.2);color:var(--green)}
.risk-banner .rb-icon{font-size:22px;flex-shrink:0}
.risk-banner .rb-tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}
.risk-banner .rb-tag{background:rgba(244,63,94,0.15);border:1px solid rgba(244,63,94,0.2);padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}
/* ═══ Holding P&L Bar ═══ */
.holding-pl-bar{display:flex;gap:6px;align-items:flex-end;height:120px;margin-top:8px}
.holding-pl-seg{flex:1;border-radius:4px 4px 0 0;position:relative;min-height:4px;transition:all .3s}
.holding-pl-seg:hover{opacity:.85}
.holding-pl-label{position:absolute;bottom:-18px;left:50%;transform:translateX(-50%);font-size:9px;color:var(--muted);white-space:nowrap}
</style></head><body>
<div class="header"><h1>🛡️ MT Risk Standard <span>— Account #{ACCOUNT}</span></h1>
<div style="display:flex;align-items:center;gap:12px">
  <div class="meta"><span id="headerCount">{COUNT}</span> 筆交易 · P/L: <b id="headerPL" style="color:{PL_COLOR}">{PL}</b> · 獲利佔比: <b id="headerWR">{WR}</b></div>
  <button class="theme-btn" onclick="toggleTheme()" id="themeBtn">{THEME_ICON}</button>
  <button class="theme-btn" onclick="window.print()" title="列印報告">🖨️</button>
</div></div>
<div class="date-bar">
  <span class="lbl">📅 快速:</span>
  <button class="quick-btn" onclick="quickFilter('today')">今日</button>
  <button class="quick-btn" onclick="quickFilter('week')">本週</button>
  <button class="quick-btn" onclick="quickFilter('month')">本月</button>
  <button class="quick-btn" onclick="quickFilter('3m')">近三月</button>
  <button class="quick-btn" onclick="quickFilter('all')">全部</button>
  <span class="lbl" style="margin-left:12px">自訂:</span>
  <input type="date" id="dateFrom" value="{DATE_MIN}" onchange="applyDateFilter()">
  <span class="lbl">至</span>
  <input type="date" id="dateTo" value="{DATE_MAX}" onchange="applyDateFilter()">
  <button onclick="resetDateFilter()">重置</button>
  <span class="lbl" id="filterInfo"></span>
</div>
<!-- ═══ Risk Banner ═══ -->
<div id="riskBanner" class="risk-banner {RISK_BANNER_LEVEL}">{RISK_BANNER_HTML}</div>
<!-- ═══ Tab Navigation ═══ -->
<div class="tab-nav" id="tabNav">
  <button class="tab-btn active" onclick="switchTab('dashboard')"><span class="tab-icon">📊</span>Dashboard 總覽</button>
  <button class="tab-btn" onclick="switchTab('risk')"><span class="tab-icon">🛡️</span>風險與權益</button>
  <button class="tab-btn" onclick="switchTab('habits')"><span class="tab-icon">🧠</span>交易習慣</button>
  <button class="tab-btn" onclick="switchTab('mae')"><span class="tab-icon">📐</span>MAE/MFE 點陣</button>
  <button class="tab-btn" onclick="switchTab('cs')"><span class="tab-icon">🔍</span>CS 風控審計</button>
</div>
<div class="main">

<!-- ════════════ Tab 1: Dashboard 總覽 ════════════ -->
<div class="tab-panel active" id="tab-dashboard">
<div id="summaryLine" class="summary-line"></div>
<div class="kpi-row kpi-core-row" id="kpiCore">{CORE_CARDS}</div>
<div class="equity-section">
  <div class="chart-box chart-box-full">
    <div class="chart-head"><div class="chart-title">📈 權益曲線與最大回撤 <span class="ct-info">ⓘ</span><span class="ct-tip">累積淨盈虧隨時間變化的曲線，下方子圖顯示每筆交易的回撤幅度。回撤越大代表風險越高。</span></div><div class="chart-sub" id="equitySub"></div></div>
    <div id="chart-equity" style="width:100%;height:400px"></div>
  </div>
</div>
<div class="kpi-row kpi-sec-row" id="kpiSec">{SEC_CARDS}</div>
{SUMMARY}
</div>

<!-- ════════════ Tab 2: 風險與權益 ════════════ -->
<div class="tab-panel" id="tab-risk">
<div class="section-title">📉 月度/季度盈虧分析</div>
<div class="chart-grid">
  <div class="chart-box">
    <div class="chart-head"><div class="chart-title">月度盈虧瀑布圖 <span class="ct-info">ⓘ</span><span class="ct-tip">從起始權益開始，每月盈虧的累加效果。綠色=盈利月，紅色=虧損月，最終柱=結束權益。</span></div><div class="chart-sub">起始權益 → 每月貢獻 → 最終權益</div></div>
    <div id="chart-waterfall" style="width:100%;height:300px"></div>
  </div>
  <div class="chart-box">
    <div class="chart-head"><div class="chart-title">每月多空傾向與獲利佔比 <span class="ct-info">ⓘ</span><span class="ct-tip">分組柱狀圖顯示每月做多(Buy)與做空(Sell)的盈虧，折線顯示當月獲利交易佔比。</span></div><div class="chart-sub">分組柱 = 做多/做空 P&L，折線 = 當月日獲利佔比</div></div>
    <div id="chart-ls-monthly" style="width:100%;height:300px"></div>
  </div>
  <div class="chart-box">
    <div class="chart-head"><div class="chart-title">季度品種偏好變化 <span class="ct-info">ⓘ</span><span class="ct-tip">100% 堆疊柱狀圖，顯示每季度各交易品種的佔比變化，觀察品種集中度趨勢。</span></div><div class="chart-sub">100% 堆疊柱：看比例變化</div></div>
    <div id="chart-quarterly-sym" style="width:100%;height:300px"></div>
  </div>
</div>
<div class="section-title">⚖️ 槓桿/手數與盈虧相關性</div>
<div class="chart-grid">
  <div class="chart-box">
    <div class="chart-head"><div class="chart-title">手數分桶盈虧分析 <span class="ct-info">ⓘ</span><span class="ct-tip">按交易手數(Lots)區間分組，顯示各組的平均盈虧(柱)和勝率(折線)。觀察大手數是否帶來更高收益或更高風險。</span></div><div class="chart-sub">按手數區間分組的平均盈虧與勝率</div></div>
    <div id="chart-leverage" style="width:100%;height:300px"></div>
  </div>
  <div class="chart-box">
    <div class="chart-head"><div class="chart-title">手數 vs 盈虧散點圖 <span class="ct-info">ⓘ</span><span class="ct-tip">每筆交易的手數(X軸)與盈虧(Y軸)分佈。氣泡大小=盈虧金額，綠=盈利、紅=虧損。觀察手數與盈虧的相關性。</span></div><div class="chart-sub">每筆交易的手數與盈虧分佈</div></div>
    <div id="chart-vol-pl-scatter" style="width:100%;height:300px"></div>
  </div>
</div>
</div>

<!-- ════════════ Tab 3: 交易習慣 ════════════ -->
<div class="tab-panel" id="tab-habits">
<div class="section-title">🕐 時間維度分析</div>
<div class="chart-grid">
  <div class="chart-box">
    <div class="chart-head"><div class="chart-title">交易時段熱力圖 <span class="ct-info">ⓘ</span><span class="ct-tip">星期×小時的交易頻率熱力圖，顏色越深代表該時段交易越密集。幫助識別交易活躍時段。</span></div><div class="chart-sub">星期 × 小時：顏色越深 = 筆數越多</div></div>
    <div id="chart-heatmap" style="width:100%;height:300px"></div>
  </div>
  <div class="chart-box">
    <div class="chart-head"><div class="chart-title">交易時段表現 <span class="ct-info">ⓘ</span><span class="ct-tip">亞洲盤、倫敦盤、紐約盤的三元雷達圖，比較各時段的交易筆數、獲利佔比和總盈虧。</span></div><div class="chart-sub">亞洲盤 vs 倫敦盤 vs 紐約盤 — 筆數/獲利佔比/盈虧 三元分析</div></div>
    <div id="chart-session-radar" style="width:100%;height:320px"></div>
  </div>
  <div class="chart-box">
    <div class="chart-head"><div class="chart-title">持倉時間分佈 <span class="ct-info">ⓘ</span><span class="ct-tip">所有交易按持倉時長分桶統計。持倉過短可能為剝頭皮，過長可能為波段策略。</span></div><div class="chart-sub" id="durationSub"></div></div>
    <div id="chart-duration" style="width:100%;height:300px"></div>
  </div>
  <div class="chart-box">
    <div class="chart-head"><div class="chart-title">持倉時間盈虧分佈 <span class="ct-info">ⓘ</span><span class="ct-tip">各持倉時間區間的累計盈虧。幫助判斷哪種持倉週期最賺錢或最虧錢。</span></div><div class="chart-sub">各時間段的累計盈虧與交易筆數</div></div>
    <div id="chart-holding-pl" style="width:100%;height:300px"></div>
  </div>
</div>
<div class="section-title">💱 品種維度分析</div>
<div class="chart-grid">
  <div class="chart-box">
    <div class="chart-head"><div class="chart-title">品種綜合矩陣 <span class="ct-info">ⓘ</span><span class="ct-tip">氣泡矩陣：X=交易次數，Y=獲利佔比，氣泡大小=盈虧貢獻。快速比較各品種的表現。</span></div><div class="chart-sub">X=交易次數 · Y=獲利佔比 · 大小=盈虧貢獻</div></div>
    <div id="chart-sym-bubble" style="width:100%;height:300px"></div>
  </div>
  <div class="chart-box">
    <div class="chart-head"><div class="chart-title">品種盈虧貢獻 <span class="ct-info">ⓘ</span><span class="ct-tip">各交易品種的總盈虧柱狀圖。綠色=盈利品種，紅色=虧損品種。點擊可篩選該品種交易。</span></div></div>
    <div id="chart-symbol-pl" style="width:100%;height:280px"></div>
  </div>
</div>
</div>

<!-- ════════════ Tab 4: MAE/MFE 點陣 ════════════ -->
<div class="tab-panel" id="tab-mae">
<div class="section-title">📐 MAE / MFE 最佳化分析</div>
<div style="font-size:12px;color:var(--muted);margin-bottom:12px;padding:8px 12px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius)">
  <b>MAE</b>（最大不利偏移）= 平倉前曾浮虧多少 · <b>MFE</b>（最大有利偏移）= 平倉前曾浮盈多少 · 評估停損點是否設得太寬、是否有及時獲利出場
</div>
<div class="scatter-grid">
  <div class="chart-box">
    <div class="chart-head"><div class="chart-title">MAE 散點圖 <span class="ct-info">ⓘ</span><span class="ct-tip">MAE=最大不利偏移(Maximum Adverse Excursion)，即平倉前最大浮虧金額。點的顏色=最終盈虧，觀察虧損交易的 MAE 是否過大。</span></div><div class="chart-sub">X=交易序號 · Y=最大浮虧金額 · 顏色=盈虧</div></div>
    <div id="chart-mae" style="width:100%;height:350px"></div>
  </div>
  <div class="chart-box">
    <div class="chart-head"><div class="chart-title">MFE 散點圖 <span class="ct-info">ⓘ</span><span class="ct-tip">MFE=最大有利偏移(Maximum Favorable Excursion)，即平倉前最大浮盈金額。如果盈利交易的 MFE 遠大於實際盈利，說明未及時獲利出場。</span></div><div class="chart-sub">X=交易序號 · Y=最大浮盈金額 · 顏色=盈虧</div></div>
    <div id="chart-mfe" style="width:100%;height:350px"></div>
  </div>
</div>
<div class="chart-grid">
  <div class="chart-box">
    <div class="chart-head"><div class="chart-title">MAE vs MFE 分佈 <span class="ct-info">ⓘ</span><span class="ct-tip">X=MAE(最大浮虧)，Y=MFE(最大浮盈)，氣泡大小=最終盈虧。理想交易應在左上方(MFE高、MAE低)。</span></div><div class="chart-sub">X=MAE · Y=MFE · 氣泡=盈虧金額</div></div>
    <div id="chart-mae-mfe-scatter" style="width:100%;height:350px"></div>
  </div>
  <div class="chart-box">
    <div class="chart-head"><div class="chart-title">MAE/MFE 統計摘要 <span class="ct-info">ⓘ</span><span class="ct-tip">按盈利/虧損分組的 MAE/MFE 統計比較。如果虧損單平均 MAE 遠大於平均虧損，說明停損設得太寬。</span></div></div>
    <div id="mae-mfe-summary" style="padding:16px;font-size:13px;line-height:2;color:var(--text)"></div>
  </div>
</div>
</div>

<!-- ════════════ Tab 5: CS 風控審計 ════════════ -->
<div class="tab-panel" id="tab-cs">
{CS_KPI_CARDS}
{CS_FILTER_TOOLBAR}
<div class="section-title">🔍 CS 客服审计图表</div>
<div class="cs-chart-grid">
  <div class="cs-chart-box">
    <div class="chart-head"><div class="chart-title">平倉原因歸因 <span class="ct-info">ⓘ</span><span class="ct-tip">自動偵測平倉原因：止盈(TP)、止損(SL)、強平(SO)、手動平倉等分佈。強平佔比高代表風險控制不足。</span></div></div>
    <div id="chart-close-reason" style="width:100%;height:260px"></div>
  </div>
  <div class="cs-chart-box">
    <div class="chart-head"><div class="chart-title">持倉時長分佈 <span class="ct-info">ⓘ</span><span class="ct-tip">秒級精度持倉時間分桶。< 10秒 可能為高頻刷單或強平特徵，需結合盈虧判斷。</span></div><div class="chart-sub">秒级分桶</div></div>
    <div id="chart-holding-time" style="width:100%;height:260px"></div>
  </div>
  <div class="cs-chart-box">
    <div class="chart-head"><div class="chart-title">品種 Swap 負擔 <span class="ct-info">ⓘ</span><span class="ct-tip">各品種的淨盈虧(綠/紅)、隔夜利息(橙)、手續費(紫)堆疊比較。Swap 佔比過高侵蝕利潤。</span></div><div class="chart-sub">盈亏 vs Swap vs 佣金</div></div>
    <div id="chart-swap-burden" style="width:100%;height:260px"></div>
  </div>
  <div class="cs-chart-box cs-chart-box-wide">
    <div class="chart-head"><div class="chart-title">出入金瀑布圖 <span class="ct-info">ⓘ</span><span class="ct-tip">帳戶資金流向：入金(綠)、出金(紅)、交易盈虧的累積效果。最終柱=當前淨權益。</span></div></div>
    <div id="chart-cashflow-waterfall" style="width:100%;height:260px"></div>
  </div>
</div>
</div>
<!-- End CS tab -->

</div><!-- end .main -->
<div class="section-title">📋 逐筆明細</div>
<div class="toolbar"><input type="text" id="searchBox" placeholder="搜尋 Ticket / 品種 / 日期..." oninput="doSearch()">
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
<th onclick="sortBy('close')">平倉<span class="sort-arrow" id="sa-close"></span></th>
<th onclick="sortBy('close_price')">平倉價<span class="sort-arrow" id="sa-close_price"></span></th>
<th onclick="sortBy('duration_h')">持倉時間<span class="sort-arrow" id="sa-duration_h"></span></th>
<th onclick="sortBy('profit_per_lot')">每手盈虧<span class="sort-arrow" id="sa-profit_per_lot"></span></th>
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
var SYM_PL_DATA={SYM_PL_JSON};
var VOL_DATA={VOL_JSON};
var SWAP_DATA={SWAP_JSON};
var data=ALL_TRADES.slice();

var CHART_WATERFALL={WATERFALL_JSON};
var CHART_LS_MONTHLY={LS_MONTHLY_JSON};
var CHART_QUARTERLY_SYM={QUARTERLY_SYM_JSON};
var CHART_EQUITY={EQUITY_JSON};
var CHART_DURATION={DURATION_JSON};
var CHART_HEATMAP={HEATMAP_JSON};
var SESSION_RADAR={SESSION_RADAR_JSON};
var SYM_BUBBLE={SYM_BUBBLE_JSON};
var CHART_GRAN="{GRAN}";
var DATE_SPAN={DATE_SPAN};
var CS_TIMELINE_DATA={CS_TIMELINE_JSON};
var CS_CLOSE_REASON={CS_CLOSE_REASON_JSON};
var CS_HOLDING_TIME={CS_HOLDING_TIME_JSON};
var CS_SWAP_BURDEN={CS_SWAP_BURDEN_JSON};
var CS_CASHFLOW_WATERFALL={CS_CASHFLOW_WATERFALL_JSON};
var MAE_MFE_DATA={MAE_MFE_JSON};
var LEVERAGE_DATA={LEVERAGE_JSON};
var VOL_PL_SCATTER={VOL_PL_SCATTER_JSON};
var HOLDING_PL_DIST={HOLDING_PL_DIST_JSON};
var SESSION_PNL_DATA={SESSION_PNL_JSON};

(function(){var s=localStorage.getItem('mt-theme');var m=window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light';var th=s||m;document.documentElement.setAttribute('data-theme',th);var btn=document.getElementById('themeBtn');if(btn)btn.textContent=th==='dark'?'🌙':'☀️';})();
window.matchMedia('(prefers-color-scheme:dark)').addEventListener('change',function(e){if(!localStorage.getItem('mt-theme')){document.documentElement.setAttribute('data-theme',e.matches?'dark':'light');initAllCharts();}});
function toggleTheme(){var c=document.documentElement.getAttribute('data-theme');var n=c==='dark'?'light':'dark';document.documentElement.setAttribute('data-theme',n);localStorage.setItem('mt-theme',n);var btn=document.getElementById('themeBtn');if(btn)btn.textContent=n==='dark'?'🌙':'☀️';initAllCharts();initNewCharts();initMAECharts();}

// ═══ Tab Switching ═══
function switchTab(tabId){
  document.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active');});
  document.querySelectorAll('.tab-btn').forEach(function(b){b.classList.remove('active');});
  var panel=document.getElementById('tab-'+tabId);
  if(panel)panel.classList.add('active');
  var btns=document.querySelectorAll('.tab-btn');
  var tabs=['dashboard','risk','habits','mae','cs'];
  var idx=tabs.indexOf(tabId);
  if(idx>=0&&btns[idx])btns[idx].classList.add('active');
  // Resize charts in the newly visible tab
  setTimeout(function(){
    var charts=panel?panel.querySelectorAll('[id^="chart-"]'):[];
    charts.forEach(function(el){if(el._ec)el._ec.resize();});
    // Init new charts if switching to their tab
    if(tabId==='risk')initNewCharts();
    if(tabId==='mae')initMAECharts();
    if(tabId==='habits')initHabitsCharts();
    if(tabId==='cs')initCSCharts();
  },50);
}

function ecOpt(o,isDark){
  var el=document.getElementById(o.id);
  if(!el)return;
  try {
    if(el._ec){try{el._ec.dispose();}catch(e){}}
    el._ec=null;
    // Clear any stale ECharts DOM
    el.removeAttribute('_echarts_instance_');
    var chart=echarts.init(el,isDark?'dark':null);
    chart.setOption(o.opt);
    el._ec=chart;
  } catch(e) {
    console.error('Chart init failed for '+o.id+': '+e.message);
  }
}

function initAllCharts(){
  var isDark=document.documentElement.getAttribute('data-theme')==='dark';
  var tc=isDark?'#e8ecf4':'#1e293b';
  var mc=isDark?'#7b879c':'#64748b';
  var C10=isDark?['#5470c6','#fac858','#ee6666','#73c0de','#3ba272','#fc8452','#9a60b4','#ea7ccc','#48b8d0','#f97316']:['#5470c6','#fac858','#ee6666','#73c0de','#3ba272','#fc8452','#9a60b4','#ea7ccc','#48b8d0','#f97316'];
  var G=isDark?'#22c55e':'#16a34a';
  var R=isDark?'#ef4444':'#dc2626';
  var B=isDark?'#3b82f6':'#2563eb';
  var Y=isDark?'#eab308':'#ca8a04';

  // Symbol pie
  ecOpt({id:'chart-symbol-pie',opt:{
    tooltip:{trigger:'item',formatter:'{b}: {c} 筆 ({d}%)'},legend:{bottom:0,textStyle:{color:mc,fontSize:10}},color:C10,
    series:[{type:'pie',radius:['45%','75%'],center:['50%','48%'],avoidLabelOverlap:false,label:{show:true,formatter:'{b} {d}%',fontSize:10,color:tc},data:SYM_PIE_DATA,emphasis:{scale:false}}]
  }},isDark);
  var pieEl=document.getElementById('chart-symbol-pie');if(pieEl&&pieEl._ec){pieEl._ec.off('click');pieEl._ec.on('click',function(params){if(params.name)filterBySymbol(params.name);});}

  // Symbol P&L bar (vertical)
  var sp=SYM_PL_DATA;
  ecOpt({id:'chart-symbol-pl',opt:{
    tooltip:{trigger:'axis',formatter:function(p){return p[0].name+': $'+p[0].value.toFixed(2);}},
    grid:{left:55,right:15,top:10,bottom:50},
    xAxis:{type:'category',data:sp.map(function(d){return d.name;}),axisLabel:{fontSize:9,rotate:30,color:tc},axisLine:{lineStyle:{color:mc}}},
    yAxis:{type:'value',axisLabel:{fontSize:9,formatter:'${value}'},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
    series:[{type:'bar',data:sp.map(function(d){return{value:d.value,itemStyle:{color:d.value>=0?G:R}};}),barWidth:'55%',label:{show:true,position:'top',formatter:function(p){return '$'+p.value.toFixed(0);},fontSize:9,color:tc}}]
  }},isDark);

  // Volume donut
  ecOpt({id:'chart-volume-donut',opt:{
    tooltip:{trigger:'item',formatter:'{b}: {c} 手 ({d}%)'},
    series:[{type:'pie',radius:['50%','75%'],center:['50%','50%'],avoidLabelOverlap:false,
      label:{show:true,formatter:'{b}\n{d}%',fontSize:10,color:tc},data:VOL_DATA,emphasis:{scale:false}}]
  }},isDark);

  // Swap bar (vertical)
  var sw=SWAP_DATA;
  ecOpt({id:'chart-swap-bar',opt:{
    tooltip:{trigger:'axis',formatter:function(p){return p[0].name+': $'+p[0].value.toFixed(2);}},
    grid:{left:50,right:15,top:10,bottom:50},
    xAxis:{type:'category',data:sw.map(function(d){return d.name;}),axisLabel:{fontSize:9,rotate:30,color:tc},axisLine:{lineStyle:{color:mc}}},
    yAxis:{type:'value',axisLabel:{fontSize:9,formatter:'${value}'},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
    series:[{type:'bar',data:sw.map(function(d){return{value:d.value,itemStyle:{color:d.value>=0?G:R}};}),barWidth:'55%',label:{show:true,position:'top',formatter:function(p){return '$'+p.value.toFixed(0);},fontSize:9,color:tc}}]
  }},isDark);

  // Waterfall monthly P&L with cumulative line
  var wf=CHART_WATERFALL;
  var waterfallSeries=[];
  var cum=0,cumData=[];
  wf.data.forEach(function(v){waterfallSeries.push({value:v,from:Math.round(cum*100)/100,to:Math.round((cum+v)*100)/100});cum+=v;cumData.push(Math.round(cum*100)/100);});
  ecOpt({id:'chart-waterfall',opt:{
    tooltip:{trigger:'axis',axisPointer:{type:'shadow'},formatter:function(p){
      var d=p[0];var item=waterfallSeries[d.dataIndex];
      return d.name+'<br/>變化: $'+d.value.toFixed(2)+'<br/>累計: $'+item.to.toFixed(2);
    }},
    grid:{left:60,right:60,top:15,bottom:35},
    xAxis:{type:'category',data:wf.labels,axisLabel:{fontSize:9,rotate:30,interval:Math.max(1,Math.floor(wf.labels.length/8))},axisLine:{lineStyle:{color:mc}}},
    yAxis:[
      {type:'value',axisLabel:{formatter:'$ {value}'},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
      {type:'value',axisLabel:{formatter:'$ {value}'}}
    ],
    series:[{
      name:'月度盈虧',type:'bar',stack:'Total',barWidth:'55%',
      itemStyle:{borderColor:'transparent',color:function(p){var v=p.value;return v>=0?G:R;}},
      data:waterfallSeries.map(function(o){return o.value;}),
      label:{show:true,position:'top',formatter:function(p){return (p.value>=0?'+':'')+p.value.toFixed(0);},fontSize:9,color:tc}
    },{
      name:'置底',type:'bar',stack:'Total',itemStyle:{borderColor:'transparent',color:'rgba(0,0,0,0)'},
      emphasis:{itemStyle:{borderColor:'transparent',color:'rgba(0,0,0,0)'}},
      data:waterfallSeries.map(function(o){return o.from>=0?o.from:0;})
    },{
      name:'累計盈虧',type:'line',yAxisIndex:1,data:cumData,
      itemStyle:{color:Y},symbol:'circle',symbolSize:5,lineStyle:{width:2,type:'dashed'},
      label:{show:true,position:'right',formatter:function(p){return '$'+p.value.toFixed(0);},fontSize:9,color:Y}
    }]
  }},isDark);

  // Long/Short monthly P&L stacked bar + win rate line
  var ls=CHART_LS_MONTHLY;
  var lsLongPos=ls.long.map(function(v){return Math.max(0,v);});
  var lsLongNeg=ls.long.map(function(v){return Math.min(0,v);});
  var lsShortPos=ls.short.map(function(v){return Math.max(0,v);});
  var lsShortNeg=ls.short.map(function(v){return Math.min(0,v);});
  ecOpt({id:'chart-ls-monthly',opt:{
    tooltip:{trigger:'axis',formatter:function(p){
      var parts=p.filter(function(s){return s.seriesName.indexOf('置底')<0;}).map(function(s){return s.marker+s.seriesName+': $'+s.value.toFixed(2);});
      parts.unshift(p[0].name);return parts.join('<br/>');
    }},
    legend:{bottom:0,textStyle:{fontSize:10,color:tc}},grid:{left:60,right:55,top:15,bottom:40},
    xAxis:{type:'category',data:ls.labels,axisLabel:{fontSize:9,rotate:30,interval:Math.max(1,Math.floor(ls.labels.length/8))},axisLine:{lineStyle:{color:mc}}},
    yAxis:[
      {type:'value',name:'P&L ($)',nameTextStyle:{fontSize:9,color:mc},axisLabel:{fontSize:9,formatter:'${value}'},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
      {type:'value',name:'日獲利佔比 %',nameTextStyle:{fontSize:9,color:mc},axisLabel:{formatter:'{value}%'},max:100}
    ],
    series:[
      {name:'做多 Long (+)',type:'bar',stack:'positive',data:lsLongPos,itemStyle:{color:G},barWidth:'40%'},
      {name:'做多 Long (-)',type:'bar',stack:'negative',data:lsLongNeg,itemStyle:{color:isDark?'#ef9a9a':'#ef4444'},barWidth:'40%'},
      {name:'做空 Short (+)',type:'bar',stack:'positive',data:lsShortPos,itemStyle:{color:isDark?'#66bb6a':'#16a34a'},barWidth:'40%'},
      {name:'做空 Short (-)',type:'bar',stack:'negative',data:lsShortNeg,itemStyle:{color:R},barWidth:'40%'},
      {name:'日獲利佔比',type:'line',yAxisIndex:1,data:ls.wr,itemStyle:{color:Y},symbol:'circle',symbolSize:6,lineStyle:{width:2},z:10}
    ]
  }},isDark);

  // Quarterly symbol 100% stacked bar
  var qs=CHART_QUARTERLY_SYM;
  var qsSeries=qs.series.map(function(s,i){return{name:s.name,type:'bar',stack:'total',data:s.data,itemStyle:{color:C10[i%10]},barWidth:'55%'};});
  ecOpt({id:'chart-quarterly-sym',opt:{
    tooltip:{trigger:'axis',formatter:function(p){var t=0;p.forEach(function(s){t+=s.value;});return p.map(function(s){return s.marker+s.seriesName+': '+(t?(s.value/t*100).toFixed(0):0)+'% ('+s.value+')';}).join('<br/>');}},
    grid:{left:55,right:15,top:15,bottom:35},legend:{bottom:0,textStyle:{fontSize:9,color:tc}},
    xAxis:{type:'category',data:qs.labels,axisLabel:{fontSize:10,color:tc},axisLine:{lineStyle:{color:mc}}},
    yAxis:{type:'value',max:100,axisLabel:{formatter:'{value}%'},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
    series:qsSeries
  }},isDark);

  // Holding duration histogram with fixed buckets
  var dur=CHART_DURATION;
  var bucketOrder=['<1h','1~4h','4~24h','1~3天','3~7天','1~4週','>1月'];
  var durData=bucketOrder.map(function(k){return{name:k,value:dur.buckets?.[k]||0};});
  ecOpt({id:'chart-duration',opt:{
    tooltip:{trigger:'axis',formatter:function(p){return p[0].name+'<br/>'+p[0].value+' 筆';}},
    grid:{left:55,right:15,top:15,bottom:25},
    xAxis:{type:'category',data:durData.map(function(d){return d.name;}),axisLabel:{fontSize:9,color:tc},axisLine:{lineStyle:{color:mc}}},
    yAxis:{type:'value',name:'筆數',nameTextStyle:{fontSize:9,color:mc},axisLabel:{fontSize:9},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
    series:[{type:'bar',data:durData.map(function(d){return d.value;}),itemStyle:{color:function(p){var colors=isDark?['#3b82f6','#60a5fa','#93c5fd','#f59e0b','#f97316','#ef4444','#dc2626']:['#2563eb','#3b82f6','#60a5fa','#d97706','#ea580c','#dc2626','#b91c1c'];return colors[p.dataIndex%7];}},barWidth:'65%',label:{show:true,position:'top',fontSize:9,color:tc}}]
  }},isDark);
  document.getElementById('durationSub').textContent='平均 '+formatHours(dur.avg)+' · 中位數 '+formatHours(dur.median);

  // Equity curve with drawdown subchart
  var eq=CHART_EQUITY;
  var ddData=[],runningPeak=-Infinity;
  eq.equity.forEach(function(v,i){
    if(v>runningPeak)runningPeak=v;
    var dd=runningPeak>0?((runningPeak-v)/runningPeak*100):0;
    ddData.push(Math.round(dd*100)/100);
  });
  var maxDDpct=Math.max.apply(null,ddData)||0;
  var markPoints=[];var markAreas=[];
  if(eq.dates.length>0){
    markPoints=[
      {name:'高點',coord:[eq.dates[eq.dd_peak_idx],eq.equity[eq.dd_peak_idx]],itemStyle:{color:G},symbol:'pin',symbolSize:40,label:{show:true,formatter:'Peak',fontSize:9}},
      {name:'低點',coord:[eq.dates[eq.dd_trough_idx],eq.equity[eq.dd_trough_idx]],itemStyle:{color:R},symbol:'pin',symbolSize:40,label:{show:true,formatter:'Trough',fontSize:9}}
    ];
    if(eq.dd_peak_idx<eq.dd_trough_idx){
      markAreas=[{itemStyle:{color:isDark?'rgba(239,68,68,0.12)':'rgba(220,38,38,0.1)'},data:[[{name:'回撤',xAxis:eq.dates[eq.dd_peak_idx],yAxis:0},{xAxis:eq.dates[eq.dd_trough_idx],yAxis:'max'}]]}];
    }
  }
  ecOpt({id:'chart-equity',opt:{
    tooltip:{trigger:'axis',formatter:function(p){
      if(p.length>=2)return p[1].name+'<br/>權益: $'+p[1].value.toFixed(2)+'<br/>回撤: '+p[0].value.toFixed(2)+'%';
      return p[0].name+'<br/>權益: $'+p[0].value.toFixed(2);
    }},
    grid:[
      {left:60,right:15,top:15,height:'55%'},
      {left:60,right:15,top:'72%',height:'20%'}
    ],
    xAxis:[
      {type:'category',data:eq.dates,gridIndex:0,axisLabel:{fontSize:9,rotate:30,interval:Math.max(1,Math.floor(eq.dates.length/8))},axisLine:{lineStyle:{color:mc}}},
      {type:'category',data:eq.dates,gridIndex:1,axisLabel:{show:false},axisLine:{lineStyle:{color:mc}}}
    ],
    yAxis:[
      {type:'value',gridIndex:0,axisLabel:{formatter:'$ {value}'},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
      {type:'value',gridIndex:1,axisLabel:{formatter:'{value}%',fontSize:9},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}},inverse:true,max:Math.max(5,Math.ceil(maxDDpct/5)*5+5)}
    ],
    series:[
      {name:'回撤 %',type:'line',xAxisIndex:1,yAxisIndex:1,data:ddData,smooth:true,symbol:'none',
        lineStyle:{color:'#ef4444',width:1.5},
        areaStyle:{color:isDark?'rgba(239,68,68,0.3)':'rgba(239,68,68,0.15)'}},
      {name:'權益曲線',type:'line',xAxisIndex:0,yAxisIndex:0,data:eq.equity,smooth:true,symbol:'none',lineStyle:{color:eq.pl>=0?G:R,width:2},
        areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:eq.pl>=0?(isDark?'rgba(34,197,94,0.25)':'rgba(22,163,74,0.15)'):(isDark?'rgba(239,68,68,0.25)':'rgba(220,38,38,0.15)')},{offset:1,color:'rgba(0,0,0,0)'}]}},
        markPoint:{data:markPoints,symbolOffset:[0,-10]},markArea:{data:markAreas}}
    ]
  }},isDark);
  document.getElementById('equitySub').textContent='最大回撤 $'+eq.max_dd.toFixed(2)+' ('+maxDDpct.toFixed(2)+'%)';

  // Weekday x hour heatmap
  var hm=CHART_HEATMAP;
  var hmData=hm.data.map(function(d){return [d[0],d[1],d[2],d[3],d[4]];});
  var hours=['00','01','02','03','04','05','06','07','08','09','10','11','12','13','14','15','16','17','18','19','20','21','22','23'];
  ecOpt({id:'chart-heatmap',opt:{
    tooltip:{position:'top',formatter:function(p){var d=p.data;return hm.weekdays[d[0]]+' '+hours[d[1]]+':00<br/>筆數: '+d[2]+'<br/>盈虧: $'+d[3].toFixed(2)+'<br/>獲利佔比: '+d[4]+'%';}},
    grid:{left:60,right:15,top:5,bottom:20},
    xAxis:{type:'category',data:hours,splitArea:{show:true},axisLabel:{fontSize:9,color:tc}},
    yAxis:{type:'category',data:hm.weekdays,splitArea:{show:true},axisLabel:{fontSize:10,color:tc}},
    visualMap:{min:0,max:Math.max(1,hmData.length?Math.max.apply(null,hmData.map(function(d){return d[2];})):1),calculable:true,orient:'horizontal',left:'center',bottom:0,inRange:{color:[isDark?'#1a1f2c':'#f1f5f9',B,isDark?'#60a5fa':'#2563eb']},textStyle:{color:tc,fontSize:9}},
    series:[{name:'筆數',type:'heatmap',data:hmData,label:{show:true,fontSize:8,color:isDark?'#fff':'#1e293b'},emphasis:{itemStyle:{shadowBlur:10,shadowColor:'rgba(0,0,0,0.5)'}}}]
  }},isDark);

  // Session radar chart
  var sr=SESSION_RADAR;
  if(sr&&sr.length){
    var srMaxCnt=Math.max.apply(null,sr.map(function(d){return d.cnt;}))||1;
    var srMaxPL=Math.max.apply(null,sr.map(function(d){return Math.abs(d.pl);}))||1;
    ecOpt({id:'chart-session-radar',opt:{
      tooltip:{},
      legend:{bottom:0,textStyle:{fontSize:10,color:tc},data:['筆數','獲利佔比 %','盈虧 $']},
      radar:{
        center:['50%','52%'],radius:'60%',
        indicator:[
          {name:'筆數',max:srMaxCnt*1.2},
          {name:'獲利佔比 %',max:100},
          {name:'盈虧 $',max:srMaxPL*1.3}
        ],
        axisName:{fontSize:9,color:mc}
      },
      series:[{
        type:'radar',
        data:sr.map(function(d){
          return{name:d.name,value:[d.cnt,d.wr,Math.abs(d.pl)],itemStyle:{color:d.pl>=0?G:R}};
        }),
        symbol:'circle',symbolSize:5,
        lineStyle:{width:2},
        areaStyle:{opacity:0.15}
      }]
    }},isDark);
  }

  // Symbol matrix bubble chart
  var sb=SYM_BUBBLE;
  if(sb&&sb.length){
    ecOpt({id:'chart-sym-bubble',opt:{
      tooltip:{formatter:function(p){var d=p.data;return d[3]+'<br/>交易: '+d[0]+' 筆<br/>獲利佔比: '+d[1]+'%<br/>盈虧: $'+d[2].toFixed(2);}},
      grid:{left:65,right:30,top:15,bottom:25},
      xAxis:{type:'value',name:'交易次數',nameTextStyle:{fontSize:9,color:mc},axisLabel:{fontSize:9},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
      yAxis:{type:'value',name:'獲利佔比 %',nameTextStyle:{fontSize:9,color:mc},axisLabel:{formatter:'{value}%',fontSize:9},max:100,splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
      series:[{
        type:'scatter',symbolSize:function(d){return Math.max(12,Math.min(60,Math.sqrt(Math.abs(d[2]))*3));},
        data:sb.map(function(d){return [d.count,d.wr,d.pl,d.name];}),
        itemStyle:{color:function(p){var pl=p.data[2];return pl>=0?G:R;},opacity:0.8},
        label:{show:true,formatter:function(p){return p.data[3];},fontSize:9,color:tc,position:'top'},
        markLine:{silent:true,data:[{yAxis:50,label:{formatter:'50% 線',fontSize:9},lineStyle:{color:'#f59e0b',type:'dashed'}}]}
      }]
    }},isDark);
  }
}
window.addEventListener('resize',function(){
  ['chart-symbol-pie','chart-symbol-pl','chart-volume-donut','chart-swap-bar','chart-waterfall','chart-ls-monthly','chart-quarterly-sym','chart-duration','chart-equity','chart-heatmap','chart-session-radar','chart-sym-bubble','chart-leverage','chart-vol-pl-scatter','chart-holding-pl','chart-mae','chart-mfe','chart-mae-mfe-scatter','chart-close-reason','chart-holding-time','chart-swap-burden','chart-cashflow-waterfall'].forEach(function(id){
    var el=document.getElementById(id);if(el&&el._ec)el._ec.resize();
  });
});
initAllCharts();renderInsights();renderQuickInsights();initNewCharts();
// Single-symbol pie check → show session P&L breakdown instead
(function(){
  var total=SYM_PIE_DATA.reduce(function(a,b){return a+b.value;},0);
  var top=SYM_PIE_DATA[0];
  if(top&&top.value/total>0.9){
    document.getElementById('chart-symbol-pie').style.display='none';
    document.getElementById('symbolPieText').style.display='block';
    document.getElementById('symbolPieText').innerHTML='主打品種：<b style="color:var(--blue);font-size:18px">'+top.name+'</b><br>佔比：<b>'+Math.round(top.value/total*100)+'%</b>（'+top.value+' 筆）';
    // Show session P&L breakdown
    var sb=document.getElementById('sessionPnlBox');
    if(sb&&SESSION_PNL_DATA){
      sb.style.display='block';
      var cl=document.getElementById('sessionPnlList');
      var h='';
      SESSION_PNL_DATA.forEach(function(s){
        var c=s.pl>=0?'var(--green)':'var(--red)';
        var sign=s.pl>=0?'+':'';
        h+='<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)">'+
          '<div><span style="font-weight:600">'+s.name+'</span> <span style="font-size:11px;color:var(--muted)">('+s.count+' 筆)</span></div>'+
          '<div style="font-family:monospace;font-weight:700;font-size:15px;color:'+c+'">'+sign+'$'+s.pl.toFixed(2)+'</div>'+
          '</div>';
      });
      cl.innerHTML=h;
    }
  }
})();
// Duration insight: if >90% in <1h, show text instead of chart
(function(){
  var dur=CHART_DURATION;
  var b=dur.buckets||{};
  var tot=Object.values(b).reduce(function(a,v){return a+v;},0)||1;
  var pct=b['<1h']?Math.round(b['<1h']/tot*100):0;
  if(pct>=90){
    document.getElementById('chart-duration').style.display='none';
    document.getElementById('durationSub').textContent='交易風格：超短線（'+pct+'% 訂單持倉小於1小時）';
  }
})();

function formatHours(h){if(h<1)return Math.round(h*60)+'分鐘';return Math.round(h*10)/10+'小時';}

function renderQuickInsights(){
  var el=document.getElementById('qiText');if(!el)return;
  var total=data.length;
  var pl=data.reduce(function(a,t){return a+t.profit;},0);
  var wins=data.filter(function(t){return t.profit>0;}).length;
  var wr=total?(wins/total*100).toFixed(1):0;
  var under1h=data.filter(function(t){return t.duration_h!==null&&t.duration_h<1;}).length;
  var durPct=total?Math.round(under1h/total*100):0;
  var durText=durPct>=80?'，超短線交易（'+durPct+'% 持倉<1h）':'';
  var buys=data.filter(function(t){return t.type==='BUY';}).length;
  var dirText='做多 '+Math.round(buys/total*100)+'% / 做空 '+Math.round((total-buys)/total*100)+'%';
  el.innerHTML='<b>'+total+'</b> 筆交易 · 淨盈虧 <b style="color:'+(pl>=0?'var(--green)':'var(--red)')+'">$'+(pl>=0?'+':'')+pl.toFixed(2)+'</b> · 獲利佔比 <b>'+wr+'%</b> · '+dirText+durText;
}

function renderInsights(){
  var list=document.getElementById('insightList');if(!list)return;
  var insights=[];
  // Best symbol
  var symProfits={};data.forEach(function(t){symProfits[t.symbol]=(symProfits[t.symbol]||0)+t.profit;});
  var bestSym=Object.keys(symProfits).sort(function(a,b){return symProfits[b]-symProfits[a];})[0];
  if(bestSym)insights.push('賣貨品種 <b>'+bestSym+'</b> 資獲 $'+symProfits[bestSym].toFixed(2));
  // Best session
  var sesMap={0:'亞洲盤',8:'倫敦盤',16:'紐約盤'};
  var sesPL={};data.forEach(function(t){if(!t.open)return;var h=parseInt(t.open.substring(11,13));var k=h<8?0:h<16?8:16;sesPL[k]=(sesPL[k]||0)+t.profit;});
  var bestSes=Object.keys(sesPL).sort(function(a,b){return sesPL[b]-sesPL[a];})[0];
  if(bestSes!==undefined)insights.push(sesMap[bestSes]+' 表現最佳，累計 $'+sesPL[bestSes].toFixed(2));
  // Volume vs profit
  var totalVol=data.reduce(function(a,t){return a+(t.volume||0);},0);
  var avgLot=totalVol?data.reduce(function(a,t){return a+t.profit;},0)/totalVol:0;
  insights.push('每手平均盈虧 $'+avgLot.toFixed(2));
  list.innerHTML=insights.map(function(s){return '<li>'+s+'</li>';}).join('');
}

// Date filter
function applyDateFilter(){
  var df=document.getElementById('dateFrom').value;
  var dt=document.getElementById('dateTo').value;
  if(!df&&!dt){resetDateFilter();return;}
  data=ALL_TRADES.filter(function(t){if(df&&t.open_date<df)return false;if(dt&&t.open_date>dt)return false;return true;});
  updateKPIs();currentPage=1;renderTable();updateChartsFromFilter();
  document.getElementById('filterInfo').textContent=' ('+data.length+' 筆)';
}
function resetDateFilter(){
  document.getElementById('dateFrom').value='{DATE_MIN}';
  document.getElementById('dateTo').value='{DATE_MAX}';
  data=ALL_TRADES.slice();updateKPIs();currentPage=1;renderTable();updateChartsFromFilter();
  document.getElementById('filterInfo').textContent='';
}
function updateKPIs(){
  var total=data.length;
  var pl=0,wins=0,losses=0,totalW=0,totalL=0,best=-Infinity,worst=Infinity;
  data.forEach(function(t){pl+=t.profit;if(t.profit>0){wins++;totalW+=t.profit;}else{losses++;totalL+=t.profit;}if(t.profit>best)best=t.profit;if(t.profit<worst)worst=t.profit;});
  var avgW=wins?(totalW/wins):0,avgL=losses?Math.abs(totalL/losses):0,plr=avgL?avgW/avgL:0;
  var pf=totalL?Math.abs(totalW/totalL):0;
  var sorted=data.slice().sort(function(a,b){return a.open<b.open?-1:1;});
  var peak=0,maxdd=0,cumDD=0;
  sorted.forEach(function(t){cumDD+=t.profit;if(cumDD>peak)peak=cumDD;var dd=peak-cumDD;if(dd>maxdd)maxdd=dd;});
  var daily={};data.forEach(function(t){var d=t.open?t.open.substring(0,10):'';if(d)daily[d]=(daily[d]||0)+t.profit;});
  var dv=Object.values(daily),sharpe=0;if(dv.length>1){var mean=dv.reduce(function(a,b){return a+b;},0)/dv.length;var variance=dv.reduce(function(a,b){return a+Math.pow(b-mean,2);},0)/dv.length;var std=Math.sqrt(variance);if(std>0)sharpe=mean/std*Math.sqrt(252);}
  document.getElementById('headerCount').textContent=total;
  document.getElementById('headerPL').textContent='$'+(pl>=0?'+':'')+pl.toFixed(2);
  document.getElementById('headerWR').textContent=(total?(wins/total*100).toFixed(0):0)+'%';
  var vals=[total,'$'+(pl>=0?'+':'')+pl.toFixed(2),(total?(wins/total*100).toFixed(0):0)+'%',
    '+$'+avgW.toFixed(2),'-$'+avgL.toFixed(2),plr.toFixed(2),pf.toFixed(2),
    '$'+maxdd.toFixed(2),(sharpe||0).toFixed(2),'$'+(best!==-Infinity?'+':'')+best.toFixed(2),'$-'+Math.abs(worst).toFixed(2)];
  var kpiVals=document.querySelectorAll('.kpi .val');
  for(var i=0;i<Math.min(vals.length,kpiVals.length);i++){kpiVals[i].textContent=vals[i];}
  updateSummaryLine(total,wins,pl);renderInsights();
}
function updateChartsFromFilter(){
  var monthly={},ls_monthly={},quarterly_sym={},wd_hour={},session={"00-07":{cnt:0,pl:0,wins:0},"08-15":{cnt:0,pl:0,wins:0},"16-23":{cnt:0,pl:0,wins:0}};
  var durations=[];
  var eq=[],eqDates=[],cum=0;
  var sorted=data.slice().sort(function(a,b){return a.open<b.open?-1:1;});
  sorted.forEach(function(t){
    cum+=t.profit;eq.push(Math.round(cum*100)/100);eqDates.push(t.open_date);
    var m=t.open?t.open.substring(0,7):'';
    if(m){monthly[m]=(monthly[m]||0)+t.profit;}
    if(m){if(!ls_monthly[m])ls_monthly[m]={long:0,short:0};if(t.type==='BUY')ls_monthly[m].long+=t.profit;else ls_monthly[m].short+=t.profit;}
    if(t.open){var yr=t.open.substring(0,4);var mo=parseInt(t.open.substring(5,7));var q=yr+'-Q'+Math.ceil(mo/3);if(!quarterly_sym[q])quarterly_sym[q]={};var s=t.symbol;quarterly_sym[q][s]=(quarterly_sym[q][s]||0)+1;}
    if(t.open){var dt=new Date(t.open.replace(' ','T'));var wd=(dt.getDay()+6)%7;var h=dt.getHours();var key=wd+'-'+h;if(!wd_hour[key])wd_hour[key]={cnt:0,pl:0,wins:0};wd_hour[key].cnt++;wd_hour[key].pl+=t.profit;if(t.profit>0)wd_hour[key].wins++;}
    if(t.duration_h!==null&&t.duration_h!==undefined)durations.push(t.duration_h);
  });
  // Update globals
  var mLabels=Object.keys(monthly).sort();CHART_WATERFALL={labels:mLabels,data:mLabels.map(function(k){return Math.round(monthly[k]*100)/100;})};
  var lsLabels=Object.keys(ls_monthly).sort();
  var lsWr=lsLabels.map(function(m){var dw=0,dt=0;Object.keys(monthly).forEach(function(k){if(k===m){dw+=(monthly[k]>0?1:0);dt++;}});return dt?Math.round(dw/dt*1000)/10:0;});
  CHART_LS_MONTHLY={labels:lsLabels,long:lsLabels.map(function(k){return ls_monthly[k].long;}),short:lsLabels.map(function(k){return ls_monthly[k].short;}),wr:lsWr};
  var qsLabels=Object.keys(quarterly_sym).sort();var allSyms={};qsLabels.forEach(function(q){Object.keys(quarterly_sym[q]).forEach(function(s){allSyms[s]=(allSyms[s]||0)+quarterly_sym[q][s];});});var topSyms=Object.keys(allSyms).sort(function(a,b){return allSyms[b]-allSyms[a];}).slice(0,6);CHART_QUARTERLY_SYM={labels:qsLabels,series:topSyms.map(function(s){return{name:s,data:qsLabels.map(function(q){return quarterly_sym[q][s]||0;})};})};
  CHART_EQUITY={dates:eqDates,equity:eq,pl:cum,dd_peak_idx:0,dd_trough_idx:0,max_dd:0};
  // Simple histogram for filtered data
  var maxH=durations.length?Math.max.apply(null,durations)*1.05:6,bucketSize=Math.max(0.5,maxH/12);
  var histLabels=[],histData=[];var cur=0;while(cur<maxH){var nxt=cur+bucketSize;var cnt=durations.filter(function(d){return d>=cur&&d<nxt;}).length;histData.push(cnt);histLabels.push(nxt<1?Math.round(nxt*60)+'m':Math.round(nxt*10)/10+'h');cur=nxt;}
  CHART_DURATION={labels:histLabels,data:histData,avg:0,median:0};
  if(durations.length){var sum=durations.reduce(function(a,b){return a+b;},0);CHART_DURATION.avg=sum/durations.length;var sd=durations.slice().sort(function(a,b){return a-b;});CHART_DURATION.median=sd[Math.floor(sd.length/2)];}
  var wdNames=['週一','週二','週三','週四','週五','週六','週日'];
  var hmData=[];Object.keys(wd_hour).forEach(function(k){var p=k.split('-');hmData.push([parseInt(p[0]),parseInt(p[1]),wd_hour[k].cnt,Math.round(wd_hour[k].pl*100)/100,Math.round(wd_hour[k].wins/wd_hour[k].cnt*1000)/10]);});
  CHART_HEATMAP={data:hmData,weekdays:wdNames};
  // Update symbol data
  var symCount={},symVol={},symSwap={},symPl={};data.forEach(function(t){symCount[t.symbol]=(symCount[t.symbol]||0)+1;symVol[t.symbol]=(symVol[t.symbol]||0)+(t.volume||0);symSwap[t.symbol]=(symSwap[t.symbol]||0)+(t.swap||0);symPl[t.symbol]=(symPl[t.symbol]||0)+t.profit;});
  SYM_PIE_DATA=Object.keys(symCount).map(function(s){return{name:s,value:symCount[s]};});
  SYM_PL_DATA=Object.keys(symPl).map(function(s){return{name:s,value:Math.round(symPl[s]*100)/100};}).sort(function(a,b){return a.value-b.value;});
  VOL_DATA=Object.keys(symVol).map(function(s){return{name:s,value:Math.round(symVol[s]*100)/100};}).sort(function(a,b){return b.value-a.value;});
  SWAP_DATA=Object.keys(symSwap).map(function(s){return{name:s,value:Math.round(symSwap[s]*100)/100};}).sort(function(a,b){return a.value-b.value;});
  // Update session radar
  var sesKey=['00-07','08-15','16-23'];var sesNames=['亞洲盤','倫敦盤','紐約盤'];
  SESSION_RADAR=sesKey.map(function(k,i){var v=session[k]||{cnt:0,pl:0,wins:0};return{name:sesNames[i],cnt:v.cnt,pl:Math.round(v.pl*100)/100,wr:v.cnt?Math.round(v.wins/v.cnt*1000)/10:0};});
  // Update symbol bubble
  SYM_BUBBLE=[];Object.keys(symPl).forEach(function(s){SYM_BUBBLE.push({name:s,count:symCount[s]||0,pl:Math.round(symPl[s]*100)/100,wr:symCount[s]?Math.round((symPl[s]>0?1:0)/symCount[s]*1000)/10:0});});
  // ── Recalculate CS Audit data from filtered trades ──
  var csCloseReason={};var csHoldTime={};var csSwapBurden={};
  data.forEach(function(t){
    // Close reason
    var comment=(t.comment||'').toLowerCase();
    var dur_s=t.duration_s||0;
    if(comment.indexOf('so')>=0||comment.indexOf('stop out')>=0||comment.indexOf('爆仓')>=0)csCloseReason['Stop Out (爆仓)']=(csCloseReason['Stop Out (爆仓)']||0)+1;
    else if(comment.indexOf('sl')>=0)csCloseReason['SL (止损)']=(csCloseReason['SL (止损)']||0)+1;
    else if(comment.indexOf('tp')>=0)csCloseReason['TP (止盈)']=(csCloseReason['TP (止盈)']||0)+1;
    else csCloseReason['Manual (手动/其他)']=(csCloseReason['Manual (手动/其他)']||0)+1;
    // Holding time buckets
    if(dur_s<10)csHoldTime['< 10s']=(csHoldTime['< 10s']||0)+1;
    else if(dur_s<60)csHoldTime['10s-1m']=(csHoldTime['10s-1m']||0)+1;
    else if(dur_s<300)csHoldTime['1m-5m']=(csHoldTime['1m-5m']||0)+1;
    else if(dur_s<3600)csHoldTime['5m-1h']=(csHoldTime['5m-1h']||0)+1;
    else if(dur_s<86400)csHoldTime['1h-24h']=(csHoldTime['1h-24h']||0)+1;
    else csHoldTime['> 24h']=(csHoldTime['> 24h']||0)+1;
    // Swap burden by symbol
    var sym=t.symbol||'unknown';
    if(!csSwapBurden[sym])csSwapBurden[sym]={name:sym,profit:0,swap:0,commission:0};
    csSwapBurden[sym].profit+=t.profit||0;csSwapBurden[sym].swap+=t.swap||0;csSwapBurden[sym].commission+=t.commission||0;
  });
  CS_CLOSE_REASON=csCloseReason;CS_HOLDING_TIME=csHoldTime;
  CS_SWAP_BURDEN=Object.keys(csSwapBurden).map(function(s){return csSwapBurden[s];});
  initAllCharts();initCSCharts();
}
function updateSummaryLine(total,wins,pl){
  var sl=document.getElementById('summaryLine');if(!sl)return;
  var wr=total?(wins/total*100).toFixed(1):'0.0';
  var cs=pl>=0?'pos':'neg';
  sl.innerHTML='📋 篩選結果：<b>'+total+'</b> 筆交易，<b class="'+cs+'">'+wins+'</b> 筆獲利（獲利佔比 <b>'+wr+'%</b>），淨盈虧 <b class="'+cs+'">$'+(pl>=0?'+':'')+pl.toFixed(2)+'</b>';
}
function quickFilter(period){
  var now=new Date();var df='',dt=now.toISOString().substring(0,10);
  var d=new Date(now);
  if(period==='today'){df=dt;}
  else if(period==='week'){d.setDate(d.getDate()-d.getDay());df=d.toISOString().substring(0,10);}
  else if(period==='month'){df=now.getFullYear()+'-'+String(now.getMonth()+1).padStart(2,'0')+'-01';}
  else if(period==='3m'){d.setMonth(d.getMonth()-3);df=d.toISOString().substring(0,10);}
  else{df='{DATE_MIN}';dt='{DATE_MAX}';}
  document.getElementById('dateFrom').value=df;document.getElementById('dateTo').value=dt;
  document.querySelectorAll('.quick-btn').forEach(function(b){b.classList.remove('active');});
  if(event&&event.target)event.target.classList.add('active');
  applyDateFilter();
}
function filterBySymbol(sym){
  document.getElementById('searchBox').value=sym;doSearch();
}
var sortCol='profit',sortDir=-1;var currentPage=1,pageSize=15,totalPages=1;var searchIdx=-1,searchMatches=[];var colsVisible=true;
function toggleCols(){colsVisible=!colsVisible;var els=document.querySelectorAll('.col-extra');els.forEach(function(el){el.classList.toggle('col-hidden',!colsVisible);});document.querySelector('.col-toggle').textContent=colsVisible?'⚙️ 欄位':'⚙️ 欄位';}
function sortBy(col){if(sortCol===col)sortDir*=-1;else{sortCol=col;sortDir=-1;}data.sort(function(a,b){var va=a[col],vb=b[col];if(typeof va==='number'&&typeof vb==='number')return(va-vb)*sortDir;return String(va||'').localeCompare(String(vb||''))*sortDir;});currentPage=1;renderTable();document.querySelectorAll('.sort-arrow').forEach(function(el){el.textContent='';});var arrow=document.getElementById('sa-'+col);if(arrow)arrow.textContent=sortDir>0?'▲':'▼';}
function doSearch(){var q=document.getElementById('searchBox').value.trim().toLowerCase();searchMatches=[];searchIdx=-1;if(!q){data=applyCurrentFilter();document.getElementById('searchInfo').textContent='';}else{data=applyCurrentFilter().filter(function(t){return String(t.ticket).toLowerCase().indexOf(q)>=0||String(t.symbol).toLowerCase().indexOf(q)>=0||String(t.open_date).indexOf(q)>=0;});document.getElementById('searchInfo').textContent=data.length+' 條匹配';ALL_TRADES.forEach(function(t,i){if(String(t.ticket).toLowerCase().indexOf(q)>=0||String(t.symbol).toLowerCase().indexOf(q)>=0||String(t.open_date).indexOf(q)>=0)searchMatches.push(i);});}currentPage=1;renderTable();}
function applyCurrentFilter(){var df=document.getElementById('dateFrom').value;var dt=document.getElementById('dateTo').value;if(!df&&!dt)return ALL_TRADES.slice();return ALL_TRADES.filter(function(t){if(df&&t.open_date<df)return false;if(dt&&t.open_date>dt)return false;return true;});}
document.getElementById('searchBox').addEventListener('keydown',function(e){if(e.key==='Enter'&&searchMatches.length>0){e.preventDefault();searchIdx=(searchIdx+1)%searchMatches.length;var gi=searchMatches[searchIdx];currentPage=Math.floor(gi/pageSize)+1;renderTable();setTimeout(function(){var rows=document.querySelectorAll('#tradeBody tr');rows.forEach(function(r){r.classList.remove('highlight');});var li=gi%pageSize;if(rows[li]){rows[li].classList.add('highlight');rows[li].scrollIntoView({behavior:'smooth',block:'center'});}document.getElementById('searchInfo').textContent=(searchIdx+1)+'/'+searchMatches.length+' 條匹配';},30);}});
function renderTable(){totalPages=Math.ceil(data.length/pageSize)||1;if(currentPage>totalPages)currentPage=totalPages;var start=(currentPage-1)*pageSize;var page=data.slice(start,start+pageSize);var h='';page.forEach(function(t){var dirCls=t.type==='BUY'?'buy':'sell';var plCls=t.profit>0?'win':'loss';var volFixed=t.volume!==undefined?Number(t.volume).toFixed(2):'0.00';h+='<tr><td>'+t.ticket+'</td><td>'+t.open+'</td><td><span class=\"dir-badge '+dirCls+'\">'+t.type+'</span></td><td class=\"vol-num\">'+volFixed+'</td><td>'+t.symbol+'</td><td>'+(t.open_price||'-')+'</td><td class=\"col-extra\">'+t.close+'</td><td class=\"col-extra\">'+(t.close_price||'-')+'</td><td>'+(t.duration_str||'-')+'</td><td><span class=\"pl-badge '+plCls+'\">$'+t.profit_per_lot.toFixed(2)+'</span></td><td>$'+(t.swap||0).toFixed(2)+'</td><td><span class=\"pl-badge '+plCls+'\">$'+t.profit.toFixed(2)+'</span></td></tr>';});document.getElementById('tradeBody').innerHTML=h;var info=currentPage+'/'+totalPages+' ('+data.length+'筆)';document.getElementById('pageInfo').textContent=info;document.getElementById('pageInfo2').textContent=info;}
renderTable();document.getElementById('sa-profit').textContent='▼';updateSummaryLine(ALL_TRADES.length,ALL_TRADES.filter(function(t){return t.profit>0;}).length,ALL_TRADES.reduce(function(a,t){return a+t.profit;},0));

// ═══ v9.0 New Charts: Leverage, Holding PL, MAE/MFE ═══
function initNewCharts(){
  var isDark=document.documentElement.getAttribute('data-theme')==='dark';
  var tc=isDark?'#e8ecf4':'#1e293b';
  var mc=isDark?'#7b879c':'#64748b';
  var G=isDark?'#22c55e':'#16a34a';
  var R=isDark?'#ef4444':'#dc2626';
  var B=isDark?'#3b82f6':'#2563eb';
  var Y=isDark?'#eab308':'#ca8a04';
  var O='#f59e0b';
  var P='#8b5cf6';


  // 2) Leverage bucket bar chart
  (function(){
    var el=document.getElementById('chart-leverage');
    if(!el||!LEVERAGE_DATA||!LEVERAGE_DATA.length)return;
    try{if(el._ec){el._ec.dispose();}el._ec=null;}catch(e){}
    var chart=echarts.init(el,isDark?'dark':null);
    chart.setOption({
      tooltip:{trigger:'axis',formatter:function(p){
        var idx=p[0].dataIndex;var d=LEVERAGE_DATA[idx];
        return d.bucket+' 手<br/>交易: '+d.count+' 筆<br/>平均手數: '+d.avg_volume+'<br/>平均盈虧: $'+d.avg_pl.toFixed(2)+'<br/>勝率: '+d.win_rate+'%';
      }},
      legend:{bottom:0,textStyle:{fontSize:10,color:tc}},
      grid:{left:60,right:60,top:15,bottom:40},
      xAxis:{type:'category',data:LEVERAGE_DATA.map(function(d){return d.bucket;}),axisLabel:{fontSize:9,color:tc},axisLine:{lineStyle:{color:mc}}},
      yAxis:[
        {type:'value',name:'平均盈虧 ($)',nameTextStyle:{fontSize:9,color:mc},axisLabel:{fontSize:9,formatter:'${value}'},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
        {type:'value',name:'勝率 (%)',nameTextStyle:{fontSize:9,color:mc},axisLabel:{formatter:'{value}%'},max:100}
      ],
      series:[
        {name:'平均盈虧',type:'bar',data:LEVERAGE_DATA.map(function(d){return{value:d.avg_pl,itemStyle:{color:d.avg_pl>=0?G:R}};}),barWidth:'50%',label:{show:true,position:'top',formatter:function(p){return '$'+p.value.toFixed(0);},fontSize:9,color:tc}},
        {name:'勝率',type:'line',yAxisIndex:1,data:LEVERAGE_DATA.map(function(d){return d.win_rate;}),itemStyle:{color:Y},symbol:'circle',symbolSize:6,lineStyle:{width:2}}
      ]
    });
    el._ec=chart;
  })();

  // 3) Volume vs P&L scatter
  (function(){
    var el=document.getElementById('chart-vol-pl-scatter');
    if(!el||!VOL_PL_SCATTER||!VOL_PL_SCATTER.length)return;
    try{if(el._ec){el._ec.dispose();}el._ec=null;}catch(e){}
    var chart=echarts.init(el,isDark?'dark':null);
    chart.setOption({
      tooltip:{formatter:function(p){return p.data[3]+'<br/>手數: '+p.data[0]+'<br/>盈虧: $'+p.data[1].toFixed(2);}},
      grid:{left:65,right:20,top:15,bottom:25},
      xAxis:{type:'value',name:'手數',nameTextStyle:{fontSize:9,color:mc},axisLabel:{fontSize:9},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
      yAxis:{type:'value',name:'盈虧 ($)',nameTextStyle:{fontSize:9,color:mc},axisLabel:{fontSize:9,formatter:'${value}'},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
      series:[{
        type:'scatter',
        symbolSize:function(d){return Math.max(6,Math.min(30,Math.sqrt(Math.abs(d[1]))*2));},
        data:VOL_PL_SCATTER.map(function(d){return[d.volume,d.profit,0,d.symbol];}),
        itemStyle:{color:function(p){return p.data[1]>=0?G:R;},opacity:0.7},
        label:{show:false}
      }],
      markLine:{silent:true,data:[{yAxis:0,label:{formatter:'盈虧平衡線',fontSize:9},lineStyle:{color:'#f59e0b',type:'dashed'}}]}
    });
    el._ec=chart;
  })();

  // 4) Holding Time P&L Distribution
  (function(){
    var el=document.getElementById('chart-holding-pl');
    if(!el||!HOLDING_PL_DIST||!HOLDING_PL_DIST.length)return;
    try{if(el._ec){el._ec.dispose();}el._ec=null;}catch(e){}
    var chart=echarts.init(el,isDark?'dark':null);
    chart.setOption({
      tooltip:{trigger:'axis',formatter:function(p){
        var idx=p[0].dataIndex;var d=HOLDING_PL_DIST[idx];
        return d.bucket+'<br/>交易: '+d.count+' 筆<br/>累計盈虧: $'+d.total_pl.toFixed(2);
      }},
      grid:{left:60,right:15,top:15,bottom:25},
      xAxis:{type:'category',data:HOLDING_PL_DIST.map(function(d){return d.bucket;}),axisLabel:{fontSize:9,color:tc},axisLine:{lineStyle:{color:mc}}},
      yAxis:{type:'value',name:'累計盈虧 ($)',nameTextStyle:{fontSize:9,color:mc},axisLabel:{fontSize:9,formatter:'${value}'},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
      series:[{type:'bar',data:HOLDING_PL_DIST.map(function(d){return{value:d.total_pl,itemStyle:{color:d.total_pl>=0?G:R}};}),barWidth:'55%',label:{show:true,position:'top',formatter:function(p){return '$'+p.value.toFixed(0);},fontSize:9,color:tc}}]
    });
    el._ec=chart;
  })();
}

// ═══ v9.0 MAE/MFE Charts ═══
function initMAECharts(){
  var isDark=document.documentElement.getAttribute('data-theme')==='dark';
  var tc=isDark?'#e8ecf4':'#1e293b';
  var mc=isDark?'#7b879c':'#64748b';
  var G=isDark?'#22c55e':'#16a34a';
  var R=isDark?'#ef4444':'#dc2626';
  var B=isDark?'#3b82f6':'#2563eb';

  if(!MAE_MFE_DATA||!MAE_MFE_DATA.length)return;

  // 1) MAE scatter
  (function(){
    var el=document.getElementById('chart-mae');
    if(!el)return;
    try{if(el._ec){el._ec.dispose();}el._ec=null;}catch(e){}
    var data=MAE_MFE_DATA.map(function(d,i){return[i+1,d.mae,d.profit,d.symbol];});
    var chart=echarts.init(el,isDark?'dark':null);
    chart.setOption({
      tooltip:{formatter:function(p){return '#'+p.data[0]+' '+p.data[3]+'<br/>MAE: $'+p.data[1].toFixed(2)+'<br/>最終盈虧: $'+p.data[2].toFixed(2);}},
      grid:{left:65,right:20,top:15,bottom:30},
      xAxis:{type:'value',name:'交易序號',nameTextStyle:{fontSize:9,color:mc},axisLabel:{fontSize:9},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
      yAxis:{type:'value',name:'MAE ($)',nameTextStyle:{fontSize:9,color:mc},axisLabel:{fontSize:9,formatter:'${value}'},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
      series:[{type:'scatter',symbolSize:function(d){return Math.max(5,Math.min(20,Math.sqrt(d[1])*2));},data:data,itemStyle:{color:function(p){return p.data[2]>=0?G:R;},opacity:0.7}}]
    });
    el._ec=chart;
  })();

  // 2) MFE scatter
  (function(){
    var el=document.getElementById('chart-mfe');
    if(!el)return;
    try{if(el._ec){el._ec.dispose();}el._ec=null;}catch(e){}
    var data=MAE_MFE_DATA.map(function(d,i){return[i+1,d.mfe,d.profit,d.symbol];});
    var chart=echarts.init(el,isDark?'dark':null);
    chart.setOption({
      tooltip:{formatter:function(p){return '#'+p.data[0]+' '+p.data[3]+'<br/>MFE: $'+p.data[1].toFixed(2)+'<br/>最終盈虧: $'+p.data[2].toFixed(2);}},
      grid:{left:65,right:20,top:15,bottom:30},
      xAxis:{type:'value',name:'交易序號',nameTextStyle:{fontSize:9,color:mc},axisLabel:{fontSize:9},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
      yAxis:{type:'value',name:'MFE ($)',nameTextStyle:{fontSize:9,color:mc},axisLabel:{fontSize:9,formatter:'${value}'},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
      series:[{type:'scatter',symbolSize:function(d){return Math.max(5,Math.min(20,Math.sqrt(d[1])*2));},data:data,itemStyle:{color:function(p){return p.data[2]>=0?G:R;},opacity:0.7}}]
    });
    el._ec=chart;
  })();

  // 3) MAE vs MFE bubble
  (function(){
    var el=document.getElementById('chart-mae-mfe-scatter');
    if(!el)return;
    try{if(el._ec){el._ec.dispose();}el._ec=null;}catch(e){}
    var data=MAE_MFE_DATA.map(function(d){return[d.mae,d.mfe,d.profit,d.symbol];});
    var chart=echarts.init(el,isDark?'dark':null);
    chart.setOption({
      tooltip:{formatter:function(p){return p.data[3]+'<br/>MAE: $'+p.data[0].toFixed(2)+'<br/>MFE: $'+p.data[1].toFixed(2)+'<br/>盈虧: $'+p.data[2].toFixed(2);}},
      grid:{left:65,right:20,top:15,bottom:30},
      xAxis:{type:'value',name:'MAE ($)',nameTextStyle:{fontSize:9,color:mc},axisLabel:{fontSize:9,formatter:'${value}'},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
      yAxis:{type:'value',name:'MFE ($)',nameTextStyle:{fontSize:9,color:mc},axisLabel:{fontSize:9,formatter:'${value}'},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
      series:[{
        type:'scatter',
        symbolSize:function(d){return Math.max(6,Math.min(30,Math.sqrt(Math.abs(d[2]))*2));},
        data:data,
        itemStyle:{color:function(p){return p.data[2]>=0?G:R;},opacity:0.7},
        label:{show:false}
      }],
      markLine:{silent:true,data:[
        {xAxis:0,lineStyle:{color:mc,type:'dashed',width:1}},
        {yAxis:0,lineStyle:{color:mc,type:'dashed',width:1}}
      ]}
    });
    el._ec=chart;
  })();

  // 4) MAE/MFE Summary stats
  (function(){
    var el=document.getElementById('mae-mfe-summary');
    if(!el)return;
    var maeVals=MAE_MFE_DATA.map(function(d){return d.mae;});
    var mfeVals=MAE_MFE_DATA.map(function(d){return d.mfe;});
    var avgMAE=maeVals.reduce(function(a,b){return a+b;},0)/maeVals.length;
    var avgMFE=mfeVals.reduce(function(a,b){return a+b;},0)/mfeVals.length;
    var maxMAE=Math.max.apply(null,maeVals);
    var maxMFE=Math.max.apply(null,mfeVals);
    var wins=MAE_MFE_DATA.filter(function(d){return d.profit>0;});
    var losses=MAE_MFE_DATA.filter(function(d){return d.profit<=0;});
    var avgWinMAE=wins.length?wins.reduce(function(a,d){return a+d.mae;},0)/wins.length:0;
    var avgLossMAE=losses.length?losses.reduce(function(a,d){return a+d.mae;},0)/losses.length:0;
    var avgWinMFE=wins.length?wins.reduce(function(a,d){return a+d.mfe;},0)/wins.length:0;
    var avgLossMFE=losses.length?losses.reduce(function(a,d){return a+d.mfe;},0)/losses.length:0;
    el.innerHTML=
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">'+
      '<div><b>📊 全部交易 ('+MAE_MFE_DATA.length+' 筆)</b><br>'+
      '平均 MAE: <b style="color:var(--red)">$'+avgMAE.toFixed(2)+'</b><br>'+
      '平均 MFE: <b style="color:var(--green)">$'+avgMFE.toFixed(2)+'</b><br>'+
      '最大 MAE: <b style="color:var(--red)">$'+maxMAE.toFixed(2)+'</b><br>'+
      '最大 MFE: <b style="color:var(--green)">$'+maxMFE.toFixed(2)+'</b></div>'+
      '<div><b>📈 盈虧分組對比</b><br>'+
      '赢单平均 MAE: <b style="color:var(--red)">$'+avgWinMAE.toFixed(2)+'</b><br>'+
      '亏单平均 MAE: <b style="color:var(--red)">$'+avgLossMAE.toFixed(2)+'</b><br>'+
      '赢单平均 MFE: <b style="color:var(--green)">$'+avgWinMFE.toFixed(2)+'</b><br>'+
      '亏单平均 MFE: <b style="color:var(--green)">$'+avgLossMFE.toFixed(2)+'</b></div>'+
      '</div>'+
      '<div style="margin-top:12px;padding:8px 12px;background:var(--surface);border-radius:6px;font-size:11px;color:var(--muted)">'+
      '💡 <b>解讀提示：</b>如果亏单的平均 MAE 遠大於平均虧損金額，說明停損點設得太寬；'+
      '如果赢单的平均 MFE 遠大於平均盈利金額，說明未能及時獲利出場。'+
      '</div>';
  })();

  // 5) Holding PL Distribution (also in habits tab)
  (function(){
    var el=document.getElementById('chart-holding-pl');
    if(!el||!HOLDING_PL_DIST||!HOLDING_PL_DIST.length)return;
    try{if(el._ec){el._ec.dispose();}el._ec=null;}catch(e){}
    var chart=echarts.init(el,isDark?'dark':null);
    chart.setOption({
      tooltip:{trigger:'axis',formatter:function(p){
        var idx=p[0].dataIndex;var d=HOLDING_PL_DIST[idx];
        return d.bucket+'<br/>交易: '+d.count+' 筆<br/>累計盈虧: $'+d.total_pl.toFixed(2);
      }},
      grid:{left:60,right:15,top:15,bottom:25},
      xAxis:{type:'category',data:HOLDING_PL_DIST.map(function(d){return d.bucket;}),axisLabel:{fontSize:9,color:tc},axisLine:{lineStyle:{color:mc}}},
      yAxis:{type:'value',name:'累計盈虧 ($)',nameTextStyle:{fontSize:9,color:mc},axisLabel:{fontSize:9,formatter:'${value}'},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
      series:[{type:'bar',data:HOLDING_PL_DIST.map(function(d){return{value:d.total_pl,itemStyle:{color:d.total_pl>=0?G:R}};}),barWidth:'55%',label:{show:true,position:'top',formatter:function(p){return '$'+p.value.toFixed(0);},fontSize:9,color:tc}}]
    });
    el._ec=chart;
  })();
}

// ═══ Habits Charts (symbol PL bar + holding PL) ═══
function initHabitsCharts(){
  initNewCharts(); // reuse holding PL chart
}

// ── v8.0 CS Audit Charts ──
function initCSCharts(){
  var isDark=document.documentElement.getAttribute('data-theme')==='dark';
  var tc=isDark?'#e8ecf4':'#1e293b';
  var mc=isDark?'#7b879c':'#64748b';
  var G=isDark?'#22c55e':'#16a34a';
  var R=isDark?'#ef4444':'#dc2626';
  var B=isDark?'#3b82f6':'#2563eb';
  var O='#f59e0b';
  var P='#8b5cf6';

  // 1) Equity timeline with CS event markers
  (function(){
    var el=document.getElementById('chart-equity');
    if(!el)return;
    try{if(el._ec){try{el._ec.dispose();}catch(e){}}el._ec=null;el.removeAttribute('_echarts_instance_');}catch(e){}
    // Build timeline data: merge trade equity + CS events
    var eq=CHART_EQUITY;
    var dates=eq.dates||[];
    var equityVals=eq.equity||[];
    // Mark points for CS events
    var markPoints=[];

    // Add deposit/withdrawal markpoints
    if(CS_TIMELINE_DATA&&CS_TIMELINE_DATA.length){
      CS_TIMELINE_DATA.forEach(function(item){
        var ts=item[0], evType=item[2], desc=item[3];
        if(evType==='deposit'){
          markPoints.push({name:'入金',coord:[ts.substring(0,10),0],value:desc,itemStyle:{color:G},symbol:'pin',symbolSize:35,label:{show:true,formatter:'入金',fontSize:9,color:'#fff',backgroundColor:G,borderRadius:3,padding:[2,6]}});
        }else if(evType==='withdrawal'){
          markPoints.push({name:'出金',coord:[ts.substring(0,10),0],value:desc,itemStyle:{color:R},symbol:'pin',symbolSize:35,label:{show:true,formatter:'出金',fontSize:9,color:'#fff',backgroundColor:R,borderRadius:3,padding:[2,6]}});
        }
      });
    }
    // Add existing peak/trough markers
    if(eq.dates.length>0){
      markPoints.push({name:'高點',coord:[eq.dates[eq.dd_peak_idx],eq.equity[eq.dd_peak_idx]],itemStyle:{color:G},symbol:'pin',symbolSize:40,label:{show:true,formatter:'Peak',fontSize:9}});
      markPoints.push({name:'低點',coord:[eq.dates[eq.dd_trough_idx],eq.equity[eq.dd_trough_idx]],itemStyle:{color:R},symbol:'pin',symbolSize:40,label:{show:true,formatter:'Trough',fontSize:9}});
    }
    var markAreas=[];
    if(eq.dd_peak_idx<eq.dd_trough_idx){
      markAreas=[{itemStyle:{color:isDark?'rgba(239,68,68,0.12)':'rgba(220,38,38,0.1)'},data:[[{name:'回撤',xAxis:eq.dates[eq.dd_peak_idx],yAxis:0},{xAxis:eq.dates[eq.dd_trough_idx],yAxis:'max'}]]}];
    }

    var chart=echarts.init(el,isDark?'dark':null);
    chart.setOption({
      tooltip:{trigger:'axis',formatter:function(p){
        if(p.length>=2)return p[1].name+'<br/>權益: $'+p[1].value.toFixed(2)+'<br/>回撤: '+p[0].value.toFixed(2)+'%';
        return p[0].name+'<br/>權益: $'+p[0].value.toFixed(2);
      }},
      grid:[{left:60,right:15,top:15,height:'55%'},{left:60,right:15,top:'72%',height:'20%'}],
      xAxis:[{type:'category',data:dates,gridIndex:0,axisLabel:{fontSize:9,rotate:30,interval:Math.max(1,Math.floor(dates.length/8))},axisLine:{lineStyle:{color:mc}}},{type:'category',data:dates,gridIndex:1,axisLabel:{show:false},axisLine:{lineStyle:{color:mc}}}],
      yAxis:[{type:'value',gridIndex:0,axisLabel:{formatter:'$ {value}'},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},{type:'value',gridIndex:1,axisLabel:{formatter:'{value}%',fontSize:9},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}},inverse:true}],
      series:[
        {name:'回撤 %',type:'line',xAxisIndex:1,yAxisIndex:1,data:CHART_EQUITY.equity.map(function(v,i){var pk=-Infinity,dd=0;eq.equity.slice(0,i+1).forEach(function(x){if(x>pk)pk=x;dd=Math.max(dd,pk>0?(pk-x)/pk*100:0);});return Math.round(dd*100)/100;}),smooth:true,symbol:'none',lineStyle:{color:'#ef4444',width:1.5},areaStyle:{color:isDark?'rgba(239,68,68,0.3)':'rgba(239,68,68,0.15)'}},
        {name:'權益曲線',type:'line',xAxisIndex:0,yAxisIndex:0,data:equityVals,smooth:true,symbol:'none',lineStyle:{color:eq.pl>=0?G:R,width:2},areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:eq.pl>=0?(isDark?'rgba(34,197,94,0.25)':'rgba(22,163,74,0.15)'):(isDark?'rgba(239,68,68,0.25)':'rgba(220,38,38,0.15)')},{offset:1,color:'rgba(0,0,0,0)'}]}},markPoint:{data:markPoints,symbolOffset:[0,-10]},markArea:{data:markAreas}}
      ]
    });
    el._ec=chart;
  })();

  // 2) Close reason donut
  (function(){
    var el=document.getElementById('chart-close-reason');
    if(!el)return;
    try{if(el._ec){el._ec.dispose();}el._ec=null;}catch(e){}
    var cr=CS_CLOSE_REASON;
    var colorMap={'Stop Out (爆仓)':'#ef4444','SL (止损)':'#f59e0b','TP (止盈)':'#22c55e','Manual (手动/其他)':'#3b82f6'};
    var data=Object.keys(cr).map(function(k){return{name:k,value:cr[k],itemStyle:{color:colorMap[k]||'#7b879c'}};});
    var chart=echarts.init(el,isDark?'dark':null);
    chart.setOption({
      tooltip:{trigger:'item',formatter:'{b}: {c} 笔 ({d}%)'},
      legend:{bottom:0,textStyle:{fontSize:10,color:mc}},
      series:[{type:'pie',radius:['40%','70%'],center:['50%','48%'],avoidLabelOverlap:false,label:{show:true,formatter:'{b}\n{d}%',fontSize:9,color:tc},data:data,emphasis:{scale:false}}]
    });
    el._ec=chart;
  })();

  // 3) Holding time bar chart (seconds buckets)
  (function(){
    var el=document.getElementById('chart-holding-time');
    if(!el)return;
    try{if(el._ec){el._ec.dispose();}el._ec=null;}catch(e){}
    var ht=CS_HOLDING_TIME;
    var order=['< 10s','10s-1m','1m-5m','5m-1h','1h-24h','> 24h'];
    var data=order.map(function(k){return{name:k,value:ht[k]||0};});
    var barColors={'< 10s':R,'10s-1m':O,'1m-5m':isDark?'#fbbf24':'#d97706','5m-1h':B,'1h-24h':G,'> 24h':P};
    var chart=echarts.init(el,isDark?'dark':null);
    chart.setOption({
      tooltip:{trigger:'axis',formatter:function(p){return p[0].name+': '+p[0].value+' 笔';}},
      grid:{left:60,right:15,top:10,bottom:25},
      xAxis:{type:'category',data:data.map(function(d){return d.name;}),axisLabel:{fontSize:9,color:tc},axisLine:{lineStyle:{color:mc}}},
      yAxis:{type:'value',name:'笔数',nameTextStyle:{fontSize:9,color:mc},axisLabel:{fontSize:9},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
      series:[{type:'bar',data:data.map(function(d){return{value:d.value,itemStyle:{color:barColors[d.name]||B}};}),barWidth:'65%',label:{show:true,position:'top',fontSize:9,color:tc}}]
    });
    el._ec=chart;
  })();

  // 4) Swap burden horizontal stacked bar
  (function(){
    var el=document.getElementById('chart-swap-burden');
    if(!el)return;
    try{if(el._ec){el._ec.dispose();}el._ec=null;}catch(e){}
    var sb=CS_SWAP_BURDEN;
    if(!sb||!sb.length){document.getElementById('chart-swap-burden').parentElement.style.display='none';return;}
    var chart=echarts.init(el,isDark?'dark':null);
    chart.setOption({
      tooltip:{trigger:'axis',axisPointer:{type:'shadow'},formatter:function(p){
        var name=p[0].name;var lines=p.map(function(s){return s.marker+s.seriesName+': $'+s.value.toFixed(2);});
        return name+'<br/>'+lines.join('<br/>');
      }},
      legend:{bottom:0,textStyle:{fontSize:10,color:mc}},
      grid:{left:55,right:15,top:10,bottom:45},
      xAxis:{type:'category',data:sb.map(function(d){return d.name;}),axisLabel:{fontSize:9,rotate:30,color:tc},axisLine:{lineStyle:{color:mc}}},
      yAxis:{type:'value',axisLabel:{formatter:'${value}',fontSize:9},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
      series:[
        {name:'净盈亏',type:'bar',stack:'total',data:sb.map(function(d){return{value:d.profit,itemStyle:{color:d.profit>=0?G:R}};}),barWidth:'50%',label:{show:true,position:'top',formatter:function(p){return '$'+p.value.toFixed(0);},fontSize:9,color:tc}},
        {name:'隔夜利息',type:'bar',stack:'total',data:sb.map(function(d){return{value:d.swap,itemStyle:{color:O}};})},
        {name:'手续费',type:'bar',stack:'total',data:sb.map(function(d){return{value:d.commission,itemStyle:{color:P}};})}
      ]
    });
    el._ec=chart;
  })();

  // 5) Cashflow waterfall
  (function(){
    var el=document.getElementById('chart-cashflow-waterfall');
    if(!el)return;
    try{if(el._ec){el._ec.dispose();}el._ec=null;}catch(e){}
    var wf=CS_CASHFLOW_WATERFALL;
    if(!wf||!wf.labels||!wf.labels.length)return;
    // Build waterfall helper arrays
    var values=wf.values;
    var base=[],cum=0;
    var colors=[G,R,'#3b82f6',O,P,P];
    values.forEach(function(v,i){
      base.push(cum);
      cum+=v;
    });
    var chart=echarts.init(el,isDark?'dark':null);
    chart.setOption({
      tooltip:{trigger:'axis',axisPointer:{type:'shadow'},formatter:function(p){
        var idx=p[0].dataIndex;return wf.labels[idx]+'<br/>$'+(values[idx]>=0?'+':'')+values[idx].toFixed(2)+'<br/>累计: $'+base[idx].toFixed(2);
      }},
      grid:{left:60,right:15,top:10,bottom:35},
      xAxis:{type:'category',data:wf.labels,axisLabel:{fontSize:9,rotate:20,color:tc,interval:0},axisLine:{lineStyle:{color:mc}}},
      yAxis:{type:'value',axisLabel:{formatter:'${value}',fontSize:9},splitLine:{lineStyle:{color:isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.06)'}}},
      series:[
        {name:'变化',type:'bar',stack:'Total',barWidth:'55%',itemStyle:{borderColor:'transparent',color:function(p){return p.value>=0?G:R;}},data:values.map(function(v,i){return v;}),label:{show:true,position:'top',formatter:function(p){return(p.value>=0?'+':'')+p.value.toFixed(0);},fontSize:9,color:tc}},
        {name:'置底',type:'bar',stack:'Total',itemStyle:{borderColor:'transparent',color:'rgba(0,0,0,0)'},emphasis:{itemStyle:{borderColor:'transparent',color:'rgba(0,0,0,0)'}},data:base.map(function(v){return v>=0?Math.max(0,v):v;})},
        {name:'累计',type:'line',data:base.map(function(v,i){return Math.round((v+(values[i]||0))*100)/100;}),itemStyle:{color:isDark?'#fbbf24':'#d97706'},symbol:'diamond',symbolSize:6,lineStyle:{width:2,type:'dashed'},label:{show:true,position:'right',formatter:function(p){return '$'+p.value.toFixed(0);},fontSize:9,color:isDark?'#fbbf24':'#d97706'}}
      ]
    });
    el._ec=chart;
  })();
}

// CS Filter toolbar
window.csFilter=function(mode){
  document.querySelectorAll('.cs-btn').forEach(function(b){b.classList.remove('active');});
  event&&event.target&&event.target.classList.add('active');
  var filtered=[];
  switch(mode){
    case 'stopout':
      filtered=ALL_TRADES.filter(function(t){return t.comment&&(t.comment.toLowerCase().indexOf('so')>=0||t.comment.toLowerCase().indexOf('stop out')>=0);});
      document.getElementById('csFilterInfo').textContent=filtered.length+' 笔爆仓单';
      break;
    case 'scalp':
      filtered=ALL_TRADES.filter(function(t){if(!t.open||!t.close)return false;var d=(new Date(t.close.replace(' ','T'))-new Date(t.open.replace(' ','T')))/1000;return d<60;});
      document.getElementById('csFilterInfo').textContent=filtered.length+' 笔超短线 (<1m)';
      break;
    case 'swap':
      filtered=ALL_TRADES.filter(function(t){return t.swap&&Math.abs(t.swap)>0;});
      document.getElementById('csFilterInfo').textContent=filtered.length+' 笔含隔夜利息单';
      break;
    default:
      filtered=ALL_TRADES.slice();
      document.getElementById('csFilterInfo').textContent='';
  }
  data=filtered.slice();
  currentPage=1;renderTable();updateKPIs();updateChartsFromFilter();
};

// Ticket click → timeline highlight (via search)
document.addEventListener('click',function(e){
  var td=e.target.closest('td');
  if(td&&td.closest('#tradeBody')){
    var row=td.closest('tr');
    var firstTd=row&&row.querySelector('td:first-child');
    if(firstTd){
      var ticket=firstTd.textContent.trim();
      document.getElementById('searchBox').value=ticket;
      doSearch();
    }
  }
});

// Init CS charts after main charts
initCSCharts();
</script>
<div class="metric-guide" style="max-width:1500px;margin:20px auto 0;padding:0 clamp(10px,1vw,20px) 20px">
<details style="background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:14px 18px;cursor:pointer">
<summary style="font-size:13px;font-weight:600;color:var(--text);outline:none">📖 指標說明與計算公式</summary>
<div style="margin-top:10px;font-size:12px;color:var(--muted);line-height:1.8">
<p><b>總交易</b>：報表中所有已平倉交易的總筆數。</p>
<p><b>總盈虧</b>：所有交易 profit 欄位的代數和（盈利 − 虧損 − 佣金 − Swap）。</p>
<p><b>獲利佔比</b>：盈利筆數 ÷ 總筆數 × 100%。高獲利佔比不等於賺錢 — 如果平均虧損遠大於平均盈利，仍然會虧損。</p>
<p><b>平均盈利 / 平均虧損</b>：分別為盈利與虧損交易的平均 profit。</p>
<p><b>盈虧比</b>：平均盈利 ÷ 平均虧損絕對值。<b style="color:var(--green)">≥1</b> 表示賺時賺的比輸時賠的多。</p>
<p><b>盈利因子</b>：總盈利 ÷ 總虧損絕對值。<b style="color:var(--red)">&lt;1</b> 代表策略長期處於負值。</p>
<p><b>最大回撤</b>：權益曲線從歷史最高點到之後最低點的跌幅（美元）。</p>
<p><b>夏普比率</b>：風險調整後報酬 = 日均盈虧均值 ÷ 日均盈虧標準差 × √252。</p>
<p><b>持倉時間</b>：從開倉到平倉的實際時長。</p>
<p><b>每手盈虧</b>：profit ÷ 手數，用來比較不同手數下的績效。</p>
</div></details></div>
</body></html>"""


def process_file(path):
    result = parse_statement(path)
    trades = result["trades"]
    cash_flows = result.get("cash_flows", [])
    if not trades:
        messagebox.showerror("失敗", "未找到交易記錄")
        return
    stats = analyze(trades, result)  # v8.0: pass full parse_data
    html = build_dashboard_html(result["account"], trades, stats, cash_flows)  # v8.0: pass cash_flows
    out = Path(tempfile.gettempdir()) / f"MT_Desk_{result['account']}.html"
    out.write_text(html, encoding="utf-8")
    threading.Timer(0.3, lambda: webbrowser.open(out.as_uri())).start()
    return result, len(trades)


def main():
    root = tk.Tk()
    root.title("MT Desk")
    root.geometry("400x260")
    root.configure(bg="#f4f6f9")
    root.resizable(False, False)
    tk.Label(root, text="MT Desk", font=("Segoe UI", 22, "bold"), fg="#2563eb", bg="#f4f6f9").pack(pady=(24, 4))
    tk.Label(root, text="洞察驅動交易習慣分析報表 · ECharts 進階圖表", font=("Segoe UI", 10), fg="#6b7280", bg="#f4f6f9").pack(pady=(0, 20))
    status_var = tk.StringVar(value="選擇 HTML 報表檔案")
    status = tk.Label(root, textvariable=status_var, font=("Segoe UI", 9), fg="#6b7280", bg="#f4f6f9")
    status.pack(pady=(0, 14))

    def open_file():
        paths = filedialog.askopenfilenames(title="選擇 MT4/MT5 報表", filetypes=[("HTML", "*.htm *.html")])
        if not paths:
            return
        def worker():
            total = len(paths)
            for i, path in enumerate(paths, 1):
                fname = Path(path).name
                root.after(0, lambda f=fname, i=i, t=total: status_var.set(f"⏳ ({i}/{t}): {f}"))
                try:
                    process_file(path)
                except Exception as e:
                    root.after(0, lambda err=str(e): messagebox.showerror("錯誤", err))
            root.after(0, lambda t=total: status_var.set(f"✅ 完成 — {t} 個檔案"))
        threading.Thread(target=worker, daemon=True).start()
    tk.Button(root, text="📂 選擇 MT4/MT5 HTML 報表", font=("Segoe UI", 12), bg="#2563eb", fg="white",
              relief="flat", padx=24, pady=10, command=open_file, cursor="hand2").pack()
    root.mainloop()


if __name__ == "__main__":
    main()
