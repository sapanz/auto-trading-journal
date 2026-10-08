"""Automated sector lookup for open-position symbols, for the sector
allocation pie chart. No hand-maintained symbol-to-sector map: each
tradingsymbol's sector is fetched from Yahoo Finance's assetProfile
data (the same unofficial, no-API-key source benchmark.py already uses
for Nifty 50 prices) and cached in the symbol_sectors table, since a
company's sector classification doesn't change day to day -- it's a
one-time lookup per symbol, not a per-request fetch.

Unlike the `chart` endpoint benchmark.py calls, Yahoo's quoteSummary
endpoint (where sector/industry data lives) has required a session
cookie + crumb since mid-2024, so fetch_sector_from_yahoo() does that
handshake first. Only plain NSE equity symbols resolve (Yahoo has no
listing for F&O contract symbols like "RELIANCE24OCTFUT") -- anything
that fails to resolve is cached as "Uncategorized" so a single bad
lookup doesn't retry on every page load; refresh_symbols() forces a
re-check (wired to a "Refresh sector data" button on the Trades page).
"""
import datetime as dt

from sqlalchemy.orm import Session

from . import models

FETCH_TIMEOUT_SECONDS = 8
UNCATEGORIZED = "Uncategorized"


def fetch_sector_from_yahoo(tradingsymbol: str) -> str | None:
    """Returns the sector name for an NSE-listed equity, or None if
    Yahoo has no assetProfile sector for it. Raises on any network/auth/
    parse failure -- callers must catch."""
    import requests

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    })
    session.get("https://fc.yahoo.com", timeout=FETCH_TIMEOUT_SECONDS)  # sets the cookie getcrumb needs
    crumb_resp = session.get("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=FETCH_TIMEOUT_SECONDS)
    crumb_resp.raise_for_status()
    crumb = crumb_resp.text.strip()

    resp = session.get(
        f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{tradingsymbol}.NS",
        params={"modules": "assetProfile", "crumb": crumb},
        timeout=FETCH_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    result = resp.json()["quoteSummary"]["result"]
    if not result:
        return None
    return result[0].get("assetProfile", {}).get("sector") or None


def get_sector(db: Session, tradingsymbol: str) -> str:
    """Cached sector lookup: fetches on first sight of a symbol, then
    reuses the cached value on every later call. A failed/empty lookup
    is cached as "Uncategorized" too, so it doesn't retry every page
    load -- call refresh_symbols() to force a re-check."""
    row = db.get(models.SymbolSector, tradingsymbol)
    if row:
        return row.sector

    try:
        sector = fetch_sector_from_yahoo(tradingsymbol) or UNCATEGORIZED
    except Exception:
        sector = UNCATEGORIZED

    db.add(models.SymbolSector(symbol=tradingsymbol, sector=sector, fetched_at=dt.datetime.utcnow()))
    db.commit()
    return sector


def refresh_symbols(db: Session, tradingsymbols: list[str]) -> None:
    """Drops the cached sector for these symbols so the next lookup
    re-fetches instead of reusing a stale/failed result."""
    symbols = set(tradingsymbols)
    if not symbols:
        return
    db.query(models.SymbolSector).filter(models.SymbolSector.symbol.in_(symbols)).delete(synchronize_session=False)
    db.commit()


def portfolio_breakdown(db: Session, open_positions):
    """Investment allocation across sectors for currently OPEN positions.
    Groups by invested value (entry_value -- capital currently deployed),
    not P&L: this is about where your open capital sits, not how those
    positions are performing. Returns (sector_rows, total_invested), rows
    sorted by invested value descending with their stocks also sorted
    descending."""
    total_invested = sum(p.entry_value for p in open_positions)
    agg: dict[str, dict] = {}
    for p in open_positions:
        sector = get_sector(db, p.tradingsymbol)
        d = agg.setdefault(sector, {"invested": 0.0, "stocks": {}})
        d["invested"] += p.entry_value
        d["stocks"][p.tradingsymbol] = d["stocks"].get(p.tradingsymbol, 0.0) + p.entry_value

    rows = []
    for sector, d in agg.items():
        stocks = [
            {
                "symbol": sym,
                "invested": round(val, 2),
                "percent_of_sector": round(val / d["invested"] * 100.0, 1) if d["invested"] else 0.0,
            }
            for sym, val in d["stocks"].items()
        ]
        stocks.sort(key=lambda s: s["invested"], reverse=True)
        rows.append({
            "sector": sector,
            "invested": round(d["invested"], 2),
            "percent": round(d["invested"] / total_invested * 100.0, 1) if total_invested else 0.0,
            "stocks": stocks,
        })
    rows.sort(key=lambda r: r["invested"], reverse=True)
    return rows, round(total_invested, 2)
