"""
NSE India data scraper.
Fetches: options chain, FII/DII, indices, market breadth, corporate actions.

Uses requests.Session (sync) via asyncio executor — more reliable than httpx
for NSE's cookie-based session management. NSE rate-limits aggressively;
all requests include proper browser headers and a session warmup sequence.
"""

import asyncio
import logging
import threading
import time
from datetime import datetime
from typing import List, Optional
import requests

from app.core.utils import IST

logger = logging.getLogger(__name__)


def _to_float(val, default: float = 0.0) -> float:
    try:
        return float(str(val).replace(",", "")) if val is not None else default
    except (ValueError, TypeError):
        return default


def _to_int(val, default: int = 0) -> int:
    try:
        return int(float(str(val).replace(",", ""))) if val is not None else default
    except (ValueError, TypeError):
        return default


NSE_BASE = "https://www.nseindia.com"
NSE_API  = "https://www.nseindia.com/api"

# No 'br' — requests doesn't decode Brotli without brotlicffi installed
NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}


class _SyncNSESession:
    """
    Thread-safe wrapper around requests.Session for NSE API calls.
    All operations are serialized through a single lock — NSE rate-limits
    aggressively, and requests.Session is not safe for concurrent access.
    """

    def __init__(self):
        self._session: Optional[requests.Session] = None
        self._lock = threading.Lock()
        self._options_warmed = False

    # Headers for page visits (different Accept from API calls)
    _PAGE_HEADERS = {
        **NSE_HEADERS,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1",
    }

    def _make_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update(NSE_HEADERS)
        return s

    # Headers for options API calls — simulates XHR from the option-chain page
    _OC_API_HEADERS = {
        **NSE_HEADERS,
        "Referer": "https://www.nseindia.com/option-chain",
        "X-Requested-With": "XMLHttpRequest",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }

    # Pages to try for warmup. nsit is set by NSE's backend servers (load-balancer
    # dependent — not every request sets it). We try multiple URLs and retry until
    # nsit appears in the session cookies.
    _WARMUP_URLS = [
        f"{NSE_BASE}/market-data/equity-derivatives-watch",
        f"{NSE_BASE}/get-quotes/derivatives?symbol=NIFTY",
        f"{NSE_BASE}/get-quotes/equity?symbol=NIFTY",
        f"{NSE_BASE}/market-data/live-equity-market",
        f"{NSE_BASE}/option-chain",
    ]

    def _warmup(self, session: requests.Session) -> bool:
        """Attempt to warm up session and obtain nsit cookie. Returns True if nsit set."""
        for url in self._WARMUP_URLS:
            try:
                r = session.get(url, headers=self._PAGE_HEADERS, timeout=10)
                cookies = list(session.cookies.keys())
                logger.info("NSE warmup [%s] → %d  cookies=%s",
                            url.split("/")[-1] or "home", r.status_code, cookies)
                if r.status_code == 200:
                    if "nsit" in session.cookies:
                        logger.info("Got nsit cookie on first warmup attempt")
                        return True
                    time.sleep(0.5)
            except Exception as e:
                logger.warning("NSE warmup failed [%s]: %s", url, e)
        return "nsit" in session.cookies

    def _ensure_session(self) -> requests.Session:
        # Must be called while holding self._lock
        if self._session is None:
            # NSE's nsit cookie is load-balancer dependent — retry with fresh sessions
            # until we get it (max 3 attempts, each ≤ 3 pages × 10s = ~30s worst case)
            for attempt in range(3):
                session = self._make_session()
                has_nsit = self._warmup(session)
                if has_nsit:
                    self._session = session
                    break
                logger.info("nsit not obtained (attempt %d/3), retrying with fresh session", attempt + 1)
                time.sleep(1.5)
            else:
                # Proceed with whatever cookies we have — may still work for non-OC calls
                self._session = session
                logger.warning("Could not obtain nsit after 3 warmup attempts")

            self._options_warmed = True
            logger.info("NSE session ready. Final cookies: %s",
                        list(self._session.cookies.keys()))
        return self._session

    def reset(self):
        with self._lock:
            self._session = None
            self._options_warmed = False

    def warmup_for_options(self):
        with self._lock:
            if self._options_warmed:
                return
            self._ensure_session()  # _ensure_session now handles options warmup

    def get(self, endpoint: str) -> Optional[dict]:
        # Full lock — requests.Session is not thread-safe; serialize all calls
        with self._lock:
            session = self._ensure_session()
            try:
                # Use options-chain referer/XHR headers for the OC endpoints
                headers = (
                    self._OC_API_HEADERS
                    if "option-chain" in endpoint
                    else None
                )
                resp = session.get(f"{NSE_API}{endpoint}", headers=headers, timeout=10)
                body_len = len(resp.content)
                logger.info("NSE API %s → %d  len=%d  cookies=%s",
                            endpoint, resp.status_code, body_len,
                            list(session.cookies.keys()))
                if resp.status_code == 200:
                    if body_len < 50:
                        logger.warning("NSE tiny body [%s]: %r", endpoint, resp.text)
                        return None
                    try:
                        return resp.json()
                    except Exception as je:
                        logger.error("NSE JSON parse error [%s]: %s | body[:200]=%r",
                                     endpoint, je, resp.text[:200])
                        return None
                if resp.status_code in (401, 403):
                    self._session = None
                    self._options_warmed = False
                return None
            except Exception as e:
                logger.error("NSE request failed [%s]: %s", endpoint, e)
                return None


class NSEScraper:
    """Async NSE data fetcher — wraps _SyncNSESession in asyncio executor."""

    def __init__(self):
        self._nse = _SyncNSESession()

    async def _get(self, endpoint: str) -> Optional[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._nse.get, endpoint)

    # ─── Options Chain ─────────────────────────────────────────────────────────

    async def get_options_chain(self, symbol: str = "NIFTY") -> Optional[dict]:
        """
        Fetch full options chain. Retries once with a fresh session on failure.
        symbol: NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, or equity symbol.
        """
        endpoint = (
            f"/option-chain-indices?symbol={symbol}"
            if symbol in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY")
            else f"/option-chain-equities?symbol={symbol}"
        )

        loop = asyncio.get_event_loop()
        for attempt in range(2):
            if attempt > 0:
                logger.info("Retrying options chain for %s (resetting session)", symbol)
                await loop.run_in_executor(None, self._nse.reset)
                await asyncio.sleep(2.0)

            await loop.run_in_executor(None, self._nse.warmup_for_options)
            data = await self._get(endpoint)
            if data and data.get("records"):
                return self._parse_options_chain(data, symbol)

        logger.warning("Options chain unavailable for %s after 2 attempts", symbol)
        return None

    def _parse_options_chain(self, raw: dict, symbol: str) -> dict:
        records = raw.get("records", {})
        rows_raw = records.get("data", [])
        expiry_dates = records.get("expiryDates", [])
        underlying_value = records.get("underlyingValue", 0)

        parsed_rows = []
        for row in rows_raw:
            ce = row.get("CE", {})
            pe = row.get("PE", {})
            parsed_rows.append({
                "expiry": row.get("expiryDate", ""),
                "strike": row.get("strikePrice", 0),
                "CE": {
                    "ltp":       ce.get("lastPrice", 0),
                    "oi":        ce.get("openInterest", 0),
                    "oi_change": ce.get("changeinOpenInterest", 0),
                    "volume":    ce.get("totalTradedVolume", 0),
                    "iv":        ce.get("impliedVolatility", 0),
                    "delta":     ce.get("delta", 0),
                },
                "PE": {
                    "ltp":       pe.get("lastPrice", 0),
                    "oi":        pe.get("openInterest", 0),
                    "oi_change": pe.get("changeinOpenInterest", 0),
                    "volume":    pe.get("totalTradedVolume", 0),
                    "iv":        pe.get("impliedVolatility", 0),
                    "delta":     pe.get("delta", 0),
                },
            })

        total_ce_oi = sum(r["CE"]["oi"] for r in parsed_rows)
        total_pe_oi = sum(r["PE"]["oi"] for r in parsed_rows)
        pcr = round(total_pe_oi / total_ce_oi, 3) if total_ce_oi else 0

        return {
            "symbol": symbol,
            "underlying": underlying_value,
            "expiry_dates": expiry_dates,
            "pcr": pcr,
            "max_pain": self._calc_max_pain(parsed_rows, underlying_value),
            "total_ce_oi": total_ce_oi,
            "total_pe_oi": total_pe_oi,
            "data": parsed_rows,
            "timestamp": datetime.now(IST).isoformat(),
        }

    def _calc_max_pain(self, rows: list, spot: float) -> float:
        strikes = sorted(set(r["strike"] for r in rows))
        if not strikes:
            return spot
        row_map = {r["strike"]: r for r in rows}
        pain = {}
        for test_strike in strikes:
            total_loss = 0
            for strike, row in row_map.items():
                if test_strike < strike:
                    total_loss += row["CE"]["oi"] * (strike - test_strike)
                if test_strike > strike:
                    total_loss += row["PE"]["oi"] * (test_strike - strike)
            pain[test_strike] = total_loss
        return min(pain, key=pain.get)

    # ─── Market Breadth ────────────────────────────────────────────────────────

    async def get_market_breadth(self) -> Optional[dict]:
        data = await self._get("/market-data-pre-open?key=ALL")
        if not data:
            return None
        pre_open = data.get("data", [])
        advances = sum(1 for s in pre_open if _to_float(s.get("metadata", {}).get("change", 0)) > 0)
        declines  = sum(1 for s in pre_open if _to_float(s.get("metadata", {}).get("change", 0)) < 0)
        unchanged = len(pre_open) - advances - declines
        return {
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged,
            "total": len(pre_open),
            "ad_ratio": round(advances / declines, 2) if declines else 0,
            "timestamp": datetime.now(IST).isoformat(),
        }

    async def get_nifty50_stocks(self) -> List[dict]:
        data = await self._get("/equity-stockIndices?index=NIFTY%2050")
        if not data:
            return []
        return [
            {
                "symbol": s.get("symbol"),
                "ltp": s.get("lastPrice", 0),
                "change": s.get("change", 0),
                "change_pct": s.get("pChange", 0),
                "volume": s.get("totalTradedVolume", 0),
            }
            for s in data.get("data", [])
        ]

    async def get_indices(self) -> List[dict]:
        data = await self._get("/allIndices")
        if not data:
            return []
        return [
            {
                "name": idx.get("indexSymbol"),
                "ltp": _to_float(idx.get("last", 0)),
                "change": _to_float(idx.get("variation", 0)),
                "change_pct": _to_float(idx.get("percentChange", 0)),
                "open": _to_float(idx.get("open", 0)),
                "high": _to_float(idx.get("high", 0)),
                "low": _to_float(idx.get("low", 0)),
                "prev_close": _to_float(idx.get("previousClose", 0)),
                "advance": _to_int(idx.get("advances", 0)),
                "decline": _to_int(idx.get("declines", 0)),
            }
            for idx in data.get("data", [])
            if idx.get("indexSymbol")
        ]

    # ─── FII / DII Data ────────────────────────────────────────────────────────

    async def get_fii_dii(self) -> Optional[dict]:
        data = await self._get("/fiidiiTradeReact")
        if not data:
            return None
        rows = data if isinstance(data, list) else data.get("data", [])
        result: dict = {"timestamp": datetime.now(IST).isoformat()}
        for row in rows:
            cat = row.get("category", "")
            if "FII" in cat or "FPI" in cat:
                result["fii_buy"]  = _to_float(row.get("buyValue",  0))
                result["fii_sell"] = _to_float(row.get("sellValue", 0))
                result["fii_net"]  = _to_float(row.get("netValue",  0))
            elif "DII" in cat:
                result["dii_buy"]  = _to_float(row.get("buyValue",  0))
                result["dii_sell"] = _to_float(row.get("sellValue", 0))
                result["dii_net"]  = _to_float(row.get("netValue",  0))
        return result

    # ─── Corporate Events ──────────────────────────────────────────────────────

    async def get_corporate_actions(self, symbol: str = "") -> List[dict]:
        endpoint = f"/corporateActions?index=equities&symbol={symbol}&from_date=&to_date=&csv=false"
        data = await self._get(endpoint)
        if not data:
            return []
        return data if isinstance(data, list) else []

    async def get_earnings_calendar(self) -> List[dict]:
        data = await self._get("/corporate-announcements?index=equities&type=Result")
        if not data:
            return []
        if isinstance(data, list):
            return [d for d in data[:50] if isinstance(d, dict)]
        return [d for d in (data.get("data") or [])[:50] if isinstance(d, dict)]

    async def close(self):
        pass  # requests.Session has no async close
