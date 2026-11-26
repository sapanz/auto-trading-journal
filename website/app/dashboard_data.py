"""The data behind the home dashboard.

The page is interactive without round trips: the server embeds every closed
position once (compact records) and static/dashboard_logic.js does the ranges,
streaks, what-ifs and so on in the browser. This module only shapes the rows -
no statistics are computed here, so there is a single source of truth for the
numbers (the JS, unit tested in tests/dashboard_logic.test.mjs).
"""
from sqlalchemy.orm import Session, selectinload

from . import models


def _iso(value):
    return value.isoformat(timespec="seconds") if value else None


def position_record(p: models.Position) -> dict:
    """One closed position as the compact record the front end expects.
    `date` is the exit date; timestamps are naive ISO strings."""
    return {
        "id": p.id,
        "sym": p.tradingsymbol,
        "prod": p.product,
        "dir": p.direction,
        "qty": p.quantity,
        "entry": round(p.entry_price or 0.0, 2),
        "exit": round(p.exit_price or 0.0, 2),
        "entryTs": _iso(p.entry_time),
        "exitTs": _iso(p.exit_time),
        "date": p.exit_date.isoformat(),
        "hold": round(p.holding_minutes or 0.0, 1),
        "gross": round(p.pnl or 0.0, 2),
        "charges": round(p.charges or 0.0, 2),
        "net": round(p.net_pnl or 0.0, 2),
        "roi": round(p.net_pnl_percent or 0.0, 2),
        "tags": sorted(t.name for t in p.tags),
        "rating": p.rating,
        "note": p.notes or "",
    }


def load_closed_positions(db: Session) -> list[models.Position]:
    """Closed positions, oldest exit first (tags loaded in one extra query
    rather than one per position). Rows without an exit are skipped - a
    closed position always has one, but a malformed row shouldn't take the
    whole page down."""
    return (
        db.query(models.Position)
        .options(selectinload(models.Position.tags))
        .filter(
            models.Position.state == "closed",
            models.Position.exit_date.isnot(None),
            models.Position.exit_time.isnot(None),
        )
        .order_by(models.Position.exit_time.asc(), models.Position.id.asc())
        .all()
    )


def build_payload(db: Session, capital: float = 0.0) -> dict:
    """{"trades": [...], "meta": {...}} - serialised into the page as JSON."""
    trades = [position_record(p) for p in load_closed_positions(db)]
    open_count = db.query(models.Position).filter(models.Position.state == "open").count()
    return {
        "trades": trades,
        "meta": {
            "capital": capital if capital and capital > 0 else 0,
            "openCount": open_count,
        },
    }
