#!/usr/bin/env python3
"""Fetch today's trades from Zerodha Kite Connect and push them into the
Odoo Trading Journal module via its ingestion API.

Intended to run on a schedule (see .github/workflows/fetch-trades.yml).
Required environment variables are documented in docs/SETUP.md.
"""
import datetime
import os
import sys

import requests
from kiteconnect import KiteConnect

from kite_auth import KiteTOTPLogin, KiteLoginError

REQUIRED_ENV_VARS = [
    'KITE_API_KEY', 'KITE_API_SECRET', 'KITE_USER_ID', 'KITE_PASSWORD', 'KITE_TOTP_SECRET',
    'ODOO_URL', 'ODOO_API_KEY',
]


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
    odoo_url = config['ODOO_URL'].rstrip('/')

    resp = requests.post(
        '%s/api/trading-journal/trades' % odoo_url,
        json=payload,
        headers={'X-Api-Key': config['ODOO_API_KEY']},
        timeout=60,
    )
    if resp.status_code != 200:
        print('Odoo ingestion failed (%d): %s' % (resp.status_code, resp.text), file=sys.stderr)
        sys.exit(1)

    print('Odoo response:', resp.json())


if __name__ == '__main__':
    main()
