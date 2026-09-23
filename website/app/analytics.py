"""Aggregate stats and charts for the /analytics page: equity curve,
drawdown, win/loss streaks, timing breakdowns, symbol/product performance,
and a trend projection. All computed in plain Python from already-fetched
Position rows (a personal journal's trade volume doesn't need SQL-side
aggregation for this).
"""
import calendar
import datetime as dt


def build_equity_curve(daily_rows):
    """daily_rows: [(date, sum_net_pnl), ...] ordered by date.
    Returns (cumulative, drawdown) lists, same length. drawdown[i] is how
    far cumulative[i] sits below the running peak so far (<= 0)."""
    cumulative = []
    drawdown = []
    running = 0.0
    peak = 0.0
    for _, pnl in daily_rows:
        running += pnl
        peak = max(peak, running)
        cumulative.append(round(running, 2))
        drawdown.append(round(running - peak, 2))
    return cumulative, drawdown


def trade_stats(positions):
    closed = [p for p in positions if p.state == "closed"]
    n = len(closed)
    if n == 0:
        return {
            "trade_count": 0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            "profit_factor": None, "expectancy": 0.0, "largest_win": 0.0, "largest_loss": 0.0,
        }
    wins = [p.net_pnl for p in closed if p.net_pnl > 0]
    losses = [p.net_pnl for p in closed if p.net_pnl < 0]
    win_rate = len(wins) / n * 100.0
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0  # negative or 0
    gross_loss = -sum(losses)  # positive
    profit_factor = (sum(wins) / gross_loss) if gross_loss > 0 else None
    expectancy = (win_rate / 100.0) * avg_win + (1 - win_rate / 100.0) * avg_loss
    return {
        "trade_count": n,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "largest_win": max(wins) if wins else 0.0,
        "largest_loss": min(losses) if losses else 0.0,
    }


def streaks(positions_ordered_by_exit):
    """positions_ordered_by_exit: closed positions, ascending exit_time."""
    closed = [p for p in positions_ordered_by_exit if p.state == "closed"]
    best_win_streak = worst_loss_streak = 0
    run_type = None  # True = win streak, False = loss streak
    run_len = 0
    for p in closed:
        won = p.net_pnl > 0
        run_len = run_len + 1 if run_type is won else 1
        run_type = won
        if won:
            best_win_streak = max(best_win_streak, run_len)
        else:
            worst_loss_streak = max(worst_loss_streak, run_len)
    return {
        "current_len": run_len,
        "current_type": ("win" if run_type else "loss") if run_type is not None else None,
        "best_win_streak": best_win_streak,
        "worst_loss_streak": worst_loss_streak,
    }


def weekday_breakdown(positions):
    totals = {i: 0.0 for i in range(7)}
    counts = {i: 0 for i in range(7)}
    for p in positions:
        if p.state != "closed" or not p.exit_date:
            continue
        wd = p.exit_date.weekday()
        totals[wd] += p.net_pnl
        counts[wd] += 1
    labels = [calendar.day_abbr[i] for i in range(7)]
    values = [round(totals[i], 2) for i in range(7)]
    return labels, values, [counts[i] for i in range(7)]


def hour_breakdown(positions):
    totals: dict[int, float] = {}
    for p in positions:
        if p.state != "closed" or not p.exit_time:
            continue
        h = p.exit_time.hour
        totals[h] = totals.get(h, 0.0) + p.net_pnl
    hours = sorted(totals.keys())
    labels = [f"{h:02d}:00" for h in hours]
    values = [round(totals[h], 2) for h in hours]
    return labels, values


def symbol_breakdown(positions):
    agg: dict[str, dict] = {}
    for p in positions:
        if p.state != "closed":
            continue
        d = agg.setdefault(p.tradingsymbol, {"pnl": 0.0, "count": 0, "wins": 0})
        d["pnl"] += p.net_pnl
        d["count"] += 1
        d["wins"] += 1 if p.net_pnl > 0 else 0
    rows = [
        {
            "symbol": sym,
            "pnl": round(v["pnl"], 2),
            "count": v["count"],
            "win_rate": round(v["wins"] / v["count"] * 100.0, 1) if v["count"] else 0.0,
        }
        for sym, v in agg.items()
    ]
    rows.sort(key=lambda r: r["pnl"], reverse=True)
    return rows


def product_breakdown(positions):
    agg: dict[str, dict] = {}
    for p in positions:
        if p.state != "closed":
            continue
        d = agg.setdefault(p.product, {"pnl": 0.0, "count": 0, "wins": 0})
        d["pnl"] += p.net_pnl
        d["count"] += 1
        d["wins"] += 1 if p.net_pnl > 0 else 0
    rows = [
        {
            "product": prod,
            "pnl": round(v["pnl"], 2),
            "count": v["count"],
            "win_rate": round(v["wins"] / v["count"] * 100.0, 1) if v["count"] else 0.0,
        }
        for prod, v in agg.items()
    ]
    rows.sort(key=lambda r: r["pnl"], reverse=True)
    return rows


def pnl_histogram(positions, bins=10):
    closed_pnls = [p.net_pnl for p in positions if p.state == "closed"]
    if not closed_pnls:
        return [], []
    lo, hi = min(closed_pnls), max(closed_pnls)
    if lo == hi:
        return [f"{lo:.0f}"], [len(closed_pnls)]
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in closed_pnls:
        idx = min(int((v - lo) / width), bins - 1)
        counts[idx] += 1
    labels = [f"{lo + i * width:.0f}" for i in range(bins)]
    return labels, counts


def _linreg(xs, ys):
    n = len(xs)
    if n < 2:
        return 0.0, (ys[-1] if ys else 0.0)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return 0.0, mean_y
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = num / den
    return slope, mean_y - slope * mean_x


def _count_weekdays(start: dt.date, end: dt.date) -> int:
    if end <= start:
        return 0
    count = 0
    d = start
    while d < end:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            count += 1
    return count


def _add_weekdays(start: dt.date, n: int) -> dt.date:
    d = start
    added = 0
    while added < n:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


def project_forward(daily_rows, cumulative, fy_end: dt.date, window: int = 20):
    """Naive linear trend projection of cumulative net P&L: fit a line on
    the trailing `window` trading days and extrapolate it to fy_end by
    weekday count. This projects the trader's own recent pace forward --
    it is NOT a prediction of any individual future trade or of market
    direction, and callers should present it with that caveat.
    Returns None if there isn't enough history (< 3 trading days) yet."""
    if len(daily_rows) < 3:
        return None

    tail_cum = cumulative[-window:]
    slope, _ = _linreg(list(range(len(tail_cum))), tail_cum)

    last_date = daily_rows[-1][0]
    last_cum = cumulative[-1]
    remaining_days = _count_weekdays(last_date, fy_end)
    if remaining_days == 0:
        return None

    labels = [last_date.isoformat()]
    values = [last_cum]
    step = max(1, remaining_days // 10)
    d = last_date
    covered = 0
    while covered < remaining_days:
        step_days = min(step, remaining_days - covered)
        d = _add_weekdays(d, step_days)
        covered += step_days
        labels.append(d.isoformat())
        values.append(round(last_cum + slope * covered, 2))

    return {
        "slope_per_trading_day": round(slope, 2),
        "remaining_trading_days": remaining_days,
        "projected_fy_end": round(last_cum + slope * remaining_days, 2),
        "labels": labels,
        "values": values,
    }
