-- AlgoVision Pro — Database Initialization
-- Run automatically on first container start via docker-entrypoint-initdb.d

CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- for fast symbol search

-- ─── Tick Data (hypertable — auto partitioned by time) ──────────────────────
CREATE TABLE IF NOT EXISTS ticks (
    time        TIMESTAMPTZ     NOT NULL,
    symbol      TEXT            NOT NULL,
    exchange    TEXT            NOT NULL,   -- NSE, BSE, NFO, MCX, CDS, BFO
    segment     TEXT            NOT NULL,   -- EQ, FUT, OPT, IDX, CUR, COM
    ltp         NUMERIC(12,2),
    open        NUMERIC(12,2),
    high        NUMERIC(12,2),
    low         NUMERIC(12,2),
    close       NUMERIC(12,2),
    volume      BIGINT,
    oi          BIGINT,                     -- Open Interest (F&O only)
    bid         NUMERIC(12,2),
    ask         NUMERIC(12,2),
    bid_qty     BIGINT,
    ask_qty     BIGINT,
    total_buy_qty   BIGINT,
    total_sell_qty  BIGINT
);

SELECT create_hypertable('ticks', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_ticks_symbol_time ON ticks (symbol, time DESC);

-- ─── OHLCV Candles — pre-aggregated for speed ────────────────────────────────
CREATE TABLE IF NOT EXISTS candles_1m (
    time        TIMESTAMPTZ     NOT NULL,
    symbol      TEXT            NOT NULL,
    exchange    TEXT            NOT NULL,
    open        NUMERIC(12,2)   NOT NULL,
    high        NUMERIC(12,2)   NOT NULL,
    low         NUMERIC(12,2)   NOT NULL,
    close       NUMERIC(12,2)   NOT NULL,
    volume      BIGINT          NOT NULL DEFAULT 0,
    oi          BIGINT          DEFAULT 0
);
SELECT create_hypertable('candles_1m', 'time', if_not_exists => TRUE);
CREATE UNIQUE INDEX IF NOT EXISTS idx_candles_1m_symbol_time ON candles_1m (symbol, exchange, time DESC);

-- ─── Instruments Master ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS instruments (
    token           TEXT            NOT NULL,
    symbol          TEXT            NOT NULL,
    name            TEXT,
    exchange        TEXT            NOT NULL,
    segment         TEXT            NOT NULL,
    instrument_type TEXT,           -- EQ, FUT, CE, PE
    expiry          DATE,
    strike          NUMERIC(12,2),
    lot_size        INTEGER         DEFAULT 1,
    tick_size       NUMERIC(8,4)    DEFAULT 0.05,
    isin            TEXT,
    is_active       BOOLEAN         DEFAULT TRUE,
    updated_at      TIMESTAMPTZ     DEFAULT NOW(),
    PRIMARY KEY (token, exchange)
);
CREATE INDEX IF NOT EXISTS idx_instruments_symbol ON instruments USING gin (symbol gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_instruments_exchange_segment ON instruments (exchange, segment);

-- ─── Options Chain Snapshots ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS options_chain (
    snapshot_time   TIMESTAMPTZ     NOT NULL,
    underlying      TEXT            NOT NULL,
    expiry          DATE            NOT NULL,
    strike          NUMERIC(10,2)   NOT NULL,
    option_type     CHAR(2)         NOT NULL,   -- CE or PE
    ltp             NUMERIC(10,2),
    bid             NUMERIC(10,2),
    ask             NUMERIC(10,2),
    iv              NUMERIC(8,4),
    delta           NUMERIC(8,6),
    gamma           NUMERIC(10,8),
    theta           NUMERIC(8,4),
    vega            NUMERIC(8,4),
    oi              BIGINT,
    oi_change       BIGINT,
    volume          BIGINT
);
SELECT create_hypertable('options_chain', 'snapshot_time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_options_chain_lookup
    ON options_chain (underlying, expiry, option_type, strike, snapshot_time DESC);

-- ─── AI Signals ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS signals (
    id              BIGSERIAL       PRIMARY KEY,
    generated_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    symbol          TEXT            NOT NULL,
    exchange        TEXT            NOT NULL,
    timeframe       TEXT            NOT NULL,   -- 1m, 5m, 15m, 1h, 1d
    signal_type     TEXT            NOT NULL,   -- BUY, SELL, HOLD
    strength        NUMERIC(4,2),               -- 0.0 to 1.0 confidence
    entry_price     NUMERIC(12,2),
    stop_loss       NUMERIC(12,2),
    target_1        NUMERIC(12,2),
    target_2        NUMERIC(12,2),
    target_3        NUMERIC(12,2),
    risk_reward     NUMERIC(6,2),
    strategy        TEXT,                       -- SMC, VWAP, ML, etc.
    notes           TEXT,
    is_active       BOOLEAN         DEFAULT TRUE,
    triggered_at    TIMESTAMPTZ,
    closed_at       TIMESTAMPTZ,
    outcome         TEXT                        -- WIN, LOSS, PARTIAL, OPEN
);
CREATE INDEX IF NOT EXISTS idx_signals_symbol_time ON signals (symbol, generated_at DESC);

-- ─── SMC Zones ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS smc_zones (
    id              BIGSERIAL       PRIMARY KEY,
    detected_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    symbol          TEXT            NOT NULL,
    exchange        TEXT            NOT NULL,
    timeframe       TEXT            NOT NULL,
    zone_type       TEXT            NOT NULL,   -- OB_BULL, OB_BEAR, FVG_BULL, FVG_BEAR, LIQ_BSL, LIQ_SSL
    price_top       NUMERIC(12,2)   NOT NULL,
    price_bottom    NUMERIC(12,2)   NOT NULL,
    candle_time     TIMESTAMPTZ,
    strength        NUMERIC(4,2),
    is_filled       BOOLEAN         DEFAULT FALSE,
    filled_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_smc_zones_symbol ON smc_zones (symbol, exchange, is_filled);

-- ─── Orders (Paper + Live) ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    id              BIGSERIAL       PRIMARY KEY,
    broker_order_id TEXT,
    placed_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    symbol          TEXT            NOT NULL,
    exchange        TEXT            NOT NULL,
    transaction     TEXT            NOT NULL,   -- BUY, SELL
    order_type      TEXT            NOT NULL,   -- MARKET, LIMIT, SL, SL-M
    product         TEXT            NOT NULL,   -- CNC, MIS, NRML
    quantity        INTEGER         NOT NULL,
    price           NUMERIC(12,2),
    trigger_price   NUMERIC(12,2),
    status          TEXT            DEFAULT 'PENDING',  -- PENDING, OPEN, COMPLETE, REJECTED, CANCELLED
    avg_price       NUMERIC(12,2),
    filled_qty      INTEGER         DEFAULT 0,
    is_paper        BOOLEAN         DEFAULT TRUE,
    broker          TEXT            DEFAULT 'PAPER',
    signal_id       BIGINT          REFERENCES signals(id),
    notes           TEXT
);

-- ─── Positions ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS positions (
    id              BIGSERIAL       PRIMARY KEY,
    symbol          TEXT            NOT NULL,
    exchange        TEXT            NOT NULL,
    product         TEXT            NOT NULL,
    quantity        INTEGER         NOT NULL,
    avg_price       NUMERIC(12,2)   NOT NULL,
    ltp             NUMERIC(12,2),
    pnl             NUMERIC(12,2),
    pnl_pct         NUMERIC(8,4),
    is_paper        BOOLEAN         DEFAULT TRUE,
    opened_at       TIMESTAMPTZ     DEFAULT NOW(),
    closed_at       TIMESTAMPTZ
);

-- ─── Market Events / Calendar ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market_events (
    id              BIGSERIAL       PRIMARY KEY,
    event_date      DATE            NOT NULL,
    event_time      TIME,
    title           TEXT            NOT NULL,
    description     TEXT,
    category        TEXT,           -- RBI, EARNINGS, FNO_EXPIRY, HOLIDAY, MACRO
    impact          TEXT,           -- HIGH, MEDIUM, LOW
    symbol          TEXT,           -- NULL for market-wide events
    source          TEXT
);
CREATE INDEX IF NOT EXISTS idx_market_events_date ON market_events (event_date);

-- ─── FII/DII Data ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fii_dii (
    trade_date      DATE            PRIMARY KEY,
    fii_buy         NUMERIC(14,2),
    fii_sell        NUMERIC(14,2),
    fii_net         NUMERIC(14,2),
    dii_buy         NUMERIC(14,2),
    dii_sell        NUMERIC(14,2),
    dii_net         NUMERIC(14,2)
);

-- ─── Continuous Aggregate for 5-min candles ───────────────────────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS candles_5m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', time) AS bucket,
    symbol,
    exchange,
    first(open, time)              AS open,
    max(high)                      AS high,
    min(low)                       AS low,
    last(close, time)              AS close,
    sum(volume)                    AS volume,
    last(oi, time)                 AS oi
FROM ticks
GROUP BY bucket, symbol, exchange
WITH NO DATA;

-- Refresh policy: keep 5m candles up to date automatically
SELECT add_continuous_aggregate_policy('candles_5m',
    start_offset => INTERVAL '1 day',
    end_offset   => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => TRUE
);

COMMIT;
