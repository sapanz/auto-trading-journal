# auto-trading-journal

Automatically maintains a trading journal from your Zerodha trades: fetches
trades daily, computes realized P&L/ROI per trade, flags discipline issues
(big losses, revenge trading, scalping), and generates weekly suggestions —
viewed as a dashboard inside your Odoo instance.

## How it fits together

```
GitHub Actions (daily cron, weekdays after market close)
    -> fetcher/fetch_trades.py
       -> logs into Zerodha Kite Connect (TOTP auto-login)
       -> kite.trades() for the day
       -> POST /api/trading-journal/trades  (API-key secured)
              |
              v
Odoo module: odoo_addon/trading_journal   (your journal.odoo.com)
    - trading.journal.trade      raw trade legs (audit trail)
    - trading.journal.position   FIFO-matched round trips: entry, exit,
                                  P&L, ROI %, holding time, discipline tags
    - trading.journal.insight    weekly digest of stats + suggestions
    - Trading Journal menu       your dashboard (list/graph/pivot views,
                                  journal notes + self-rating per trade)
```

## Repository layout

- `odoo_addon/trading_journal/` — the Odoo module. See
  [docs/SETUP.md](docs/SETUP.md) for installation.
- `fetcher/` — the Kite Connect fetch/sync script run by the scheduled
  workflow.
- `.github/workflows/fetch-trades.yml` — the daily cron.
- `docs/SETUP.md` — full setup instructions (Odoo install, API key,
  Kite Connect app, GitHub secrets, testing, and caveats).

## Quick start

See [docs/SETUP.md](docs/SETUP.md) — it walks through installing the Odoo
module, configuring the shared API key, registering a Kite Connect app,
and wiring up GitHub Actions secrets.

## What it computes

- **Realized P&L and ROI %** per closed trade, matched via FIFO across
  buys/sells (handles both long and intraday short round trips).
- **Discipline flags**: Big Loss / Big Win (configurable ROI% threshold),
  Quick Scalp (<2 min hold on MIS), Possible Revenge Trade (bigger size
  re-entered within 10 minutes of a loss on the same symbol).
- **Weekly insight digest**: win rate, net P&L, best/worst symbol, and
  templated suggestions (e.g. low win rate, repeated big losses, MIS vs.
  delivery win-rate gap) — extend the rules in
  `trading_journal_insight.py` as you learn what signals matter to you.
- Per-trade **journal notes** and a **1–5 self-rating** field for your own
  reflections, right next to the numbers.
