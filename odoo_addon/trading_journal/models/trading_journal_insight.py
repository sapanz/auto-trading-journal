from datetime import timedelta

from odoo import models, fields, api


class TradingJournalInsight(models.Model):
    """A generated weekly digest of trading stats and rule-based
    suggestions, built from the closed positions of the last 7 days."""
    _name = 'trading.journal.insight'
    _description = 'Trading Journal Insight'
    _order = 'period_end desc'

    name = fields.Char(required=True, default='Weekly Trading Insight')
    period_start = fields.Date(required=True)
    period_end = fields.Date(required=True)
    body = fields.Html(readonly=True)

    @api.model
    def _cron_generate_weekly_insight(self):
        Position = self.env['trading.journal.position']
        today = fields.Date.context_today(self)
        period_start = today - timedelta(days=7)
        positions = Position.search([
            ('state', '=', 'closed'),
            ('exit_date', '>=', period_start),
            ('exit_date', '<=', today),
        ])
        if not positions:
            return

        total_pnl = sum(positions.mapped('pnl'))
        wins = positions.filtered('is_win')
        win_rate = (len(wins) / len(positions) * 100.0) if positions else 0.0

        by_symbol = {}
        for p in positions:
            by_symbol[p.tradingsymbol] = by_symbol.get(p.tradingsymbol, 0.0) + p.pnl
        best_symbol = max(by_symbol, key=by_symbol.get) if by_symbol else '-'
        worst_symbol = min(by_symbol, key=by_symbol.get) if by_symbol else '-'

        big_losses = positions.filtered(lambda p: 'Big Loss' in p.tag_ids.mapped('name'))
        revenge = positions.filtered(lambda p: 'Possible Revenge Trade' in p.tag_ids.mapped('name'))

        mis = positions.filtered(lambda p: p.product == 'MIS')
        other = positions - mis
        mis_win_rate = (len(mis.filtered('is_win')) / len(mis) * 100.0) if mis else None
        other_win_rate = (len(other.filtered('is_win')) / len(other) * 100.0) if other else None

        suggestions = []
        if win_rate < 40:
            suggestions.append(
                'Your win rate this week (%.1f%%) is low — review entry criteria before adding size.' % win_rate)
        if big_losses:
            suggestions.append(
                '%d trade(s) were flagged as Big Loss (%s) — consider tighter stop-losses.' % (
                    len(big_losses), ', '.join(sorted(set(big_losses.mapped('tradingsymbol'))))))
        if revenge:
            suggestions.append(
                '%d trade(s) looked like revenge trading (bigger size re-entered within 10 minutes of a loss). '
                'Consider a mandatory cooldown after a loss.' % len(revenge))
        if mis_win_rate is not None and other_win_rate is not None and mis_win_rate < other_win_rate - 15:
            suggestions.append(
                'Intraday (MIS) win rate (%.1f%%) is well below your delivery/positional win rate (%.1f%%) — '
                'you may be forcing intraday trades.' % (mis_win_rate, other_win_rate))
        if not suggestions:
            suggestions.append('No major red flags this week — keep following your process.')

        body = """
            <p><b>Period:</b> %s to %s</p>
            <p><b>Closed trades:</b> %d &nbsp;|&nbsp; <b>Win rate:</b> %.1f%% &nbsp;|&nbsp; <b>Net P&amp;L:</b> %.2f</p>
            <p><b>Best symbol:</b> %s &nbsp;|&nbsp; <b>Worst symbol:</b> %s</p>
            <ul>%s</ul>
        """ % (
            period_start, today, len(positions), win_rate, total_pnl, best_symbol, worst_symbol,
            ''.join('<li>%s</li>' % s for s in suggestions),
        )

        return self.create({
            'name': 'Weekly Trading Insight (%s - %s)' % (period_start, today),
            'period_start': period_start,
            'period_end': today,
            'body': body,
        })
