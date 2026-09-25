# Website Setup Guide

This is the standalone trading journal website: a self-contained FastAPI
app under `website/`, using SQLite for local development and Postgres
(e.g. a free Neon database) for any real deployment. It's the active path
for now — the Odoo module (`odoo_addon/`) is on hold and can be revisited
later; the fetcher talks to whichever backend is configured via
`JOURNAL_URL`.

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
| `VERCEL_PROTECTION_BYPASS_SECRET` | Only if deployed on Vercel with "Protection Bypass for Automation" enabled (see the Vercel deploy section below) — omit entirely for other hosts. |

Plus the Kite Connect variables (`KITE_API_KEY`, `KITE_API_SECRET`,
`KITE_USER_ID`, `KITE_PASSWORD`, `KITE_TOTP_SECRET`) — see the Kite Connect
setup section in `docs/SETUP.md` for how to get these; that part is
unchanged regardless of which backend the fetcher targets.

Set these as GitHub Actions secrets once you've deployed the website
somewhere reachable from the internet (see below), then trigger the
workflow manually to test end to end.

## 3b. Backfilling historical trades

`kite.trades()` (what the daily cron uses) only returns the **current
trading day's** trades — there's no Kite Connect API for pulling past
trades. To backfill history, use `fetcher/import_tradebook.py` against a
Tradebook CSV export instead:

1. In Console (console.zerodha.com), go to **Reports → Tradebook**, pick a
   financial year, and download the CSV. Repeat per year for however far
   back you want.
2. With the same `JOURNAL_URL` / `JOURNAL_API_KEY` /
   `VERCEL_PROTECTION_BYPASS_SECRET` environment variables set locally as
   the fetcher uses:
   ```bash
   cd fetcher
   pip install -r requirements.txt
   python import_tradebook.py path/to/tradebook.csv
   ```
   Re-running on the same file is safe — trades already present (by
   `trade_id`) are skipped, not duplicated.

**Known limitation**: the Tradebook export doesn't include a product
(CNC/MIS/NRML) column, unlike the live API. The importer infers it per
symbol per day — if that day's total buy quantity exactly matches total
sell quantity (a net-zero day), it's tagged intraday (MIS); otherwise
delivery (CNC). This gets ordinary days right, but can misclassify a rare
day where you both day-traded *and* separately adjusted a holding in the
same symbol. See the docstring in `import_tradebook.py` for details.

## 3c. Realized P&L (charges included)

Neither Kite Connect's `trades()` API nor the Tradebook CSV export include
brokerage, STT, exchange charges, stamp duty, or GST — those only appear on
contract notes / Console's Tax P&L report, which nothing here imports. So
`website/app/charges.py` estimates them per closed position from Zerodha's
published retail equity charge structure (brokerage, STT, exchange
transaction charges, SEBI charges, stamp duty, GST), given the round trip's
product (CNC/MIS/NRML), direction, and buy/sell value.

Every closed position now has both:
- **Gross P&L** — pure price movement (what `pnl` always meant before).
- **Charges** — the estimated total above.
- **Net P&L** — `pnl - charges`, the realized figure; this is what the
  dashboard total, the win/loss coloring, ROI %, and the discipline tags
  (Big Loss/Big Win/revenge-trade) are now based on.

**Known limitations** (see the docstring in `charges.py` for the exact
rates used): this models plain equity delivery and intraday/carry-forward
only, not F&O's different STT/brokerage rules; it doesn't include the flat
per-scrip DP charge on delivery sells (~Rs 15-20/scrip/day, independent of
value, which would need day-level grouping to attribute); and the rates
are current as of when this was written but Zerodha/SEBI/GST can change
them. Override the per-unit rates via `JOURNAL_CHARGES_*` environment
variables if you need to tune them (see `charges.py`).

Upgrading an existing deployment: the app auto-adds the new `charges` /
`net_pnl` / `net_pnl_percent` columns to the `positions` table on startup
(see `run_migrations()` in `database.py`) — no manual DB change needed. But
existing positions won't have charges backfilled automatically, since
re-running the CSV importer skips trades it's already seen and only
recomputes positions touched by genuinely new trades. To backfill charges
onto positions built before this change, call the new recompute endpoint
once after deploying:

```bash
curl -X POST "$JOURNAL_URL/api/positions/recompute" \
  -H "X-Api-Key: <your JOURNAL_API_KEY>"
```

This rebuilds every position from its existing trade legs (same FIFO logic,
now with charges) without touching the underlying trades.

## 4. Deploying

### Free, no-card option: Vercel (compute) + Neon (Postgres)

This is the path actually used for this project (Render, below, now asks
for a card-on-file even for its free plan — Vercel's free Hobby tier does
not).

The app runs on Vercel as a Python serverless function via **root-level**
`api/index.py` and `vercel.json` — not under `website/`. This is
deliberate: Vercel builds from the actual repository root unless "Root
Directory" is overridden in project settings, and that override isn't
available on every plan/team. `api/index.py` just re-exports the same
FastAPI `app` from `website/app/main.py` (adding `website/` to
`sys.path`) — no code fork; the identical app runs locally via uvicorn and
on Vercel. The root `requirements.txt` mirrors `website/requirements.txt`
(minus `uvicorn`, which Vercel's own runtime replaces) since Vercel's
Python builder looks for `requirements.txt` next to the function.

1. **Database**: create a free account at https://neon.tech, create a
   project/database, and copy its connection string (looks like
   `postgresql://user:password@host/dbname?sslmode=require`) — use the
   **pooled** connection string if Neon offers both (works better with
   serverless's many short-lived connections).
2. **Web app**: create a free account at https://vercel.com (GitHub OAuth,
   no card), then **Add New → Project → Import** this GitHub repo.
   - Leave **Root Directory** as the repo root (default) — do not set it
     to `website`.
   - Framework preset: Vercel should auto-detect Python via the root
     `vercel.json`; if it asks, choose "Other".
   - Under **Environment Variables**, add:
     - `DATABASE_URL` — the Neon connection string from step 1
     - `JOURNAL_API_KEY` — a long random string (same value goes in the
       `JOURNAL_API_KEY` GitHub secret)
     - `JOURNAL_BIG_LOSS_PERCENT` — optional, defaults to `2.0`
   - Deploy.
3. Vercel gives you a public URL like
   `https://<project>.vercel.app` — that's your `JOURNAL_URL`.

Since the PR branch may not be `main` yet, either point Vercel's
Production Branch at the feature branch temporarily, or use the automatic
Preview Deployment URL Vercel creates for that branch's pushes.

The app auto-detects `DATABASE_URL` and uses Postgres when it's set,
falling back to local SQLite (via `JOURNAL_DB_PATH`) otherwise — see
`website/app/database.py`. Serverless functions have no persistent local
disk, so `DATABASE_URL` (Postgres) is required here, not optional.

**Deployment Protection**: on Team/Pro workspaces, Vercel often enables
"Vercel Authentication" by default, which puts an SSO wall in front of
every deployment (including preview URLs) — any unauthenticated request,
including the GitHub Actions cron's `POST /api/trades`, gets a 401
`{"error":{"code":"401","message":"Protected deployment"}}` instead of
reaching the app. Check **Settings → Deployment Protection**:

- If it's on and you want to keep it (recommended, since the app itself
  has no login yet — see the note below): enable **"Protection Bypass for
  Automation"**, which generates a secret. Set it as the
  `VERCEL_PROTECTION_BYPASS_SECRET` GitHub Actions secret — the fetcher
  sends it as the `x-vercel-protection-bypass` header automatically when
  that secret is present (see `fetcher/fetch_trades.py`). Any manual
  `curl` testing needs the same header.
- If you'd rather have no wall at all, turn "Vercel Authentication" off
  entirely — the dashboard and API become fully public to anyone with the
  URL.

### Render (compute) + Neon (Postgres) — requires a card

Render's free web service tier has an **ephemeral filesystem** — anything
written to disk (a local SQLite file) is wiped on every restart or
redeploy. To get a genuinely persistent, genuinely free deployment, pair
it with a free hosted Postgres database instead of local SQLite:

1. **Database**: create a free account at https://neon.tech, create a
   project/database, and copy its connection string (looks like
   `postgresql://user:password@host/dbname?sslmode=require`).
2. **Web service**: create a free account at https://render.com — note
   Render now requires a card on file to create any web service, even on
   the free plan (a verification hold, not a recurring charge; use Vercel
   above if you'd rather avoid that). Either:
   - Use the included `render.yaml` blueprint (repo root) via Render's
     "New → Blueprint" flow pointed at this GitHub repo, or
   - Create a web service manually: connect this repo, runtime **Docker**,
     Dockerfile path `website/Dockerfile`, docker context `website`, plan
     **Free**.
3. Set these environment variables on the Render service:
   - `DATABASE_URL` — the Neon connection string from step 1
   - `JOURNAL_API_KEY` — a long random string (same value goes in the
     `JOURNAL_API_KEY` GitHub secret)
   - `JOURNAL_BIG_LOSS_PERCENT` — optional, defaults to `2.0`
4. Deploy. Render gives you a public URL like
   `https://trading-journal-xxxx.onrender.com` — that's your `JOURNAL_URL`.

The app auto-detects `DATABASE_URL` and uses Postgres when it's set,
falling back to local SQLite (via `JOURNAL_DB_PATH`) otherwise — see
`website/app/database.py`. No other code changes needed to move between
them.

Note: Render's free web services also spin down after periods of
inactivity and take a few seconds to wake back up on the next request —
fine for a personal journal, just don't expect instant load on a cold
visit.

### Other options

- **Docker, self-hosted**: `docker build -t trading-journal website/` then
  `docker run -d -p 8000:8000 -e JOURNAL_API_KEY=... -e DATABASE_URL=... trading-journal`
  (or omit `DATABASE_URL` and mount a volume at `/data` to persist
  `journal.db` locally instead).
- **systemd + uvicorn/gunicorn**: run
  `uvicorn app.main:app --host 0.0.0.0 --port 8000` (or gunicorn with
  uvicorn workers) as a systemd service, with `JOURNAL_API_KEY` and either
  `DATABASE_URL` or `JOURNAL_DB_PATH` set in the unit's `Environment=`
  lines, behind a reverse proxy (nginx/Caddy) for TLS.
- Any other host that runs a long-lived Python process and can reach the
  internet (for the GitHub Actions fetcher to POST to it) works too.

Once deployed, put its public URL in `JOURNAL_URL` and the app's
`JOURNAL_API_KEY` in the `JOURNAL_API_KEY` GitHub secret.

## Notes

- **PIN-protected.** Every page (`/`, `/analytics`, `/tax-report`,
  `/positions`, `/trades`, `/insights`, and the notes/tags forms) requires
  entering a PIN once per browser (a 30-day signed session cookie, via
  Starlette's `SessionMiddleware`) — set the `JOURNAL_ACCESS_PIN`
  environment variable (e.g. a 4+ digit PIN) to enable it; without it set,
  `/login` returns a 500 rather than silently leaving the site open. The
  machine-to-machine endpoints the fetcher cron uses
  (`POST`/`DELETE /api/trades`, `POST /api/positions/recompute`,
  `GET /api/ping`) are unaffected — they keep using `JOURNAL_API_KEY`
  instead, since the cron has no browser session. Optionally set
  `JOURNAL_SESSION_SECRET` to a separate random string for signing the
  session cookie; it falls back to reusing `JOURNAL_API_KEY` if unset.
  A short numeric PIN is convenient, not hardened — it has no login-attempt
  rate limiting, so treat it as "keeps casual visitors out" rather than
  a defense against a determined, scripted attacker.
- Weekly insight generation is currently manual (the "Generate insight
  now" button on `/insights`). If you want it automatic, either add it to
  the same GitHub Actions cron (a `curl -X POST $JOURNAL_URL/insights/generate`
  step) or run it as a separate scheduled job on whatever host you deploy
  to.
- The FIFO matching logic here is a straight Python/SQLAlchemy port of the
  same algorithm in the Odoo module (`odoo_addon/trading_journal`), so
  moving to Odoo later — or running both side by side — doesn't require
  re-deriving the P&L logic.
- **Orders are clubbed by order_id.** Zerodha's tradebook records each
  partial fill of a limit/market order as its own row with its own
  `trade_id` — a single order can genuinely execute in several pieces at
  slightly different prices. `matching.group_by_order()` collapses same-
  order fills into one logical trade (summed quantity, quantity-weighted
  average price) before both FIFO position matching and the `/trades`
  display, so one order doesn't fragment into several tiny positions or
  clutter the raw trades list. Genuinely separate orders (different
  `order_id`, even same symbol/day) are always kept separate. The
  individual fills aren't lost — expand the "N fills" badge on `/trades`
  to see them.
