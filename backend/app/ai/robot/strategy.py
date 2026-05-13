"""
Entry/exit condition logic for the options robot.
Wraps existing SMC detector, indicators, and signal generator.
"""

from __future__ import annotations
import logging
import pandas as pd
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ai.robot.engine import RobotConfig, RobotTrade

from app.ai.signals.generator import Signal

logger = logging.getLogger(__name__)


# ─── Entry Conditions ─────────────────────────────────────────────────────────

def check_entry_conditions(
    signal: Signal,
    df: pd.DataFrame,
    smc_result: dict,
    options_data: dict | None,
    config: "RobotConfig",
) -> tuple[bool, list[str]]:
    """
    All 5 conditions must pass to enter a trade.
    Returns (should_enter, reasons).
    """
    reasons: list[str] = []

    # 1. Signal must be actionable
    if signal.signal_type not in ("BUY", "SELL"):
        return False, ["Signal is HOLD"]
    if signal.strength < 0.5:
        return False, [f"Signal strength too low: {signal.strength:.2f}"]
    reasons.append(f"Signal: {signal.signal_type} (strength {signal.strength:.2f})")

    # 2. Volume confirmation
    if len(df) >= 21:
        last_vol = float(df["volume"].iloc[-1])
        avg_vol = float(df["volume"].rolling(20).mean().iloc[-1])
        if avg_vol > 0 and last_vol < 1.2 * avg_vol:
            return False, ["Insufficient volume confirmation"]
        reasons.append(f"Volume confirmed: {last_vol/avg_vol:.1f}× avg")

    # 3. False breakout check — close must be beyond BOS level, not just a wick
    bos_events = [e for e in smc_result.get("bos_choch", []) if "BOS" in e.get("type", "")]
    if bos_events:
        latest_bos = bos_events[-1]
        bos_level = latest_bos.get("level", 0)
        close = float(df["close"].iloc[-1])
        if signal.signal_type == "BUY" and close < bos_level:
            return False, ["Price closed below BOS level — false breakout suspected"]
        if signal.signal_type == "SELL" and close > bos_level:
            return False, ["Price closed above BOS level — false breakout suspected"]
        reasons.append(f"BOS confirmed at {bos_level:.1f}")

    # 4. PCR liquidity check
    if options_data:
        pcr = options_data.get("pcr", 1.0)
        if signal.signal_type == "BUY" and pcr > 1.0:
            return False, [f"PCR {pcr:.2f} too high for CE entry (bearish flow)"]
        if signal.signal_type == "SELL" and pcr < 1.0:
            return False, [f"PCR {pcr:.2f} too low for PE entry (bullish flow)"]
        reasons.append(f"PCR favorable: {pcr:.2f}")

    # 5. No recent stop hunt in trade direction (last 3 bars)
    hunts = smc_result.get("stop_hunts", [])
    recent_hunts = [h for h in hunts if h.get("bar", -99) >= len(df) - 3]
    for hunt in recent_hunts:
        hunt_type = hunt.get("type", "")
        if signal.signal_type == "BUY" and "BULL" in hunt_type:
            return False, ["Recent bullish stop hunt — smart money may have exited"]
        if signal.signal_type == "SELL" and "BEAR" in hunt_type:
            return False, ["Recent bearish stop hunt — smart money may have exited"]

    reasons.extend(signal.reasons[:3])
    return True, reasons


# ─── Option Selection ─────────────────────────────────────────────────────────

def select_option(
    symbol: str,
    signal_type: str,
    underlying_price: float,
    options_data: dict,
    config: "RobotConfig",
    expiry_preference: str = "WEEKLY",
) -> tuple[float, str, str, float] | None:
    """
    Returns (strike, expiry, option_type, ltp) or None if no suitable option found.
    """
    from app.ai.robot.engine import classify_expiries

    option_type = "CE" if signal_type == "BUY" else "PE"
    expiry_dates = options_data.get("expiry_dates", [])
    weekly_exp, monthly_exp = classify_expiries(expiry_dates)

    target_expiries = weekly_exp if expiry_preference == "WEEKLY" else monthly_exp
    if not target_expiries:
        target_expiries = expiry_dates[:1]  # fallback to nearest

    target_expiry = target_expiries[0]

    # Select strike based on config
    strike_offset = {
        "ATM": 0,
        "OTM1": 1,
        "OTM2": 2,
        "ITM1": -1,
    }.get(config.strike_selection, 0)

    rows = [r for r in options_data.get("data", []) if r.get("expiry") == target_expiry]
    if not rows:
        return None

    # Find ATM strike
    atm_row = min(rows, key=lambda r: abs(r["strike"] - underlying_price))
    atm_strike = atm_row["strike"]

    # Get sorted unique strikes
    strikes = sorted(set(r["strike"] for r in rows))
    try:
        atm_idx = strikes.index(atm_strike)
    except ValueError:
        return None

    # Apply offset: for CE buy, OTM means higher strike; for PE sell, OTM means lower
    if option_type == "CE":
        target_idx = atm_idx + strike_offset
    else:
        target_idx = atm_idx - strike_offset

    target_idx = max(0, min(target_idx, len(strikes) - 1))
    target_strike = strikes[target_idx]

    # Get LTP
    for row in rows:
        if abs(row["strike"] - target_strike) < 0.01:
            ltp = row.get(option_type, {}).get("ltp", 0)
            if ltp and ltp > 0:
                return target_strike, target_expiry, option_type, ltp

    return None


# ─── Exit Conditions ──────────────────────────────────────────────────────────

def check_exit_conditions(
    trade: "RobotTrade",
    current_price: float,
    smc_result: dict,
    df: pd.DataFrame,
    config: "RobotConfig",
) -> tuple[bool, str, str]:
    """
    Returns (should_exit, exit_reason, new_status).
    Checks SL, targets, CHOCH reversal, VWAP cross, RSI divergence, stop hunt.
    """
    # 1. Stop loss hit
    if current_price <= trade.sl_price:
        return True, f"Stop loss hit at ₹{current_price:.2f}", "CLOSED_SL"

    # 2. Target hits (handled separately in _check_exits but also here for full exit)
    if not trade.t2_hit and current_price >= trade.t2_price:
        return True, f"Target 2 hit at ₹{current_price:.2f}", "CLOSED_T2"
    if not trade.t1_hit and current_price >= trade.t1_price:
        return True, f"Target 1 hit at ₹{current_price:.2f}", "CLOSED_T1"

    # 3. CHOCH reversal — trend change detected against our position
    bos_choch = smc_result.get("bos_choch", [])
    recent_events = [e for e in bos_choch if e.get("bar", -99) >= len(df) - 2]
    for event in recent_events:
        etype = event.get("type", "")
        if trade.option_type == "CE" and "CHOCH_BEAR" in etype:
            return True, "CHOCH reversal — bearish structure change, exiting CE", "CLOSED_REVERSAL"
        if trade.option_type == "PE" and "CHOCH_BULL" in etype:
            return True, "CHOCH reversal — bullish structure change, exiting PE", "CLOSED_REVERSAL"

    # 4. VWAP cross against position
    if len(df) >= 2:
        from app.ai.indicators import vwap as calc_vwap
        try:
            vwap_val = calc_vwap(df)
            close = float(df["close"].iloc[-1])
            prev_close = float(df["close"].iloc[-2])
            if trade.option_type == "CE" and prev_close >= vwap_val and close < vwap_val:
                return True, f"Price crossed below VWAP ({vwap_val:.1f}) — exiting CE", "CLOSED_REVERSAL"
            if trade.option_type == "PE" and prev_close <= vwap_val and close > vwap_val:
                return True, f"Price crossed above VWAP ({vwap_val:.1f}) — exiting PE", "CLOSED_REVERSAL"
        except Exception:
            pass

    # 5. RSI divergence check
    if len(df) >= 14:
        divergence = _detect_rsi_divergence(df)
        if trade.option_type == "CE" and divergence == "BEAR_DIV":
            return True, "Bearish RSI divergence detected — exiting CE", "CLOSED_REVERSAL"
        if trade.option_type == "PE" and divergence == "BULL_DIV":
            return True, "Bullish RSI divergence detected — exiting PE", "CLOSED_REVERSAL"

    # 6. Stop hunt in trade direction
    hunts = smc_result.get("stop_hunts", [])
    recent_hunts = [h for h in hunts if h.get("bar", -99) >= len(df) - 2]
    for hunt in recent_hunts:
        hunt_type = hunt.get("type", "")
        if trade.option_type == "CE" and "BULL" in hunt_type:
            return True, "Stop hunt in CE direction — smart money may be reversing", "CLOSED_REVERSAL"
        if trade.option_type == "PE" and "BEAR" in hunt_type:
            return True, "Stop hunt in PE direction — smart money may be reversing", "CLOSED_REVERSAL"

    return False, "", ""


def _detect_rsi_divergence(df: pd.DataFrame) -> str | None:
    """
    Compare last 2 swing points in price vs RSI series (10-bar lookback).
    Returns 'BEAR_DIV', 'BULL_DIV', or None.
    """
    try:
        closes = df["close"].values.astype(float)
        if len(closes) < 14:
            return None

        # Compute RSI series
        delta = pd.Series(closes).diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-10)
        rsi_series = (100 - 100 / (1 + rs)).values

        # Last 10 bars
        n = min(10, len(closes))
        price_window = closes[-n:]
        rsi_window = rsi_series[-n:]

        price_max_idx = price_window.argmax()
        price_min_idx = price_window.argmin()

        # Bearish divergence: price HH but RSI LH
        if price_max_idx > n // 2:
            half_rsi_max = rsi_window[:price_max_idx].max() if price_max_idx > 0 else rsi_window[0]
            if rsi_window[price_max_idx] < half_rsi_max:
                return "BEAR_DIV"

        # Bullish divergence: price LL but RSI HL
        if price_min_idx > n // 2:
            half_rsi_min = rsi_window[:price_min_idx].min() if price_min_idx > 0 else rsi_window[0]
            if rsi_window[price_min_idx] > half_rsi_min:
                return "BULL_DIV"

    except Exception:
        pass
    return None
