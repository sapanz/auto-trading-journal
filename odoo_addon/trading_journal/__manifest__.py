{
    'name': 'Zerodha Trading Journal',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Trading',
    'summary': 'Automated trading journal for Zerodha trades: P&L, ROI and discipline insights',
    'description': """
Zerodha Trading Journal
========================
Ingests trades fetched from Zerodha Kite Connect (via an external cron, e.g.
GitHub Actions) and automatically:

* Matches raw trade legs into round-trip positions (FIFO, long and short)
* Computes realized P&L, ROI % and holding time per position
* Flags trades with discipline warnings (big loss, revenge trading, scalps)
* Generates a weekly text insight/suggestion digest

Trades are pushed in via a simple API endpoint
(`POST /api/trading-journal/trades`) secured with an API key, so this module
has no dependency on how or where the fetch job runs.
""",
    'author': 'Auto Trading Journal',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/trading_journal_data.xml',
        'views/trading_journal_trade_views.xml',
        'views/trading_journal_position_views.xml',
        'views/trading_journal_insight_views.xml',
        'views/trading_journal_menus.xml',
    ],
    'application': True,
    'installable': True,
}
