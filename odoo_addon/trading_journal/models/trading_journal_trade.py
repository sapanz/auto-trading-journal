from odoo import models, fields, api


class TradingJournalTrade(models.Model):
    """A single Zerodha trade leg (one fill), as returned by kite.trades().

    Immutable audit trail — never edited after import. trading.journal.position
    matches these legs into round trips.
    """
    _name = 'trading.journal.trade'
    _description = 'Zerodha Trade Leg'
    _order = 'exchange_timestamp asc, id asc'

    trade_id = fields.Char(required=True, index=True, help='Zerodha trade_id')
    order_id = fields.Char(required=True, index=True)
    exchange_order_id = fields.Char()
    tradingsymbol = fields.Char(required=True, index=True)
    exchange = fields.Char(required=True)
    instrument_token = fields.Char()
    product = fields.Selection([
        ('CNC', 'Delivery (CNC)'),
        ('MIS', 'Intraday (MIS)'),
        ('NRML', 'Normal (NRML)'),
    ], required=True, index=True)
    transaction_type = fields.Selection([
        ('BUY', 'Buy'),
        ('SELL', 'Sell'),
    ], required=True)
    quantity = fields.Float(required=True)
    price = fields.Float(required=True, help='Average execution price for this fill')
    order_timestamp = fields.Datetime()
    exchange_timestamp = fields.Datetime(required=True)
    trade_date = fields.Date(required=True, index=True)

    _sql_constraints = [
        ('trade_id_uniq', 'unique(trade_id)', 'This trade has already been imported.'),
    ]

    @api.model
    def ingest_trades(self, trade_vals_list):
        """Bulk-import trade legs, skipping ones already imported, then
        re-run FIFO position matching for every symbol/product touched.

        Returns the recordset of newly created trades.
        """
        if not trade_vals_list:
            return self.browse()

        incoming_ids = [v['trade_id'] for v in trade_vals_list]
        existing_ids = set(self.search([('trade_id', 'in', incoming_ids)]).mapped('trade_id'))

        touched = set()
        created = self.browse()
        for vals in trade_vals_list:
            if vals['trade_id'] in existing_ids:
                continue
            rec = self.create(vals)
            created |= rec
            touched.add((rec.tradingsymbol, rec.product))

        Position = self.env['trading.journal.position']
        for tradingsymbol, product in touched:
            Position._recompute_fifo(tradingsymbol, product)

        return created
