"""
Tick ingestion pipeline.

Flow:
  Angel One WebSocket tick
    → normalize
    → publish to Redis channel "ticks:{symbol}"
    → store to TimescaleDB (batched, every 1 second)
    → trigger AI signal check (every N ticks)

This runs as a long-lived asyncio task started at app startup.
"""

import asyncio
import json
import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List

from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_redis
from app.core.utils import IST, SEGMENT_BY_EXCHANGE
from app.data.ingestion.angel_feed import AngelOneFeed, DEFAULT_INDEX_TOKENS
from app.websocket.manager import ws_manager

logger = logging.getLogger(__name__)

# Buffer ticks — flush to DB every second to avoid per-row overhead
_tick_buffer: List[dict] = []
_FLUSH_INTERVAL = 1.0  # seconds
_last_flush = time.monotonic()


async def _flush_to_db(ticks: List[dict]):
    """Batch insert ticks into TimescaleDB."""
    if not ticks:
        return
    rows = [
        {
            "time": t["timestamp"],
            "symbol": t["symbol"],
            "exchange": t["exchange"],
            "segment": _guess_segment(t["exchange"]),
            "ltp": t["ltp"],
            "open": t["open"],
            "high": t["high"],
            "low": t["low"],
            "close": t["close"],
            "volume": t["volume"],
            "oi": t["oi"],
            "bid": t["bid"],
            "ask": t["ask"],
            "total_buy_qty": t["total_buy_qty"],
            "total_sell_qty": t["total_sell_qty"],
        }
        for t in ticks
    ]
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("""
                    INSERT INTO ticks (time,symbol,exchange,segment,ltp,open,high,low,close,
                                       volume,oi,bid,ask,total_buy_qty,total_sell_qty)
                    VALUES (:time,:symbol,:exchange,:segment,:ltp,:open,:high,:low,:close,
                            :volume,:oi,:bid,:ask,:total_buy_qty,:total_sell_qty)
                    ON CONFLICT DO NOTHING
                """),
                rows,
            )
            await session.commit()
    except Exception as e:
        logger.error("DB flush error: %s", e)


def _guess_segment(exchange: str) -> str:
    return SEGMENT_BY_EXCHANGE.get(exchange, "EQ")


async def _on_tick(tick: dict):
    """Callback from Angel WebSocket — called for every incoming tick."""
    global _tick_buffer, _last_flush

    symbol = tick.get("symbol", "")
    if not symbol:
        return

    # 1. Push to Redis pub/sub for WebSocket broadcast
    redis: aioredis.Redis = await get_redis()
    await redis.publish(f"ticks:{symbol}", json.dumps(tick))

    # 2. Cache latest quote in Redis (key: quote:{symbol})
    await redis.setex(f"quote:{symbol}", 60, json.dumps(tick))

    # 3. Broadcast to subscribed WebSocket clients
    await ws_manager.broadcast(f"ticks:{symbol}", {"type": "tick", "data": tick})

    # 4. Buffer for DB (cap to prevent unbounded growth if flush stalls)
    if len(_tick_buffer) < 10_000:
        _tick_buffer.append(tick)
    now = time.monotonic()
    if now - _last_flush >= _FLUSH_INTERVAL:
        batch = _tick_buffer.copy()
        _tick_buffer.clear()
        _last_flush = now
        asyncio.create_task(_flush_to_db(batch))


async def start_feed(token_list: list = None):
    """Start the Angel One live feed. Runs forever."""
    feed = AngelOneFeed(on_tick=lambda tick: asyncio.create_task(_on_tick(tick)))

    if not feed.login():
        logger.error("Angel One login failed — live feed not started")
        logger.info("Running without live feed (historical data only)")
        return

    tokens = token_list or [DEFAULT_INDEX_TOKENS]
    feed.connect_live(tokens)
    logger.info("Angel One live feed started")

    # Keep alive — reconnect on disconnect
    while True:
        await asyncio.sleep(30)
        if not feed.is_connected:
            logger.warning("Feed disconnected — reconnecting...")
            if feed.refresh_session():
                feed.connect_live(tokens)
