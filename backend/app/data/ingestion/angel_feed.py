"""
Angel One SmartAPI — real-time tick feed via WebSocket.

Setup:
  1. Open Angel One demat account at: https://www.angelone.in/
  2. Register for SmartAPI at: https://smartapi.angelbroking.com/
  3. Generate TOTP secret from the Angel One mobile app (Settings → SmartAPI)
  4. Fill ANGEL_* variables in .env

Data provided: LTP, OHLCV, OI, Bid/Ask for all NSE/BSE/MCX instruments.
"""

import asyncio
import json
import logging
import pyotp
from typing import Callable, Dict, List, Optional
from datetime import datetime, date

try:
    from SmartApi import SmartConnect
    # V1 package uses SmartWebSocket, V2 renamed to SmartWebSocketV2
    try:
        from SmartApi.SmartWebSocketV2 import SmartWebSocketV2
    except ImportError:
        from SmartApi import SmartWebSocket as SmartWebSocketV2
    _ANGEL_AVAILABLE = True
except ImportError:
    SmartConnect = None
    SmartWebSocketV2 = None
    _ANGEL_AVAILABLE = False

from app.core.config import settings
from app.core.utils import IST, EXCHANGE_NUM_TO_STR

logger = logging.getLogger(__name__)

# Angel One exchange codes
EXCHANGE_CODE = {
    "NSE": 1,
    "NFO": 2,   # NSE F&O
    "BSE": 3,
    "MCX": 5,
    "CDS": 13,  # Currency Derivatives
    "BFO": 7,   # BSE F&O
}

# Subscription modes
MODE_LTP = 1        # Last Traded Price only
MODE_QUOTE = 2      # LTP + OHLCV
MODE_SNAP_QUOTE = 3 # Full depth + OI


class AngelOneFeed:
    """
    Manages Angel One SmartAPI WebSocket connection.
    Publishes ticks to Redis pub/sub channel for other services to consume.
    """

    def __init__(self, on_tick: Optional[Callable] = None):
        self._smart: Optional[SmartConnect] = None
        self._sws: Optional[SmartWebSocketV2] = None
        self._auth_token: str = ""
        self._feed_token: str = ""
        self._subscribed_tokens: Dict[str, List[dict]] = {}  # mode → [{exchangeType, tokens}]
        self._on_tick = on_tick  # external callback
        self._connected = False

    # ─── Authentication ────────────────────────────────────────────────────────

    def login(self) -> bool:
        """Synchronous login — call once at startup."""
        if not _ANGEL_AVAILABLE:
            logger.warning("SmartAPI library not available — live feed disabled")
            return False
        if not settings.ANGEL_API_KEY:
            logger.info("ANGEL_API_KEY not set — live feed disabled (set in .env to enable)")
            return False

        try:
            totp = pyotp.TOTP(settings.ANGEL_TOTP_SECRET).now()
            self._smart = SmartConnect(api_key=settings.ANGEL_API_KEY)
            data = self._smart.generateSession(
                settings.ANGEL_CLIENT_ID,
                settings.ANGEL_PASSWORD,
                totp,
            )
            if data["status"]:
                self._auth_token = data["data"]["jwtToken"]
                self._feed_token = self._smart.getfeedToken()
                logger.info("Angel One login successful for client: %s", settings.ANGEL_CLIENT_ID)
                return True
            else:
                logger.error("Angel One login failed: %s", data.get("message"))
                return False
        except Exception as e:
            logger.error("Angel One login exception: %s", e)
            return False

    def refresh_session(self) -> bool:
        """Refresh JWT token (tokens expire daily — call before market open)."""
        try:
            totp = pyotp.TOTP(settings.ANGEL_TOTP_SECRET).now()
            data = self._smart.generateSession(
                settings.ANGEL_CLIENT_ID,
                settings.ANGEL_PASSWORD,
                totp,
            )
            if data["status"]:
                self._auth_token = data["data"]["jwtToken"]
                self._feed_token = self._smart.getfeedToken()
                return True
            return False
        except Exception as e:
            logger.error("Session refresh failed: %s", e)
            return False

    # ─── Historical Data ───────────────────────────────────────────────────────

    def get_historical_candles(
        self,
        exchange: str,
        token: str,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> List[dict]:
        """
        Fetch OHLCV candles from Angel One.
        interval: ONE_MINUTE, THREE_MINUTE, FIVE_MINUTE, TEN_MINUTE,
                  FIFTEEN_MINUTE, THIRTY_MINUTE, ONE_HOUR, ONE_DAY
        from_date / to_date: "YYYY-MM-DD HH:MM"
        """
        try:
            params = {
                "exchange": exchange,
                "symboltoken": token,
                "interval": interval,
                "fromdate": from_date,
                "todate": to_date,
            }
            resp = self._smart.getCandleData(params)
            if resp.get("status") and resp["data"]:
                candles = []
                for row in resp["data"]:
                    # Angel returns: [timestamp, open, high, low, close, volume]
                    candles.append({
                        "time": row[0],
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": int(row[5]),
                    })
                return candles
            return []
        except Exception as e:
            logger.error("Historical data fetch failed: %s", e)
            return []

    def search_symbol(self, query: str, exchange: str = "NSE") -> List[dict]:
        """Search instruments by name/symbol."""
        try:
            resp = self._smart.searchScrip(exchange, query)
            return resp.get("data", []) or []
        except Exception as e:
            logger.error("Symbol search failed: %s", e)
            return []

    def get_quote(self, exchange: str, token: str) -> Optional[dict]:
        """Get single instrument quote."""
        try:
            resp = self._smart.getMarketData(
                mode="FULL",
                exchangeTokens={exchange: [token]}
            )
            data = resp.get("data", {}).get("fetched", [])
            return data[0] if data else None
        except Exception as e:
            logger.error("Quote fetch failed: %s", e)
            return None

    def get_instruments_list(self, exchange: str) -> List[dict]:
        """Download full instrument master for an exchange."""
        try:
            return self._smart.fetchAllInstruments(exchange) or []
        except Exception as e:
            logger.error("Instruments download failed for %s: %s", exchange, e)
            return []

    # ─── WebSocket — Real-Time Feed ────────────────────────────────────────────

    def connect_live(self, token_list: List[dict], mode: int = MODE_SNAP_QUOTE):
        """
        Connect to WebSocket and subscribe to real-time ticks.

        token_list format:
            [{"exchangeType": 1, "tokens": ["26000", "1594"]}, ...]
            exchangeType: 1=NSE, 2=NFO, 3=BSE, 5=MCX
        """
        if not self._auth_token:
            logger.error("Not logged in — call login() first")
            return

        self._sws = SmartWebSocketV2(
            self._auth_token,
            settings.ANGEL_API_KEY,
            settings.ANGEL_CLIENT_ID,
            self._feed_token,
        )

        self._sws.on_open = self._on_open
        self._sws.on_data = self._on_data
        self._sws.on_error = self._on_error
        self._sws.on_close = self._on_close

        self._subscribed_tokens = {"mode": mode, "token_list": token_list}
        self._sws.connect()

    def _on_open(self, wsapp):
        self._connected = True
        logger.info("Angel One WebSocket connected")
        mode = self._subscribed_tokens.get("mode", MODE_SNAP_QUOTE)
        token_list = self._subscribed_tokens.get("token_list", [])
        self._sws.subscribe("algotrade_sub", mode, token_list)

    def _on_data(self, wsapp, message):
        """Called for every tick received. Normalize and forward."""
        try:
            tick = self._normalize_tick(message)
            if tick and self._on_tick:
                self._on_tick(tick)
        except Exception as e:
            logger.error("Tick processing error: %s | raw: %s", e, message)

    def _on_error(self, wsapp, error):
        logger.error("Angel One WebSocket error: %s", error)
        self._connected = False

    def _on_close(self, wsapp):
        logger.warning("Angel One WebSocket closed")
        self._connected = False

    def disconnect(self):
        if self._sws:
            self._sws.close_connection()
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ─── Data Normalization ────────────────────────────────────────────────────

    def _normalize_tick(self, raw: dict) -> Optional[dict]:
        """Convert Angel One tick format to our internal format."""
        if not raw or "token" not in raw:
            return None

        token = raw.get("token", "")
        exchange_type = raw.get("exchange_type", 1)

        return {
            "token": token,
            "symbol": raw.get("trading_symbol", ""),
            "exchange": EXCHANGE_NUM_TO_STR.get(exchange_type, "NSE"),
            "ltp": raw.get("last_traded_price", 0) / 100,  # Angel returns paise
            "open": raw.get("open_price_of_the_day", 0) / 100,
            "high": raw.get("high_price_of_the_day", 0) / 100,
            "low": raw.get("low_price_of_the_day", 0) / 100,
            "close": raw.get("close_price", 0) / 100,
            "volume": raw.get("volume_trade_for_the_day", 0),
            "oi": raw.get("open_interest", 0),
            "bid": raw.get("best_5_buy_data", [{}])[0].get("price", 0) / 100 if raw.get("best_5_buy_data") else 0,
            "ask": raw.get("best_5_sell_data", [{}])[0].get("price", 0) / 100 if raw.get("best_5_sell_data") else 0,
            "total_buy_qty": raw.get("total_buy_quantity", 0),
            "total_sell_qty": raw.get("total_sell_quantity", 0),
            "timestamp": datetime.now(IST).isoformat(),
        }


# ─── Default Watchlist Tokens ─────────────────────────────────────────────────
# These are Angel One token numbers for major instruments

DEFAULT_INDEX_TOKENS = {
    "exchangeType": 1,  # NSE
    "tokens": [
        "26000",  # NIFTY 50
        "26009",  # NIFTY BANK
        "26037",  # NIFTY FIN SERVICE
        "26074",  # NIFTY MIDCAP 50
        "26021",  # INDIA VIX
    ]
}

DEFAULT_FNO_TOKENS = {
    "exchangeType": 2,  # NFO — tokens fetched dynamically from instruments master
    "tokens": []  # populated at startup from DB
}
