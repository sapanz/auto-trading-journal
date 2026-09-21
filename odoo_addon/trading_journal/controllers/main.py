import hmac
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class TradingJournalController(http.Controller):

    def _check_api_key(self):
        """Constant-time comparison against the API key configured in
        Settings > Technical > System Parameters (trading_journal.api_key).
        """
        provided = request.httprequest.headers.get('X-Api-Key', '')
        expected = request.env['ir.config_parameter'].sudo().get_param('trading_journal.api_key', '')
        if not expected or not provided:
            return False
        return hmac.compare_digest(provided, expected)

    @http.route('/api/trading-journal/ping', type='http', auth='none', methods=['GET'], csrf=False)
    def ping(self, **kwargs):
        if not self._check_api_key():
            return request.make_json_response({'error': 'unauthorized'}, status=401)
        return request.make_json_response({'status': 'ok'})

    @http.route('/api/trading-journal/trades', type='http', auth='none', methods=['POST'], csrf=False)
    def ingest_trades(self, **kwargs):
        if not self._check_api_key():
            return request.make_json_response({'error': 'unauthorized'}, status=401)

        try:
            payload = json.loads(request.httprequest.data or b'{}')
        except ValueError:
            return request.make_json_response({'error': 'invalid json body'}, status=400)

        trades = payload.get('trades') or []
        vals_list = []
        for t in trades:
            try:
                vals_list.append({
                    'trade_id': str(t['trade_id']),
                    'order_id': str(t['order_id']),
                    'exchange_order_id': str(t.get('exchange_order_id') or '') or None,
                    'tradingsymbol': t['tradingsymbol'],
                    'exchange': t['exchange'],
                    'instrument_token': str(t.get('instrument_token') or '') or None,
                    'product': t['product'],
                    'transaction_type': t['transaction_type'],
                    'quantity': float(t['quantity']),
                    'price': float(t['average_price']),
                    'order_timestamp': t.get('order_timestamp'),
                    'exchange_timestamp': t['exchange_timestamp'],
                    'trade_date': t.get('trade_date') or (t['exchange_timestamp'] or '')[:10],
                })
            except (KeyError, TypeError, ValueError) as exc:
                _logger.warning('Skipping malformed trade payload %r: %s', t, exc)

        created = request.env['trading.journal.trade'].sudo().ingest_trades(vals_list)
        return request.make_json_response({
            'received': len(trades),
            'imported': len(created),
            'skipped': len(trades) - len(created),
        })
