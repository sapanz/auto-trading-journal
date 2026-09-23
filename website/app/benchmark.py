"""Fetches and caches index closing prices (Nifty 50 by default) for the
Analytics page's benchmark comparison chart.

There's no free official NSE/BSE historical-data API, so this uses Yahoo
Finance's public chart endpoint (query1.finance.yahoo.com/v8/finance/chart)
-- unofficial and undocumented, but widely used and doesn't require an API
key. Results are cached in the benchmark_prices table so a given date range
is only fetched once; if Yahoo is unreachable or changes shape, callers
degrade gracefully (see ensure_cached) rather than breaking the page.
"""
import datetime as dt

from sqlalchemy.orm import Session

from . import models

YAHOO_SYMBOLS = {
    "NIFTY50": "%5ENSEI",   # ^NSEI, URL-encoded
    "SENSEX": "%5EBSESN",   # ^BSESN, URL-encoded
}
FETCH_TIMEOUT_SECONDS = 8


def fetch_yahoo_closes(yahoo_symbol: str, start: dt.date, end: dt.date) -> list[tuple[dt.date, float]]:
    """Raises on any network/parse failure -- callers must catch."""
    import requests

    period1 = int(dt.datetime.combine(start, dt.time.min).timestamp())
    period2 = int(dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
    resp = requests.get(
        url,
        params={"period1": period1, "period2": period2, "interval": "1d"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=FETCH_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]

    out = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        d = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).date()
        out.append((d, float(close)))
    return out


def ensure_cached(db: Session, symbol: str, start: dt.date, end: dt.date) -> bool:
    """Fetches and stores any data missing for [start, end] if the cache
    looks empty/sparse for this range. Returns True if the cache should
    have usable data afterward, False if a fetch was needed but failed
    (caller should show a "benchmark unavailable" message, not crash)."""
    existing_count = (
        db.query(models.BenchmarkPrice)
        .filter(models.BenchmarkPrice.symbol == symbol,
                models.BenchmarkPrice.date >= start,
                models.BenchmarkPrice.date <= end)
        .count()
    )
    expected_weekdays = sum(1 for i in range((end - start).days + 1) if (start + dt.timedelta(days=i)).weekday() < 5)
    if expected_weekdays == 0 or existing_count >= expected_weekdays * 0.9:
        return True  # already well covered, including "no trading days in range yet"

    yahoo_symbol = YAHOO_SYMBOLS.get(symbol)
    if not yahoo_symbol:
        return False
    try:
        fetched = fetch_yahoo_closes(yahoo_symbol, start, end)
    except Exception:
        return existing_count > 0  # partial/stale cache is still better than nothing

    if not fetched:
        return existing_count > 0

    existing_dates = {
        row[0] for row in
        db.query(models.BenchmarkPrice.date)
        .filter(models.BenchmarkPrice.symbol == symbol, models.BenchmarkPrice.date >= start, models.BenchmarkPrice.date <= end)
        .all()
    }
    for d, close in fetched:
        if start <= d <= end and d not in existing_dates:
            db.add(models.BenchmarkPrice(symbol=symbol, date=d, close=close))
            existing_dates.add(d)
    db.commit()
    return True


def get_cached_closes(db: Session, symbol: str, start: dt.date, end: dt.date) -> list[tuple[dt.date, float]]:
    rows = (
        db.query(models.BenchmarkPrice.date, models.BenchmarkPrice.close)
        .filter(models.BenchmarkPrice.symbol == symbol, models.BenchmarkPrice.date >= start, models.BenchmarkPrice.date <= end)
        .order_by(models.BenchmarkPrice.date)
        .all()
    )
    return [(d, c) for d, c in rows]


def normalize_to_100(prices: list[tuple[dt.date, float]]):
    if not prices:
        return [], []
    base = prices[0][1]
    labels = [d.isoformat() for d, _ in prices]
    values = [round(c / base * 100, 2) for _, c in prices]
    return labels, values


def your_capital_weighted_series(daily_capital_rows):
    """Index (start=100) of return on capital actually deployed in trades,
    chain-linked day over day: each day's return is that day's net P&L
    divided by that day's capital committed (sum of entry_value across
    positions closed that day), compounded across days like a fund's NAV.
    This sidesteps needing to track total account capital or deposits/
    withdrawals -- which this app has no record of -- since it's derived
    entirely from trade data already in the journal.
    Caveat: it measures the efficiency of capital you actually put into
    trades, not your whole account's return. If you keep money on the
    sidelines rather than fully deployed, your real account return will be
    lower than this line -- it answers "how good are my trades", not "how
    good is my whole portfolio"."""
    labels = []
    values = []
    index = 100.0
    for d, pnl, capital in daily_capital_rows:
        if capital:
            index *= (1 + pnl / capital)
        labels.append(d.isoformat())
        values.append(round(index, 2))
    return {"labels": labels, "values": values}
