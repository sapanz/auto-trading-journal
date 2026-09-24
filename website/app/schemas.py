import datetime as dt
from typing import List, Optional

from pydantic import BaseModel


class TradeIn(BaseModel):
    """Matches the payload shape the fetcher script (fetcher/fetch_trades.py)
    already sends: {"trades": [...]} with Kite Connect's own field names."""
    trade_id: str
    order_id: str
    exchange_order_id: Optional[str] = None
    tradingsymbol: str
    exchange: str
    instrument_token: Optional[str] = None
    product: str
    transaction_type: str
    quantity: float
    average_price: float
    order_timestamp: Optional[str] = None
    exchange_timestamp: str
    trade_date: Optional[str] = None

    def to_dict(self) -> dict:
        exchange_ts = _parse_dt(self.exchange_timestamp)
        return {
            "trade_id": self.trade_id,
            "order_id": self.order_id,
            "exchange_order_id": self.exchange_order_id,
            "tradingsymbol": self.tradingsymbol,
            "exchange": self.exchange,
            "instrument_token": self.instrument_token,
            "product": self.product,
            "transaction_type": self.transaction_type,
            "quantity": self.quantity,
            "price": self.average_price,
            "order_timestamp": (
                _parse_dt(self.order_timestamp, fallback_date=exchange_ts.date())
                if self.order_timestamp else None
            ),
            "exchange_timestamp": exchange_ts,
            "trade_date": _parse_date(self.trade_date) if self.trade_date else exchange_ts.date(),
        }


class TradesPayload(BaseModel):
    trades: List[TradeIn]


def _parse_dt(value: str, fallback_date: Optional[dt.date] = None) -> dt.datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(value[:19], fmt)
        except ValueError:
            continue
    # Kite Connect's trades() API sometimes returns order_timestamp as a
    # bare "HH:MM:SS" with no date, for trades placed earlier the same
    # trading day -- combine it with the trade's own exchange-timestamp
    # date rather than failing the whole ingestion batch over a field
    # that isn't used by any matching/charges logic.
    if fallback_date is not None:
        try:
            time_part = dt.datetime.strptime(value[:8], "%H:%M:%S").time()
            return dt.datetime.combine(fallback_date, time_part)
        except ValueError:
            pass
    raise ValueError(f"Unrecognized datetime format: {value!r}")


def _parse_date(value: str) -> dt.date:
    return dt.datetime.strptime(value[:10], "%Y-%m-%d").date()
