from odoo import models, fields


class TradingJournalTag(models.Model):
    _name = 'trading.journal.tag'
    _description = 'Trading Journal Flag'
    _order = 'name'

    name = fields.Char(required=True)
    color = fields.Integer()
