"""
AlgoVision Pro — FastAPI Application Entry Point
"""

import asyncio
import logging
import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from app.core.config import settings
from app.core.database import init_db, get_redis
from app.api.v1 import market, trading, backtest, alerts as alerts_api
from app.websocket.manager import ws_manager
from app.data.tick_pipeline import start_feed

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("algotrade")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("AlgoVision Pro starting up")

    # Initialize DB tables
    await init_db()
    logger.info("Database initialized")

    # Start Angel One live feed in background (won't fail if creds not set)
    asyncio.create_task(start_feed())
    logger.info("Data feed task started")

    # Start Redis subscriber for options chain refresh (every 60s during market hours)
    asyncio.create_task(_periodic_nse_refresh())

    # Auto-generate signals every 15 minutes for watchlist symbols
    asyncio.create_task(_periodic_signal_scan())

    # Seed market events from NSE corporate announcements (on startup + every 6h)
    asyncio.create_task(_seed_market_events())

    yield

    logger.info("AlgoVision Pro shutting down")


app = FastAPI(
    title="AlgoVision Pro API",
    version="1.0.0",
    description="Indian Market Algorithmic Trading Platform",
    lifespan=lifespan,
)

# ─── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# ─── Routers ──────────────────────────────────────────────────────────────────

app.include_router(market.router,   prefix="/api/v1/market",   tags=["Market Data"])
app.include_router(trading.router,  prefix="/api/v1/trading",  tags=["Trading"])
app.include_router(backtest.router,    prefix="/api/v1/backtest", tags=["Backtesting"])
app.include_router(alerts_api.router,  prefix="/api/v1/alerts",   tags=["Alerts"])


# ─── WebSocket Endpoints ──────────────────────────────────────────────────────

@app.websocket("/ws/ticks/{symbol}")
async def websocket_ticks(websocket: WebSocket, symbol: str):
    """
    Real-time tick stream for a symbol.
    Client subscribes and receives every tick as JSON.
    """
    channel = f"ticks:{symbol.upper()}"
    await ws_manager.connect(websocket, channel)
    logger.info("WS client connected for %s", symbol)
    try:
        while True:
            # Keep connection alive; data is pushed by tick_pipeline
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        logger.info("WS client disconnected from %s", symbol)


@app.websocket("/ws/signals")
async def websocket_signals(websocket: WebSocket):
    """Stream AI signals as they're generated."""
    await ws_manager.connect(websocket, "signals")
    try:
        while True:
            await asyncio.sleep(60)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.websocket("/ws/market")
async def websocket_market(websocket: WebSocket):
    """Broadcast market-wide updates: indices, breadth, FII/DII."""
    await ws_manager.connect(websocket, "market")
    try:
        while True:
            await asyncio.sleep(15)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "paper_trade_mode": settings.PAPER_TRADE_MODE,
        "ws_clients": ws_manager.client_count(),
    }


@app.get("/")
async def root():
    return {
        "name": "AlgoVision Pro",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


# ─── Background Tasks ─────────────────────────────────────────────────────────

async def _periodic_nse_refresh():
    """
    Refresh NSE data (indices, breadth, FII/DII, options chain for Nifty/BankNifty)
    every 60 seconds during market hours. Pushes updates to WebSocket clients.
    """
    import json
    from datetime import datetime
    from app.data.ingestion.nse_scraper import NSEScraper
    from app.core.utils import IST

    scraper = NSEScraper()

    tick = 0
    while True:
        try:
            now = datetime.now(IST)
            time_str = now.strftime("%H:%M")

            if "09:00" <= time_str <= "16:00":
                redis = await get_redis()

                # Fetch indices, breadth, and FII/DII in parallel
                indices, breadth, fii_dii = await asyncio.gather(
                    scraper.get_indices(),
                    scraper.get_market_breadth(),
                    scraper.get_fii_dii(),
                    return_exceptions=True,
                )

                if isinstance(indices, list):
                    await redis.setex("nse:indices", 60, json.dumps({"data": indices}))
                    await ws_manager.broadcast("market", {"type": "indices", "data": indices})

                if isinstance(breadth, dict):
                    await redis.setex("nse:breadth", 60, json.dumps(breadth))
                    await ws_manager.broadcast("market", {"type": "breadth", "data": breadth})

                if isinstance(fii_dii, dict):
                    await redis.setex("nse:fii_dii", 300, json.dumps(fii_dii))
                    await ws_manager.broadcast("market", {"type": "fii_dii", "data": fii_dii})

                # Options chain every 2 minutes (every other tick)
                if tick % 2 == 0:
                    chains = await asyncio.gather(
                        *[scraper.get_options_chain(sym) for sym in ("NIFTY", "BANKNIFTY", "FINNIFTY")],
                        return_exceptions=True,
                    )
                    for sym, oc in zip(("NIFTY", "BANKNIFTY", "FINNIFTY"), chains):
                        if isinstance(oc, dict):
                            await redis.setex(f"options_chain:{sym}", 120, json.dumps(oc))
                            await ws_manager.broadcast("market", {"type": "options_chain", "symbol": sym, "data": oc})

            tick += 1
            await asyncio.sleep(60)
        except Exception as e:
            logger.error("NSE refresh error: %s", e)
            await asyncio.sleep(60)


# ─────────────────────────────────────────────────────────────────────────────

async def _periodic_signal_scan():
    """
    Auto-generate signals for watchlist symbols every 15 minutes during market hours.
    Uses yfinance in DEV_MODE to fetch recent OHLCV data; live ticks otherwise.
    Broadcasts results via WebSocket and sends Telegram/email alerts on BUY/SELL.
    """
    import json
    import pandas as pd
    import yfinance as yf
    from datetime import datetime
    from app.core.utils import IST
    from app.ai.signals.generator import SignalGenerator
    from app.alerts.notifier import notifier

    _signal_gen = SignalGenerator()

    _WATCHLIST = [
        ("NIFTY",     "^NSEI",                  "NSE"),
        ("BANKNIFTY", "^NSEBANK",               "NSE"),
        ("FINNIFTY",  "NIFTY_FIN_SERVICE.NS",   "NFO"),
        ("RELIANCE",  "RELIANCE.NS",             "NSE"),
        ("TCS",       "TCS.NS",                  "NSE"),
        ("INFY",      "INFY.NS",                 "NSE"),
        ("HDFCBANK",  "HDFCBANK.NS",             "NSE"),
        ("ICICIBANK", "ICICIBANK.NS",            "NSE"),
        ("SBIN",      "SBIN.NS",                 "NSE"),
    ]

    while True:
        try:
            now = datetime.now(IST)
            time_str = now.strftime("%H:%M")

            if "09:15" <= time_str <= "15:30":
                redis = await get_redis()

                for symbol, yf_sym, exchange in _WATCHLIST:
                    try:
                        df = await asyncio.to_thread(
                            yf.download, yf_sym,
                            period="60d", interval="15m",
                            auto_adjust=True, progress=False,
                        )
                        if df is None or len(df) < 30:
                            continue

                        if isinstance(df.columns, pd.MultiIndex):
                            df.columns = [col[0] for col in df.columns]
                        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
                        df.columns = ["open", "high", "low", "close", "volume"]
                        df = df.tail(300)

                        options_data = None
                        if symbol in ("NIFTY", "BANKNIFTY", "FINNIFTY"):
                            raw = await redis.get(f"options_chain:{symbol}")
                            if raw:
                                options_data = json.loads(raw)

                        fii_raw = await redis.get("nse:fii_dii")
                        fii_net = json.loads(fii_raw).get("fii_net") if fii_raw else None

                        signal = _signal_gen.generate(
                            symbol=symbol, exchange=exchange,
                            df=df, timeframe="15m",
                            options_data=options_data, fii_net=fii_net,
                        )

                        sig_dict = signal.to_dict()
                        sig_dict["generated_at"] = now.isoformat()

                        await redis.setex(f"signal:{symbol}:15m", 900, json.dumps(sig_dict))
                        await ws_manager.broadcast("signals", {"type": "signal", "data": sig_dict})

                        if signal.signal_type in ("BUY", "SELL") and signal.strength >= 0.5:
                            logger.info(
                                "Signal: %s %s strength=%.2f", signal.signal_type, symbol, signal.strength
                            )
                            await notifier.notify_signal(sig_dict)

                        await asyncio.sleep(3)  # rate-limit yfinance calls

                    except Exception as e:
                        logger.error("Signal scan error [%s]: %s", symbol, e)

        except Exception as e:
            logger.error("Signal scanner error: %s", e)

        await asyncio.sleep(900)  # 15 minutes


# ─────────────────────────────────────────────────────────────────────────────

async def _seed_market_events():
    """
    Populate market_events table from NSE corporate announcements and
    pre-computed F&O expiry dates. Runs once on startup, then every 6 hours.
    """
    import json
    from datetime import datetime, date, timedelta
    from app.data.ingestion.nse_scraper import NSEScraper
    from app.models.market import MarketEvent
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import select

    scraper = NSEScraper()

    def _next_thursdays(weeks: int = 12) -> list[date]:
        """Compute upcoming Thursday dates (weekly F&O expiry)."""
        today = date.today()
        # Find next Thursday (weekday 3)
        days_until = (3 - today.weekday()) % 7
        if days_until == 0:
            days_until = 7
        first = today + timedelta(days=days_until)
        return [first + timedelta(weeks=w) for w in range(weeks)]

    def _monthly_expiry(months: int = 6) -> list[date]:
        """Last Thursday of each month for the next N months."""
        expiries = []
        today = date.today()
        year, month = today.year, today.month
        for _ in range(months):
            # Last day of month
            if month == 12:
                last = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                last = date(year, month + 1, 1) - timedelta(days=1)
            # Walk back to Thursday
            while last.weekday() != 3:
                last -= timedelta(days=1)
            if last >= today:
                expiries.append(last)
            month += 1
            if month > 12:
                month = 1
                year += 1
        return expiries

    async def _upsert_event(db, title: str, ev_date: date, category: str,
                             impact: str, time_str: str = None,
                             description: str = None, symbol: str = None,
                             source: str = "computed"):
        title = title[:200]  # enforce DB column length
        existing = await db.execute(
            select(MarketEvent).where(
                MarketEvent.title == title,
                MarketEvent.event_date == ev_date,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return
        db.add(MarketEvent(
            event_date=ev_date,
            event_time=time_str,
            title=title,
            description=description,
            category=category,
            impact=impact,
            symbol=symbol,
            source=source,
        ))

    while True:
        try:
            async with AsyncSessionLocal() as db:
                # ── F&O weekly expiry dates ──────────────────────────────────
                for exp_date in _next_thursdays(weeks=8):
                    monthly = exp_date in _monthly_expiry(months=6)
                    label = "Monthly" if monthly else "Weekly"
                    await _upsert_event(
                        db,
                        title=f"NSE F&O {label} Expiry",
                        ev_date=exp_date,
                        category="F&O Expiry",
                        impact="HIGH" if monthly else "MEDIUM",
                        time_str="15:30",
                        description=f"NSE F&O {label} expiry — increased volatility expected near close.",
                    )

                # ── NSE earnings calendar ────────────────────────────────────
                try:
                    announcements = await scraper.get_earnings_calendar()
                    for item in announcements[:40]:
                        raw_dt = item.get("dissemDT") or item.get("date") or ""
                        sym = item.get("symbol") or item.get("sm_name") or ""
                        company = item.get("company") or item.get("sm_fullName") or sym
                        desc = item.get("desc") or item.get("type") or "Board Meeting"

                        if not raw_dt or not sym:
                            continue

                        # Parse date: "DD-MMM-YYYY HH:MM:SS" or "YYYY-MM-DD HH:MM:SS"
                        ev_date = None
                        for fmt in ("%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S",
                                    "%d-%b-%Y", "%Y-%m-%d"):
                            try:
                                parsed = datetime.strptime(raw_dt.strip(), fmt)
                                ev_date = parsed.date()
                                break
                            except ValueError:
                                continue

                        if ev_date is None or ev_date < date.today():
                            continue

                        impact = "HIGH" if any(k in desc for k in ("Result", "Dividend", "Bonus", "Split")) \
                                 else "MEDIUM"

                        await _upsert_event(
                            db,
                            title=f"{company} — {desc}",
                            ev_date=ev_date,
                            category="Corporate Action",
                            impact=impact,
                            description=desc,
                            symbol=sym.upper(),
                            source="nse",
                        )
                except Exception as e:
                    logger.warning("Earnings calendar fetch failed: %s", e)

                await db.commit()
                logger.info("Market events seeded/updated")

        except Exception as e:
            logger.error("Event seeder error: %s", e)

        await asyncio.sleep(6 * 3600)  # re-seed every 6 hours
