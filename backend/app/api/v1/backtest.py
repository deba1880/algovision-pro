"""
Backtesting engine — SMC-inspired strategy on NSE historical data via yfinance.

Strategy: Break-of-Structure (BOS) + pullback entry
  - Detect swing high/low (20-bar rolling)
  - Bullish BOS: close breaks above swing high  → bullish bias
  - Bearish BOS: close breaks below swing low   → bearish bias
  - Entry: bias candle after pullback (RSI 30–55 for bull, 45–70 for bear)
            + candle direction confirmation + price above/below EMA20
  - Entry at open of next bar; SL = entry ± ATR × multiplier; TP = entry ± SL-distance × RR

Segments:
  SPOT       — trade the underlying index/equity directly
  FUTURES    — same signals, lot-size position sizing (NIFTY=25, BANKNIFTY=15, …)
  OPTIONS_CE — bullish BUY signals only; buy ATM call, P&L via Black-Scholes
  OPTIONS_PE — bearish SELL signals only; buy ATM put, P&L via Black-Scholes
"""

import asyncio
import logging
import math

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.utils import LOT_SIZES as _LOT_SIZES, STRIKE_GAPS as _STRIKE_GAPS

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
# Approximate bars-per-day for theta decay
_BARS_PER_DAY = {
    "5m": 75, "15m": 25, "30m": 12, "1h": 6, "1d": 1, "1w": 0.2,
}


class BacktestConfig(BaseModel):
    symbol: str = "NIFTY"
    timeframe: str = "1d"
    from_date: str = "2024-01-01"
    to_date: str = "2024-12-31"
    initial_capital: float = Field(100_000, ge=10_000)
    risk_per_trade_pct: float = Field(1.0, ge=0.1, le=5.0)
    sl_atr_mult: float = Field(1.5, ge=0.5, le=5.0)
    tp_rr: float = Field(2.0, ge=1.0, le=10.0)
    segment: str = "SPOT"           # SPOT | FUTURES | OPTIONS_CE | OPTIONS_PE
    assumed_iv_pct: float = Field(15.0, ge=5.0, le=80.0)
    option_dte: int = Field(15, ge=1, le=90)


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

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]

    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()

    ts_fmt = "%Y-%m-%d" if config.timeframe in ("1d", "1w") else "%Y-%m-%dT%H:%M:%S"
    return _run(df, config, ts_fmt)


# ─── Black-Scholes helpers ─────────────────────────────────────────────────────

def _norm_cdf(x: float) -> float:
    a = abs(x)
    t = 1.0 / (1.0 + 0.2316419 * a)
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
    p = 1.0 - (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * a * a) * poly
    return p if x >= 0.0 else 1.0 - p


def _bs_call(S: float, K: float, T: float, sigma: float) -> float:
    if T <= 0:
        return max(S - K, 0.0)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * _norm_cdf(d1) - K * _norm_cdf(d2)


def _bs_put(S: float, K: float, T: float, sigma: float) -> float:
    if T <= 0:
        return max(K - S, 0.0)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * _norm_cdf(-d2) - S * _norm_cdf(-d1)


# ─── Indicator Computation ─────────────────────────────────────────────────────

def _add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift()).abs()
    lc = (df["Low"] - df["Close"].shift()).abs()
    df["atr"] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))

    df["ema20"] = df["Close"].ewm(span=20).mean()

    df["swing_high"] = df["High"].rolling(20).max().shift(1)
    df["swing_low"]  = df["Low"].rolling(20).min().shift(1)
    return df


# ─── Signal Detection ──────────────────────────────────────────────────────────

def _add_signals(df: pd.DataFrame) -> pd.DataFrame:
    bos_bull = (df["Close"] > df["swing_high"]) & (df["Close"].shift(1) <= df["swing_high"].shift(1))
    bos_bear = (df["Close"] < df["swing_low"])  & (df["Close"].shift(1) >= df["swing_low"].shift(1))

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

    n         = len(df)
    equity    = cfg.initial_capital
    risk_frac = cfg.risk_per_trade_pct / 100
    sl_mult   = cfg.sl_atr_mult
    rr        = cfg.tp_rr
    segment   = cfg.segment.upper()

    sym       = cfg.symbol.upper()
    lot_size  = _LOT_SIZES.get(sym, 1)
    strike_gap = _STRIKE_GAPS.get(sym, 10)
    sigma     = cfg.assumed_iv_pct / 100.0
    bars_per_day = _BARS_PER_DAY.get(cfg.timeframe, 1)

    trades: list[dict] = []
    equity_curve: list[list] = []
    trade: dict | None = None

    for i in range(n):
        equity_curve.append([ts[i], round(equity, 2)])

        if trade is None:
            if np.isnan(atr[i]) or sig[i] == 0 or i + 1 >= n:
                continue
            # OPTIONS_CE only acts on bullish signals; OPTIONS_PE only on bearish
            if segment == "OPTIONS_CE" and sig[i] != 1:
                continue
            if segment == "OPTIONS_PE" and sig[i] != -1:
                continue

            entry = float(opens[i + 1])
            if sig[i] == 1:
                sl = entry - float(atr[i]) * sl_mult
                tp = entry + (entry - sl) * rr
                direction = "BUY"
            else:
                sl = entry + float(atr[i]) * sl_mult
                tp = entry - (sl - entry) * rr
                direction = "SELL"

            risk_pts = abs(entry - sl)
            if risk_pts < 0.01:
                continue

            if segment == "SPOT":
                qty = max(1, int((equity * risk_frac) / risk_pts))
                trade = {
                    "entry_time": ts[i + 1], "signal": direction,
                    "entry": round(entry, 2), "sl": round(sl, 2), "tp": round(tp, 2),
                    "qty": qty, "_bar": i + 1,
                }

            elif segment == "FUTURES":
                qty_lots = max(1, int((equity * risk_frac) / (risk_pts * lot_size)))
                trade = {
                    "entry_time": ts[i + 1], "signal": direction,
                    "entry": round(entry, 2), "sl": round(sl, 2), "tp": round(tp, 2),
                    "qty": qty_lots * lot_size, "_bar": i + 1,
                    "_lots": qty_lots, "_lot_size": lot_size,
                }

            else:  # OPTIONS_CE / OPTIONS_PE
                K = round(entry / strike_gap) * strike_gap
                T_entry = cfg.option_dte / 365.0
                if segment == "OPTIONS_CE":
                    p_entry = _bs_call(entry, K, T_entry, sigma)
                else:
                    p_entry = _bs_put(entry, K, T_entry, sigma)
                if p_entry < 0.01:
                    continue
                qty_lots = max(1, int((equity * risk_frac) / (p_entry * lot_size)))
                trade = {
                    "entry_time": ts[i + 1], "signal": direction,
                    "entry": round(p_entry, 2),  # display option premium as "entry"
                    "sl": round(sl, 2), "tp": round(tp, 2),
                    "qty": qty_lots * lot_size, "_bar": i + 1,
                    "_lots": qty_lots, "_lot_size": lot_size,
                    "_K": K, "_T_entry": T_entry, "_p_entry": p_entry,
                    "_spot_entry": entry,
                }

        else:
            if i <= trade["_bar"]:
                continue

            outcome = exit_px = None

            if trade["signal"] == "BUY":
                if low[i] <= trade["sl"]:
                    exit_px, outcome = trade["sl"], "LOSS"
                elif high[i] >= trade["tp"]:
                    exit_px, outcome = trade["tp"], "WIN"
            else:
                if high[i] >= trade["sl"]:
                    exit_px, outcome = trade["sl"], "LOSS"
                elif low[i] <= trade["tp"]:
                    exit_px, outcome = trade["tp"], "WIN"

            if outcome is None:
                continue

            if segment == "SPOT":
                if trade["signal"] == "BUY":
                    pnl = (exit_px - trade["entry"]) * trade["qty"]
                else:
                    pnl = (trade["entry"] - exit_px) * trade["qty"]
                exit_display = round(float(exit_px), 2)

            elif segment == "FUTURES":
                if trade["signal"] == "BUY":
                    pnl = (exit_px - float(opens[trade["_bar"]])) * trade["qty"]
                else:
                    pnl = (float(opens[trade["_bar"]]) - exit_px) * trade["qty"]
                exit_display = round(float(exit_px), 2)

            else:  # OPTIONS
                bars_held = i - trade["_bar"]
                days_held = bars_held / bars_per_day if bars_per_day > 0 else bars_held
                T_exit = max((cfg.option_dte - days_held) / 365.0, 0.5 / 365.0)
                K = trade["_K"]
                if segment == "OPTIONS_CE":
                    p_exit = _bs_call(float(exit_px), K, T_exit, sigma)
                else:
                    p_exit = _bs_put(float(exit_px), K, T_exit, sigma)
                pnl = (p_exit - trade["_p_entry"]) * trade["qty"]
                exit_display = round(p_exit, 2)

            equity += pnl
            t_out = {
                "entry_time": trade["entry_time"], "exit_time": ts[i],
                "signal": trade["signal"],
                "entry": trade["entry"], "exit": exit_display,
                "sl": trade["sl"], "tp": trade["tp"],
                "qty": trade["qty"], "pnl": round(float(pnl), 2), "outcome": outcome,
            }
            trades.append(t_out)
            trade = None

    # Force-close open trade at end of data
    if trade is not None:
        last_spot = float(close[-1])
        if segment == "SPOT":
            pnl = (last_spot - trade["entry"]) * trade["qty"] if trade["signal"] == "BUY" \
                  else (trade["entry"] - last_spot) * trade["qty"]
            exit_display = round(last_spot, 2)
        elif segment == "FUTURES":
            entry_spot = float(opens[trade["_bar"]])
            pnl = (last_spot - entry_spot) * trade["qty"] if trade["signal"] == "BUY" \
                  else (entry_spot - last_spot) * trade["qty"]
            exit_display = round(last_spot, 2)
        else:
            K = trade["_K"]
            T_exit = max(0.5 / 365.0, trade["_T_entry"] - (n - 1 - trade["_bar"]) / (bars_per_day * 365))
            if segment == "OPTIONS_CE":
                p_exit = _bs_call(last_spot, K, T_exit, sigma)
            else:
                p_exit = _bs_put(last_spot, K, T_exit, sigma)
            pnl = (p_exit - trade["_p_entry"]) * trade["qty"]
            exit_display = round(p_exit, 2)

        equity += pnl
        equity_curve[-1][1] = round(equity, 2)
        trades.append({
            "entry_time": trade["entry_time"], "exit_time": ts[-1],
            "signal": trade["signal"],
            "entry": trade["entry"], "exit": exit_display,
            "sl": trade["sl"], "tp": trade["tp"],
            "qty": trade["qty"], "pnl": round(float(pnl), 2), "outcome": "OPEN",
        })

    return {
        "metrics":      _metrics(trades, equity_curve, cfg.initial_capital),
        "equity_curve": equity_curve,
        "trades":       trades,
        "data_range":   {"from": ts[0], "to": ts[-1], "bars": n},
        "segment":      segment,
        "lot_size":     lot_size if segment != "SPOT" else 1,
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

    peak, max_dd = initial, 0.0
    for _, eq in equity_curve:
        peak   = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak * 100)

    series = pd.Series(pnls)
    sharpe = float((series.mean() / series.std()) * (252 ** 0.5)) if len(pnls) > 1 and series.std() > 0 else 0.0

    avg_win  = sum(wins) / len(wins)     if wins   else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0

    return {
        "initial_capital":  initial,
        "final_equity":     round(initial + net, 2),
        "net_pnl":          round(net, 2),
        "total_return_pct": round(net / initial * 100, 2),
        "total_trades":     len(closed),
        "win_rate":         round(len(wins) / len(closed) * 100, 1),
        "profit_factor":    round(sum(wins) / abs(sum(losses)), 2) if losses else 0.0,
        "sharpe_ratio":     round(sharpe, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "avg_win":          round(avg_win, 2),
        "avg_loss":         round(avg_loss, 2),
        "avg_rr":           round(abs(avg_win / avg_loss), 2) if avg_loss else 0.0,
    }


def _run(df: pd.DataFrame, cfg: BacktestConfig, ts_fmt: str) -> dict:
    df = _add_indicators(df)
    df = _add_signals(df)
    df = df.dropna(subset=["atr", "rsi"])
    if len(df) < 10:
        raise HTTPException(422, "Too few valid candles after indicator warmup (need ≥10).")
    return _simulate(df, cfg, ts_fmt)
