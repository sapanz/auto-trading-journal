# Website Setup Guide

This is the standalone trading journal website: a self-contained FastAPI +
SQLite app under `website/`. It's the active path for now — the Odoo
module (`odoo_addon/`) is on hold and can be revisited later; the fetcher
talks to whichever backend is configured via `JOURNAL_URL`.

## 1. Run it locally

```bash
cd website
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # then edit .env, at minimum set JOURNAL_API_KEY
export $(grep -v '^#' .env | xargs)   # or use a tool like direnv/python-dotenv

uvicorn app.main:app --reload
```

Visit http://127.0.0.1:8000 — you'll see an empty dashboard (no trades
synced yet). The SQLite database file is created automatically at
`website/journal.db` (configurable via `JOURNAL_DB_PATH`).

## 2. Try it with sample data

Before wiring up real Zerodha credentials, you can sanity-check the whole
pipeline with a fake trade:

```bash
curl -X POST http://127.0.0.1:8000/api/trades \
  -H "X-Api-Key: <your JOURNAL_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "trades": [
      {"trade_id": "T1", "order_id": "O1", "tradingsymbol": "RELIANCE",
       "exchange": "NSE", "product": "MIS", "transaction_type": "BUY",
       "quantity": 10, "average_price": 2500.0,
       "exchange_timestamp": "2026-01-01 09:20:00", "trade_date": "2026-01-01"},
      {"trade_id": "T2", "order_id": "O2", "tradingsymbol": "RELIANCE",
       "exchange": "NSE", "product": "MIS", "transaction_type": "SELL",
       "quantity": 10, "average_price": 2530.0,
       "exchange_timestamp": "2026-01-01 10:05:00", "trade_date": "2026-01-01"}
    ]
  }'
```

Refresh the dashboard — you should see a closed RELIANCE position with a
₹300 P&L. Open **Trading Journal → Trades** for the matched position, or
its detail page to add a journal note and self-rating. Visit **Insights**
and click "Generate insight now" to see the weekly digest logic run.

## 3. Configure the fetcher to push here

In `fetcher/`, the required environment variables (see
`.github/workflows/fetch-trades.yml`) now point at this website instead of
Odoo:

| Variable | Value |
|---|---|
| `JOURNAL_URL` | Base URL of this website, e.g. `https://journal.yourdomain.com` or `http://<host>:8000` |
| `JOURNAL_API_KEY` | Same value as the website's `JOURNAL_API_KEY` |

Plus the Kite Connect variables (`KITE_API_KEY`, `KITE_API_SECRET`,
`KITE_USER_ID`, `KITE_PASSWORD`, `KITE_TOTP_SECRET`) — see the Kite Connect
setup section in `docs/SETUP.md` for how to get these; that part is
unchanged regardless of which backend the fetcher targets.

Set these as GitHub Actions secrets once you've deployed the website
somewhere reachable from the internet (see below), then trigger the
workflow manually to test end to end.

## 4. Deploying

This is a single Python process with a local SQLite file — no separate
database server needed. Pick whichever of these fits what you already run:

- **Docker**: `docker build -t trading-journal website/` then
  `docker run -d -p 8000:8000 -e JOURNAL_API_KEY=... -v journal-data:/data trading-journal`
  (the volume persists `journal.db` across restarts).
- **systemd + uvicorn/gunicorn**: run
  `uvicorn app.main:app --host 0.0.0.0 --port 8000` (or gunicorn with
  uvicorn workers) as a systemd service, with `JOURNAL_API_KEY` and
  `JOURNAL_DB_PATH` set in the unit's `Environment=` lines, behind a
  reverse proxy (nginx/Caddy) for TLS.
- Any other host that runs a long-lived Python process and can reach the
  internet (for the GitHub Actions fetcher to POST to it) works too.

Once deployed, put its public URL in `JOURNAL_URL` and the app's
`JOURNAL_API_KEY` in the `JOURNAL_API_KEY` GitHub secret.

## Notes

- **No authentication yet.** The dashboard pages (`/`, `/positions`,
  `/trades`, `/insights`, and the notes/rating form) are unauthenticated —
  anyone who can reach the URL can view and edit your journal. Only the
  `/api/trades` ingestion endpoint is protected (by `JOURNAL_API_KEY`).
  Don't expose this publicly without adding auth first (a reverse-proxy
  basic-auth in front of it is the fastest stopgap; a real login page is a
  follow-up).
- Weekly insight generation is currently manual (the "Generate insight
  now" button on `/insights`). If you want it automatic, either add it to
  the same GitHub Actions cron (a `curl -X POST $JOURNAL_URL/insights/generate`
  step) or run it as a separate scheduled job on whatever host you deploy
  to.
- The FIFO matching logic here is a straight Python/SQLAlchemy port of the
  same algorithm in the Odoo module (`odoo_addon/trading_journal`), so
  moving to Odoo later — or running both side by side — doesn't require
  re-deriving the P&L logic.
