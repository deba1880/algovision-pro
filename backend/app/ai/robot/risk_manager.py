"""Position sizing, SL/target calculation, and trailing stop logic."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ai.robot.engine import RobotConfig, RobotTrade

from app.core.utils import LOT_SIZES


def calculate_position_size(
    config: "RobotConfig",
    capital: float,
    option_premium: float,
    today_trade_count: int,
    active_trade_count: int,
) -> tuple[int, int]:
    """Return (lots, quantity). Returns (0, 0) if sizing constraints prevent entry."""
    if today_trade_count >= config.max_trades_per_day:
        return 0, 0
    if active_trade_count >= 2:  # hard cap: never more than 2 concurrent robot trades
        return 0, 0
    if option_premium <= 0:
        return 0, 0

    capital_per_trade = capital * config.capital_per_trade_pct / 100.0
    lot_size = config.lot_sizes.get(list(config.lot_sizes.keys())[0], 25)  # fallback
    cost_per_lot = option_premium * lot_size

    if cost_per_lot <= 0:
        return 0, 0

    lots = min(int(capital_per_trade / cost_per_lot), config.max_lots_per_trade)
    lots = max(lots, 1)  # always at least 1 lot if we're entering
    qty = lots * lot_size
    return lots, qty


def get_lot_size(symbol: str, config: "RobotConfig") -> int:
    return config.lot_sizes.get(symbol, LOT_SIZES.get(symbol, 25))


def calculate_trade_levels(entry_price: float, config: "RobotConfig") -> tuple[float, float, float, float]:
    """Return (sl_price, t1_price, t2_price, t3_price) based on % targets from entry premium."""
    sl = round(entry_price * (1 - config.stoploss_pct / 100), 2)
    t1 = round(entry_price * (1 + config.target1_pct / 100), 2)
    t2 = round(entry_price * (1 + config.target2_pct / 100), 2)
    t3 = round(entry_price * (1 + config.target3_pct / 100), 2)
    return sl, t1, t2, t3


def update_trailing_sl(trade: "RobotTrade", current_price: float, config: "RobotConfig") -> float:
    """After T1 hit, trail SL to breakeven + 5% buffer. Never move SL against the trade."""
    if not trade.t1_hit:
        return trade.sl_price
    # Trail to entry cost to lock in breakeven
    new_sl = round(trade.entry_price * 1.05, 2)
    # Only move SL upward (never lower it)
    return max(new_sl, trade.sl_price)
