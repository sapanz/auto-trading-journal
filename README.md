# auto-trading-journal

Automatically maintains a trading journal from your Zerodha trades: fetches
trades daily, computes realized P&L/ROI per trade, flags discipline issues
(big losses, revenge trading, scalping), and generates weekly suggestions —
viewed on a small self-hosted website.

## How it fits together

```
GitHub Actions (daily cron, weekdays after market close)
    -> fetcher/fetch_trades.py
       -> logs into Zerodha Kite Connect (TOTP auto-login)
       -> kite.trades() for the day
       -> POST /api/trades  (API-key secured)
              |
              v
website/  (FastAPI + SQLite)
    - Trade      raw trade legs (audit trail)
    - Position   FIFO-matched round trips: entry, exit, P&L, ROI %,
                 holding time, discipline tags
    - Insight    weekly digest of stats + suggestions
    - Dashboard  stats, P&L chart, trade list, journal notes + self-rating
```

## Repository layout

- `website/` — **the active dashboard**: a standalone FastAPI + SQLite app.
  See [docs/WEBSITE_SETUP.md](docs/WEBSITE_SETUP.md) to run it locally,
  try it with sample data, and deploy it.
- `fetcher/` — the Kite Connect fetch/sync script run by the scheduled
  workflow; pushes trades into whichever backend `JOURNAL_URL` points at.
- `.github/workflows/fetch-trades.yml` — the daily cron.
- `odoo_addon/trading_journal/` — an equivalent Odoo module (same FIFO
  matching logic, ported), for running this as part of an existing Odoo
  instance instead. **Currently on hold** — see
  [docs/SETUP.md](docs/SETUP.md).

## Quick start

See [docs/WEBSITE_SETUP.md](docs/WEBSITE_SETUP.md) — run the site locally,
sanity-check it with a sample trade, then wire up the GitHub Actions
secrets (Kite Connect credentials + the website's URL/API key) once it's
deployed somewhere reachable.

## What it computes

- **Realized P&L and ROI %** per closed trade, matched via FIFO across
  buys/sells (handles both long and intraday short round trips).
- **Discipline flags**: Big Loss / Big Win (configurable ROI% threshold),
  Quick Scalp (<2 min hold on MIS), Possible Revenge Trade (bigger size
  re-entered within 10 minutes of a loss on the same symbol).
- **Weekly insight digest**: win rate, net P&L, best/worst symbol, and
  templated suggestions (e.g. low win rate, repeated big losses, MIS vs.
  delivery win-rate gap) — extend the rules in `website/app/insights.py`
  as you learn what signals matter to you.
- Per-trade **journal notes** and a **1–5 self-rating** field for your own
  reflections, right next to the numbers.

## Status / caveats

- The website has **no authentication yet** — see
  [docs/WEBSITE_SETUP.md](docs/WEBSITE_SETUP.md) before exposing it
  publicly.
- The Zerodha login automation is unofficial (drives Zerodha's own web
  login, not a supported headless API) — see the caveats in
  [docs/SETUP.md](docs/SETUP.md#notes-limits-and-fallback).
