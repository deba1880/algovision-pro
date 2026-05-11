"""
Signal Generator — combines SMC analysis + technical indicators + options flow
to produce precise BUY / SELL signals with entry, SL, and targets.
"""

import logging
from dataclasses import dataclass, asdict
from typing import Optional, List
import pandas as pd

from app.ai.smc.detector import SMCDetector
from app.ai.indicators import atr_scalar, rsi, macd, vwap

logger = logging.getLogger(__name__)

smc = SMCDetector()


@dataclass
class Signal:
    symbol: str
    exchange: str
    timeframe: str
    signal_type: str        # BUY, SELL, HOLD
    strength: float         # 0.0 – 1.0 confidence
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    target_3: float
    risk_reward: float
    strategy: str
    reasons: List[str]
    warnings: List[str]

    def to_dict(self) -> dict:
        return asdict(self)


class SignalGenerator:

    def generate(
        self,
        symbol: str,
        exchange: str,
        df: pd.DataFrame,
        timeframe: str = "15m",
        options_data: Optional[dict] = None,
        fii_net: Optional[float] = None,
    ) -> Signal:
        """
        Main signal generation combining all sub-engines.
        Returns a Signal with precise levels.
        """
        reasons: List[str] = []
        warnings: List[str] = []
        bull_score = 0
        bear_score = 0

        current_price = float(df["close"].iloc[-1])
        atr = atr_scalar(df)

        # ── 1. SMC Analysis ─────────────────────────────────────────────────
        smc_result = smc.analyse(df, timeframe)
        trend = smc_result.get("trend", "SIDEWAYS")

        if trend == "UPTREND":
            bull_score += 2
            reasons.append("Trend: UPTREND (price > EMA20 > EMA50)")
        elif trend == "DOWNTREND":
            bear_score += 2
            reasons.append("Trend: DOWNTREND (price < EMA20 < EMA50)")

        # BOS / CHOCH
        for event in smc_result.get("bos_choch", []):
            if event["type"] in ("BOS_BULL", "CHOCH_BULL"):
                bull_score += 2
                reasons.append(event["description"])
            elif event["type"] in ("BOS_BEAR", "CHOCH_BEAR"):
                bear_score += 2
                reasons.append(event["description"])

        # Stop hunt warning
        for hunt in smc_result.get("stop_hunts", []):
            if hunt["type"] == "STOP_HUNT_BEAR":
                bear_score += 3
                warnings.append(hunt["alert"])
            elif hunt["type"] == "STOP_HUNT_BULL":
                bull_score += 3
                warnings.append(hunt["alert"])

        # Price near Bullish OB
        for ob in smc_result.get("order_blocks", []):
            if ob["zone_type"] == "OB_BULL" and ob["price_bottom"] <= current_price <= ob["price_top"] * 1.005:
                bull_score += 3
                reasons.append(f"Price at Bullish Order Block [{ob['price_bottom']:.2f} – {ob['price_top']:.2f}]")
            elif ob["zone_type"] == "OB_BEAR" and ob["price_bottom"] * 0.995 <= current_price <= ob["price_top"]:
                bear_score += 3
                reasons.append(f"Price at Bearish Order Block [{ob['price_bottom']:.2f} – {ob['price_top']:.2f}]")

        # Price at Bullish FVG
        for fvg in smc_result.get("fair_value_gaps", []):
            if fvg["zone_type"] == "FVG_BULL" and fvg["price_bottom"] <= current_price <= fvg["price_top"]:
                bull_score += 2
                reasons.append(f"Price filling Bullish FVG [{fvg['price_bottom']:.2f} – {fvg['price_top']:.2f}]")
            elif fvg["zone_type"] == "FVG_BEAR" and fvg["price_bottom"] <= current_price <= fvg["price_top"]:
                bear_score += 2
                reasons.append(f"Price filling Bearish FVG [{fvg['price_bottom']:.2f} – {fvg['price_top']:.2f}]")

        # ── 2. Technical Indicators ─────────────────────────────────────────
        rsi_val = rsi(df)
        macd_line, macd_signal = macd(df)
        vwap_val = vwap(df)

        if 40 <= rsi_val <= 60:
            reasons.append(f"RSI neutral {rsi_val:.1f} — momentum building")
        elif rsi_val < 35:
            bull_score += 1
            reasons.append(f"RSI oversold {rsi_val:.1f}")
        elif rsi_val > 65:
            bear_score += 1
            reasons.append(f"RSI overbought {rsi_val:.1f}")

        if macd_line > macd_signal:
            bull_score += 1
            reasons.append("MACD bullish crossover")
        elif macd_line < macd_signal:
            bear_score += 1
            reasons.append("MACD bearish crossover")

        if current_price > vwap_val * 1.001:
            bull_score += 1
            reasons.append(f"Price above VWAP ({vwap_val:.2f})")
        elif current_price < vwap_val * 0.999:
            bear_score += 1
            reasons.append(f"Price below VWAP ({vwap_val:.2f})")

        # ── 3. Options Flow ──────────────────────────────────────────────────
        if options_data:
            pcr = options_data.get("pcr", 1.0)
            if pcr < 0.7:
                bear_score += 1
                warnings.append(f"PCR = {pcr:.2f} — extreme bullishness, contrarian warning")
            elif 0.7 <= pcr < 0.9:
                bull_score += 2
                reasons.append(f"PCR = {pcr:.2f} — bullish bias")
            elif 0.9 <= pcr <= 1.2:
                reasons.append(f"PCR = {pcr:.2f} — neutral market")
            elif pcr > 1.2:
                bear_score += 1
                warnings.append(f"PCR = {pcr:.2f} — elevated fear")

        # ── 4. FII/DII ───────────────────────────────────────────────────────
        if fii_net is not None:
            if fii_net > 500:
                bull_score += 1
                reasons.append(f"FII net buyers ₹{fii_net:.0f} Cr")
            elif fii_net < -500:
                bear_score += 1
                reasons.append(f"FII net sellers ₹{abs(fii_net):.0f} Cr")

        # ── Determine Signal ─────────────────────────────────────────────────
        total = bull_score + bear_score
        if total == 0:
            signal_type = "HOLD"
            strength = 0.0
        elif bull_score > bear_score and bull_score >= 5:
            signal_type = "BUY"
            strength = min(bull_score / (total + 1), 0.99)
        elif bear_score > bull_score and bear_score >= 5:
            signal_type = "SELL"
            strength = min(bear_score / (total + 1), 0.99)
        else:
            signal_type = "HOLD"
            strength = 0.3

        # ── Calculate Levels ─────────────────────────────────────────────────
        entry, sl, t1, t2, t3, rr = self._calculate_levels(
            signal_type, current_price, atr, smc_result
        )

        return Signal(
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            signal_type=signal_type,
            strength=round(strength, 3),
            entry_price=round(entry, 2),
            stop_loss=round(sl, 2),
            target_1=round(t1, 2),
            target_2=round(t2, 2),
            target_3=round(t3, 2),
            risk_reward=round(rr, 2),
            strategy="SMC+VWAP+Options",
            reasons=reasons,
            warnings=warnings,
        )

    def _calculate_levels(
        self,
        signal_type: str,
        price: float,
        atr: float,
        smc_result: dict,
    ) -> tuple:
        """Calculate SL and targets based on ATR and SMC zones."""
        if signal_type == "BUY":
            # SL below nearest OB bottom or 1.5 ATR below entry
            sl_candidates = [
                z["price_bottom"] - atr * 0.2
                for z in smc_result.get("order_blocks", [])
                if z["zone_type"] == "OB_BULL" and z["price_bottom"] < price
            ]
            sl = max(sl_candidates) if sl_candidates else price - atr * 1.5
            risk = price - sl
            return price, sl, price + risk * 1.5, price + risk * 2.5, price + risk * 4.0, risk and round((risk * 2.5) / risk, 2)

        elif signal_type == "SELL":
            sl_candidates = [
                z["price_top"] + atr * 0.2
                for z in smc_result.get("order_blocks", [])
                if z["zone_type"] == "OB_BEAR" and z["price_top"] > price
            ]
            sl = min(sl_candidates) if sl_candidates else price + atr * 1.5
            risk = sl - price
            return price, sl, price - risk * 1.5, price - risk * 2.5, price - risk * 4.0, risk and round((risk * 2.5) / risk, 2)

        return price, price, price, price, price, 0.0

