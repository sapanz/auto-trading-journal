import datetime as dt
import os
from collections import deque

from sqlalchemy.orm import Session

from . import models
from .charges import estimate_charges

QTY_EPSILON = 1e-6


def ingest_trades(db: Session, trades_data: list[dict]) -> dict:
    """Bulk-import trade legs, skipping ones already imported, then re-run
    FIFO position matching for every symbol/product touched."""
    if not trades_data:
        return {"received": 0, "imported": 0, "skipped": 0}

    incoming_ids = [t["trade_id"] for t in trades_data]
    existing_ids = {
        row[0]
        for row in db.query(models.Trade.trade_id).filter(models.Trade.trade_id.in_(incoming_ids)).all()
    }

    touched = set()
    imported = 0
    for t in trades_data:
        if t["trade_id"] in existing_ids:
            continue
        trade = models.Trade(
            trade_id=t["trade_id"],
            order_id=t["order_id"],
            exchange_order_id=t.get("exchange_order_id"),
            tradingsymbol=t["tradingsymbol"],
            exchange=t["exchange"],
            instrument_token=t.get("instrument_token"),
            product=t["product"],
            transaction_type=t["transaction_type"],
            quantity=t["quantity"],
            price=t["price"],
            order_timestamp=t.get("order_timestamp"),
            exchange_timestamp=t["exchange_timestamp"],
            trade_date=t["trade_date"],
        )
        db.add(trade)
        imported += 1
        touched.add((trade.tradingsymbol, trade.product))

    db.flush()

    for tradingsymbol, product in touched:
        recompute_fifo(db, tradingsymbol, product)

    db.commit()
    return {"received": len(trades_data), "imported": imported, "skipped": len(trades_data) - imported}


def recompute_fifo(db: Session, tradingsymbol: str, product: str):
    """Rebuild every position for this symbol/product from its raw trade
    legs using FIFO matching (handles both long and short round trips)."""
    legs = (
        db.query(models.Trade)
        .filter(models.Trade.tradingsymbol == tradingsymbol, models.Trade.product == product)
        .order_by(models.Trade.exchange_timestamp.asc(), models.Trade.id.asc())
        .all()
    )

    stale = (
        db.query(models.Position)
        .filter(models.Position.tradingsymbol == tradingsymbol, models.Position.product == product)
        .all()
    )
    for pos in stale:
        db.delete(pos)
    db.flush()

    buy_queue = deque()   # open LONG entries waiting to be closed by a SELL
    sell_queue = deque()  # open SHORT entries waiting to be closed by a BUY
    new_positions = []

    for leg in legs:
        remaining = leg.quantity
        if leg.transaction_type == "BUY":
            opposite_queue, same_queue, closes_direction = sell_queue, buy_queue, "SHORT"
        else:
            opposite_queue, same_queue, closes_direction = buy_queue, sell_queue, "LONG"

        while remaining > QTY_EPSILON and opposite_queue:
            chunk = opposite_queue[0]
            matched_qty = min(remaining, chunk["qty"])
            entry_value = matched_qty * chunk["price"]
            exit_value = matched_qty * leg.price
            pnl = (exit_value - entry_value) if closes_direction == "LONG" else (entry_value - exit_value)
            pnl_percent = (pnl / entry_value * 100.0) if entry_value else 0.0
            holding_minutes = (leg.exchange_timestamp - chunk["time"]).total_seconds() / 60.0

            charge_breakdown = estimate_charges(product, closes_direction, entry_value, exit_value)
            total_charges = charge_breakdown["total"]
            net_pnl = pnl - total_charges
            net_pnl_percent = (net_pnl / entry_value * 100.0) if entry_value else 0.0

            pos = models.Position(
                tradingsymbol=tradingsymbol,
                product=product,
                direction=closes_direction,
                state="closed",
                quantity=matched_qty,
                entry_time=chunk["time"],
                exit_time=leg.exchange_timestamp,
                entry_date=chunk["date"],
                exit_date=leg.trade_date,
                entry_value=entry_value,
                exit_value=exit_value,
                entry_price=chunk["price"],
                exit_price=leg.price,
                pnl=pnl,
                pnl_percent=pnl_percent,
                charges=total_charges,
                net_pnl=net_pnl,
                net_pnl_percent=net_pnl_percent,
                is_win=1 if net_pnl > 0 else 0,
                holding_minutes=holding_minutes,
            )
            pos.entry_trades.append(chunk["trade"])
            pos.exit_trades.append(leg)
            db.add(pos)
            new_positions.append(pos)

            chunk["qty"] -= matched_qty
            remaining -= matched_qty
            if chunk["qty"] <= QTY_EPSILON:
                opposite_queue.popleft()

        if remaining > QTY_EPSILON:
            same_queue.append({
                "qty": remaining, "price": leg.price, "trade": leg,
                "time": leg.exchange_timestamp, "date": leg.trade_date,
            })

    for chunk in buy_queue:
        pos = models.Position(
            tradingsymbol=tradingsymbol, product=product, direction="LONG", state="open",
            quantity=chunk["qty"], entry_time=chunk["time"], entry_date=chunk["date"],
            entry_value=chunk["qty"] * chunk["price"], entry_price=chunk["price"],
        )
        pos.entry_trades.append(chunk["trade"])
        db.add(pos)
        new_positions.append(pos)

    for chunk in sell_queue:
        pos = models.Position(
            tradingsymbol=tradingsymbol, product=product, direction="SHORT", state="open",
            quantity=chunk["qty"], entry_time=chunk["time"], entry_date=chunk["date"],
            entry_value=chunk["qty"] * chunk["price"], entry_price=chunk["price"],
        )
        pos.entry_trades.append(chunk["trade"])
        db.add(pos)
        new_positions.append(pos)

    db.flush()
    _apply_discipline_tags(db, new_positions)
    return new_positions


def _get_or_create_tag(db: Session, name: str, css_class: str) -> models.Tag:
    tag = db.query(models.Tag).filter_by(name=name).first()
    if not tag:
        tag = models.Tag(name=name, css_class=css_class)
        db.add(tag)
        db.flush()
    return tag


def _apply_discipline_tags(db: Session, positions: list):
    """Rule-based flags — a simple, extensible starting point for
    trade-discipline suggestions (see insights.py for the weekly narrative
    digest built on top of these)."""
    big_loss_pct = float(os.environ.get("JOURNAL_BIG_LOSS_PERCENT", "2.0"))

    tag_big_loss = _get_or_create_tag(db, "Big Loss", "tag-loss")
    tag_big_win = _get_or_create_tag(db, "Big Win", "tag-win")
    tag_scalp = _get_or_create_tag(db, "Quick Scalp", "tag-scalp")
    tag_revenge = _get_or_create_tag(db, "Possible Revenge Trade", "tag-revenge")

    for pos in positions:
        if pos.state != "closed":
            continue
        if pos.net_pnl_percent <= -big_loss_pct and tag_big_loss not in pos.tags:
            pos.tags.append(tag_big_loss)
        if pos.net_pnl_percent >= big_loss_pct * 2 and tag_big_win not in pos.tags:
            pos.tags.append(tag_big_win)
        if pos.product == "MIS" and 0 < pos.holding_minutes < 2 and tag_scalp not in pos.tags:
            pos.tags.append(tag_scalp)

    _flag_revenge_trades(db, positions, tag_revenge)
    db.flush()


def _flag_revenge_trades(db: Session, positions: list, tag_revenge: models.Tag):
    """Flag a position entered within 10 minutes of a losing exit on the
    same symbol, with a bigger size than the losing trade — a common
    emotional-trading pattern."""
    for pos in positions:
        if pos.state != "closed" or pos.net_pnl >= 0 or not pos.exit_time:
            continue
        window_end = pos.exit_time + dt.timedelta(minutes=10)
        next_trade = (
            db.query(models.Position)
            .filter(
                models.Position.id != pos.id,
                models.Position.tradingsymbol == pos.tradingsymbol,
                models.Position.entry_time > pos.exit_time,
                models.Position.entry_time <= window_end,
                models.Position.quantity > pos.quantity,
            )
            .first()
        )
        if next_trade and tag_revenge not in next_trade.tags:
            next_trade.tags.append(tag_revenge)
