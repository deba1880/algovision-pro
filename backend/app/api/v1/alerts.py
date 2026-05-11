"""
Alert configuration status and test endpoints.
"""

import logging
from datetime import datetime

from fastapi import APIRouter

from app.core.config import settings
from app.core.utils import IST
from app.alerts.notifier import notifier

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/status")
async def alert_status():
    """Return which alert channels are configured (without exposing secrets)."""
    return {
        "telegram": {
            "configured": bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID),
            "chat_id": settings.TELEGRAM_CHAT_ID or None,
        },
        "email": {
            "configured": bool(settings.SMTP_USER and settings.SMTP_PASSWORD),
            "smtp_host": settings.SMTP_HOST,
            "smtp_port": settings.SMTP_PORT,
            "user": settings.SMTP_USER or None,
        },
        "paper_trade_mode": settings.PAPER_TRADE_MODE,
        "risk_controls": {
            "max_daily_loss_pct": settings.MAX_DAILY_LOSS_PCT,
            "max_open_positions": settings.MAX_OPEN_POSITIONS,
            "max_order_value_inr": settings.MAX_ORDER_VALUE_INR,
        },
    }


@router.post("/test")
async def send_test_alert():
    """Send a test alert to all configured channels."""
    now = datetime.now(IST).isoformat()[:19].replace("T", " ")
    test_signal = {
        "signal_type": "BUY",
        "symbol": "NIFTY",
        "exchange": "NSE",
        "timeframe": "15m",
        "strength": 0.75,
        "entry_price": 22500.00,
        "stop_loss": 22350.00,
        "target_1": 22725.00,
        "target_2": 22950.00,
        "risk_reward": 2.5,
        "strategy": "SMC+VWAP+Options (TEST)",
        "generated_at": now,
    }

    tg_sent = await notifier.send_telegram(
        f"🧪 *Test Alert — AlgoVision Pro*\n_{now} IST_\n\nTelegram alerts are working correctly."
    )
    email_sent = await notifier.send_email(
        subject="[AlgoVision] Test Alert",
        body_html=f"<p>AlgoVision Pro test alert sent at {now} IST.</p><p>Email alerts are working correctly.</p>",
    )

    return {
        "telegram_sent": tg_sent,
        "email_sent": email_sent,
        "message": "Test alert sent to configured channels.",
    }
