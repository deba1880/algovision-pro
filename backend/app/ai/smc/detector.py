"""
Smart Money Concept (SMC) detector.

Detects: Order Blocks, Fair Value Gaps, Break of Structure, Change of Character,
         Liquidity Zones, Stop Hunts, Inducement levels.

All methods operate on a pandas DataFrame with columns: open, high, low, close, volume.
Returns structured zone dicts that are stored in DB and sent to frontend for rendering.
"""

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional, Tuple
import numpy as np
import pandas as pd

from app.ai.indicators import atr

logger = logging.getLogger(__name__)


@dataclass
class SMCZone:
    zone_type: str      # OB_BULL, OB_BEAR, FVG_BULL, FVG_BEAR, LIQ_BSL, LIQ_SSL, STOP_HUNT
    price_top: float
    price_bottom: float
    candle_time: str
    strength: float = 1.0
    is_filled: bool = False
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class SMCDetector:

    def __init__(
        self,
        ob_strength_atr: float = 1.5,    # OB move must be > N * ATR
        fvg_min_size_pct: float = 0.05,  # FVG must be >= 0.05% of price
        liq_tolerance_pct: float = 0.15, # Equal high/low within 0.15%
        swing_lookback: int = 5,         # Bars each side to confirm swing
    ):
        self.ob_strength_atr = ob_strength_atr
        self.fvg_min_size_pct = fvg_min_size_pct
        self.liq_tolerance_pct = liq_tolerance_pct
        self.swing_lookback = swing_lookback

    # ─── Swing Highs / Lows ────────────────────────────────────────────────────

    def _swing_highs(self, df: pd.DataFrame) -> pd.Series:
        n = self.swing_lookback
        return df["high"].rolling(2 * n + 1, center=True).max() == df["high"]

    def _swing_lows(self, df: pd.DataFrame) -> pd.Series:
        n = self.swing_lookback
        return df["low"].rolling(2 * n + 1, center=True).min() == df["low"]

    # ─── Order Blocks ──────────────────────────────────────────────────────────

    def detect_order_blocks(self, df: pd.DataFrame) -> List[SMCZone]:
        """
        Bullish OB: Last bearish candle before a strong bullish impulse.
        Bearish OB: Last bullish candle before a strong bearish impulse.
        'Strong' = move size > ob_strength_atr * ATR.
        """
        zones: List[SMCZone] = []
        atr_series = atr(df)

        for i in range(1, len(df) - 1):
            if pd.isna(atr_series.iloc[i]):
                continue

            next_move_up   = df["close"].iloc[i + 1] - df["open"].iloc[i + 1]
            next_move_down = df["open"].iloc[i + 1] - df["close"].iloc[i + 1]
            threshold = self.ob_strength_atr * atr_series.iloc[i]

            # Bullish OB
            if (df["close"].iloc[i] < df["open"].iloc[i]
                    and next_move_up > threshold):
                strength = round(next_move_up / atr_series.iloc[i], 2)
                zones.append(SMCZone(
                    zone_type="OB_BULL",
                    price_top=float(df["open"].iloc[i]),
                    price_bottom=float(df["close"].iloc[i]),
                    candle_time=str(df.index[i]),
                    strength=strength,
                    description=f"Bullish OB — strength {strength:.1f}x ATR",
                ))

            # Bearish OB
            elif (df["close"].iloc[i] > df["open"].iloc[i]
                    and next_move_down > threshold):
                strength = round(next_move_down / atr_series.iloc[i], 2)
                zones.append(SMCZone(
                    zone_type="OB_BEAR",
                    price_top=float(df["close"].iloc[i]),
                    price_bottom=float(df["open"].iloc[i]),
                    candle_time=str(df.index[i]),
                    strength=strength,
                    description=f"Bearish OB — strength {strength:.1f}x ATR",
                ))

        # Only return the last 5 OBs of each type (most recent are most relevant)
        bull_obs = [z for z in zones if z.zone_type == "OB_BULL"][-5:]
        bear_obs = [z for z in zones if z.zone_type == "OB_BEAR"][-5:]
        return bull_obs + bear_obs

    # ─── Fair Value Gaps ───────────────────────────────────────────────────────

    def detect_fvg(self, df: pd.DataFrame) -> List[SMCZone]:
        """
        Bullish FVG:  candle[i-2].high < candle[i].low  → gap between them
        Bearish FVG:  candle[i-2].low  > candle[i].high → gap between them
        """
        zones: List[SMCZone] = []
        for i in range(2, len(df)):
            price = df["close"].iloc[i]
            min_size = price * self.fvg_min_size_pct / 100

            # Bullish FVG
            gap_bottom = float(df["high"].iloc[i - 2])
            gap_top    = float(df["low"].iloc[i])
            if gap_top > gap_bottom and (gap_top - gap_bottom) >= min_size:
                zones.append(SMCZone(
                    zone_type="FVG_BULL",
                    price_top=gap_top,
                    price_bottom=gap_bottom,
                    candle_time=str(df.index[i - 1]),
                    strength=round((gap_top - gap_bottom) / price * 100, 3),
                    description="Bullish FVG — expect price to return and react",
                ))

            # Bearish FVG
            gap_top    = float(df["low"].iloc[i - 2])
            gap_bottom = float(df["high"].iloc[i])
            if gap_top > gap_bottom and (gap_top - gap_bottom) >= min_size:
                zones.append(SMCZone(
                    zone_type="FVG_BEAR",
                    price_top=gap_top,
                    price_bottom=gap_bottom,
                    candle_time=str(df.index[i - 1]),
                    strength=round((gap_top - gap_bottom) / price * 100, 3),
                    description="Bearish FVG — expect price to return and react",
                ))

        # Return only unfilled FVGs (filled = price passed through the zone)
        current_price = float(df["close"].iloc[-1])
        active = []
        for z in zones[-20:]:  # last 20
            if z.zone_type == "FVG_BULL" and current_price < z.price_top:
                active.append(z)
            elif z.zone_type == "FVG_BEAR" and current_price > z.price_bottom:
                active.append(z)
        return active

    # ─── Break of Structure / Change of Character ──────────────────────────────

    def detect_bos_choch(self, df: pd.DataFrame) -> List[dict]:
        """
        BOS (Break of Structure): price breaks the last swing high/low IN the direction
                                  of the existing trend — continuation signal.
        CHOCH (Change of Character): price breaks the last swing high/low AGAINST the
                                     trend — potential reversal signal.
        """
        events = []
        sh = self._swing_highs(df)
        sl = self._swing_lows(df)

        swing_highs = df["high"][sh].dropna()
        swing_lows  = df["low"][sl].dropna()

        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return events

        last_sh = swing_highs.iloc[-2]  # second-to-last swing high
        last_sl = swing_lows.iloc[-2]   # second-to-last swing low
        last_close = float(df["close"].iloc[-1])
        last_bar = str(df.index[-1])

        # Determine trend: HH + HL = uptrend, LH + LL = downtrend
        hh = swing_highs.iloc[-1] > swing_highs.iloc[-2]
        hl = swing_lows.iloc[-1]  > swing_lows.iloc[-2]
        ll = swing_lows.iloc[-1]  < swing_lows.iloc[-2]
        lh = swing_highs.iloc[-1] < swing_highs.iloc[-2]

        uptrend   = hh and hl
        downtrend = ll and lh

        # BOS — bullish (uptrend, price breaks above last swing high)
        if uptrend and last_close > last_sh:
            events.append({
                "type": "BOS_BULL",
                "level": last_sh,
                "bar": last_bar,
                "description": "Bullish BOS — trend continuation upward",
            })

        # BOS — bearish (downtrend, price breaks below last swing low)
        if downtrend and last_close < last_sl:
            events.append({
                "type": "BOS_BEAR",
                "level": last_sl,
                "bar": last_bar,
                "description": "Bearish BOS — trend continuation downward",
            })

        # CHOCH — bearish (uptrend broken, price below last swing low)
        if uptrend and last_close < last_sl:
            events.append({
                "type": "CHOCH_BEAR",
                "level": last_sl,
                "bar": last_bar,
                "description": "⚠ Bearish CHOCH — possible trend reversal down",
            })

        # CHOCH — bullish (downtrend broken, price above last swing high)
        if downtrend and last_close > last_sh:
            events.append({
                "type": "CHOCH_BULL",
                "level": last_sh,
                "bar": last_bar,
                "description": "⚠ Bullish CHOCH — possible trend reversal up",
            })

        return events

    # ─── Liquidity Zones ──────────────────────────────────────────────────────

    def detect_liquidity_zones(self, df: pd.DataFrame) -> List[SMCZone]:
        """
        Equal highs (buy-side liquidity — BSL): retail stops cluster just above.
        Equal lows (sell-side liquidity — SSL): retail stops cluster just below.
        Institutions sweep these levels to fill their large orders.
        """
        zones: List[SMCZone] = []
        tol_pct = self.liq_tolerance_pct / 100

        highs = df["high"].values
        lows  = df["low"].values
        idx   = df.index

        seen_bsl = set()
        seen_ssl = set()

        for i in range(len(highs) - 10):
            for j in range(i + 5, len(highs)):
                # Buy-side liquidity — equal highs
                ref_h = highs[i]
                tol   = ref_h * tol_pct
                if abs(highs[j] - ref_h) <= tol:
                    level = round(max(highs[i], highs[j]), 2)
                    if level not in seen_bsl:
                        seen_bsl.add(level)
                        zones.append(SMCZone(
                            zone_type="LIQ_BSL",
                            price_top=level + tol,
                            price_bottom=level - tol,
                            candle_time=str(idx[i]),
                            strength=1.0,
                            description=f"Buy-side Liquidity @ {level:.2f} — stops above equal highs",
                        ))

                # Sell-side liquidity — equal lows
                ref_l = lows[i]
                tol   = ref_l * tol_pct
                if abs(lows[j] - ref_l) <= tol:
                    level = round(min(lows[i], lows[j]), 2)
                    if level not in seen_ssl:
                        seen_ssl.add(level)
                        zones.append(SMCZone(
                            zone_type="LIQ_SSL",
                            price_top=level + tol,
                            price_bottom=level - tol,
                            candle_time=str(idx[i]),
                            strength=1.0,
                            description=f"Sell-side Liquidity @ {level:.2f} — stops below equal lows",
                        ))

        return sorted(zones, key=lambda z: z.price_bottom, reverse=True)[:20]

    # ─── Stop Hunt Detector ────────────────────────────────────────────────────

    def detect_stop_hunts(self, df: pd.DataFrame, liq_zones: Optional[List[SMCZone]] = None) -> List[dict]:
        """
        Stop hunt (operator trap) signature:
        1. Price pierces a liquidity zone (sweeps equal highs/lows)
        2. Candle has a long wick (>65% of total range) into the zone
        3. Volume spike (>1.5x 20-bar average)
        4. Closes back inside the range — strong reversal candle follows
        """
        alerts = []
        if liq_zones is None:
            liq_zones = self.detect_liquidity_zones(df)
        vol_avg = df["volume"].rolling(20).mean()

        for i in range(1, len(df) - 1):
            candle = df.iloc[i]
            total_range = candle["high"] - candle["low"]
            if total_range < 1e-6:
                continue

            upper_wick = candle["high"] - max(candle["open"], candle["close"])
            lower_wick = min(candle["open"], candle["close"]) - candle["low"]
            vol_spike  = candle["volume"] > 1.5 * vol_avg.iloc[i] if not pd.isna(vol_avg.iloc[i]) else False

            # Bearish stop hunt (price spiked up — swept BSL — closed below)
            if upper_wick / total_range > 0.65 and vol_spike:
                bsl_swept = any(
                    z.zone_type == "LIQ_BSL"
                    and z.price_bottom <= candle["high"] <= z.price_top + z.price_top * 0.003
                    for z in liq_zones
                )
                if bsl_swept:
                    alerts.append({
                        "type": "STOP_HUNT_BEAR",
                        "bar": str(df.index[i]),
                        "sweep_level": float(candle["high"]),
                        "close": float(candle["close"]),
                        "alert": (
                            "OPERATOR TRAP DETECTED — Buy-side liquidity swept. "
                            "Price likely to reverse DOWN. Avoid buying the spike."
                        ),
                        "severity": "HIGH",
                    })

            # Bullish stop hunt (price spiked down — swept SSL — closed above)
            if lower_wick / total_range > 0.65 and vol_spike:
                ssl_swept = any(
                    z.zone_type == "LIQ_SSL"
                    and z.price_bottom - z.price_bottom * 0.003 <= candle["low"] <= z.price_top
                    for z in liq_zones
                )
                if ssl_swept:
                    alerts.append({
                        "type": "STOP_HUNT_BULL",
                        "bar": str(df.index[i]),
                        "sweep_level": float(candle["low"]),
                        "close": float(candle["close"]),
                        "alert": (
                            "OPERATOR TRAP DETECTED — Sell-side liquidity swept. "
                            "Price likely to reverse UP. Avoid panic selling."
                        ),
                        "severity": "HIGH",
                    })

        return alerts[-5:]  # return 5 most recent

    # ─── Full Analysis ─────────────────────────────────────────────────────────

    def analyse(self, df: pd.DataFrame, timeframe: str = "15m") -> dict:
        """Run all SMC detectors on a DataFrame. Returns full analysis dict."""
        if len(df) < 30:
            return {"error": "Insufficient data (need at least 30 candles)"}

        liq_zones = self.detect_liquidity_zones(df)
        return {
            "timeframe": timeframe,
            "order_blocks": [z.to_dict() for z in self.detect_order_blocks(df)],
            "fair_value_gaps": [z.to_dict() for z in self.detect_fvg(df)],
            "bos_choch": self.detect_bos_choch(df),
            "liquidity_zones": [z.to_dict() for z in liq_zones],
            "stop_hunts": self.detect_stop_hunts(df, liq_zones=liq_zones),
            "trend": self._determine_trend(df),
            "current_price": float(df["close"].iloc[-1]),
            "analysed_at": datetime.utcnow().isoformat(),
        }

    def _determine_trend(self, df: pd.DataFrame) -> str:
        """Simple trend direction from EMA 20 vs EMA 50."""
        ema20 = df["close"].ewm(span=20).mean().iloc[-1]
        ema50 = df["close"].ewm(span=50).mean().iloc[-1]
        price = df["close"].iloc[-1]
        if price > ema20 > ema50:
            return "UPTREND"
        elif price < ema20 < ema50:
            return "DOWNTREND"
        else:
            return "SIDEWAYS"
