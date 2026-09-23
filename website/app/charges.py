"""Estimated statutory + brokerage charges on a closed equity round trip,
using Zerodha's published retail equity charge structure.

This is an ESTIMATE, not the exact figure from a contract note: rates are
current as of this writing but can change, and this only models plain
equity delivery (CNC) and intraday/carry-forward (MIS/NRML) -- it doesn't
special-case F&O (different STT/brokerage rules) or the flat per-scrip DP
charge Zerodha/CDSL levies on delivery sells (~Rs 15-20/scrip/day,
independent of value or quantity, which would need day-level trade
grouping to attribute correctly rather than a per-round-trip estimate).
Good enough to see realized P&L net of the charges that actually move the
needle -- brokerage, STT, exchange transaction charges, stamp duty, GST --
instead of pretending they're zero.
"""
import os

# Exchange transaction charges: NSE rate is used as the default since the
# app doesn't otherwise distinguish which exchange a position traded on;
# BSE's rate runs slightly higher.
_EXCHANGE_TXN_RATE = float(os.environ.get("JOURNAL_CHARGES_EXCHANGE_TXN_RATE", "0.0000297"))
_SEBI_RATE = float(os.environ.get("JOURNAL_CHARGES_SEBI_RATE", "0.000001"))  # Rs 10 / crore
_GST_RATE = 0.18

_DELIVERY_BROKERAGE_RATE = 0.0  # Zerodha: zero brokerage on equity delivery
_INTRADAY_BROKERAGE_RATE = float(os.environ.get("JOURNAL_CHARGES_INTRADAY_BROKERAGE_RATE", "0.0003"))
_INTRADAY_BROKERAGE_CAP = float(os.environ.get("JOURNAL_CHARGES_INTRADAY_BROKERAGE_CAP", "20.0"))

_DELIVERY_STT_RATE = 0.001     # 0.1%, both legs
_INTRADAY_STT_RATE = 0.00025   # 0.025%, sell leg only

_DELIVERY_STAMP_DUTY_RATE = 0.00015  # 0.015%, buy leg only
_INTRADAY_STAMP_DUTY_RATE = 0.00003  # 0.003%, buy leg only


def estimate_charges(product: str, direction: str, entry_value: float, exit_value: float) -> dict:
    """entry_value/exit_value are quantity * price for this round trip.
    direction is LONG (buy then sell) or SHORT (sell then buy) -- the buy
    and sell legs matter separately since STT and stamp duty aren't
    symmetric between them."""
    is_delivery = product == "CNC"
    buy_value = entry_value if direction == "LONG" else exit_value
    sell_value = exit_value if direction == "LONG" else entry_value

    if is_delivery:
        brokerage = _DELIVERY_BROKERAGE_RATE * (buy_value + sell_value)
        stt = _DELIVERY_STT_RATE * (buy_value + sell_value)
        stamp_duty = _DELIVERY_STAMP_DUTY_RATE * buy_value
    else:
        brokerage = (
            min(_INTRADAY_BROKERAGE_RATE * buy_value, _INTRADAY_BROKERAGE_CAP)
            + min(_INTRADAY_BROKERAGE_RATE * sell_value, _INTRADAY_BROKERAGE_CAP)
        )
        stt = _INTRADAY_STT_RATE * sell_value
        stamp_duty = _INTRADAY_STAMP_DUTY_RATE * buy_value

    turnover = buy_value + sell_value
    exchange_txn_charges = _EXCHANGE_TXN_RATE * turnover
    sebi_charges = _SEBI_RATE * turnover
    gst = _GST_RATE * (brokerage + exchange_txn_charges + sebi_charges)

    total = brokerage + stt + exchange_txn_charges + sebi_charges + stamp_duty + gst
    return {
        "brokerage": brokerage,
        "stt": stt,
        "exchange_txn_charges": exchange_txn_charges,
        "sebi_charges": sebi_charges,
        "stamp_duty": stamp_duty,
        "gst": gst,
        "total": total,
    }
