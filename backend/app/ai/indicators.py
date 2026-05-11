"""
Shared technical indicator helpers used by both the SMC detector and signal generator.
All functions operate on a pandas DataFrame with open/high/low/close/volume columns.
"""

import numpy as np
import pandas as pd


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range — returns a Series aligned with df.index."""
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"]  - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def atr_scalar(df: pd.DataFrame, period: int = 14) -> float:
    """Last ATR value as a float."""
    return float(atr(df, period).iloc[-1] or 0)


def rsi(df: pd.DataFrame, period: int = 14) -> float:
    """Last RSI value."""
    delta = df["close"].diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    series = 100 - 100 / (1 + rs)
    return float(series.iloc[-1] or 50)


def macd(df: pd.DataFrame) -> tuple[float, float]:
    """Returns (macd_line, signal_line) — last values."""
    ema12  = df["close"].ewm(span=12).mean()
    ema26  = df["close"].ewm(span=26).mean()
    line   = ema12 - ema26
    signal = line.ewm(span=9).mean()
    return float(line.iloc[-1] or 0), float(signal.iloc[-1] or 0)


def vwap(df: pd.DataFrame) -> float:
    """Session VWAP — last value."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    cumvol  = df["volume"].cumsum()
    series  = (typical * df["volume"]).cumsum() / cumvol.replace(0, np.nan)
    return float(series.iloc[-1] or df["close"].iloc[-1])
