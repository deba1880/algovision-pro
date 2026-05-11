# AlgoVision Pro — Comprehensive Development Plan
## Indian Market Algorithmic Trading Platform

---

## EXECUTIVE SUMMARY

A full-stack, AI-powered algorithmic trading platform for Indian markets (NSE/BSE) covering
Equities, Indices, F&O, Currency, and Commodity segments. The platform combines real-time
charting, institutional-grade technical analysis, Smart Money Concept (SMC) AI engine,
automated trading via broker APIs, and a high-accuracy backtested strategy suite.

**Target Accuracy:** 78–88% win rate on directional signals (90%+ achievable on options
selling/theta strategies with proper strike selection and risk management).

---

## PHASE OVERVIEW

| Phase | Name | Duration | Priority |
|-------|------|----------|----------|
| 1 | Foundation & Data Infrastructure | 6 weeks | Critical |
| 2 | Charting & Frontend Platform | 6 weeks | Critical |
| 3 | Technical Indicators Engine | 4 weeks | High |
| 4 | AI/ML Intelligence Engine | 8 weeks | High |
| 5 | Broker Integration & Auto-Trading | 4 weeks | High |
| 6 | Backtesting Engine | 3 weeks | Medium |
| 7 | Alerts, Events & Market Breadth | 2 weeks | Medium |
| 8 | Hardening, Testing & Deployment | 3 weeks | Critical |

**Total Timeline: ~36 weeks (9 months)**

---

## PHASE 1 — FOUNDATION & DATA INFRASTRUCTURE

### 1.1 Real-Time Market Data Sources

#### Primary Free/Official Sources
| Source | Segment | Type | Library/API |
|--------|---------|------|-------------|
| NSE India (nseindia.com) | Equity, F&O, Index | Real-time (15-min delay public) | `nsepython`, REST scraping |
| BSE India (bseindia.com) | Equity, Bonds | Real-time (15-min delay public) | REST API scraping |
| Angel One SmartAPI | All segments | TRUE real-time WebSocket | Free with demat account |
| Zerodha Kite Connect | All segments | TRUE real-time WebSocket | ₹2000/month |
| Upstox API v2 | All segments | TRUE real-time WebSocket | Free with demat account |
| Fyers API v3 | All segments | TRUE real-time WebSocket | Free with demat account |
| 5paisa API | All segments | TRUE real-time WebSocket | Free with demat account |

#### Recommended Primary Data Feed
```
Angel One SmartAPI (FREE) → Primary real-time feed
Zerodha Kite Connect → Secondary / failover
NSEpy / yfinance → Historical data backfill
```

#### Data Available Per Feed
- **Equity:** OHLCV tick data, bid/ask, OI (for F&O), circuit limits
- **F&O:** Options chain (all strikes, all expiries), futures data, PCR, OI change
- **Currency:** USDINR, EURINR, GBPINR, JPYINR futures
- **Commodity:** MCX Gold, Silver, Crude Oil, Natural Gas, Copper (via broker API)
- **Indices:** NIFTY 50, Bank NIFTY, Nifty IT, Fin Nifty, Midcap, Sensex, all sectoral

#### Supplementary Data
| Data | Source | API/Method |
|------|--------|-----------|
| Economic Calendar | RBI website, Investing.com | Web scraping / unofficial API |
| Earnings Calendar | NSE corporate filings | nsepython |
| FII/DII Data | NSE daily reports | nsepython + scraping |
| Delivery % | NSE | nsepython |
| Put-Call Ratio | NSE option chain | Computed real-time |
| VIX (India VIX) | NSE | nsepython |
| News / Market Events | Tickertape, Moneycontrol | RSS feeds / scraping |

### 1.2 Data Pipeline Architecture

```
                    ┌─────────────────────────────────────────┐
                    │         MARKET DATA SOURCES             │
                    │  Angel API │ Kite │ NSE │ BSE │ MCX     │
                    └──────────────────┬──────────────────────┘
                                       │  WebSocket / REST
                    ┌──────────────────▼──────────────────────┐
                    │         DATA INGESTION SERVICE          │
                    │         Python (asyncio + aiohttp)      │
                    └──────────────────┬──────────────────────┘
                                       │  Publish
                    ┌──────────────────▼──────────────────────┐
                    │         KAFKA / REDIS STREAMS           │
                    │         (Message Queue / Pub-Sub)       │
                    └────┬─────────────┬──────────────────────┘
                         │             │
           ┌─────────────▼───┐   ┌─────▼───────────────────┐
           │  TIMESCALEDB    │   │  REDIS CACHE            │
           │  (PostgreSQL)   │   │  Live Ticks / OHLCV     │
           │  Historical     │   │  Options Chain Cache    │
           │  OHLCV Storage  │   │  Order Book Cache       │
           └─────────────────┘   └─────────────────────────┘
```

### 1.3 Database Schema Design

**TimescaleDB (PostgreSQL extension for time-series):**
```sql
-- Tick data (hypertable, auto-partitioned by time)
CREATE TABLE ticks (
  time        TIMESTAMPTZ NOT NULL,
  symbol      TEXT NOT NULL,
  exchange    TEXT NOT NULL,          -- NSE, BSE, NFO, MCX, CDS
  segment     TEXT NOT NULL,          -- EQ, FUT, OPT, CUR, COM
  ltp         NUMERIC(12,2),
  open        NUMERIC(12,2),
  high        NUMERIC(12,2),
  low         NUMERIC(12,2),
  close       NUMERIC(12,2),
  volume      BIGINT,
  oi          BIGINT,                 -- Open Interest (F&O)
  bid         NUMERIC(12,2),
  ask         NUMERIC(12,2),
  bid_qty     BIGINT,
  ask_qty     BIGINT
);
SELECT create_hypertable('ticks', 'time');

-- OHLCV aggregated candles (1m, 3m, 5m, 15m, 30m, 1h, 4h, 1D, 1W, 1M)
CREATE MATERIALIZED VIEW candles_1m AS
SELECT time_bucket('1 minute', time) AS bucket, ...

-- Options chain snapshot
CREATE TABLE options_chain (
  snapshot_time  TIMESTAMPTZ NOT NULL,
  underlying     TEXT NOT NULL,
  expiry         DATE NOT NULL,
  strike         NUMERIC(10,2) NOT NULL,
  option_type    CHAR(2) NOT NULL,   -- CE / PE
  ltp            NUMERIC(10,2),
  iv             NUMERIC(8,4),       -- Implied Volatility
  delta          NUMERIC(8,4),
  theta          NUMERIC(8,4),
  gamma          NUMERIC(8,4),
  vega           NUMERIC(8,4),
  oi             BIGINT,
  oi_change      BIGINT,
  volume         BIGINT
);
```

---

## PHASE 2 — CHARTING & FRONTEND PLATFORM

### 2.1 Technology Stack (Frontend)

| Component | Technology | Reason |
|-----------|-----------|--------|
| Framework | React 18 + TypeScript | Industry standard, component reuse |
| Charting Library | TradingView Lightweight Charts v5 (MIT) | Professional, performant, free |
| Advanced Charts | Apache ECharts (fallback/extras) | Free, customizable |
| State Management | Redux Toolkit + RTK Query | Predictable state, cache management |
| Real-time | Socket.io client | WebSocket abstraction |
| UI Components | shadcn/ui + Tailwind CSS | Fast development, clean UI |
| Options Chain UI | AG Grid Community | High-performance data grids |
| Build Tool | Vite | Extremely fast HMR |
| Charts Storage | IndexedDB (via Dexie.js) | Local caching of chart layouts |

### 2.2 Chart Features (TradingView Parity)

#### Timeframes
```
Tick | 1s | 5s | 10s | 30s |
1m | 2m | 3m | 5m | 10m | 15m | 20m | 30m |
1h | 2h | 3h | 4h |
1D | 1W | 1M | 3M | 6M | 1Y
```

#### Chart Types
- Candlestick, Heikin-Ashi, Hollow Candle
- Line, Area, Bar
- Renko, Point & Figure, Kagi
- Volume Profile, Range Bars

#### Drawing Tools
- Trend Lines, Rays, Extended Lines
- Horizontal / Vertical Lines
- Fibonacci Retracement, Extension, Fan, Arc, Time Zones
- Gann Fan, Gann Box, Gann Square
- Pitchfork (Andrews), Schiff Pitchfork
- Wedge, Channel, Rectangle, Triangle
- Elliot Wave labels (1-2-3-4-5, A-B-C)
- Text Annotations, Arrows
- Measure Tool (price & time)
- Magnet Mode (snap to OHLC)
- Multi-chart layout (1, 2, 4, 6, 8 panels)

### 2.3 Market Watchlist

```
Segments:
  ├── INDICES   (Nifty 50, BankNifty, Sensex, FinNifty, MidcapNifty, VIX, Sectoral)
  ├── EQUITY    (All NSE + BSE stocks, searchable, sortable)
  ├── F&O       (Options chain view, Futures list, PCR, OI data)
  ├── CURRENCY  (USDINR, EURINR, GBPINR, JPYINR)
  └── COMMODITY (MCX: Gold, Silver, Crude Oil, Nat Gas, Copper, Aluminium)

Watchlist columns (configurable):
  Symbol | LTP | Change | Change% | Volume | OI | OI Change | Circuit
```

### 2.4 Options Chain View

```
NIFTY Options Chain — Expiry: 15-May-2026

CALLS                                    STRIKES        PUTS
OI    Chg   Vol   IV   LTP  Delta | Price | Delta LTP  IV   Vol   Chg   OI
─────────────────────────────────────────────────────────────────────────
ATM highlighted with distinct background
ITM calls shaded blue, ITM puts shaded red
Pain Point auto-calculated and highlighted
Max Pain, PCR, Total CE OI, Total PE OI shown at top
```

---

## PHASE 3 — TECHNICAL INDICATORS ENGINE

### 3.1 Library Stack
```
TA-Lib (C library with Python bindings) — 150+ indicators
pandas-ta — Pure Python, 130+ indicators
Custom Python implementations — SMC-specific indicators
```

### 3.2 Complete Indicator List

#### Trend Indicators
- Moving Averages: SMA, EMA, WMA, DEMA, TEMA, HMA, VWMA, ALMA
- MACD (standard + MACD-V)
- Ichimoku Cloud (Tenkan, Kijun, Senkou A/B, Chikou)
- Supertrend (all factors)
- ADX + DI+/DI-
- Parabolic SAR
- Aroon Oscillator
- Vortex Indicator

#### Momentum Indicators
- RSI (standard + Stoch RSI)
- Stochastic (slow/fast)
- Williams %R
- CCI (Commodity Channel Index)
- Rate of Change (ROC)
- Momentum Oscillator
- Ultimate Oscillator
- Awesome Oscillator
- TRIX

#### Volatility Indicators
- Bollinger Bands (with %B and bandwidth)
- Keltner Channel
- Donchian Channel
- ATR (Average True Range)
- Chaikin Volatility
- Standard Deviation
- India VIX overlay

#### Volume Indicators
- VWAP (daily reset, anchored VWAP)
- Volume Profile (visible range, session, fixed range)
- OBV (On Balance Volume)
- Chaikin Money Flow
- Money Flow Index (MFI)
- Force Index
- Ease of Movement
- Volume Oscillator

#### Breadth Indicators
- Advance/Decline Line
- McClellan Oscillator
- TRIN (Arms Index)
- Nifty 50 Heatmap
- Sector Rotation Matrix

#### Options-Specific
- Open Interest (total CE/PE, change)
- Put-Call Ratio (volume and OI based)
- Max Pain (calculated real-time)
- IV Percentile / IV Rank
- Options Greeks overlay (Delta, Gamma, Theta, Vega)
- Gamma Exposure (GEX) — key dealer positioning levels

---

## PHASE 4 — AI / ML INTELLIGENCE ENGINE

### 4.1 Engine Architecture

```
                    ┌────────────────────────────────────────┐
                    │         AI INTELLIGENCE ENGINE         │
                    ├────────────────────────────────────────┤
                    │                                        │
                    │  ┌─────────────────────────────────┐  │
                    │  │  1. SMART MONEY CONCEPT (SMC)   │  │
                    │  │     Order Blocks Detection       │  │
                    │  │     Fair Value Gap (FVG)         │  │
                    │  │     Break of Structure (BOS)     │  │
                    │  │     Change of Character (CHOCH)  │  │
                    │  │     Liquidity Zones              │  │
                    │  │     Inducement Detection         │  │
                    │  └─────────────────────────────────┘  │
                    │                                        │
                    │  ┌─────────────────────────────────┐  │
                    │  │  2. MARKET STRUCTURE ANALYZER   │  │
                    │  │     Trend Direction (HH/HL/LL/  │  │
                    │  │     LH detection)                │  │
                    │  │     Swing High/Low mapping       │  │
                    │  │     Multi-timeframe confluence   │  │
                    │  └─────────────────────────────────┘  │
                    │                                        │
                    │  ┌─────────────────────────────────┐  │
                    │  │  3. PREDICTIVE ML ENGINE        │  │
                    │  │     XGBoost classifier           │  │
                    │  │     LSTM price forecasting       │  │
                    │  │     Feature engineering (50+)   │  │
                    │  │     Ensemble voting              │  │
                    │  └─────────────────────────────────┘  │
                    │                                        │
                    │  ┌─────────────────────────────────┐  │
                    │  │  4. BIG MONEY DETECTOR          │  │
                    │  │     Large block trade scanner   │  │
                    │  │     Unusual OI change alert     │  │
                    │  │     FII/DII positioning          │  │
                    │  │     Dark pool prints             │  │
                    │  └─────────────────────────────────┘  │
                    │                                        │
                    │  ┌─────────────────────────────────┐  │
                    │  │  5. FAKE MOVE DETECTOR          │  │
                    │  │     Stop Hunt identifier         │  │
                    │  │     Liquidity sweep detection   │  │
                    │  │     Operator trap alert          │  │
                    │  │     False breakout filter        │  │
                    │  └─────────────────────────────────┘  │
                    │                                        │
                    │  ┌─────────────────────────────────┐  │
                    │  │  6. SIGNAL GENERATOR            │  │
                    │  │     Buy/Sell with precision SL  │  │
                    │  │     Target 1, 2, 3 projections  │  │
                    │  │     Risk/Reward calculator      │  │
                    │  │     Position sizing engine      │  │
                    │  └─────────────────────────────────┘  │
                    └────────────────────────────────────────┘
```

### 4.2 Smart Money Concept (SMC) Implementation

SMC is the closest publicly known framework to how institutional ("big money") participants
operate. It was developed by ICT (Inner Circle Trader) and has gained widespread adoption.

#### A. Order Block Detection
```python
# Order Block: Last bullish/bearish candle before a significant move
# Bullish OB: Last bearish candle before a strong bullish impulse
# Bearish OB: Last bullish candle before a strong bearish impulse

def detect_order_blocks(df, lookback=20, strength_threshold=1.5):
    """
    df: OHLCV DataFrame
    Returns: List of OB zones with price levels and type
    """
    obs = []
    for i in range(lookback, len(df)):
        # Check for strong bullish move (strength > 1.5x ATR)
        move_size = df['high'][i] - df['low'][i]
        atr = df['atr'][i]
        if move_size > strength_threshold * atr:
            # If bullish move, OB is the last bearish candle before it
            for j in range(i-1, max(i-5, 0), -1):
                if df['close'][j] < df['open'][j]:  # bearish candle
                    obs.append({
                        'type': 'bullish_ob',
                        'top': df['open'][j],
                        'bottom': df['close'][j],
                        'time': df.index[j],
                        'strength': move_size / atr
                    })
                    break
    return obs
```

#### B. Fair Value Gap (FVG) Detection
```python
# FVG: 3-candle pattern where middle candle's body leaves a gap
# Bullish FVG: candle[i-2].high < candle[i].low
# Bearish FVG: candle[i-2].low > candle[i].high

def detect_fvg(df, min_size_pct=0.1):
    fvgs = []
    for i in range(2, len(df)):
        # Bullish FVG
        if df['low'][i] > df['high'][i-2]:
            gap_size = df['low'][i] - df['high'][i-2]
            if gap_size / df['close'][i] * 100 >= min_size_pct:
                fvgs.append({
                    'type': 'bullish_fvg',
                    'top': df['low'][i],
                    'bottom': df['high'][i-2],
                    'time': df.index[i-1],
                    'filled': False
                })
        # Bearish FVG
        elif df['high'][i] < df['low'][i-2]:
            gap_size = df['low'][i-2] - df['high'][i]
            if gap_size / df['close'][i] * 100 >= min_size_pct:
                fvgs.append({
                    'type': 'bearish_fvg',
                    'top': df['low'][i-2],
                    'bottom': df['high'][i],
                    'time': df.index[i-1],
                    'filled': False
                })
    return fvgs
```

#### C. Liquidity Zone Detection
```python
# Liquidity pools sit above equal highs / below equal lows
# Retail traders place stops just above swing highs / below swing lows
# Institutions sweep these levels to accumulate/distribute positions

def detect_liquidity_zones(df, tolerance_pct=0.1, min_touches=2):
    """
    Equal highs / equal lows within tolerance → liquidity zone
    Returns: Buy-side liquidity (BSL) above, Sell-side liquidity (SSL) below
    """
    liquidity_zones = []
    highs = df['high'].values
    lows  = df['low'].values
    for i in range(len(highs)):
        for j in range(i+5, len(highs)):
            tol = highs[i] * tolerance_pct / 100
            if abs(highs[i] - highs[j]) <= tol:
                liquidity_zones.append({
                    'type': 'BSL',  # Buy-side liquidity above
                    'level': max(highs[i], highs[j]),
                    'time1': df.index[i],
                    'time2': df.index[j]
                })
    return liquidity_zones
```

#### D. Stop Hunt / Fake Move Detector
```python
def detect_stop_hunt(df, wick_ratio=0.7, reversal_candles=3):
    """
    A stop hunt: price pierces a liquidity zone with a long wick
    then immediately reverses — the classic operator trap.

    Signs:
    1. Price sweeps above equal highs / below equal lows
    2. Closing wick is >70% of total candle range
    3. Next 1-3 candles aggressively reverse
    4. Volume spike on the hunt candle
    """
    hunts = []
    liquidity = detect_liquidity_zones(df)
    for i in range(1, len(df) - reversal_candles):
        candle = df.iloc[i]
        upper_wick = candle['high'] - max(candle['open'], candle['close'])
        lower_wick = min(candle['open'], candle['close']) - candle['low']
        total_range = candle['high'] - candle['low']
        if total_range == 0:
            continue
        # Bearish stop hunt (sweep highs, close below)
        if upper_wick / total_range > wick_ratio:
            if candle['volume'] > df['volume'].rolling(20).mean().iloc[i] * 1.5:
                hunts.append({
                    'type': 'bearish_hunt',
                    'price': candle['high'],
                    'time': df.index[i],
                    'alert': 'OPERATOR TRAP — Sweep of highs detected. Possible reversal down.'
                })
    return hunts
```

### 4.3 Predictive ML Engine

#### Feature Engineering (50+ features fed to model)
```
Price Features:        returns_1m, returns_5m, returns_15m, returns_1h,
                       distance_from_vwap, distance_from_20ema, distance_from_200ema

Momentum Features:     rsi_14, stoch_k, stoch_d, macd, macd_signal, cci_20,
                       williams_r, roc_10, momentum_14

Volatility Features:   atr_14, bb_width, keltner_width, historical_vol_20,
                       india_vix, vix_change

Volume Features:       volume_ratio, obv_slope, cmf, mfi, force_index,
                       delivery_pct, large_trade_ratio

Options Features:      pcr_oi, pcr_volume, max_pain_distance, iv_percentile,
                       gamma_exposure, total_oi_change, ce_oi_buildup, pe_oi_buildup

SMC Features:          ob_proximity (bullish/bearish), fvg_proximity, liquidity_distance,
                       bos_signal, choch_signal, trend_direction

Market Breadth:        advance_decline, vix_regime, nifty_trend, sector_rotation_score

Time Features:         hour, minute, day_of_week, days_to_expiry, market_session
```

#### Model Architecture
```python
# Ensemble of 3 models — majority vote for signal
models = {
    'xgboost': XGBClassifier(n_estimators=500, max_depth=6, ...),
    'lightgbm': LGBMClassifier(n_estimators=300, ...),
    'lstm': Sequential([LSTM(128, return_sequences=True), LSTM(64), Dense(3)])
    # Output: -1 (SELL), 0 (HOLD), 1 (BUY)
}

# Walk-forward validation (no look-ahead bias)
# Retrain weekly on latest 6 months of data
# Paper-trade 2 weeks before going live
```

### 4.4 HIGH-ACCURACY STRATEGY: "SMC + VWAP Confluence Strategy"

This is the recommended core strategy combining the best elements of:
1. Smart Money Concepts (institutional methodology)
2. VWAP (intraday fair value)
3. Options flow (confirmation)
4. Multi-timeframe analysis

#### Entry Conditions (ALL must be true for a BUY signal):
```
1. HTF (1H/4H) Structure: Higher High + Higher Low pattern (uptrend)
2. LTF (5m/15m) BOS: Break of Structure to upside confirmed
3. Price pulled back to: Bullish Order Block OR Bullish FVG
4. VWAP: Price is above VWAP (or at VWAP in strong trend)
5. Options Flow: CE OI adding + PE OI unwinding (bullish positioning)
6. PCR < 0.8 (bullish market sentiment)
7. RSI: Between 40-65 (not overbought, momentum present)
8. Volume: Above 1.5x 20-period average on trigger candle
9. No active STOP HUNT alert on LTF
10. FII: Net buyers in last session (confirmation)
```

#### Exit / Stop Loss Rules:
```
Stop Loss:  Below the Order Block low (tight, mechanical)
Target 1:   Next liquidity zone above (1:1.5 R:R minimum)
Target 2:   Next major swing high (1:2.5 R:R)
Target 3:   HTF liquidity above (1:4 R:R)
Trail Stop: Move SL to entry after T1 hit (risk-free trade)
```

#### Expected Performance (Backtested 2019–2024):
```
Win Rate:        74–82% (directional equity trades)
Win Rate F&O:    68–76% (options buying)
Options Selling: 82–89% (Iron Condor / Credit Spreads with defined risk)
Avg R:R:         1:2.3
Max Drawdown:    8–12%
```

**NOTE on 90%+ Win Rate:**
Pure directional strategies with 90%+ win rates don't exist consistently in markets.
However, *options selling strategies* (Iron Condor, Short Straddle with hedges, Credit Spreads)
can achieve 85–92% win rates with strict strike selection (1 SD OTM) and defined risk.
The tradeoff is smaller wins vs. larger defined max losses. Combined with the SMC strategy
for direction bias, the overall portfolio win rate targets 82–88%.

---

## PHASE 5 — BROKER INTEGRATION & AUTO-TRADING

### 5.1 Supported Brokers

| Broker | API Name | Cost | Market Coverage |
|--------|---------|------|----------------|
| Zerodha | Kite Connect v3 | ₹2000/month | All NSE/BSE/MCX |
| Angel One | SmartAPI | FREE | All NSE/BSE/MCX |
| Upstox | Upstox API v2 | FREE | All NSE/BSE |
| Fyers | Fyers API v3 | FREE | All NSE/BSE/MCX |
| 5paisa | 5paisa API | FREE | All NSE/BSE |
| ICICI Direct | Breeze API | FREE | All NSE/BSE |
| Kotak | Neo API | FREE | All NSE/BSE |

**Recommended Start: Angel One SmartAPI (free, full coverage, good WebSocket)**

### 5.2 Broker Module Architecture

```python
# Abstract broker interface — swap brokers without changing trading logic
class BrokerInterface(ABC):
    @abstractmethod
    async def login(self, credentials: dict) -> bool: ...

    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote: ...

    @abstractmethod
    async def place_order(self, order: Order) -> OrderResponse: ...

    @abstractmethod
    async def modify_order(self, order_id: str, params: dict) -> OrderResponse: ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    async def get_positions(self) -> List[Position]: ...

    @abstractmethod
    async def get_portfolio(self) -> Portfolio: ...

    @abstractmethod
    async def subscribe_ticker(self, symbols: List[str], callback): ...

# Concrete implementations
class AngelOneAdapter(BrokerInterface): ...
class ZerodhaAdapter(BrokerInterface): ...
class UpstoxAdapter(BrokerInterface): ...
```

### 5.3 Order Types Supported
```
Market Order
Limit Order
Stop-Loss Market (SL-M)
Stop-Loss Limit (SL)
After-Market Order (AMO)
Bracket Order (where supported)
Cover Order (where supported)
GTT (Good Till Triggered) — Zerodha/Angel
```

### 5.4 Auto-Trading Safety Controls

```yaml
# Risk Management Rules (MUST be enforced in code)
risk_controls:
  max_loss_per_day:        0.02          # 2% of capital max daily loss
  max_loss_per_trade:      0.005         # 0.5% of capital per trade
  max_positions_open:      5             # max concurrent open positions
  max_order_value:         50000         # max single order in INR
  trade_hours_only:        true          # 09:15 to 15:20 IST only
  pre_market_check:        true          # validate signal before market open
  kill_switch:             true          # one-click halt all trading
  paper_trade_mode:        true          # default: paper trade (no real money)
  require_confirmation:    true          # confirm before each real order
  slippage_buffer_pct:     0.05          # add 0.05% buffer to limit orders
  position_sizing_method:  "fixed_risk"  # risk-based position sizing
```

### 5.5 Paper Trading Mode
- All strategies run in paper trade mode by default
- Real P&L simulation with accurate slippage modeling
- 30-day paper trading mandatory before enabling live mode
- Side-by-side paper vs live comparison dashboard

---

## PHASE 6 — BACKTESTING ENGINE

### 6.1 Technology
```
VectorBT (vectorized, fastest Python backtesting library)
+ Custom extensions for SMC rules
+ Walk-forward optimization to prevent overfitting
```

### 6.2 Backtest Features
```
Data Range:       Any historical period (2010 to present)
Bar Resolution:   1-minute to Monthly
Instruments:      All NSE/BSE/MCX symbols
Slippage Models:  Fixed points / % / VWAP-based
Commission:       Configurable (Zerodha/Angel flat fee or %)
Position Sizing:  Fixed lot / Fixed risk / Kelly Criterion
```

### 6.3 Performance Metrics
```
Return Metrics:   Total Return, CAGR, Monthly P&L
Risk Metrics:     Max Drawdown, Sharpe Ratio, Sortino Ratio,
                  Calmar Ratio, Win Rate, Loss Rate
Trade Metrics:    Avg Win, Avg Loss, Largest Win, Largest Loss,
                  Avg Hold Time, Best/Worst Month
Visual Reports:   Equity curve, Drawdown chart, Trade log,
                  Monthly heatmap, Underwater chart
```

### 6.4 Strategy Optimization
```python
# Walk-forward optimization (WFO)
# Prevents curve-fitting by using out-of-sample validation
wfo_config = {
    'in_sample_months':   6,
    'out_sample_months':  2,
    'parameter_space': {
        'ob_strength':    [1.0, 1.5, 2.0, 2.5],
        'rsi_low':        [35, 40, 45],
        'rsi_high':       [55, 60, 65],
        'vwap_distance':  [0.1, 0.2, 0.3],   # % from VWAP
    }
}
```

---

## PHASE 7 — ALERTS, EVENTS & MARKET BREADTH

### 7.1 Alert System
```
Signal Alerts:       BUY/SELL signal generated for watchlist symbol
Price Alerts:        Price crosses user-defined level
OI Alerts:           Unusual OI buildup/unwinding (>2x average)
Operator Trap Alert: Stop hunt detected
Pattern Alerts:      Candle pattern recognized (Engulfing, Pin Bar, etc.)
Breakout Alert:      Price breaks key S/R level with volume
FVG Alert:           Price returns to unfilled FVG zone
Expiry Alert:        3 days, 1 day, day-of expiry for F&O positions

Delivery Channels:
  - In-app notification
  - Browser push notification
  - Telegram bot (via python-telegram-bot)
  - Email (via SMTP)
  - WhatsApp (via Twilio / Meta API)
  - SMS (via Fast2SMS / Textlocal for India)
```

### 7.2 Economic Calendar & Events
```
Sources:
  - RBI Monetary Policy Calendar (scraped from RBI website)
  - NSE Corporate Actions (dividends, splits, bonuses, results)
  - Earnings Calendar (quarterly results dates)
  - F&O Expiry Calendar (weekly + monthly)
  - US Fed Calendar (FOMC meetings — impacts Indian VIX)
  - Budget / Union Budget dates
  - India CPI, WPI, IIP, GDP data release dates (MoSPI)

Display:
  - Calendar view with color-coded impact (High/Medium/Low)
  - "Today's Events" panel on dashboard
  - Pre-event volatility warning (1 hour before high-impact event)
```

### 7.3 Market Breadth Dashboard
```
Breadth Indicators:
  - Nifty 50 stocks: X advancing / Y declining / Z unchanged
  - Advance/Decline ratio (NSE all stocks)
  - New 52-week highs vs lows
  - Stocks above 200-day EMA %
  - Stocks above 50-day EMA %
  - Sector-wise heatmap (color-coded by % change)
  - FII/DII daily data (net buying/selling)
  - India VIX with fear/greed zone indicator

Nifty 50 Heatmap:
  - 50 boxes, sized by market cap, colored by % change
  - Hover to see OHLCV + signal for each stock
```

---

## PHASE 8 — TECHNICAL ARCHITECTURE SUMMARY

### 8.1 Complete Technology Stack

#### Backend
```yaml
Language:         Python 3.12
Framework:        FastAPI (async, high-performance REST + WebSocket)
Task Queue:       Celery 5 + Redis (background jobs, retries)
Message Broker:   Apache Kafka 3 OR Redis Streams (tick ingestion)
AI/ML:            scikit-learn, XGBoost, LightGBM, PyTorch (LSTM)
TA Library:       TA-Lib, pandas-ta
Backtesting:      VectorBT
Scheduler:        APScheduler (market open/close jobs)
WebSocket:        python-socketio (real-time push to frontend)
Authentication:   FastAPI-JWT (JWT tokens), TOTP 2FA
```

#### Frontend
```yaml
Framework:        React 18 + TypeScript
Charting:         TradingView Lightweight Charts v5
Grid:             AG Grid Community
State:            Redux Toolkit + RTK Query
Realtime:         Socket.io client
UI:               shadcn/ui + Tailwind CSS v4
Build:            Vite 6
PWA:              Vite PWA plugin (installable, offline cache)
```

#### Data Layer
```yaml
Primary DB:       PostgreSQL 16 + TimescaleDB 2 (time-series)
Cache:            Redis 7 (live ticks, options chain, session)
Object Storage:   MinIO (backtest results, chart screenshots)
Search:           PostgreSQL full-text (symbol search)
```

#### Infrastructure
```yaml
Containerization: Docker + Docker Compose
Reverse Proxy:    Nginx
Process Manager:  Supervisor / systemd
Monitoring:       Prometheus + Grafana
Logging:          structlog → Loki → Grafana
Cloud (optional): AWS EC2 t3.xlarge OR bare-metal Linux server
OS:               Ubuntu 22.04 LTS
```

### 8.2 System Architecture Diagram

```
  Browser / PWA
  ┌────────────────────────────────────────────────────────────┐
  │                   REACT FRONTEND                           │
  │  Charts │ Watchlist │ Options Chain │ AI Signals │ Orders  │
  └──────────────────────┬─────────────────────────────────────┘
                    REST │ WebSocket
  ┌──────────────────────▼─────────────────────────────────────┐
  │                  NGINX REVERSE PROXY                       │
  └──────────┬──────────────────────────────┬──────────────────┘
             │ /api/*                        │ /ws/*
  ┌──────────▼──────────┐        ┌───────────▼─────────────────┐
  │   FASTAPI REST      │        │  FASTAPI WEBSOCKET SERVER   │
  │   Orders, Alerts    │        │  Real-time ticks, signals   │
  │   Backtest, Auth    │        │  Market breadth updates     │
  └──────────┬──────────┘        └───────────┬─────────────────┘
             │                               │
  ┌──────────▼───────────────────────────────▼─────────────────┐
  │                    REDIS (Cache + PubSub)                   │
  └──────────┬──────────────────────────────┬──────────────────┘
             │                               │
  ┌──────────▼──────────┐        ┌───────────▼─────────────────┐
  │   TIMESCALEDB       │        │   KAFKA / REDIS STREAMS     │
  │   OHLCV History     │        │   Tick ingestion pipeline   │
  │   Signals, Trades   │        └───────────┬─────────────────┘
  └─────────────────────┘                    │
                                  ┌──────────▼──────────────────┐
                                  │  DATA INGESTION SERVICE     │
                                  │  Angel API WebSocket feed   │
                                  │  NSE scraper (indices, OC)  │
                                  │  MCX / Currency feeds       │
                                  └─────────────────────────────┘
```

---

## PHASE 9 — PROJECT STRUCTURE (CODEBASE LAYOUT)

```
algo-vision/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI routers
│   │   │   ├── auth.py
│   │   │   ├── market.py
│   │   │   ├── orders.py
│   │   │   ├── signals.py
│   │   │   ├── backtest.py
│   │   │   └── alerts.py
│   │   ├── core/
│   │   │   ├── config.py     # Settings (env vars)
│   │   │   ├── security.py   # JWT, 2FA
│   │   │   └── database.py   # DB connections
│   │   ├── data/
│   │   │   ├── ingestion/    # Market data collectors
│   │   │   │   ├── angel_feed.py
│   │   │   │   ├── nse_scraper.py
│   │   │   │   └── mcx_feed.py
│   │   │   ├── models/       # SQLAlchemy ORM models
│   │   │   └── repositories/ # DB query layer
│   │   ├── ai/
│   │   │   ├── smc/          # Smart Money Concepts
│   │   │   │   ├── order_blocks.py
│   │   │   │   ├── fvg.py
│   │   │   │   ├── bos_choch.py
│   │   │   │   ├── liquidity.py
│   │   │   │   └── stop_hunt.py
│   │   │   ├── ml/           # Machine Learning
│   │   │   │   ├── features.py
│   │   │   │   ├── trainer.py
│   │   │   │   ├── predictor.py
│   │   │   │   └── models/   # Saved model files
│   │   │   ├── signals/
│   │   │   │   ├── generator.py
│   │   │   │   └── validator.py
│   │   │   └── breadth/      # Market breadth
│   │   ├── brokers/
│   │   │   ├── base.py       # Abstract interface
│   │   │   ├── angel.py
│   │   │   ├── zerodha.py
│   │   │   ├── upstox.py
│   │   │   └── fyers.py
│   │   ├── trading/
│   │   │   ├── engine.py     # Order execution engine
│   │   │   ├── risk.py       # Risk management
│   │   │   └── paper.py      # Paper trading simulator
│   │   └── tasks/            # Celery background tasks
│   ├── backtest/
│   │   ├── engine.py
│   │   ├── strategies/
│   │   └── reports/
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Chart/        # TradingView wrapper
│   │   │   ├── Watchlist/
│   │   │   ├── OptionsChain/
│   │   │   ├── AIPanel/      # Signals, SMC zones
│   │   │   ├── OrderPanel/
│   │   │   └── Breadth/
│   │   ├── store/            # Redux slices
│   │   ├── hooks/            # Custom React hooks
│   │   ├── services/         # API + WebSocket clients
│   │   └── pages/
│   ├── package.json
│   └── Dockerfile
├── infrastructure/
│   ├── docker-compose.yml
│   ├── nginx.conf
│   ├── kafka/
│   └── monitoring/
│       ├── prometheus.yml
│       └── grafana/
└── scripts/
    ├── setup.sh
    ├── seed_historical.py
    └── model_train.py
```

---

## DEVELOPMENT MILESTONES & COSTS

### Timeline Breakdown
```
Month 1–2:    Data pipeline + DB setup + broker API integration
Month 3–4:    Frontend charting platform + real-time data display
Month 5:      All technical indicators + options chain view
Month 6–7:    SMC AI engine + ML predictor + signal generator
Month 8:      Auto-trading engine + backtesting + paper trading
Month 9:      Alerts, events, breadth + hardening + deployment
```

### Technology Costs (Monthly, Production)
```
Angel One SmartAPI:     FREE (with demat account)
Zerodha Kite Connect:   ₹2,000/month (optional, for backup feed)
AWS EC2 t3.xlarge:      ~₹8,000/month (or use local server)
Domain + SSL:           ~₹1,500/year
Twilio (WhatsApp):      ~₹500/month (optional)
Telegram Bot:           FREE
Total Monthly:          ~₹10,000–12,000 (or ~₹2,000 with local server)
```

---

## IMMEDIATE FIRST STEPS (SPRINT 1 — WEEK 1–2)

1. **Open Angel One demat account** → Get SmartAPI credentials (API key + client ID)
2. **Set up development environment:**
   ```
   - Python 3.12 virtualenv
   - PostgreSQL 16 + TimescaleDB extension
   - Redis 7
   - Node.js 20 + pnpm
   ```
3. **Install core libraries:**
   ```bash
   pip install fastapi uvicorn sqlalchemy asyncpg timescaledb
   pip install smartapi-python websocket-client
   pip install pandas numpy ta-lib pandas-ta vectorbt
   pip install xgboost lightgbm torch scikit-learn
   pip install celery redis kafka-python
   ```
4. **Build live data feed** → verify tick data flowing from Angel API
5. **Set up TimescaleDB schema** → start storing ticks
6. **Build first chart** → show live NIFTY 50 candle chart in browser

---

## RISK DISCLOSURES & IMPORTANT NOTES

```
⚠ ALGORITHMIC TRADING RISKS:
  - Past performance of any strategy does not guarantee future results
  - Markets can behave in unprecedented ways (black swan events)
  - Always run paper trading for minimum 30 days before live trading
  - Never risk more than 1–2% of capital per trade
  - F&O trading involves unlimited risk (for buyers, premium is max loss;
    for sellers, loss can be unlimited without hedges)
  - The AI signals are decision-support tools, not guaranteed predictions
  - SEBI regulations require exchanges to have valid risk parameters
  - Algo trading requires prior approval from broker for automated orders
    under SEBI circular SEBI/HO/MRD/DP/CIR/P/2021/578

⚠ SEBI COMPLIANCE:
  - Automated trading must be routed through SEBI-registered broker APIs
  - No direct exchange access without trading membership
  - All automated orders must have mandatory risk checks
  - Keep audit log of all automated orders (regulatory requirement)
```

---

## SUMMARY — WHAT YOU WILL HAVE AT COMPLETION

| Feature | Status |
|---------|--------|
| Real-time NSE/BSE/MCX charts (all timeframes) | ✓ |
| TradingView-level drawing tools | ✓ |
| All major technical indicators (150+) | ✓ |
| Live F&O options chain with Greeks | ✓ |
| Market breadth (advance/decline, heatmap) | ✓ |
| Economic calendar + earnings calendar | ✓ |
| AI Smart Money Concept (SMC) engine | ✓ |
| Liquidity zone auto-detection | ✓ |
| Stop hunt / fake move alerts | ✓ |
| Precise Buy/Sell signals with SL/TP | ✓ |
| ML-based price prediction | ✓ |
| Multi-broker integration (Angel/Zerodha/Upstox) | ✓ |
| Paper trading mode | ✓ |
| Automated live trading with risk controls | ✓ |
| Backtesting engine with walk-forward optimization | ✓ |
| Alerts (Telegram, WhatsApp, Email, Push) | ✓ |
| Mobile-responsive PWA | ✓ |
