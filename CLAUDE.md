# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend
```bash
cd backend

# Install deps (dev mode — no Docker needed)
pip install -r requirements-dev.txt

# Run dev server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run full prod server (requires PostgreSQL + Redis)
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Apply DB migrations
alembic upgrade head
```

### Frontend
```bash
cd frontend

# Install deps (uses pnpm)
pnpm install

# Dev server (Vite, port 5173)
pnpm dev

# Production build
pnpm build

# Preview built output
pnpm preview
```

### Full stack locally (no Docker)
Set `DEV_MODE=true` in `.env`. Then run backend + frontend dev servers in separate terminals. No Redis or PostgreSQL needed — SQLite and an in-memory cache are used.

### Docker (full production stack)
```bash
docker-compose up --build
```

## Architecture

### Two deployment modes controlled by `DEV_MODE`
`backend/app/core/config.py` is the central control point. When `DEV_MODE=true`:
- Database: SQLite (`algotrade_dev.db`) via `aiosqlite`
- Cache: In-process `_MemoryCache` dict with TTL (no Redis)
- `requirements-dev.txt` is used (lean set — no ML libs, no Redis, no Kafka)

When `DEV_MODE=false`:
- Database: PostgreSQL/TimescaleDB via `asyncpg`
- Cache: Redis via `aioredis`
- Full `requirements.txt` with scikit-learn, xgboost, vectorbt, etc.

The same application code runs in both modes — only the engine/client swap.

### Backend structure (`backend/app/`)
```
main.py           — FastAPI app, lifespan (startup tasks), routers, WebSocket endpoints
core/
  config.py       — All settings via Pydantic (DEV_MODE, broker keys, risk limits)
  database.py     — Engine factory + get_db() dep + Redis/MemoryCache abstraction
  utils.py        — IST timezone, SEGMENT_BY_EXCHANGE, TIMEFRAME_SECONDS maps
models/market.py  — All ORM models: Tick, Instrument, Signal, Order, Position,
                    MarketEvent, SMCZoneModel, FiiDii
api/v1/           — REST routers (market, trading, backtest, alerts)
websocket/manager.py — ConnectionManager: channel-based broadcast to all WS clients
data/
  tick_pipeline.py     — Receives Angel One ticks → normalize → Redis → batch DB insert
  ingestion/
    angel_feed.py      — SmartAPI WebSocket connector; pyotp guarded with try/except
    nse_scraper.py     — NSE HTTP scraper (indices, breadth, FII/DII, options chain)
ai/
  indicators.py        — ATR, RSI, MACD, VWAP, S/R, pivot points
  smc/detector.py      — Smart Money Concepts: imbalance zones, BOS/CHOCH, trend
  signals/generator.py — Combines SMC + TA + options flow → Signal dataclass
alerts/notifier.py     — Telegram + email; only fires on BUY/SELL with strength ≥ 0.5
```

### Background tasks (started in `main.py` lifespan)
All run as `asyncio.create_task()`:
- **`_periodic_nse_refresh`** — Every 60s (09:00–16:00 IST): fetch indices, breadth, FII/DII from NSE; broadcast to `/ws/market`; every 2nd cycle also fetches options chains.
- **`_periodic_signal_scan`** — Every 15min (09:15–15:30 IST): for each watchlist symbol, pulls yfinance candles → runs SMC + TA → caches signal → broadcasts via `/ws/signals` → sends Telegram/email if strong signal.
- **`_seed_market_events`** — On startup then every 6h: computes F&O expiry Thursdays, fetches NSE earnings calendar, upserts into `market_events` table.
- **Angel One tick feed** — Connects to SmartAPI WebSocket; ticks flow through `tick_pipeline.py`.

### WebSocket channels
```
/ws/market         — Broadcasts: indices, breadth, fii_dii, options_chain, ping
/ws/ticks/{symbol} — Per-symbol tick stream for the chart
/ws/signals        — AI-generated signals as they're produced
```

### Frontend structure (`frontend/src/`)
```
App.tsx            — React Router v6 route tree (all routes inside <Layout />)
store/
  index.ts         — Redux store: market | chart | trading | signals slices
  slices/          — marketSlice (indices/breadth/FII/DII/quotes/connected),
                     tradingSlice (positions/orders/isPaperMode/dailyPnl),
                     chartSlice, signalSlice
services/
  api.ts           — Axios client; baseURL from VITE_API_BASE_URL env var
  websocket.ts     — initWebSocket(dispatch) connects /ws/market and dispatches
                     Redux actions; connectTickWebSocket(symbol, cb) for per-chart ticks
pages/             — DashboardPage, ChartPage, OptionsChainPage, SignalsPage,
                     TradingPage, BacktestPage, EventsPage, SettingsPage
components/
  Layout/          — Layout (sidebar hidden on mobile via `hidden md:block`),
                     TopBar (hamburger on mobile), MarketTicker (dynamic duration)
  Chart/TradingChart.tsx — TradingView Lightweight Charts wrapper
  AI/SignalPanel.tsx      — Signal card (BUY/SELL/HOLD)
```

### Critical env vars
```
DEV_MODE=true           # Must be true on Render free tier (SQLite, no Redis)
PAPER_TRADE_MODE=true   # Never set false without a real broker configured
VITE_API_BASE_URL       # Set on Vercel to point at the Render backend URL
ANGEL_TOTP_SECRET       # 32-char base32 from Angel One mobile app
```

### Key data flow
1. Angel One WebSocket → `tick_pipeline.py` → Redis pub/sub `ticks:{symbol}` → `/ws/ticks/{symbol}` → frontend chart
2. NSE scraper (every 60s) → Redis cache → `/ws/market` broadcast → Redux `setIndices` / `setBreadth` / `setFiiDii`
3. Signal scan (every 15m) → `SignalGenerator.generate()` → Redis + `/ws/signals` → Redux `setSignal` + Telegram/email

### Signal scoring system (`ai/signals/generator.py`)
Signals are scored by summing: SMC trend (+2/-2), BOS/CHOCH events (+2/-2 each), RSI, MACD crossovers, VWAP, options OI flow, FII sentiment. Final `strength = score / max_possible`. Only BUY/SELL with strength ≥ 0.5 trigger notifications.

### Candles fallback (`api/v1/market.py`)
`GET /candles/{symbol}` first queries the `ticks` table (aggregated by bucket). If empty (no live Angel feed), it falls back to `_fetch_candles_yfinance()`. Index symbols map to Yahoo tickers (`NIFTY → ^NSEI`, `BANKNIFTY → ^NSEBANK`, `SENSEX → ^BSESN`); equities get `.NS` or `.BO` suffix.

### Options chain limitation
NSE India blocks non-Indian IPs. On Render.com (Singapore/Oregon), `GET /options-chain/{symbol}` will always return 503. The frontend shows a user-friendly error message rather than a blank table.

### Deployment
- **Backend**: Render.com free tier — `render.yaml` at repo root; uses `requirements-dev.txt`, `DEV_MODE=true`, SQLite
- **Frontend**: Vercel — `frontend/vercel.json` has SPA rewrite (`/* → /index.html`); `VITE_API_BASE_URL` env var points at the Render URL
- Pushing to `master` on GitHub triggers both Render (auto-deploy) and can be manually triggered via Render API
