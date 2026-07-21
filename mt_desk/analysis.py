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

    # Equity curve
    sorted_trades = sorted(trades, key=lambda x: x["open_time"] or datetime.min)
    cum = 0.0
    equity = []; equity_dates = []
    for t in sorted_trades:
        cum += t["profit"]
        equity.append(round(cum, 2))
        equity_dates.append(t["open_time"].strftime("%Y-%m-%d") if t["open_time"] else "")

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
    for t in trades:
        sym_volume[t["symbol"]] += t.get("volume", 0)

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
    }
