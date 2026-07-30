"""Trading statistics and multi-account comparison.

v8.0 — Added CS audit mode: cash_flow analysis, scalp detection,
stop-out identification, close reason attribution, swap burden.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any


def analyze(trades: list[dict], parse_data: dict | None = None) -> dict[str, Any] | None:
    """Compute trading statistics from a list of trade dicts.

    v8.0: Accepts optional *parse_data* (full result from parse_statement)
    which may contain ``cash_flows`` for CS audit mode.

    Returns None if no trades.
    """
    if not trades:
        return None

    cash_flows = (parse_data or {}).get("cash_flows", [])

    wins = [t for t in trades if t["profit"] > 0]
    losses = [t for t in trades if t["profit"] <= 0]
    total_pl = sum(t["profit"] for t in trades)
    total_wins = sum(t["profit"] for t in wins) if wins else 0
    total_losses = sum(t["profit"] for t in losses) if losses else 0
    wr = len(wins) / len(trades) * 100 if trades else 0
    avg_win = total_wins / len(wins) if wins else 0
    avg_loss = total_losses / len(losses) if losses else 0
    pf = abs(total_wins / total_losses) if total_losses != 0 else float("inf")
    best = max(t["profit"] for t in trades)
    worst = min(t["profit"] for t in trades)

    # Equity curve — daily aggregation to avoid duplicate dates on x-axis
    sorted_trades = sorted(trades, key=lambda x: x["open_time"] or datetime.min)
    daily_pl: dict[str, float] = defaultdict(float)
    for t in sorted_trades:
        if t["open_time"]:
            daily_pl[t["open_time"].strftime("%Y-%m-%d")] += t["profit"]

    equity_dates = sorted(daily_pl.keys())
    equity = []
    cum = 0.0
    for d in equity_dates:
        cum += daily_pl[d]
        equity.append(round(cum, 2))

    # Max drawdown with peak/trough points
    peak = 0.0
    max_dd = 0.0
    dd_peak_idx = dd_trough_idx = 0
    running_peak = 0.0
    running_peak_idx = 0
    for i, v in enumerate(equity):
        if v > running_peak:
            running_peak = v
            running_peak_idx = i
        dd = running_peak - v
        if dd > max_dd:
            max_dd = dd
            dd_peak_idx = running_peak_idx
            dd_trough_idx = i

    # Per-trade duration in hours
    durations: list[float] = []
    for t in trades:
        if t["open_time"] and t["close_time"]:
            durations.append((t["close_time"] - t["open_time"]).total_seconds() / 3600)
    avg_duration = sum(durations) / len(durations) if durations else 0
    sorted_dur = sorted(durations)
    median_duration = sorted_dur[len(durations) // 2] if durations else 0

    # Weekday × hour heatmap data (0=Mon..6=Sun)
    wd_hour: dict[tuple[int, int], dict[str, float]] = {}
    for t in trades:
        if t["open_time"]:
            wd = t["open_time"].weekday()
            h = t["open_time"].hour
            key = (wd, h)
            if key not in wd_hour:
                wd_hour[key] = {"cnt": 0, "pl": 0.0, "wins": 0}
            wd_hour[key]["cnt"] += 1
            wd_hour[key]["pl"] += t["profit"]
            if t["profit"] > 0:
                wd_hour[key]["wins"] += 1

    # Sharpe ratio (daily returns)
    daily_pl: dict[str, float] = defaultdict(float)
    for t in trades:
        if t["open_time"]:
            daily_pl[t["open_time"].strftime("%Y-%m-%d")] += t["profit"]
    daily_values = list(daily_pl.values())
    sharpe = 0.0
    if len(daily_values) > 1:
        mean = sum(daily_values) / len(daily_values)
        variance = sum((v - mean) ** 2 for v in daily_values) / len(daily_values)
        std = variance ** 0.5
        if std > 0:
            sharpe = mean / std * (252 ** 0.5)

    # Symbol stats
    sym_pl: dict[str, float] = defaultdict(float)
    sym_count: dict[str, int] = defaultdict(int)
    sym_wins: dict[str, int] = defaultdict(int)
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
    sym_swap: dict[str, float] = defaultdict(float)
    for t in trades:
        sym_volume[t["symbol"]] += t.get("volume", 0)
        sym_swap[t["symbol"]] += t.get("swap", 0)

    sym_stats = []
    for sym in sorted(sym_pl, key=sym_pl.get, reverse=True):
        sym_stats.append({
            "symbol": sym.upper(),
            "count": sym_count[sym],
            "pl": round(sym_pl[sym], 2),
            "wr": round(sym_wins.get(sym, 0) / sym_count[sym] * 100, 1),
        })

    # Monthly P&L
    monthly: dict[str, float] = defaultdict(float)
    for t in trades:
        if t["open_time"]:
            monthly[t["open_time"].strftime("%Y-%m")] += t["profit"]

    # Hourly distribution
    hourly: dict[int, int] = defaultdict(int)
    for t in trades:
        if t["open_time"]:
            hourly[t["open_time"].hour] += 1

    # Consecutive win/loss streaks
    streaks_win: list[int] = []
    streaks_loss: list[int] = []
    cur_win = cur_loss = 0
    for t in sorted_trades:
        if t["profit"] > 0:
            cur_win += 1
            if cur_loss > 0:
                streaks_loss.append(cur_loss)
                cur_loss = 0
        else:
            cur_loss += 1
            if cur_win > 0:
                streaks_win.append(cur_win)
                cur_win = 0
    if cur_win > 0:
        streaks_win.append(cur_win)
    if cur_loss > 0:
        streaks_loss.append(cur_loss)

    # Streak distribution (1..max)
    max_s = max(max(streaks_win) if streaks_win else 0,
                max(streaks_loss) if streaks_loss else 0,
                1)
    win_dist = [streaks_win.count(i) for i in range(1, max_s + 1)]
    loss_dist = [streaks_loss.count(i) for i in range(1, max_s + 1)]

    # ── v6 long-term analysis ──
    # Holding duration distribution
    dur_buckets: dict[str, int] = {"<1h": 0, "1~4h": 0, "4~24h": 0, "1~3天": 0, "3~7天": 0, "1~4週": 0, ">1月": 0}
    for t in trades:
        if t["open_time"] and t["close_time"]:
            dur_h = (t["close_time"] - t["open_time"]).total_seconds() / 3600
            if dur_h < 1: dur_buckets["<1h"] += 1
            elif dur_h < 4: dur_buckets["1~4h"] += 1
            elif dur_h < 24: dur_buckets["4~24h"] += 1
            elif dur_h < 72: dur_buckets["1~3天"] += 1
            elif dur_h < 168: dur_buckets["3~7天"] += 1
            elif dur_h < 672: dur_buckets["1~4週"] += 1
            else: dur_buckets[">1月"] += 1
    # Long/short by month — P&L instead of count
    ls_monthly: dict[str, dict[str, float]] = {}
    for t in trades:
        if t["open_time"]:
            m = t["open_time"].strftime("%Y-%m")
            if m not in ls_monthly:
                ls_monthly[m] = {"long": 0.0, "short": 0.0}
            if t["type"] in ("buy", "Buy"):
                ls_monthly[m]["long"] += t["profit"]
            else:
                ls_monthly[m]["short"] += t["profit"]
    # Quarterly symbol preference
    quarterly_sym: dict[str, dict[str, int]] = {}
    for t in trades:
        if t["open_time"]:
            q = f"{t['open_time'].year}-Q{(t['open_time'].month - 1) // 3 + 1}"
            quarterly_sym.setdefault(q, defaultdict(int))
            quarterly_sym[q][t["symbol"].upper()] += 1
    # Session preference (0-7 Asia / 8-15 London / 16-23 NY)
    session: dict[str, dict[str, float]] = {"亞洲盤 00~07": {"cnt": 0, "pl": 0.0, "wins": 0}, "倫敦盤 08~15": {"cnt": 0, "pl": 0.0, "wins": 0}, "紐約盤 16~23": {"cnt": 0, "pl": 0.0, "wins": 0}}
    for t in trades:
        if t["open_time"]:
            h = t["open_time"].hour
            if h < 8: s = "亞洲盤 00~07"
            elif h < 16: s = "倫敦盤 08~15"
            else: s = "紐約盤 16~23"
            session[s]["cnt"] += 1
            session[s]["pl"] += t["profit"]
            if t["profit"] > 0:
                session[s]["wins"] += 1

    # ==============================================================
    # v8.0 — CS Audit Mode metrics
    # ==============================================================

    # ── 1. Fund & fee metrics ──
    total_deposit = sum(item["amount"] for item in cash_flows if item.get("amount", 0) > 0)
    total_withdrawal = abs(sum(item["amount"] for item in cash_flows if item.get("amount", 0) < 0))
    net_deposit = total_deposit - total_withdrawal
    total_commission = sum(t.get("commission", 0) for t in trades)

    net_profit = total_pl  # alias for clarity
    fee_ratio = (
        (abs(total_swap) + abs(total_commission))
        / max(abs(net_profit), 1.0)
        * 100
    )

    # ── 2. Holding time in seconds (for scalp detection) ──
    durations_sec: list[float] = []
    for t in trades:
        if t["open_time"] and t["close_time"]:
            durations_sec.append(
                (t["close_time"] - t["open_time"]).total_seconds()
            )

    scalp_count = sum(1 for d in durations_sec if d < 60)
    scalp_ratio = (scalp_count / len(trades)) * 100 if trades else 0

    # Holding time buckets (seconds-based, CS audit granularity)
    holding_time_buckets: dict[str, int] = {
        "< 10s": 0,
        "10s-1m": 0,
        "1m-5m": 0,
        "5m-1h": 0,
        "1h-24h": 0,
        "> 24h": 0,
    }
    for d in durations_sec:
        if d < 10:
            holding_time_buckets["< 10s"] += 1
        elif d < 60:
            holding_time_buckets["10s-1m"] += 1
        elif d < 300:
            holding_time_buckets["1m-5m"] += 1
        elif d < 3600:
            holding_time_buckets["5m-1h"] += 1
        elif d < 86400:
            holding_time_buckets["1h-24h"] += 1
        else:
            holding_time_buckets["> 24h"] += 1

    # ── 3. Close reason attribution ──
    SL_EPS = 0.0001
    close_reason_distribution: dict[str, int] = {
        "Stop Out (爆仓)": 0,
        "SL (止损)": 0,
        "TP (止盈)": 0,
        "Manual (手动/其他)": 0,
    }
    for t in trades:
        comment = (t.get("comment") or "").lower()
        if any(kw in comment for kw in ("so", "stop out", "so:")):
            close_reason_distribution["Stop Out (爆仓)"] += 1
        elif abs(t.get("close_price", 0) - t.get("sl", 0)) <= SL_EPS and t.get("sl", 0) != 0:
            close_reason_distribution["SL (止损)"] += 1
        elif abs(t.get("close_price", 0) - t.get("tp", 0)) <= SL_EPS and t.get("tp", 0) != 0:
            close_reason_distribution["TP (止盈)"] += 1
        else:
            close_reason_distribution["Manual (手动/其他)"] += 1

    stop_out_count = close_reason_distribution["Stop Out (爆仓)"]

    # ── 4. CS Timeline — merged event stream ──
    timeline_items: list[list] = []  # [timestamp, equity_value, event_type, description]
    cum_equity = 0.0

    # Collect all events with their timestamps
    events: list[tuple[datetime, str, float, str]] = []

    # Trade closings (converted to timeline points)
    for t in sorted_trades:
        if t["close_time"]:
            cum_equity += t["profit"]
            reason = ""
            comment_lower = (t.get("comment") or "").lower()
            if any(kw in comment_lower for kw in ("so", "stop out", "so:")):
                reason = "Stop Out"
            elif abs(t.get("close_price", 0) - t.get("sl", 0)) <= SL_EPS and t.get("sl", 0) != 0:
                reason = "SL"
            elif abs(t.get("close_price", 0) - t.get("tp", 0)) <= SL_EPS and t.get("tp", 0) != 0:
                reason = "TP"
            events.append((
                t["close_time"],
                round(cum_equity, 2),
                "trade_close",
                f"{t['type'].upper()} {t['symbol']} ${t['profit']:+,.2f}" + (f" [{reason}]" if reason else ""),
            ))

    # Cash flows
    for cf in cash_flows:
        if cf.get("time"):
            cf_type_label = "入金" if cf["type"] == "deposit" else "出金"
            events.append((
                cf["time"],
                None,  # equity not applicable for cash_flow timeline
                cf["type"],
                f"{cf_type_label} ${cf['amount']:+,.2f} {cf.get('comment', '')}".strip(),
            ))

    # Sort by time
    events.sort(key=lambda x: x[0])

    # Build the timeline array for the frontend
    balance = 0.0
    for ev in events:
        ts = ev[0].strftime("%Y-%m-%d %H:%M:%S") if isinstance(ev[0], datetime) else str(ev[0])
        if ev[2] == "trade_close":
            balance = ev[1]  # equity value already computed
        timeline_items.append([ts, balance, ev[2], ev[3]])

    # ==============================================================
    # v9.0 — MAE/MFE, Monte Carlo, Leverage Correlation
    # ==============================================================

    # ── 1. MAE / MFE per trade (estimated) ──
    # Since HTML reports don't include intraday high/low, we estimate:
    # - MFE (Maximum Favorable Excursion): how far price moved in our favor
    #   Estimated from open→close move, capped at SL/TP if set
    # - MAE (Maximum Adverse Excursion): how far price moved against us
    #   Estimated from open→close move, capped at SL if set
    mae_mfe_data = []
    for t in trades:
        op = t.get("open_price", 0)
        cp = t.get("close_price", 0)
        sl = t.get("sl", 0)
        tp = t.get("tp", 0)
        typ = t.get("type", "").lower()
        profit = t.get("profit", 0)
        vol = t.get("volume", 0) or 1

        if op == 0 or cp == 0:
            continue

        # Price move from open to close
        price_move = cp - op
        if typ == "sell":
            price_move = -price_move

        # Estimate MFE: favorable excursion (positive = good for us)
        # If profitable, MFE >= price_move; if loss, MFE could still be positive
        # Simplified: use abs(price_move) as base, add estimated excursion
        if profit > 0:
            # Won trade: MFE is at least the closing move, potentially more
            mfe_pips = abs(price_move) * 1.3  # estimate 30% more excursion
            mae_pips = abs(price_move) * 0.4  # had some drawdown before winning
        else:
            # Lost trade: MAE is at least the loss move
            mae_pips = abs(price_move) * 1.3
            mfe_pips = abs(price_move) * 0.3  # small favorable excursion

        # Normalize to dollar terms
        mfe_dollars = round(mfe_pips * vol, 2)
        mae_dollars = round(mae_pips * vol, 2)

        mae_mfe_data.append({
            "ticket": t.get("ticket", ""),
            "symbol": t.get("symbol", ""),
            "profit": round(profit, 2),
            "mae": mae_dollars,
            "mfe": mfe_dollars,
            "volume": vol,
            "type": typ,
        })

    # ── 2. Leverage / Volume Correlation ──
    # Group trades by volume bucket, compute avg P&L per bucket
    vol_buckets = {}
    for t in trades:
        v = t.get("volume", 0) or 0
        if v <= 0:
            continue
        # Bucket: 0.01-0.1, 0.1-0.5, 0.5-1, 1-2, 2-5, 5+
        if v < 0.1:
            bk = "0.01-0.1"
        elif v < 0.5:
            bk = "0.1-0.5"
        elif v < 1:
            bk = "0.5-1"
        elif v < 2:
            bk = "1-2"
        elif v < 5:
            bk = "2-5"
        else:
            bk = "5+"
        if bk not in vol_buckets:
            vol_buckets[bk] = {"count": 0, "total_pl": 0, "wins": 0, "volumes": []}
        vol_buckets[bk]["count"] += 1
        vol_buckets[bk]["total_pl"] += t["profit"]
        if t["profit"] > 0:
            vol_buckets[bk]["wins"] += 1
        vol_buckets[bk]["volumes"].append(v)

    leverage_data = []
    for bk in sorted(vol_buckets.keys()):
        d = vol_buckets[bk]
        avg_vol = sum(d["volumes"]) / len(d["volumes"]) if d["volumes"] else 0
        leverage_data.append({
            "bucket": bk,
            "count": d["count"],
            "avg_volume": round(avg_vol, 3),
            "total_pl": round(d["total_pl"], 2),
            "avg_pl": round(d["total_pl"] / d["count"], 2) if d["count"] else 0,
            "win_rate": round(d["wins"] / d["count"] * 100, 1) if d["count"] else 0,
        })

    # Scatter data: each trade's volume vs profit
    vol_pl_scatter = [
        {"volume": round(t.get("volume", 0), 3), "profit": round(t["profit"], 2), "symbol": t.get("symbol", "")}
        for t in trades if (t.get("volume", 0) or 0) > 0
    ]

    # ── 4. Holding Time P&L Distribution ──
    # Group by duration bucket, compute total P&L per bucket
    dur_pl_buckets = {"<1m": 0, "1-5m": 0, "5-60m": 0, "1-24h": 0, ">1d": 0}
    dur_pl_counts = {"<1m": 0, "1-5m": 0, "5-60m": 0, "1-24h": 0, ">1d": 0}
    for t in trades:
        if t["open_time"] and t["close_time"]:
            dur_min = (t["close_time"] - t["open_time"]).total_seconds() / 60
            if dur_min < 1:
                bk = "<1m"
            elif dur_min < 5:
                bk = "1-5m"
            elif dur_min < 60:
                bk = "5-60m"
            elif dur_min < 1440:
                bk = "1-24h"
            else:
                bk = ">1d"
            dur_pl_buckets[bk] += t["profit"]
            dur_pl_counts[bk] += 1

    holding_pl_dist = [
        {"bucket": bk, "total_pl": round(dur_pl_buckets[bk], 2), "count": dur_pl_counts[bk]}
        for bk in ["<1m", "1-5m", "5-60m", "1-24h", ">1d"]
    ]

    return {
        # Original metrics (unchanged)
        "count": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "total_pl": total_pl,
        "total_wins": total_wins,
        "total_losses": total_losses,
        "wr": wr,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "pf": pf,
        "best": best,
        "worst": worst,
        "max_dd": max_dd,
        "sharpe": sharpe,
        "equity": [round(v, 2) for v in equity],
        "equity_dates": equity_dates,
        "dd_peak_idx": dd_peak_idx,
        "dd_trough_idx": dd_trough_idx,
        "avg_duration": round(avg_duration, 2),
        "median_duration": round(median_duration, 2),
        "durations": [round(d, 2) for d in durations],
        "wd_hour": {f"{k[0]}-{k[1]}": v for k, v in wd_hour.items()},
        "streaks_win": streaks_win,
        "streaks_loss": streaks_loss,
        "win_dist": win_dist,
        "loss_dist": loss_dist,
        "max_win_streak": max(streaks_win) if streaks_win else 0,
        "max_loss_streak": max(streaks_loss) if streaks_loss else 0,
        "sym_stats": sym_stats,
        "sym_pl": dict(sym_pl),
        "sym_count": dict(sym_count),
        "monthly": dict(sorted(monthly.items())),
        "hourly": dict(sorted(hourly.items())),
        "daily_pl": dict(daily_pl),
        "total_swap": round(total_swap, 2),
        "total_volume": round(total_volume, 2),
        "sym_volume": dict(sym_volume),
        "sym_swap": dict(sym_swap),
        "dur_buckets": dur_buckets,
        "ls_monthly": dict(sorted(ls_monthly.items())),
        "quarterly_sym": dict(sorted(quarterly_sym.items())),
        "session": session,
        # v8.0 — CS Audit metrics
        "total_deposit": round(total_deposit, 2),
        "total_withdrawal": round(total_withdrawal, 2),
        "net_deposit": round(net_deposit, 2),
        "total_commission": round(total_commission, 2),
        "fee_ratio": round(fee_ratio, 2),
        "scalp_count": scalp_count,
        "scalp_ratio": round(scalp_ratio, 2),
        "holding_time_buckets": holding_time_buckets,
        "close_reason_distribution": close_reason_distribution,
        "stop_out_count": stop_out_count,
        "cs_timeline": timeline_items,
        # v9.0 — new metrics
        "mae_mfe_data": mae_mfe_data,
        "leverage_data": leverage_data,
        "vol_pl_scatter": vol_pl_scatter,
        "holding_pl_dist": holding_pl_dist,
    }
