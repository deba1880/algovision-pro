"""
Alert notifications via Telegram and email.
Sends BUY/SELL signal alerts when confidence exceeds threshold.
"""

import asyncio
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

try:
    import aiosmtplib
    _HAS_SMTP = True
except ImportError:
    _HAS_SMTP = False

try:
    from telegram import Bot
    _HAS_TELEGRAM = True
except ImportError:
    _HAS_TELEGRAM = False

from app.core.config import settings

logger = logging.getLogger(__name__)


class AlertNotifier:
    """Send signal alerts via Telegram and/or SMTP email."""

    def __init__(self):
        self._bot: Optional[object] = None

    def _get_bot(self):
        if not _HAS_TELEGRAM or not settings.TELEGRAM_BOT_TOKEN:
            return None
        if self._bot is None:
            self._bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        return self._bot

    async def send_telegram(self, message: str) -> bool:
        bot = self._get_bot()
        if bot is None or not settings.TELEGRAM_CHAT_ID:
            return False
        try:
            await bot.send_message(
                chat_id=settings.TELEGRAM_CHAT_ID,
                text=message,
                parse_mode="Markdown",
            )
            return True
        except Exception as e:
            logger.warning("Telegram send failed: %s", e)
            return False

    async def send_email(self, subject: str, body_html: str) -> bool:
        if not _HAS_SMTP or not settings.SMTP_USER or not settings.SMTP_PASSWORD:
            return False
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_USER
        msg["To"] = settings.SMTP_USER
        msg.attach(MIMEText(body_html, "html"))
        try:
            await aiosmtplib.send(
                msg,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                start_tls=True,
            )
            return True
        except Exception as e:
            logger.warning("Email send failed: %s", e)
            return False

    async def notify_signal(self, signal: dict) -> None:
        """Send alert for a BUY/SELL signal. No-op for HOLD."""
        if signal.get("signal_type") == "HOLD":
            return

        is_buy = signal["signal_type"] == "BUY"
        emoji = "🟢" if is_buy else "🔴"
        color = "#22c55e" if is_buy else "#ef4444"
        conf = f"{signal.get('strength', 0) * 100:.0f}%"
        ts = signal.get("generated_at", "")[:19].replace("T", " ")

        tg = (
            f"{emoji} *{signal['signal_type']} — {signal['symbol']}*\n"
            f"_{signal.get('exchange','NSE')} · {signal.get('timeframe','15m')} · Confidence {conf}_\n\n"
            f"Entry:    `{signal['entry_price']:.2f}`\n"
            f"Stop Loss: `{signal['stop_loss']:.2f}`\n"
            f"Target 1:  `{signal['target_1']:.2f}`\n"
            f"Target 2:  `{signal['target_2']:.2f}`\n"
            f"R:R: 1:{signal.get('risk_reward', 0):.2f}\n\n"
            f"Strategy: {signal.get('strategy', '')}\n"
            f"{ts} IST"
        )

        email_html = f"""
<div style="font-family:sans-serif;max-width:480px">
  <h2 style="color:{color};margin:0">{signal['signal_type']} Signal — {signal['symbol']}</h2>
  <p style="color:#666;margin:4px 0">{signal.get('exchange','NSE')} &bull;
     {signal.get('timeframe','15m')} &bull; Confidence {conf}</p>
  <table style="border-collapse:collapse;width:100%;margin-top:12px">
    <tr><td style="padding:4px 8px;color:#666">Entry</td>
        <td style="padding:4px 8px;font-family:monospace">{signal['entry_price']:.2f}</td></tr>
    <tr><td style="padding:4px 8px;color:#666">Stop Loss</td>
        <td style="padding:4px 8px;font-family:monospace;color:#ef4444">{signal['stop_loss']:.2f}</td></tr>
    <tr><td style="padding:4px 8px;color:#666">Target 1</td>
        <td style="padding:4px 8px;font-family:monospace;color:#22c55e">{signal['target_1']:.2f}</td></tr>
    <tr><td style="padding:4px 8px;color:#666">Target 2</td>
        <td style="padding:4px 8px;font-family:monospace;color:#22c55e">{signal['target_2']:.2f}</td></tr>
    <tr><td style="padding:4px 8px;color:#666">R:R</td>
        <td style="padding:4px 8px;font-family:monospace">1:{signal.get('risk_reward',0):.2f}</td></tr>
  </table>
  <p style="color:#666;font-size:12px;margin-top:12px">
    Strategy: {signal.get('strategy','')}<br>{ts} IST
  </p>
  <p style="color:#aaa;font-size:11px">AlgoVision Pro — paper trade only, not financial advice</p>
</div>"""

        await asyncio.gather(
            self.send_telegram(tg),
            self.send_email(
                subject=f"[AlgoVision] {signal['signal_type']} {signal['symbol']} @ {signal['entry_price']:.2f}",
                body_html=email_html,
            ),
            return_exceptions=True,
        )

    async def notify_event(self, event: dict) -> None:
        """Send alert for an upcoming high-impact market event."""
        if event.get("impact") not in ("HIGH", "MEDIUM"):
            return
        emoji = "🔔" if event.get("impact") == "HIGH" else "📅"
        tg = (
            f"{emoji} *Market Event: {event.get('title', '')}*\n"
            f"Date: {event.get('date', '')}  Time: {event.get('time') or 'All Day'}\n"
            f"Category: {event.get('category', '')}  Impact: {event.get('impact', '')}\n"
        )
        if event.get("description"):
            tg += f"\n_{event['description']}_"
        await self.send_telegram(tg)


notifier = AlertNotifier()
