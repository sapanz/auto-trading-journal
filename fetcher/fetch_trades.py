#!/usr/bin/env python3
"""Fetch today's trades from Zerodha Kite Connect and push them into the
Trading Journal website via its ingestion API.

Intended to run on a schedule (see .github/workflows/fetch-trades.yml).
Required environment variables are documented in docs/WEBSITE_SETUP.md.
"""
import datetime
import os
import sys

import requests
from kiteconnect import KiteConnect

from kite_auth import KiteTOTPLogin, KiteLoginError

REQUIRED_ENV_VARS = [
    'KITE_API_KEY', 'KITE_API_SECRET', 'KITE_USER_ID', 'KITE_PASSWORD', 'KITE_TOTP_SECRET',
    'JOURNAL_URL', 'JOURNAL_API_KEY',
]

# Optional: only needed if JOURNAL_URL points at a Vercel deployment with
# "Protection Bypass for Automation" configured (Settings > Deployment
# Protection). Lets this script through Vercel's own SSO wall without
# weakening it for regular browser visitors. Not used by other hosts.
VERCEL_PROTECTION_BYPASS_SECRET = os.environ.get('VERCEL_PROTECTION_BYPASS_SECRET')


def get_config():
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        print('Missing required environment variable(s): %s' % ', '.join(missing), file=sys.stderr)
        sys.exit(1)
    return {name: os.environ[name] for name in REQUIRED_ENV_VARS}


def to_str(value):
    if value is None:
        return None
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    return str(value)


def to_date_str(value):
    if value is None:
        return None
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.strftime('%Y-%m-%d')
    return str(value)[:10]


def build_payload(raw_trades):
    trades = []
    for t in raw_trades:
        trades.append({
            'trade_id': t['trade_id'],
            'order_id': t['order_id'],
            'exchange_order_id': t.get('exchange_order_id'),
            'tradingsymbol': t['tradingsymbol'],
            'exchange': t['exchange'],
            'instrument_token': t.get('instrument_token'),
            'product': t['product'],
            'transaction_type': t['transaction_type'],
            'quantity': t['quantity'],
            'average_price': t['average_price'],
            'order_timestamp': to_str(t.get('order_timestamp')),
            'exchange_timestamp': to_str(t.get('exchange_timestamp')),
            'trade_date': to_date_str(t.get('trade_date') or t.get('exchange_timestamp')),
        })
    return trades


def main():
    config = get_config()

    print('Logging into Kite Connect as %s ...' % config['KITE_USER_ID'])
    try:
        login = KiteTOTPLogin(
            api_key=config['KITE_API_KEY'],
            api_secret=config['KITE_API_SECRET'],
            user_id=config['KITE_USER_ID'],
            password=config['KITE_PASSWORD'],
            totp_secret=config['KITE_TOTP_SECRET'],
        )
        access_token = login.get_access_token()
    except KiteLoginError as exc:
        print('Kite login failed: %s' % exc, file=sys.stderr)
        sys.exit(1)

    kite = KiteConnect(api_key=config['KITE_API_KEY'])
    kite.set_access_token(access_token)

    raw_trades = kite.trades()
    print('Fetched %d trade(s) from Kite Connect.' % len(raw_trades))

    if not raw_trades:
        print('Nothing to sync.')
        return

    payload = {'trades': build_payload(raw_trades)}
    journal_url = config['JOURNAL_URL'].rstrip('/')

    headers = {'X-Api-Key': config['JOURNAL_API_KEY']}
    if VERCEL_PROTECTION_BYPASS_SECRET:
        headers['x-vercel-protection-bypass'] = VERCEL_PROTECTION_BYPASS_SECRET

    resp = requests.post(
        '%s/api/trades' % journal_url,
        json=payload,
        headers=headers,
        timeout=60,
    )
    if resp.status_code != 200:
        print('Journal ingestion failed (%d): %s' % (resp.status_code, resp.text), file=sys.stderr)
        sys.exit(1)

    print('Journal response:', resp.json())


if __name__ == '__main__':
    main()
