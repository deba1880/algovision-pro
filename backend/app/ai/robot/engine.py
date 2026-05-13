"""
Intelligent Paper Trading Robot Engine.
Runs as an asyncio task; state lives in module-level singletons (single event loop, no locks needed).
"""

from __future__ import annotations
import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from typing import Optional

import pandas as pd
import yfinance as yf

from app.core.utils import IST, LOT_SIZES
from app.core.config import settings
from app.ai.smc.detector import SMCDetector
from app.ai.signals.generator import SignalGenerator

logger = logging.getLogger(__name__)

_smc = SMCDetector()
_signal_gen = SignalGenerator()

_YF_INDEX_MAP = {
    "NIFTY":     "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "FINNIFTY":  "NIFTY_FIN_SERVICE.NS",
}


# ─── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class RobotConfig:
    symbols: list[str]              = field(default_factory=lambda: ["NIFTY", "BANKNIFTY"])
    lot_sizes: dict[str, int]       = field(default_factory=lambda: dict(LOT_SIZES))
    max_lots_per_trade: int         = 2
    capital_per_trade_pct: float    = 5.0
    strike_selection: str           = "ATM"       # ATM | OTM1 | OTM2 | ITM1
    expiry_preference: str          = "WEEKLY"    # WEEKLY | MONTHLY
    timeframe: str                  = "15m"
    target1_pct: float              = 30.0
    target2_pct: float              = 60.0
    target3_pct: float              = 100.0
    stoploss_pct: float             = 30.0
    trail_sl_after_t1: bool         = True
    exit1_qty_pct: int              = 40
    exit2_qty_pct: int              = 40
    exit3_qty_pct: int              = 20
    max_trades_per_day: int         = 3
    auto_square_off_time: str       = "15:15"
    enabled: bool                   = False


@dataclass
class RobotTrade:
    id: str
    symbol: str
    option_type: str      # CE | PE
    strike: float
    expiry: str
    entry_price: float
    current_price: float
    quantity: int
    lots: int
    sl_price: float
    t1_price: float
    t2_price: float
    t3_price: float
    t1_hit: bool                     = False
    t2_hit: bool                     = False
    status: str                      = "OPEN"
    entry_time: str                  = ""
    exit_time: Optional[str]         = None
    exit_price: Optional[float]      = None
    pnl: float                       = 0.0
    pnl_pct: float                   = 0.0
    reasons: list[str]               = field(default_factory=list)


# ─── Module-level state ───────────────────────────────────────────────────────

_robot_task: Optional[asyncio.Task]  = None
_monitor_task: Optional[asyncio.Task] = None
_config: RobotConfig                 = RobotConfig()
_active_trades: dict[str, RobotTrade] = {}   # id → trade
_trade_history: list[RobotTrade]     = []
_today_trade_count: int              = 0
_today_date: str                     = ""
_last_analysis: dict                 = {}     # symbol → last analysis dict


# ─── Public API ───────────────────────────────────────────────────────────────

async def start_robot() -> bool:
    global _robot_task, _monitor_task
    if _robot_task and not _robot_task.done():
        return False  # already running
    _robot_task = asyncio.create_task(_robot_loop())
    _monitor_task = asyncio.create_task(_monitor_loop())
    logger.info("Robot started")
    return True


async def stop_robot() -> None:
    global _robot_task, _monitor_task
    for task in (_robot_task, _monitor_task):
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    _robot_task = None
    _monitor_task = None
    logger.info("Robot stopped")


def is_running() -> bool:
    return bool(_robot_task and not _robot_task.done())


def get_status() -> dict:
    today_pnl = sum(
        t.pnl for t in _trade_history
        if t.entry_time.startswith(_today_date) and t.status != "OPEN"
    ) + sum(t.pnl for t in _active_trades.values())
    return {
        "running": is_running(),
        "active_trades": [asdict(t) for t in list(_active_trades.values())],
        "trade_history": [asdict(t) for t in _trade_history[-20:]],
        "today_pnl": round(today_pnl, 2),
        "today_trades": _today_trade_count,
        "last_analysis": _last_analysis,
    }


def get_config() -> RobotConfig:
    return _config


async def update_config(new_cfg: dict) -> RobotConfig:
    global _config
    cur = asdict(_config)
    cur.update({k: v for k, v in new_cfg.items() if v is not None})
    _config = RobotConfig(**{k: cur[k] for k in RobotConfig.__dataclass_fields__})
    return _config


def get_trades(status_filter: str | None = None, limit: int = 50) -> list[dict]:
    all_trades = list(_active_trades.values()) + _trade_history
    if status_filter:
        all_trades = [t for t in all_trades if t.status == status_filter]
    return [asdict(t) for t in all_trades[-limit:]]


# ─── Expiry classification (shared with strategy.py) ─────────────────────────

def classify_expiries(expiry_dates: list[str]) -> tuple[list[str], list[str]]:
    """Split expiry strings into (weekly, monthly)."""
    from datetime import date, timedelta

    MONTHS = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
              "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}

    def parse(s: str) -> date | None:
        parts = s.split("-")
        if len(parts) == 3:
            try:
                return date(int(parts[2]), MONTHS.get(parts[1], 1), int(parts[0]))
            except Exception:
                pass
        return None

    def is_last_thursday(d: date) -> bool:
        if d.weekday() != 3:
            return False
        return (d + timedelta(weeks=1)).month != d.month

    weekly, monthly = [], []
    for e in expiry_dates:
        d = parse(e)
        if d and is_last_thursday(d):
            monthly.append(e)
        else:
            weekly.append(e)
    return weekly, monthly


# ─── Candle helpers ───────────────────────────────────────────────────────────

def _prepare_candle_df(raw_df) -> pd.DataFrame | None:
    """Normalize a raw yfinance DataFrame to lowercase OHLCV columns. Returns None if too small."""
    if raw_df is None or len(raw_df) < 5:
        return None
    if isinstance(raw_df.columns, pd.MultiIndex):
        raw_df = raw_df.copy()
        raw_df.columns = [col[0] for col in raw_df.columns]
    df = raw_df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df.columns = ["open", "high", "low", "close", "volume"]
    return df


# ─── Analysis cycle (every 5 minutes) ────────────────────────────────────────

async def _robot_loop():
    while True:
        try:
            await _run_cycle()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Robot analysis cycle error: %s", e)
        await asyncio.sleep(300)   # 5 minutes


async def _run_cycle():
    global _today_trade_count, _today_date

    now = datetime.now(IST)
    time_str = now.strftime("%H:%M")
    today_str = now.strftime("%Y-%m-%d")

    # Reset daily counter on new day
    if today_str != _today_date:
        _today_date = today_str
        _today_trade_count = 0

    # Auto square-off
    if time_str >= _config.auto_square_off_time and _active_trades:
        await _square_off_all("CLOSED_EOD")
        return

    # Only analyze during market hours with buffer
    if not ("09:20" <= time_str <= "15:10"):
        return

    from app.core.database import get_redis
    redis = await get_redis()

    for symbol in _config.symbols:
        try:
            await _analyze_symbol(symbol, redis)
        except Exception as e:
            logger.error("Robot error for %s: %s", symbol, e)


async def _analyze_symbol(symbol: str, redis):
    from app.websocket.manager import ws_manager

    yf_sym = _YF_INDEX_MAP.get(symbol, f"{symbol}.NS")

    # Fetch candles
    tf = _config.timeframe
    yf_period = "30d" if tf in ("5m", "15m") else "60d"
    yf_interval = {"5m": "5m", "15m": "15m"}.get(tf, "15m")

    raw = await asyncio.to_thread(
        yf.download, yf_sym,
        period=yf_period, interval=yf_interval,
        auto_adjust=True, progress=False,
    )
    df = _prepare_candle_df(raw)
    if df is None or len(df) < 30:
        return
    df = df.tail(300)

    # Fetch options data from cache
    options_raw = await redis.get(f"options_chain:{symbol}")
    options_data = json.loads(options_raw) if options_raw else None

    fii_raw = await redis.get("nse:fii_dii")
    fii_net = json.loads(fii_raw).get("fii_net") if fii_raw else None

    # Run analysis
    smc_result = _smc.analyse(df, _config.timeframe)
    signal = _signal_gen.generate(
        symbol=symbol, exchange="NSE",
        df=df, timeframe=_config.timeframe,
        options_data=options_data, fii_net=fii_net,
    )

    underlying_price = float(df["close"].iloc[-1])

    # Build analysis summary
    analysis = {
        "symbol": symbol,
        "trend": smc_result.get("trend", "SIDEWAYS"),
        "signal_type": signal.signal_type,
        "signal_strength": round(signal.strength, 3),
        "underlying_price": round(underlying_price, 2),
        "reasons": signal.reasons[:4],
        "warnings": signal.warnings[:2],
        "bos_choch": smc_result.get("bos_choch", [])[-3:],
        "stop_hunts": smc_result.get("stop_hunts", [])[-2:],
        "timestamp": datetime.now(IST).isoformat(),
    }
    _last_analysis[symbol] = analysis

    await ws_manager.broadcast("market", {"type": "robot_analysis", "data": analysis})

    # Check entry
    if _today_trade_count < _config.max_trades_per_day:
        await _check_entry(symbol, signal, df, smc_result, options_data, underlying_price, redis)


async def _check_entry(symbol, signal, df, smc_result, options_data, underlying_price, redis):
    global _today_trade_count
    from app.ai.robot.strategy import check_entry_conditions, select_option
    from app.ai.robot.risk_manager import calculate_position_size, calculate_trade_levels, get_lot_size
    from app.websocket.manager import ws_manager

    # Don't re-enter if we already have an open trade for this symbol
    existing = [t for t in _active_trades.values() if t.symbol == symbol and t.status == "OPEN"]
    if existing:
        return

    ok, reasons = check_entry_conditions(signal, df, smc_result, options_data, _config)
    if not ok:
        return

    if not options_data:
        logger.debug("No options data for %s, cannot select option", symbol)
        return

    result = select_option(
        symbol=symbol,
        signal_type=signal.signal_type,
        underlying_price=underlying_price,
        options_data=options_data,
        config=_config,
        expiry_preference=_config.expiry_preference,
    )
    if not result:
        return

    strike, expiry, option_type, ltp = result

    lots, qty = calculate_position_size(
        _config, settings.PAPER_TRADE_CAPITAL, ltp,
        _today_trade_count, len(_active_trades),
    )
    if lots == 0:
        return

    sl, t1, t2, t3 = calculate_trade_levels(ltp, _config)

    trade = RobotTrade(
        id=str(uuid.uuid4())[:8],
        symbol=symbol,
        option_type=option_type,
        strike=strike,
        expiry=expiry,
        entry_price=ltp,
        current_price=ltp,
        quantity=qty,
        lots=lots,
        sl_price=sl,
        t1_price=t1,
        t2_price=t2,
        t3_price=t3,
        entry_time=datetime.now(IST).isoformat(),
        reasons=reasons,
    )

    _active_trades[trade.id] = trade
    _today_trade_count += 1

    logger.info("ROBOT ENTRY: %s %s %s @ ₹%.2f (%d lots)", symbol, strike, option_type, ltp, lots)

    await ws_manager.broadcast("market", {
        "type": "robot_trade",
        "data": asdict(trade),
    })

    # Record paper order in DB
    await _record_paper_order(symbol, option_type, strike, expiry, qty, ltp, "BUY")


# ─── Monitor loop (every 60 seconds) ─────────────────────────────────────────

async def _monitor_loop():
    while True:
        try:
            await _check_exits()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Robot monitor error: %s", e)
        await asyncio.sleep(60)


async def _check_exits():
    if not _active_trades:
        return

    from app.core.database import get_redis
    from app.ai.robot.strategy import check_exit_conditions
    from app.ai.robot.risk_manager import update_trailing_sl
    from app.websocket.manager import ws_manager

    redis = await get_redis()

    for trade_id in list(_active_trades.keys()):
        trade = _active_trades.get(trade_id)
        if not trade or trade.status != "OPEN":
            continue

        symbol = trade.symbol
        yf_sym = _YF_INDEX_MAP.get(symbol, f"{symbol}.NS")

        try:
            raw = await asyncio.to_thread(
                yf.download, yf_sym,
                period="5d", interval="5m",
                auto_adjust=True, progress=False,
            )
            df = _prepare_candle_df(raw)
            if df is None:
                continue

            # Try to get current option LTP from cache
            options_raw = await redis.get(f"options_chain:{symbol}")
            current_ltp = trade.current_price  # default to last known
            if options_raw:
                chain = json.loads(options_raw)
                for row in chain.get("data", []):
                    if abs(row["strike"] - trade.strike) < 0.01 and row.get("expiry") == trade.expiry:
                        ltp = row.get(trade.option_type, {}).get("ltp")
                        if ltp:
                            current_ltp = ltp
                            break

            if current_ltp != trade.current_price:
                trade.current_price = current_ltp
                trade.pnl = round((current_ltp - trade.entry_price) * trade.quantity, 2)
                trade.pnl_pct = round((current_ltp - trade.entry_price) / trade.entry_price * 100, 2)

            # Trail SL after T1
            if _config.trail_sl_after_t1 and trade.t1_hit:
                trade.sl_price = update_trailing_sl(trade, current_ltp, _config)

            # Check T1 hit (partial exit handled separately)
            if not trade.t1_hit and current_ltp >= trade.t1_price:
                trade.t1_hit = True
                await ws_manager.broadcast("market", {
                    "type": "robot_analysis",
                    "data": {
                        "symbol": symbol,
                        "event": "T1_HIT",
                        "trade_id": trade_id,
                        "price": current_ltp,
                        "timestamp": datetime.now(IST).isoformat(),
                    }
                })
                logger.info("ROBOT T1 HIT: %s %s @ ₹%.2f", symbol, trade.option_type, current_ltp)

            smc_result = _smc.analyse(df, "5m")
            should_exit, reason, new_status = check_exit_conditions(
                trade, current_ltp, smc_result, df, _config
            )

            if should_exit:
                await _close_trade(trade, current_ltp, reason, new_status)

        except Exception as e:
            logger.error("Monitor error for trade %s: %s", trade_id, e)


async def _close_trade(trade: RobotTrade, exit_price: float, reason: str, status: str):
    from app.websocket.manager import ws_manager

    trade.status = status
    trade.exit_time = datetime.now(IST).isoformat()
    trade.exit_price = exit_price
    trade.pnl = round((exit_price - trade.entry_price) * trade.quantity, 2)
    trade.pnl_pct = round((exit_price - trade.entry_price) / trade.entry_price * 100, 2)

    _trade_history.append(trade)
    if len(_trade_history) > 200:
        _trade_history.pop(0)
    del _active_trades[trade.id]

    logger.info("ROBOT EXIT: %s %s @ ₹%.2f | P&L ₹%.2f | %s",
                trade.symbol, trade.option_type, exit_price, trade.pnl, reason)

    trade_dict = asdict(trade)
    trade_dict["exit_reason"] = reason

    await ws_manager.broadcast("market", {
        "type": "robot_exit",
        "data": trade_dict,
    })

    await _record_paper_order(
        trade.symbol, trade.option_type, trade.strike,
        trade.expiry, trade.quantity, exit_price, "SELL"
    )


async def _square_off_all(status: str):
    from app.core.database import get_redis
    redis = await get_redis()

    for trade_id in list(_active_trades.keys()):
        trade = _active_trades.get(trade_id)
        if not trade:
            continue
        # Use last known price or entry
        await _close_trade(trade, trade.current_price, "Auto square-off", status)


async def _record_paper_order(symbol: str, option_type: str, strike: float, expiry: str,
                               qty: int, price: float, transaction: str):
    """Persist paper order to DB for audit trail."""
    try:
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import text

        option_symbol = f"{symbol}{strike:.0f}{option_type}"
        async with AsyncSessionLocal() as db:
            await db.execute(text("""
                INSERT INTO orders (symbol, exchange, "transaction", order_type, product,
                                    quantity, price, status, avg_price, filled_qty,
                                    is_paper, broker)
                VALUES (:symbol, 'NFO', :transaction, 'MARKET', 'NRML',
                        :qty, :price, 'COMPLETE', :price, :qty, TRUE, 'ROBOT')
            """), {
                "symbol": option_symbol,
                "transaction": transaction,
                "qty": qty,
                "price": price,
            })
            await db.commit()
    except Exception as e:
        logger.warning("Failed to record robot paper order: %s", e)
