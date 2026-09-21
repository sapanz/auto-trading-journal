from collections import deque

from odoo import models, fields, api

QTY_EPSILON = 1e-6


class TradingJournalPosition(models.Model):
    """A matched round trip (entry + exit), FIFO-matched from raw trade legs.

    Rebuilt from scratch for the affected symbol/product every time new
    trades are ingested (see _recompute_fifo), rather than updated
    incrementally — this keeps the matching logic simple and correct instead
    of maintaining fragile partial-fill bookkeeping across calls.
    """
    _name = 'trading.journal.position'
    _description = 'Matched Trade (Round Trip)'
    _order = 'exit_time desc, entry_time desc'

    tradingsymbol = fields.Char(required=True, index=True)
    exchange = fields.Char()
    product = fields.Selection([
        ('CNC', 'Delivery (CNC)'),
        ('MIS', 'Intraday (MIS)'),
        ('NRML', 'Normal (NRML)'),
    ], required=True, index=True)
    direction = fields.Selection([
        ('LONG', 'Long'),
        ('SHORT', 'Short'),
    ], required=True)
    state = fields.Selection([
        ('open', 'Open'),
        ('closed', 'Closed'),
    ], required=True, default='open', index=True)

    quantity = fields.Float(required=True)
    entry_time = fields.Datetime(required=True)
    exit_time = fields.Datetime()
    entry_date = fields.Date(required=True, index=True)
    exit_date = fields.Date(index=True)

    entry_value = fields.Float()
    exit_value = fields.Float()
    entry_price = fields.Float(compute='_compute_prices', store=True)
    exit_price = fields.Float(compute='_compute_prices', store=True)

    pnl = fields.Float(compute='_compute_pnl', store=True)
    pnl_percent = fields.Float(compute='_compute_pnl', store=True, string='ROI %')
    is_win = fields.Boolean(compute='_compute_pnl', store=True)
    holding_minutes = fields.Float(compute='_compute_pnl', store=True)

    entry_trade_ids = fields.Many2many(
        'trading.journal.trade', 'trading_journal_position_entry_rel',
        'position_id', 'trade_id', string='Entry Trade(s)')
    exit_trade_ids = fields.Many2many(
        'trading.journal.trade', 'trading_journal_position_exit_rel',
        'position_id', 'trade_id', string='Exit Trade(s)')

    tag_ids = fields.Many2many('trading.journal.tag', string='Flags')
    notes = fields.Text(string='Journal Notes')
    rating = fields.Selection([
        ('1', '1 - Poor discipline'),
        ('2', '2'),
        ('3', '3 - Average'),
        ('4', '4'),
        ('5', '5 - Textbook'),
    ], string='Self Rating')

    @api.depends('entry_value', 'exit_value', 'quantity', 'state')
    def _compute_prices(self):
        for rec in self:
            rec.entry_price = rec.entry_value / rec.quantity if rec.quantity else 0.0
            rec.exit_price = (rec.exit_value / rec.quantity) if (rec.state == 'closed' and rec.quantity) else 0.0

    @api.depends('entry_value', 'exit_value', 'state', 'entry_time', 'exit_time', 'direction')
    def _compute_pnl(self):
        for rec in self:
            if rec.state == 'closed':
                if rec.direction == 'LONG':
                    rec.pnl = rec.exit_value - rec.entry_value
                else:
                    rec.pnl = rec.entry_value - rec.exit_value
                rec.pnl_percent = (rec.pnl / rec.entry_value * 100.0) if rec.entry_value else 0.0
                rec.is_win = rec.pnl > 0
                rec.holding_minutes = (
                    (rec.exit_time - rec.entry_time).total_seconds() / 60.0
                    if rec.entry_time and rec.exit_time else 0.0
                )
            else:
                rec.pnl = 0.0
                rec.pnl_percent = 0.0
                rec.is_win = False
                rec.holding_minutes = 0.0

    @api.model
    def _recompute_fifo(self, tradingsymbol, product):
        """Rebuild every position for this symbol/product from its raw trade
        legs using FIFO matching (handles both long and short round trips).
        """
        Trade = self.env['trading.journal.trade']
        legs = Trade.search([
            ('tradingsymbol', '=', tradingsymbol),
            ('product', '=', product),
        ], order='exchange_timestamp asc, id asc')

        self.search([
            ('tradingsymbol', '=', tradingsymbol),
            ('product', '=', product),
        ]).unlink()

        buy_queue = deque()   # open LONG entries waiting to be closed by a SELL
        sell_queue = deque()  # open SHORT entries waiting to be closed by a BUY
        position_vals = []

        for leg in legs:
            remaining = leg.quantity
            if leg.transaction_type == 'BUY':
                opposite_queue, same_queue, closes_direction = sell_queue, buy_queue, 'SHORT'
            else:
                opposite_queue, same_queue, closes_direction = buy_queue, sell_queue, 'LONG'

            while remaining > QTY_EPSILON and opposite_queue:
                chunk = opposite_queue[0]
                matched_qty = min(remaining, chunk['qty'])
                position_vals.append({
                    'tradingsymbol': tradingsymbol,
                    'product': product,
                    'direction': closes_direction,
                    'state': 'closed',
                    'quantity': matched_qty,
                    'entry_time': chunk['time'],
                    'exit_time': leg.exchange_timestamp,
                    'entry_date': chunk['date'],
                    'exit_date': leg.trade_date,
                    'entry_value': matched_qty * chunk['price'],
                    'exit_value': matched_qty * leg.price,
                    'entry_trade_ids': [(4, chunk['trade_id'])],
                    'exit_trade_ids': [(4, leg.id)],
                })
                chunk['qty'] -= matched_qty
                remaining -= matched_qty
                if chunk['qty'] <= QTY_EPSILON:
                    opposite_queue.popleft()

            if remaining > QTY_EPSILON:
                same_queue.append({
                    'qty': remaining,
                    'price': leg.price,
                    'trade_id': leg.id,
                    'time': leg.exchange_timestamp,
                    'date': leg.trade_date,
                })

        for chunk in buy_queue:
            position_vals.append({
                'tradingsymbol': tradingsymbol, 'product': product, 'direction': 'LONG', 'state': 'open',
                'quantity': chunk['qty'], 'entry_time': chunk['time'], 'entry_date': chunk['date'],
                'entry_value': chunk['qty'] * chunk['price'],
                'entry_trade_ids': [(4, chunk['trade_id'])],
            })
        for chunk in sell_queue:
            position_vals.append({
                'tradingsymbol': tradingsymbol, 'product': product, 'direction': 'SHORT', 'state': 'open',
                'quantity': chunk['qty'], 'entry_time': chunk['time'], 'entry_date': chunk['date'],
                'entry_value': chunk['qty'] * chunk['price'],
                'entry_trade_ids': [(4, chunk['trade_id'])],
            })

        new_positions = self.create(position_vals)
        new_positions._apply_discipline_tags()
        return new_positions

    def _apply_discipline_tags(self):
        """Rule-based flags — a simple, extensible starting point for
        trade-discipline suggestions (see trading.journal.insight for the
        weekly narrative digest built on top of these)."""
        ICP = self.env['ir.config_parameter'].sudo()
        big_loss_pct = float(ICP.get_param('trading_journal.big_loss_percent', 2.0))

        def tag(xmlid):
            return self.env.ref(xmlid, raise_if_not_found=False) or self.env['trading.journal.tag']

        tag_big_loss = tag('trading_journal.tag_big_loss')
        tag_big_win = tag('trading_journal.tag_big_win')
        tag_scalp = tag('trading_journal.tag_scalp')

        for rec in self:
            if rec.state != 'closed':
                continue
            tags = self.env['trading.journal.tag']
            if rec.pnl_percent <= -big_loss_pct:
                tags |= tag_big_loss
            if rec.pnl_percent >= big_loss_pct * 2:
                tags |= tag_big_win
            if rec.product == 'MIS' and 0 < rec.holding_minutes < 2:
                tags |= tag_scalp
            if tags:
                rec.tag_ids = [(4, t.id) for t in tags]

        self._flag_revenge_trades()

    def _flag_revenge_trades(self):
        """Flag a position entered within 10 minutes of a losing exit on the
        same symbol, with a bigger size than the losing trade — a common
        emotional-trading pattern."""
        tag_revenge = self.env.ref('trading_journal.tag_revenge', raise_if_not_found=False)
        if not tag_revenge:
            return
        for rec in self:
            if rec.state != 'closed' or rec.pnl >= 0 or not rec.exit_time:
                continue
            window_end = fields.Datetime.add(rec.exit_time, minutes=10)
            next_trade = self.search([
                ('id', '!=', rec.id),
                ('tradingsymbol', '=', rec.tradingsymbol),
                ('entry_time', '>', rec.exit_time),
                ('entry_time', '<=', window_end),
                ('quantity', '>', rec.quantity),
            ], limit=1)
            if next_trade:
                next_trade.tag_ids = [(4, tag_revenge.id)]
