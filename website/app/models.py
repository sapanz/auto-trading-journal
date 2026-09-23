import datetime as dt

from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Text, ForeignKey, Table
from sqlalchemy.orm import relationship

from .database import Base

position_tags = Table(
    "position_tags",
    Base.metadata,
    Column("position_id", ForeignKey("positions.id"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id"), primary_key=True),
)

position_entry_trades = Table(
    "position_entry_trades",
    Base.metadata,
    Column("position_id", ForeignKey("positions.id"), primary_key=True),
    Column("trade_id", ForeignKey("trades.id"), primary_key=True),
)

position_exit_trades = Table(
    "position_exit_trades",
    Base.metadata,
    Column("position_id", ForeignKey("positions.id"), primary_key=True),
    Column("trade_id", ForeignKey("trades.id"), primary_key=True),
)


class Trade(Base):
    """A single Zerodha trade leg (one fill), as returned by kite.trades().

    Immutable audit trail — never edited after import. Position rows are
    matched from these legs (see matching.py).
    """
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    trade_id = Column(String, unique=True, nullable=False, index=True)
    order_id = Column(String, nullable=False, index=True)
    exchange_order_id = Column(String)
    tradingsymbol = Column(String, nullable=False, index=True)
    exchange = Column(String, nullable=False)
    instrument_token = Column(String)
    product = Column(String, nullable=False, index=True)  # CNC / MIS / NRML
    transaction_type = Column(String, nullable=False)  # BUY / SELL
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    order_timestamp = Column(DateTime)
    exchange_timestamp = Column(DateTime, nullable=False)
    trade_date = Column(Date, nullable=False, index=True)


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    css_class = Column(String, default="tag-default")


class Position(Base):
    """A matched round trip (entry + exit), FIFO-matched from raw trade legs.

    Rebuilt from scratch for the affected symbol/product every time new
    trades are ingested (see matching.recompute_fifo) rather than updated
    incrementally, which keeps the matching logic correct by construction
    instead of maintaining fragile partial-fill bookkeeping across calls.
    """
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True)
    tradingsymbol = Column(String, nullable=False, index=True)
    exchange = Column(String)
    product = Column(String, nullable=False, index=True)
    direction = Column(String, nullable=False)  # LONG / SHORT
    state = Column(String, nullable=False, default="open", index=True)  # open / closed

    quantity = Column(Float, nullable=False)
    entry_time = Column(DateTime, nullable=False)
    exit_time = Column(DateTime)
    entry_date = Column(Date, nullable=False, index=True)
    exit_date = Column(Date, index=True)

    entry_value = Column(Float, nullable=False, default=0.0)
    exit_value = Column(Float, default=0.0)
    entry_price = Column(Float, default=0.0)
    exit_price = Column(Float, default=0.0)

    pnl = Column(Float, default=0.0)  # gross, before charges
    pnl_percent = Column(Float, default=0.0)
    charges = Column(Float, default=0.0)  # estimated brokerage/STT/taxes for this round trip (see charges.py)
    net_pnl = Column(Float, default=0.0)  # pnl - charges: the realized P&L
    net_pnl_percent = Column(Float, default=0.0)
    is_win = Column(Integer, default=0)  # sqlite has no bool type; 0/1 — based on net_pnl
    holding_minutes = Column(Float, default=0.0)

    notes = Column(Text)
    rating = Column(Integer)

    tags = relationship("Tag", secondary=position_tags, backref="positions")
    entry_trades = relationship("Trade", secondary=position_entry_trades)
    exit_trades = relationship("Trade", secondary=position_exit_trades)


class Insight(Base):
    """A generated weekly digest of trading stats and rule-based suggestions."""
    __tablename__ = "insights"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    body_html = Column(Text, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
