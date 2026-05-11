"""
SQLAlchemy ORM models — work with both SQLite (dev) and PostgreSQL (prod).
TimescaleDB hypertable features (continuous aggregates etc.) are prod-only.
"""

from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    String, Float, Integer, BigInteger, Boolean, Text,
    DateTime, Date, Time, ForeignKey, Index
)
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Tick(Base):
    __tablename__ = "ticks"

    id:         Mapped[int]   = mapped_column(Integer, primary_key=True, autoincrement=True)
    time:       Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    symbol:     Mapped[str]   = mapped_column(String(50), nullable=False)
    exchange:   Mapped[str]   = mapped_column(String(10), nullable=False)
    segment:    Mapped[str]   = mapped_column(String(10), nullable=False, default="EQ")
    ltp:        Mapped[Optional[float]] = mapped_column(Float)
    open:       Mapped[Optional[float]] = mapped_column(Float)
    high:       Mapped[Optional[float]] = mapped_column(Float)
    low:        Mapped[Optional[float]] = mapped_column(Float)
    close:      Mapped[Optional[float]] = mapped_column(Float)
    volume:     Mapped[Optional[int]]   = mapped_column(BigInteger)
    oi:         Mapped[Optional[int]]   = mapped_column(BigInteger)
    bid:        Mapped[Optional[float]] = mapped_column(Float)
    ask:        Mapped[Optional[float]] = mapped_column(Float)
    total_buy_qty:  Mapped[Optional[int]] = mapped_column(BigInteger)
    total_sell_qty: Mapped[Optional[int]] = mapped_column(BigInteger)

    __table_args__ = (
        Index("idx_ticks_symbol_time", "symbol", "time"),
    )


class Instrument(Base):
    __tablename__ = "instruments"

    token:           Mapped[str] = mapped_column(String(20), primary_key=True)
    exchange:        Mapped[str] = mapped_column(String(10), primary_key=True)
    symbol:          Mapped[str] = mapped_column(String(50), nullable=False)
    name:            Mapped[Optional[str]] = mapped_column(String(200))
    segment:         Mapped[str] = mapped_column(String(10), nullable=False, default="EQ")
    instrument_type: Mapped[Optional[str]] = mapped_column(String(10))
    expiry:          Mapped[Optional[date]] = mapped_column(Date)
    strike:          Mapped[Optional[float]] = mapped_column(Float)
    lot_size:        Mapped[int] = mapped_column(Integer, default=1)
    tick_size:       Mapped[float] = mapped_column(Float, default=0.05)
    isin:            Mapped[Optional[str]] = mapped_column(String(20))
    is_active:       Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at:      Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_instruments_symbol", "symbol"),
        Index("idx_instruments_exchange_segment", "exchange", "segment"),
    )


class Signal(Base):
    __tablename__ = "signals"

    id:           Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    symbol:       Mapped[str] = mapped_column(String(50), nullable=False)
    exchange:     Mapped[str] = mapped_column(String(10), nullable=False)
    timeframe:    Mapped[str] = mapped_column(String(10), nullable=False)
    signal_type:  Mapped[str] = mapped_column(String(10), nullable=False)
    strength:     Mapped[Optional[float]] = mapped_column(Float)
    entry_price:  Mapped[Optional[float]] = mapped_column(Float)
    stop_loss:    Mapped[Optional[float]] = mapped_column(Float)
    target_1:     Mapped[Optional[float]] = mapped_column(Float)
    target_2:     Mapped[Optional[float]] = mapped_column(Float)
    target_3:     Mapped[Optional[float]] = mapped_column(Float)
    risk_reward:  Mapped[Optional[float]] = mapped_column(Float)
    strategy:     Mapped[Optional[str]]   = mapped_column(String(100))
    notes:        Mapped[Optional[str]]   = mapped_column(Text)
    is_active:    Mapped[bool]            = mapped_column(Boolean, default=True)
    outcome:      Mapped[Optional[str]]   = mapped_column(String(20))

    __table_args__ = (
        Index("idx_signals_symbol_time", "symbol", "generated_at"),
    )


class SMCZoneModel(Base):
    __tablename__ = "smc_zones"

    id:           Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    detected_at:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    symbol:       Mapped[str] = mapped_column(String(50), nullable=False)
    exchange:     Mapped[str] = mapped_column(String(10), nullable=False)
    timeframe:    Mapped[str] = mapped_column(String(10), nullable=False)
    zone_type:    Mapped[str] = mapped_column(String(20), nullable=False)
    price_top:    Mapped[float] = mapped_column(Float, nullable=False)
    price_bottom: Mapped[float] = mapped_column(Float, nullable=False)
    candle_time:  Mapped[Optional[datetime]] = mapped_column(DateTime)
    strength:     Mapped[Optional[float]] = mapped_column(Float)
    is_filled:    Mapped[bool] = mapped_column(Boolean, default=False)
    filled_at:    Mapped[Optional[datetime]] = mapped_column(DateTime)


class Order(Base):
    __tablename__ = "orders"

    id:             Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    broker_order_id: Mapped[Optional[str]] = mapped_column(String(50))
    placed_at:      Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    symbol:         Mapped[str] = mapped_column(String(50), nullable=False)
    exchange:       Mapped[str] = mapped_column(String(10), nullable=False)
    transaction:    Mapped[str] = mapped_column(String(10), nullable=False)
    order_type:     Mapped[str] = mapped_column(String(10), nullable=False)
    product:        Mapped[str] = mapped_column(String(10), nullable=False)
    quantity:       Mapped[int] = mapped_column(Integer, nullable=False)
    price:          Mapped[Optional[float]] = mapped_column(Float)
    trigger_price:  Mapped[Optional[float]] = mapped_column(Float)
    status:         Mapped[str] = mapped_column(String(20), default="PENDING")
    avg_price:      Mapped[Optional[float]] = mapped_column(Float)
    filled_qty:     Mapped[int] = mapped_column(Integer, default=0)
    is_paper:       Mapped[bool] = mapped_column(Boolean, default=True)
    broker:         Mapped[str] = mapped_column(String(20), default="PAPER")
    signal_id:      Mapped[Optional[int]] = mapped_column(BigInteger)
    notes:          Mapped[Optional[str]] = mapped_column(Text)


class Position(Base):
    __tablename__ = "positions"

    id:        Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol:    Mapped[str] = mapped_column(String(50), nullable=False)
    exchange:  Mapped[str] = mapped_column(String(10), nullable=False)
    product:   Mapped[str] = mapped_column(String(10), nullable=False)
    quantity:  Mapped[int] = mapped_column(Integer, nullable=False)
    avg_price: Mapped[float] = mapped_column(Float, nullable=False)
    ltp:       Mapped[Optional[float]] = mapped_column(Float)
    pnl:       Mapped[Optional[float]] = mapped_column(Float)
    pnl_pct:   Mapped[Optional[float]] = mapped_column(Float)
    is_paper:  Mapped[bool] = mapped_column(Boolean, default=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class MarketEvent(Base):
    __tablename__ = "market_events"

    id:          Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_date:  Mapped[date] = mapped_column(Date, nullable=False, index=True)
    event_time:  Mapped[Optional[str]] = mapped_column(String(10))
    title:       Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category:    Mapped[Optional[str]] = mapped_column(String(50))
    impact:      Mapped[Optional[str]] = mapped_column(String(10))
    symbol:      Mapped[Optional[str]] = mapped_column(String(50))
    source:      Mapped[Optional[str]] = mapped_column(String(100))


class FiiDii(Base):
    __tablename__ = "fii_dii"

    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    fii_buy:    Mapped[Optional[float]] = mapped_column(Float)
    fii_sell:   Mapped[Optional[float]] = mapped_column(Float)
    fii_net:    Mapped[Optional[float]] = mapped_column(Float)
    dii_buy:    Mapped[Optional[float]] = mapped_column(Float)
    dii_sell:   Mapped[Optional[float]] = mapped_column(Float)
    dii_net:    Mapped[Optional[float]] = mapped_column(Float)
