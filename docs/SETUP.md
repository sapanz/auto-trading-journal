# Setup Guide

This project has two parts:

1. **`odoo_addon/trading_journal`** — an Odoo module that stores trades,
   auto-matches them into round-trip positions, computes P&L/ROI, flags
   discipline issues, and generates weekly insights. This is your
   "website" — it runs inside your existing `journal.odoo.com` instance
   and is viewed through the normal Odoo web client.
2. **`fetcher/`** — a script, run daily by GitHub Actions, that logs into
   Zerodha Kite Connect, fetches the day's trades, and pushes them into
   Odoo via a small API endpoint the module exposes.

## 1. Install the Odoo module

1. Copy (or symlink) `odoo_addon/trading_journal` into your Odoo instance's
   custom addons path on `journal.odoo.com`.
2. Restart Odoo, then in the UI: **Settings → General Settings → Activate
   developer mode**, then **Apps → Update Apps List**.
3. Search for "Zerodha Trading Journal" and install it.
4. A new **Trading Journal** top-level menu appears with **Trades**,
   **Insights**, and **Raw Trades**.

If `journal.odoo.com` is an Odoo.sh or Odoo hosted (SaaS) instance, custom
modules must be pushed through that platform's normal deployment process
(e.g. an Odoo.sh git branch) rather than copied by hand — use whichever
deploy path you already use for custom modules there.

## 2. Configure the API key

The fetcher authenticates to Odoo with a shared secret, not an Odoo user
login.

1. Enable developer mode, then go to **Settings → Technical → System
   Parameters**.
2. Create a parameter:
   - **Key**: `trading_journal.api_key`
   - **Value**: a long random string, e.g. generate one with
     `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
3. (Optional) Create `trading_journal.big_loss_percent` (default `2.0`) to
   tune what ROI% counts as a "Big Loss" flag.

Keep this value secret — anyone with it can write trades into your journal
via the API.

## 3. Get Zerodha Kite Connect credentials

Kite Connect is a separate paid API subscription from your regular Zerodha
trading account (register at https://developers.kite.trade, ~₹500/month).

1. Create a Kite Connect app in the developer console. The **Redirect URL**
   field must be set to something (it doesn't need to be reachable — the
   fetcher intercepts the redirect before it's followed), e.g.
   `https://kite.zerodha.com`.
2. Note the **API key** and **API secret** it gives you.
3. Enable **TOTP-based two-factor authentication** on your Zerodha login if
   you haven't already, and save the TOTP secret (the same base32 string
   you'd scan into Google Authenticator/Authy — shown once when you enable
   2FA, or re-orderable from Zerodha's security settings).

## 4. Configure GitHub Actions secrets

In this repository: **Settings → Secrets and variables → Actions**, add:

| Secret | Value |
|---|---|
| `KITE_API_KEY` | Kite Connect API key |
| `KITE_API_SECRET` | Kite Connect API secret |
| `KITE_USER_ID` | Your Zerodha client ID (e.g. `AB1234`) |
| `KITE_PASSWORD` | Your Zerodha login password |
| `KITE_TOTP_SECRET` | Your Zerodha TOTP base32 secret |
| `ODOO_URL` | e.g. `https://journal.odoo.com` |
| `ODOO_API_KEY` | The `trading_journal.api_key` value from step 2 |

The workflow at `.github/workflows/fetch-trades.yml` runs weekdays at
15:35 IST (10:05 UTC), shortly after market close, and can also be
triggered manually from the **Actions** tab (**Run workflow**) to backfill
or test.

## 5. Test it

1. Trigger the workflow manually once (**Actions → Fetch Zerodha Trades →
   Run workflow**) and check the run logs.
2. In Odoo, open **Trading Journal → Raw Trades** to confirm trades came
   in, and **Trading Journal → Trades** to see them matched into
   positions with P&L/ROI.
3. Alternatively, test the Odoo endpoint directly:
   ```bash
   curl -H "X-Api-Key: $ODOO_API_KEY" https://journal.odoo.com/api/trading-journal/ping
   # {"status": "ok"}
   ```

## Notes, limits and fallback

- **The Zerodha login automation is unofficial.** It drives the same web
  login Zerodha's own site uses; there's no supported headless-login API
  in Kite Connect. If Zerodha changes their login page, adds a captcha, or
  starts blocking automated logins, `fetch_trades.py` will start failing
  with a `KiteLoginError`. If that happens, the more robust fallback is a
  small "Connect Zerodha" button/page in Odoo where you complete the login
  redirect once a day by hand (Kite Connect's supported flow) — ask to
  have that added if the automated login becomes unreliable.
- **Storing your Zerodha password + TOTP secret as GitHub secrets is a
  real risk to weigh.** Anyone with admin/write access to this repo's
  settings can read them. Keep this repo private, limit collaborators, and
  consider a dedicated Zerodha login with position-only permissions if
  your broker supports sub-accounts.
- The fetcher currently pulls **all of today's trades** on each run
  (`kite.trades()` returns the current trading day only, per Kite Connect's
  API). Positions are recomputed via FIFO matching from all historical raw
  trades already in Odoo, so re-running the workflow multiple times a day
  is safe — duplicate trade IDs are skipped.
- Weekly insight generation runs automatically inside Odoo (a built-in
  scheduled action, "Trading Journal: Generate Weekly Insight" under
  **Settings → Technical → Automation → Scheduled Actions**) — no separate
  cron needed for that part.
