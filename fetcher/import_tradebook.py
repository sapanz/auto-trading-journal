#!/usr/bin/env python3
"""Import a Zerodha Tradebook CSV export (Console -> Reports -> Tradebook)
into the trading journal, for backfilling historical trades that Kite
Connect's kite.trades() API can't provide (it only returns the current
trading day).

Usage:
    python import_tradebook.py path/to/tradebook.csv

Required environment variables (same as fetch_trades.py):
    JOURNAL_URL, JOURNAL_API_KEY, VERCEL_PROTECTION_BYPASS_SECRET (optional)

CSV format expected (Zerodha's standard Tradebook export):
    symbol,isin,trade_date,exchange,segment,series,trade_type,auction,
    quantity,price,trade_id,order_id,order_execution_time

Important limitation: the Tradebook export does NOT include a product
(CNC/MIS/NRML) column, unlike Kite Connect's live trades() API. Product
type matters here because positions are FIFO-matched separately per
(symbol, product) -- mixing same-day intraday round trips with unrelated
delivery holdings in one bucket would misattribute holding times and
discipline tags.

To work around this, trades are grouped by (symbol, trade_date) and
classified as a whole day:
  - If total buy quantity == total sell quantity for that symbol that day
    (a net-zero day -- nothing carried into/out of holdings), it's tagged
    'MIS' (intraday).
  - Otherwise (net position change), it's tagged 'CNC' (delivery).

This gets the common cases right (a pure day-trade, or a pure delivery
buy/sell) but can misclassify a day where you both day-traded AND
separately added to/reduced a holding in the same symbol on the same day
-- a rare pattern this script doesn't attempt to split out.
"""
import csv
import os
import sys
from collections import defaultdict

import requests

REQUIRED_ENV_VARS = ['JOURNAL_URL', 'JOURNAL_API_KEY']
BATCH_SIZE = 300


def get_config():
    values = {name: (os.environ.get(name) or '').strip() for name in REQUIRED_ENV_VARS}
    missing = [name for name, value in values.items() if not value]
    if missing:
        print('Missing required environment variable(s): %s' % ', '.join(missing), file=sys.stderr)
        sys.exit(1)
    values['VERCEL_PROTECTION_BYPASS_SECRET'] = (os.environ.get('VERCEL_PROTECTION_BYPASS_SECRET') or '').strip()
    return values


def read_tradebook_rows(csv_path):
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = [row for row in reader if row.get('symbol')]
    return rows


def classify_products(rows):
    """Assign each row a 'product' (MIS/CNC) using the same-day net-zero
    heuristic described in the module docstring. Returns a new list of
    rows (dicts) with a 'product' key added."""
    groups = defaultdict(list)
    for row in rows:
        key = (row['symbol'], row['trade_date'])
        groups[key].append(row)

    tagged = []
    for (symbol, trade_date), group_rows in groups.items():
        buy_qty = sum(float(r['quantity']) for r in group_rows if r['trade_type'].lower() == 'buy')
        sell_qty = sum(float(r['quantity']) for r in group_rows if r['trade_type'].lower() == 'sell')
        product = 'MIS' if (buy_qty > 0 and sell_qty > 0 and abs(buy_qty - sell_qty) < 1e-6) else 'CNC'
        for row in group_rows:
            row = dict(row)
            row['product'] = product
            tagged.append(row)
    return tagged


def build_payload(rows):
    trades = []
    for r in rows:
        trades.append({
            'trade_id': r['trade_id'],
            'order_id': r['order_id'],
            'exchange_order_id': None,
            'tradingsymbol': r['symbol'],
            'exchange': r['exchange'],
            'instrument_token': None,
            'product': r['product'],
            'transaction_type': r['trade_type'].upper(),
            'quantity': float(r['quantity']),
            'average_price': float(r['price']),
            'order_timestamp': None,
            'exchange_timestamp': r['order_execution_time'],
            'trade_date': r['trade_date'],
        })
    return trades


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def main():
    if len(sys.argv) != 2:
        print('Usage: python import_tradebook.py path/to/tradebook.csv', file=sys.stderr)
        sys.exit(1)
    csv_path = sys.argv[1]

    config = get_config()
    journal_url = config['JOURNAL_URL'].rstrip('/')
    headers = {'X-Api-Key': config['JOURNAL_API_KEY']}
    if config['VERCEL_PROTECTION_BYPASS_SECRET']:
        headers['x-vercel-protection-bypass'] = config['VERCEL_PROTECTION_BYPASS_SECRET']

    rows = read_tradebook_rows(csv_path)
    print('Read %d row(s) from %s' % (len(rows), csv_path))
    if not rows:
        print('Nothing to import.')
        return

    tagged_rows = classify_products(rows)
    mis_count = sum(1 for r in tagged_rows if r['product'] == 'MIS')
    print('Classified %d row(s) as MIS (intraday), %d as CNC (delivery)' % (mis_count, len(tagged_rows) - mis_count))

    trades = build_payload(tagged_rows)
    total_imported = 0
    total_skipped = 0
    for i, batch in enumerate(chunked(trades, BATCH_SIZE), start=1):
        resp = requests.post(
            '%s/api/trades' % journal_url,
            json={'trades': batch},
            headers=headers,
            timeout=60,
        )
        if resp.status_code != 200:
            print('Batch %d failed (%d): %s' % (i, resp.status_code, resp.text), file=sys.stderr)
            sys.exit(1)
        result = resp.json()
        total_imported += result.get('imported', 0)
        total_skipped += result.get('skipped', 0)
        print('Batch %d/%d: %s' % (i, (len(trades) + BATCH_SIZE - 1) // BATCH_SIZE, result))

    print('Done. Imported %d, skipped %d (already present) out of %d total rows.'
          % (total_imported, total_skipped, len(trades)))


if __name__ == '__main__':
    main()
