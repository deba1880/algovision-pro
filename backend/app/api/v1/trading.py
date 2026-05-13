"""
Trading API endpoints — orders, positions, portfolio.
Supports paper trading and live trading via broker adapters.
"""

import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.market import Order, Position

from app.core.config import settings
from app.core.database import get_db
from app.core.utils import IST

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Request / Response Models ─────────────────────────────────────────────────

class OrderRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"
    transaction: str = Field(..., pattern="^(BUY|SELL)$")
    order_type: str = Field("MARKET", pattern="^(MARKET|LIMIT|SL|SL-M)$")
    product: str = Field("MIS", pattern="^(MIS|CNC|NRML)$")
    quantity: int = Field(..., gt=0)
    price: float = Field(0, ge=0)
    trigger_price: float = Field(0, ge=0)
    signal_id: int | None = None


class ModifyOrderRequest(BaseModel):
    price: float = Field(0, ge=0)
    quantity: int | None = None
    trigger_price: float = Field(0, ge=0)


# ─── Risk Check ───────────────────────────────────────────────────────────────

async def _risk_check(order: OrderRequest, db: AsyncSession) -> tuple[bool, str]:
    """Run risk management checks before placing any order."""
    # 1. Max order value
    if order.price > 0 and (order.price * order.quantity) > settings.MAX_ORDER_VALUE_INR:
        return False, f"Order value exceeds limit of ₹{settings.MAX_ORDER_VALUE_INR:,.0f}"

    # 2. Max open positions
    result = await db.execute(text(
        "SELECT COUNT(*) FROM positions WHERE closed_at IS NULL AND is_paper = :paper"
    ), {"paper": settings.PAPER_TRADE_MODE})
    open_count = result.scalar()
    if open_count >= settings.MAX_OPEN_POSITIONS:
        return False, f"Max open positions ({settings.MAX_OPEN_POSITIONS}) reached"

    # 3. Market hours check
    now_ist = datetime.now(IST)
    current_time = now_ist.strftime("%H:%M")
    if not (settings.MARKET_OPEN <= current_time <= settings.MARKET_CLOSE):
        if order.order_type != "LIMIT":  # AMO logic: allow limit orders outside hours
            return False, f"Market closed. Trading hours: {settings.MARKET_OPEN}–{settings.MARKET_CLOSE} IST"

    # 4. Daily loss check
    result = await db.execute(text("""
        SELECT COALESCE(SUM(pnl), 0) FROM positions
        WHERE DATE(opened_at) = CURRENT_DATE AND closed_at IS NOT NULL
          AND is_paper = :paper
    """), {"paper": settings.PAPER_TRADE_MODE})
    daily_pnl = float(result.scalar() or 0)
    max_loss = settings.PAPER_TRADE_CAPITAL * settings.MAX_DAILY_LOSS_PCT / 100
    if daily_pnl < -max_loss:
        return False, f"Daily loss limit reached (₹{abs(daily_pnl):,.0f}). Trading halted."

    return True, "OK"


# ─── Place Order ──────────────────────────────────────────────────────────────

@router.post("/orders")
async def place_order(
    order: OrderRequest,
    db: AsyncSession = Depends(get_db),
):
    """Place order (paper or live based on PAPER_TRADE_MODE setting)."""
    ok, msg = await _risk_check(order, db)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Risk check failed: {msg}")

    if settings.PAPER_TRADE_MODE:
        return await _place_paper_order(order, db)
    else:
        return await _place_live_order(order, db)


async def _place_paper_order(order: OrderRequest, db: AsyncSession) -> dict:
    """Simulate order execution at current LTP."""
    from app.core.database import get_redis
    import json

    redis = await get_redis()
    quote_raw = await redis.get(f"quote:{order.symbol.upper()}")
    ltp = float(json.loads(quote_raw)["ltp"]) if quote_raw else order.price

    exec_price = ltp if order.order_type == "MARKET" else order.price

    result = await db.execute(text("""
        INSERT INTO orders (symbol, exchange, "transaction", order_type, product,
                            quantity, price, status, avg_price, filled_qty,
                            is_paper, broker, signal_id)
        VALUES (:symbol, :exchange, :transaction, :order_type, :product,
                :quantity, :price, 'COMPLETE', :avg_price, :quantity,
                TRUE, 'PAPER', :signal_id)
        RETURNING id, placed_at
    """), {
        "symbol": order.symbol.upper(),
        "exchange": order.exchange.upper(),
        "transaction": order.transaction,
        "order_type": order.order_type,
        "product": order.product,
        "quantity": order.quantity,
        "price": exec_price,
        "avg_price": exec_price,
        "signal_id": order.signal_id,
    })
    row = result.fetchone()

    # Create or update position
    qty = order.quantity if order.transaction == "BUY" else -order.quantity
    await db.execute(text("""
        INSERT INTO positions (symbol, exchange, product, quantity, avg_price, ltp, pnl, is_paper)
        VALUES (:symbol, :exchange, :product, :qty, :price, :ltp, 0, TRUE)
        ON CONFLICT DO NOTHING
    """), {
        "symbol": order.symbol.upper(), "exchange": order.exchange.upper(),
        "product": order.product, "qty": qty, "price": exec_price, "ltp": ltp,
    })

    await db.commit()
    logger.info("PAPER ORDER placed: %s %s %d @ ₹%.2f", order.transaction, order.symbol, order.quantity, exec_price)
    return {
        "status": "success",
        "order_id": row.id,
        "mode": "PAPER",
        "symbol": order.symbol,
        "transaction": order.transaction,
        "quantity": order.quantity,
        "avg_price": exec_price,
        "placed_at": str(row.placed_at),
        "message": f"Paper order executed at ₹{exec_price:.2f}",
    }


async def _place_live_order(order: OrderRequest, db: AsyncSession) -> dict:
    """Route to configured live broker."""
    # Import the active broker adapter
    broker = settings.ANGEL_API_KEY and "angel" or None
    if not broker:
        raise HTTPException(status_code=503, detail="No live broker configured. Set credentials in .env")

    # Angel One order placement
    try:
        from app.brokers.angel import AngelBroker
        angel = AngelBroker()
        resp = angel.place_order(
            symbol=order.symbol,
            exchange=order.exchange,
            transaction=order.transaction,
            order_type=order.order_type,
            product=order.product,
            quantity=order.quantity,
            price=order.price,
            trigger_price=order.trigger_price,
        )
        # Save to DB
        await db.execute(text("""
            INSERT INTO orders (broker_order_id, symbol, exchange, "transaction", order_type,
                                product, quantity, price, status, is_paper, broker, signal_id)
            VALUES (:broker_id, :symbol, :exchange, :transaction, :order_type,
                    :product, :quantity, :price, :status, FALSE, 'ANGEL', :signal_id)
        """), {
            "broker_id": resp.get("orderid", ""),
            "symbol": order.symbol.upper(),
            "exchange": order.exchange.upper(),
            "transaction": order.transaction,
            "order_type": order.order_type,
            "product": order.product,
            "quantity": order.quantity,
            "price": order.price,
            "status": resp.get("status", "PENDING"),
            "signal_id": order.signal_id,
        })
        await db.commit()
        return {"status": "success", "mode": "LIVE", "broker_response": resp}
    except Exception as e:
        logger.error("Live order failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Order placement failed: {e}")


# ─── Positions ────────────────────────────────────────────────────────────────

@router.get("/positions")
async def get_positions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT id, symbol, exchange, product, quantity, avg_price, ltp, pnl, pnl_pct, opened_at
        FROM positions
        WHERE closed_at IS NULL AND is_paper = :paper
        ORDER BY opened_at DESC
    """), {"paper": settings.PAPER_TRADE_MODE})
    rows = result.fetchall()
    return {
        "mode": "PAPER" if settings.PAPER_TRADE_MODE else "LIVE",
        "positions": [
            {
                "id": r.id,
                "symbol": r.symbol,
                "exchange": r.exchange,
                "product": r.product,
                "quantity": r.quantity,
                "avg_price": float(r.avg_price),
                "ltp": float(r.ltp or 0),
                "pnl": float(r.pnl or 0),
                "pnl_pct": float(r.pnl_pct or 0),
                "opened_at": str(r.opened_at),
            }
            for r in rows
        ],
    }


@router.get("/orders")
async def get_orders(limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT id, broker_order_id, placed_at, symbol, exchange, "transaction",
               order_type, product, quantity, price, status, avg_price, filled_qty,
               is_paper, broker
        FROM orders
        ORDER BY placed_at DESC
        LIMIT :limit
    """), {"limit": limit})
    rows = result.fetchall()
    return {
        "orders": [dict(r._mapping) for r in rows]
    }


@router.delete("/orders/{order_id}")
async def cancel_order(order_id: int, db: AsyncSession = Depends(get_db)):
    """Cancel a pending order."""
    await db.execute(text(
        "UPDATE orders SET status = 'CANCELLED' WHERE id = :id AND status IN ('PENDING','OPEN')"
    ), {"id": order_id})
    await db.commit()
    return {"status": "cancelled", "order_id": order_id}
