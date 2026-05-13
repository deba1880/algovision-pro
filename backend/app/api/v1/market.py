"""
Market data REST API endpoints.
Works with both SQLite (dev) and PostgreSQL/TimescaleDB (prod).
"""

import json
import logging
from typing import Optional
from datetime import datetime, date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db, get_redis
from app.core.utils import IST, TIMEFRAME_SECONDS
from app.models.market import Tick, Instrument, Signal as SignalModel, MarketEvent
from app.data.ingestion.nse_scraper import NSEScraper
from app.ai.smc.detector import SMCDetector
from app.ai.signals.generator import SignalGenerator, Signal

logger = logging.getLogger(__name__)
router = APIRouter()

_scraper = NSEScraper()
_smc = SMCDetector()
_signal_gen = SignalGenerator()


# ─── Quote ─────────────────────────────────────────────────────────────────────

@router.get("/quote/{symbol}")
async def get_quote(
    symbol: str,
    exchange: str = Query("NSE"),
    redis=Depends(get_redis),
):
    key = f"quote:{symbol.upper()}"
    cached = await redis.get(key)
    if cached:
        return {"source": "live", "data": json.loads(cached)}

    # Fallback: fetch from NSE
    try:
        stocks = await _scraper.get_nifty50_stocks()
        match = next((s for s in stocks if s["symbol"] == symbol.upper()), None)
        if match:
            return {"source": "nse", "data": match}
    except Exception as e:
        logger.warning("NSE quote fetch failed: %s", e)

    raise HTTPException(status_code=404, detail=f"Quote not found for {symbol}")


# ─── Historical Candles ────────────────────────────────────────────────────────

_YF_TF_MAP = {
    "1m": ("1m", "7d"),   "3m": ("2m", "7d"),  "5m": ("5m", "60d"),
    "15m": ("15m", "60d"), "30m": ("30m", "60d"), "1h": ("60m", "730d"),
    "4h": ("1d", "5y"),   "1d": ("1d", "5y"),
}
_YF_INDEX_MAP = {
    "NIFTY": "^NSEI", "BANKNIFTY": "^NSEBANK", "SENSEX": "^BSESN",
    "FINNIFTY": "NIFTY_FIN_SERVICE.NS", "MIDCPNIFTY": "NIFTY_MIDCAP_50.NS",
}


async def _fetch_candles_yfinance(symbol: str, exchange: str, timeframe: str, limit: int) -> list:
    import asyncio
    import yfinance as yf

    yf_interval, period = _YF_TF_MAP.get(timeframe, ("15m", "60d"))
    sym = symbol.upper()
    suffix = ".NS" if exchange.upper() in ("NSE", "NFO") else ".BO" if exchange.upper() in ("BSE", "BFO") else ""
    ticker = _YF_INDEX_MAP.get(sym, f"{sym}{suffix}")

    def _download():
        return yf.Ticker(ticker).history(period=period, interval=yf_interval, auto_adjust=True)

    loop = asyncio.get_event_loop()
    try:
        df = await loop.run_in_executor(None, _download)
        if df is None or df.empty:
            return []
        candles = []
        for ts, row in df.tail(limit).iterrows():
            candles.append({
                "time": int(ts.timestamp()),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row.get("Volume", 0)),
                "oi": 0,
            })
        return candles
    except Exception as e:
        logger.warning("yfinance fallback failed for %s: %s", ticker, e)
        return []


@router.get("/candles/{symbol}")
async def get_candles(
    symbol: str,
    exchange: str = Query("NSE"),
    timeframe: str = Query("15m"),
    limit: int = Query(500),
    db: AsyncSession = Depends(get_db),
):
    """Fetch OHLCV candles aggregated from the ticks table."""
    bucket_secs = TIMEFRAME_SECONDS.get(timeframe, 900)

    if settings.DEV_MODE:
        # SQLite-compatible grouping (no TimescaleDB)
        result = await db.execute(text("""
            SELECT
                (CAST(strftime('%s', time) AS INTEGER) / :bucket) * :bucket AS bucket,
                MIN(time) AS bar_time,
                MIN(CASE WHEN open IS NOT NULL THEN open END) AS open,
                MAX(high)  AS high,
                MIN(low)   AS low,
                MAX(CASE WHEN close IS NOT NULL THEN close END) AS close,
                SUM(COALESCE(volume, 0)) AS volume,
                MAX(COALESCE(oi, 0)) AS oi
            FROM ticks
            WHERE symbol = :symbol AND exchange = :exchange
            GROUP BY bucket
            ORDER BY bucket DESC
            LIMIT :limit
        """), {"bucket": bucket_secs, "symbol": symbol.upper(), "exchange": exchange.upper(), "limit": limit})
    else:
        # PostgreSQL / TimescaleDB
        interval = f"{bucket_secs} seconds"
        result = await db.execute(text("""
            SELECT
                EXTRACT(EPOCH FROM time_bucket(:interval, time))::int AS bucket,
                first(open, time) AS open, max(high) AS high,
                min(low) AS low, last(close, time) AS close,
                sum(volume) AS volume, last(oi, time) AS oi
            FROM ticks
            WHERE symbol = :symbol AND exchange = :exchange
            GROUP BY time_bucket(:interval, time)
            ORDER BY time_bucket(:interval, time) DESC
            LIMIT :limit
        """), {"interval": interval, "symbol": symbol.upper(), "exchange": exchange.upper(), "limit": limit})

    rows = result.fetchall()
    candles = [
        {
            "time": int(row[0]),
            "open": float(row[2] or 0),
            "high": float(row[3] or 0),
            "low":  float(row[4] or 0),
            "close": float(row[5] or 0),
            "volume": int(row[6] or 0),
            "oi": int(row[7] or 0),
        }
        for row in reversed(rows)
        if row[2] and row[5]  # skip rows with no open/close
    ]

    if not candles:
        candles = await _fetch_candles_yfinance(symbol, exchange, timeframe, limit)

    return {"symbol": symbol, "exchange": exchange, "timeframe": timeframe, "candles": candles}


# ─── Options Chain ─────────────────────────────────────────────────────────────

@router.get("/options-chain/{symbol}")
async def get_options_chain(symbol: str, redis=Depends(get_redis)):
    cache_key = f"options_chain:{symbol.upper()}"
    cached = await redis.get(cache_key)
    if cached:
        return {"source": "cache", "data": json.loads(cached)}

    try:
        data = await _scraper.get_options_chain(symbol.upper())
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Options chain fetch failed: {e}. NSE may be blocking non-Indian IPs.",
        )

    if not data:
        raise HTTPException(
            status_code=503,
            detail=(
                "Options chain unavailable. NSE India blocks non-Indian IPs. "
                "This feature works when the backend is hosted in India or run locally."
            ),
        )

    await redis.setex(cache_key, 60, json.dumps(data))
    return {"source": "live", "data": data}


# ─── Option LTP (served from cache) ──────────────────────────────────────────

@router.get("/option-ltp/{underlying}")
async def get_option_ltp(
    underlying: str,
    strike: float = Query(...),
    option_type: str = Query(...),   # CE or PE
    expiry: str = Query(...),
    redis=Depends(get_redis),
):
    """Return current LTP for a specific option contract from the options chain cache."""
    cache_key = f"options_chain:{underlying.upper()}"
    cached = await redis.get(cache_key)
    if not cached:
        raise HTTPException(status_code=503, detail="Options chain cache is empty. Backend may not have warmed up yet.")

    chain = json.loads(cached)
    ot = option_type.upper()
    for row in chain.get("data", []):
        if abs(row["strike"] - strike) < 0.01 and row.get("expiry") == expiry:
            side = row.get(ot, {})
            ltp = side.get("ltp")
            if ltp is None:
                raise HTTPException(status_code=404, detail=f"No LTP for {underlying} {strike} {ot} {expiry}")
            return {
                "underlying": underlying.upper(),
                "strike": strike,
                "option_type": ot,
                "expiry": expiry,
                "ltp": ltp,
                "oi": side.get("oi", 0),
                "iv": side.get("iv", 0),
                "timestamp": chain.get("timestamp", ""),
            }
    raise HTTPException(status_code=404, detail=f"Strike {strike} {ot} not found in chain for {underlying}")


# ─── Indices ──────────────────────────────────────────────────────────────────

@router.get("/indices")
async def get_indices(redis=Depends(get_redis)):
    cached = await redis.get("nse:indices")
    if cached:
        return json.loads(cached)

    try:
        indices = await _scraper.get_indices()
    except Exception as e:
        logger.warning("Indices fetch failed: %s", e)
        return {"data": []}

    result = {"data": indices}
    await redis.setex("nse:indices", 30, json.dumps(result))
    return result


# ─── Market Breadth ────────────────────────────────────────────────────────────

@router.get("/breadth")
async def get_market_breadth(redis=Depends(get_redis)):
    cached = await redis.get("nse:breadth")
    if cached:
        return json.loads(cached)

    try:
        breadth = await _scraper.get_market_breadth()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not breadth:
        raise HTTPException(status_code=503, detail="Breadth data unavailable")

    await redis.setex("nse:breadth", 60, json.dumps(breadth))
    return breadth


# ─── FII / DII ────────────────────────────────────────────────────────────────

@router.get("/fii-dii")
async def get_fii_dii(redis=Depends(get_redis)):
    cached = await redis.get("nse:fii_dii")
    if cached:
        return json.loads(cached)

    try:
        data = await _scraper.get_fii_dii()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not data:
        raise HTTPException(status_code=503, detail="FII/DII data unavailable")

    await redis.setex("nse:fii_dii", 300, json.dumps(data))
    return data


# ─── Market Events ────────────────────────────────────────────────────────────

@router.get("/events")
async def get_events(days_ahead: int = Query(30), db: AsyncSession = Depends(get_db)):
    today = date.today()
    to_date = today + timedelta(days=days_ahead)
    result = await db.execute(
        select(MarketEvent)
        .where(MarketEvent.event_date >= today, MarketEvent.event_date <= to_date)
        .order_by(MarketEvent.event_date, MarketEvent.event_time)
        .limit(100)
    )
    events = result.scalars().all()
    return {
        "events": [
            {
                "id": e.id,
                "date": str(e.event_date),
                "time": e.event_time,
                "title": e.title,
                "description": e.description,
                "category": e.category,
                "impact": e.impact,
                "symbol": e.symbol,
            }
            for e in events
        ]
    }


# ─── AI Signal ────────────────────────────────────────────────────────────────

@router.get("/signal/{symbol}")
async def get_signal(
    symbol: str,
    exchange: str = Query("NSE"),
    timeframe: str = Query("15m"),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    import pandas as pd

    cache_key = f"signal:{symbol.upper()}:{timeframe}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    # Load candles from ticks table
    bucket_secs = TIMEFRAME_SECONDS.get(timeframe, 900)

    if settings.DEV_MODE:
        result = await db.execute(text("""
            SELECT
                (CAST(strftime('%s', time) AS INTEGER) / :bucket) * :bucket AS bucket,
                MIN(CASE WHEN open IS NOT NULL THEN open END) AS open,
                MAX(high) AS high, MIN(low) AS low,
                MAX(CASE WHEN close IS NOT NULL THEN close END) AS close,
                SUM(COALESCE(volume, 0)) AS volume
            FROM ticks
            WHERE symbol = :symbol AND exchange = :exchange
            GROUP BY bucket
            ORDER BY bucket
            LIMIT 300
        """), {"bucket": bucket_secs, "symbol": symbol.upper(), "exchange": exchange.upper()})
    else:
        result = await db.execute(text("""
            SELECT EXTRACT(EPOCH FROM time_bucket(:interval, time))::int,
                   first(open, time), max(high), min(low), last(close, time), sum(volume)
            FROM ticks WHERE symbol=:symbol AND exchange=:exchange
            GROUP BY time_bucket(:interval, time) ORDER BY 1 LIMIT 300
        """), {"interval": f"{bucket_secs} seconds", "symbol": symbol.upper(), "exchange": exchange.upper()})

    rows = result.fetchall()
    if len(rows) < 30:
        raise HTTPException(status_code=422, detail=f"Need at least 30 candles. Got {len(rows)}. Load a symbol first.")

    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    df = df.set_index("time")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "close"])

    # Get options data
    options_data = None
    if symbol.upper() in ("NIFTY", "BANKNIFTY", "FINNIFTY"):
        options_raw = await redis.get(f"options_chain:{symbol.upper()}")
        if options_raw:
            options_data = json.loads(options_raw)

    fii_raw = await redis.get("nse:fii_dii")
    fii_net = json.loads(fii_raw).get("fii_net") if fii_raw else None

    signal: Signal = _signal_gen.generate(
        symbol=symbol.upper(), exchange=exchange.upper(),
        df=df, timeframe=timeframe,
        options_data=options_data, fii_net=fii_net,
    )

    result_dict = signal.to_dict()
    result_dict["generated_at"] = datetime.now(IST).isoformat()
    await redis.setex(cache_key, 120, json.dumps(result_dict))
    return result_dict


# ─── Symbol Search ────────────────────────────────────────────────────────────

@router.get("/search")
async def search_symbols(q: str = Query(..., min_length=1), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Instrument)
        .where(
            Instrument.is_active == True,
            (Instrument.symbol.ilike(f"%{q}%")) | (Instrument.name.ilike(f"%{q}%"))
        )
        .order_by(Instrument.exchange, Instrument.symbol)
        .limit(20)
    )
    instruments = result.scalars().all()
    return {
        "results": [
            {
                "token": i.token,
                "symbol": i.symbol,
                "name": i.name,
                "exchange": i.exchange,
                "segment": i.segment,
                "type": i.instrument_type,
                "expiry": str(i.expiry) if i.expiry else None,
                "strike": i.strike,
                "lot_size": i.lot_size,
            }
            for i in instruments
        ]
    }
