"""
Backtesting engine — SMC-inspired strategy on NSE historical data via yfinance.

Strategy: Break-of-Structure (BOS) + pullback entry
  - Detect swing high/low (20-bar rolling)
  - Bullish BOS: close breaks above swing high  → bullish bias
  - Bearish BOS: close breaks below swing low   → bearish bias
  - Entry: bias candle after pullback (RSI 30–55 for bull, 45–70 for bear)
            + candle direction confirmation + price above/below EMA20
  - Entry at open of next bar; SL = entry ± ATR × multiplier; TP = entry ± SL-distance × RR
"""

import asyncio
import logging

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()

_YF_SYM = {
    "NIFTY":      "^NSEI",
    "BANKNIFTY":  "^NSEBANK",
    "FINNIFTY":   "NIFTY_FIN_SERVICE.NS",
    "MIDCPNIFTY": "NIFTY_MID_SELECT.NS",
    "SENSEX":     "^BSESN",
}
_YF_INTERVAL = {
    "5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h", "1d": "1d", "1w": "1wk",
}
_INTRADAY = {"5m", "15m", "30m", "1h"}


class BacktestConfig(BaseModel):
    symbol: str = "NIFTY"
    timeframe: str = "15m"
    from_date: str = "2024-01-01"
    to_date: str = "2024-12-31"
    initial_capital: float = Field(100_000, ge=10_000)
    risk_per_trade_pct: float = Field(1.0, ge=0.1, le=5.0)
    sl_atr_mult: float = Field(1.5, ge=0.5, le=5.0)
    tp_rr: float = Field(2.0, ge=1.0, le=10.0)


@router.post("/run")
async def run_backtest(config: BacktestConfig):
    yf_sym = _YF_SYM.get(config.symbol.upper(), f"{config.symbol.upper()}.NS")
    interval = _YF_INTERVAL.get(config.timeframe, "15m")

    try:
        df = await asyncio.to_thread(
            yf.download,
            yf_sym,
            start=config.from_date,
            end=config.to_date,
            interval=interval,
            auto_adjust=True,
            progress=False,
        )
    except Exception as e:
        raise HTTPException(502, f"Yahoo Finance fetch failed: {e}")

    if df is None or len(df) < 50:
        hint = " Note: intraday data (≤1h) is limited to last 60 days." if config.timeframe in _INTRADAY else ""
        raise HTTPException(404, f"Insufficient data for {config.symbol}/{config.timeframe}.{hint}")

    # Flatten multi-level columns (multi-ticker download returns MultiIndex)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]

    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()

    ts_fmt = "%Y-%m-%d" if config.timeframe in ("1d", "1w") else "%Y-%m-%dT%H:%M:%S"
    return _run(df, config, ts_fmt)


# ─── Indicator Computation ─────────────────────────────────────────────────────

def _add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    # ATR (Wilder smoothing via simple rolling for speed)
    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift()).abs()
    lc = (df["Low"] - df["Close"].shift()).abs()
    df["atr"] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()

    # RSI
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))

    # EMA20 for trend filter
    df["ema20"] = df["Close"].ewm(span=20).mean()

    # Rolling swing high/low (look-back only — shift(1) prevents lookahead)
    df["swing_high"] = df["High"].rolling(20).max().shift(1)
    df["swing_low"] = df["Low"].rolling(20).min().shift(1)
    return df


# ─── Signal Detection ──────────────────────────────────────────────────────────

def _add_signals(df: pd.DataFrame) -> pd.DataFrame:
    # Break of Structure
    bos_bull = (df["Close"] > df["swing_high"]) & (df["Close"].shift(1) <= df["swing_high"].shift(1))
    bos_bear = (df["Close"] < df["swing_low"]) & (df["Close"].shift(1) >= df["swing_low"].shift(1))

    # Track rolling market bias
    bias = np.zeros(len(df), dtype=np.int8)
    cur = 0
    for i, (b, s) in enumerate(zip(bos_bull, bos_bear)):
        if b:
            cur = 1
        elif s:
            cur = -1
        bias[i] = cur
    df["bias"] = bias

    bull_candle = df["Close"] > df["Open"]
    bear_candle = df["Close"] < df["Open"]

    buy = (
        (df["bias"] == 1)
        & df["rsi"].between(30, 55)
        & bull_candle
        & (df["Close"] > df["ema20"])
    )
    sell = (
        (df["bias"] == -1)
        & df["rsi"].between(45, 70)
        & bear_candle
        & (df["Close"] < df["ema20"])
    )

    df["signal"] = np.where(buy, 1, np.where(sell, -1, 0))
    return df


# ─── Trade Simulation ──────────────────────────────────────────────────────────

def _simulate(df: pd.DataFrame, cfg: BacktestConfig, ts_fmt: str) -> dict:
    close = df["Close"].values
    high  = df["High"].values
    low   = df["Low"].values
    opens = df["Open"].values
    atr   = df["atr"].values
    sig   = df["signal"].values
    ts    = df.index.strftime(ts_fmt).tolist()

    n          = len(df)
    equity     = cfg.initial_capital
    risk_frac  = cfg.risk_per_trade_pct / 100
    sl_mult    = cfg.sl_atr_mult
    rr         = cfg.tp_rr

    trades: list[dict] = []
    equity_curve: list[list] = []
    trade: dict | None = None

    for i in range(n):
        equity_curve.append([ts[i], round(equity, 2)])

        if trade is None:
            # Look for entry signal; need room for at least one exit bar
            if np.isnan(atr[i]) or sig[i] == 0 or i + 1 >= n:
                continue

            entry = float(opens[i + 1])
            if sig[i] == 1:   # BUY
                sl = entry - float(atr[i]) * sl_mult
                tp = entry + (entry - sl) * rr
                direction = "BUY"
            else:             # SELL
                sl = entry + float(atr[i]) * sl_mult
                tp = entry - (sl - entry) * rr
                direction = "SELL"

            risk_pts = abs(entry - sl)
            if risk_pts < 0.01:
                continue

            qty = max(1, int((equity * risk_frac) / risk_pts))
            trade = {
                "entry_time": ts[i + 1],
                "signal":     direction,
                "entry":      round(entry, 2),
                "sl":         round(sl, 2),
                "tp":         round(tp, 2),
                "qty":        qty,
                "_bar":       i + 1,   # removed before returning
            }

        else:
            if i <= trade["_bar"]:
                continue  # don't check exit on entry bar itself

            if trade["signal"] == "BUY":
                if low[i] <= trade["sl"]:
                    pnl, outcome, exit_px = (trade["sl"] - trade["entry"]) * trade["qty"], "LOSS", trade["sl"]
                elif high[i] >= trade["tp"]:
                    pnl, outcome, exit_px = (trade["tp"] - trade["entry"]) * trade["qty"], "WIN",  trade["tp"]
                else:
                    continue
            else:
                if high[i] >= trade["sl"]:
                    pnl, outcome, exit_px = (trade["entry"] - trade["sl"]) * trade["qty"], "LOSS", trade["sl"]
                elif low[i] <= trade["tp"]:
                    pnl, outcome, exit_px = (trade["entry"] - trade["tp"]) * trade["qty"], "WIN",  trade["tp"]
                else:
                    continue

            equity += pnl
            trade.update({"exit_time": ts[i], "exit": round(float(exit_px), 2),
                          "pnl": round(float(pnl), 2), "outcome": outcome})
            del trade["_bar"]
            trades.append(trade)
            trade = None

    # Force-close any trade still open at end of data
    if trade is not None:
        last = float(close[-1])
        pnl = (last - trade["entry"]) * trade["qty"] if trade["signal"] == "BUY" \
              else (trade["entry"] - last) * trade["qty"]
        equity += pnl
        equity_curve[-1][1] = round(equity, 2)
        trade.update({"exit_time": ts[-1], "exit": round(last, 2),
                      "pnl": round(float(pnl), 2), "outcome": "OPEN"})
        del trade["_bar"]
        trades.append(trade)

    return {
        "metrics":      _metrics(trades, equity_curve, cfg.initial_capital),
        "equity_curve": equity_curve,
        "trades":       trades,
        "data_range":   {"from": ts[0], "to": ts[-1], "bars": n},
    }


# ─── Performance Metrics ───────────────────────────────────────────────────────

def _metrics(trades: list, equity_curve: list, initial: float) -> dict:
    closed = [t for t in trades if t["outcome"] != "OPEN"]
    if not closed:
        return {"total_trades": 0, "note": "No completed trades found in this period."}

    pnls   = [t["pnl"] for t in closed]
    wins   = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    net    = sum(pnls)

    # Max drawdown from equity high-watermark
    peak, max_dd = initial, 0.0
    for _, eq in equity_curve:
        peak  = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak * 100)

    # Trade-based Sharpe (annualised, no risk-free rate)
    series = pd.Series(pnls)
    sharpe = float((series.mean() / series.std()) * (252 ** 0.5)) if len(pnls) > 1 and series.std() > 0 else 0.0

    avg_win  = sum(wins) / len(wins)   if wins   else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0

    return {
        "initial_capital":   initial,
        "final_equity":      round(initial + net, 2),
        "net_pnl":           round(net, 2),
        "total_return_pct":  round(net / initial * 100, 2),
        "total_trades":      len(closed),
        "win_rate":          round(len(wins) / len(closed) * 100, 1),
        "profit_factor":     round(sum(wins) / abs(sum(losses)), 2) if losses else 0.0,
        "sharpe_ratio":      round(sharpe, 2),
        "max_drawdown_pct":  round(max_dd, 2),
        "avg_win":           round(avg_win, 2),
        "avg_loss":          round(avg_loss, 2),
        "avg_rr":            round(abs(avg_win / avg_loss), 2) if avg_loss else 0.0,
    }


def _run(df: pd.DataFrame, cfg: BacktestConfig, ts_fmt: str) -> dict:
    df = _add_indicators(df)
    df = _add_signals(df)
    df = df.dropna(subset=["atr", "rsi"])
    if len(df) < 10:
        raise HTTPException(422, "Too few valid candles after indicator warmup (need ≥10).")
    return _simulate(df, cfg, ts_fmt)
