"""Trading statistics and multi-account comparison."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any


def analyze(trades: list[dict]) -> dict[str, Any] | None:
    """Compute trading statistics from a list of trade dicts.

    Returns None if no trades.
    """
    if not trades:
        return None

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
    cum = 0.0
    equity = []; equity_dates = []
    last_date = None
    for t in sorted_trades:
        cum += t["profit"]
        d = t["open_time"].strftime("%Y-%m-%d") if t["open_time"] else ""
        if d != last_date and last_date is not None:
            equity.append(round(cum - t["profit"], 2))
            equity_dates.append(last_date)
        last_date = d
    # Append final point
    if last_date is not None:
        equity.append(round(cum, 2))
        equity_dates.append(last_date)

    # Max drawdown
    peak = 0.0
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd

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
    # Long/short by month
    ls_monthly: dict[str, dict[str, float]] = {}
    for t in trades:
        if t["open_time"]:
            m = t["open_time"].strftime("%Y-%m")
            if m not in ls_monthly:
                ls_monthly[m] = {"long": 0, "short": 0}
            if t["type"] in ("buy", "Buy"):
                ls_monthly[m]["long"] += 1
            else:
                ls_monthly[m]["short"] += 1
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

    return {
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
    }
