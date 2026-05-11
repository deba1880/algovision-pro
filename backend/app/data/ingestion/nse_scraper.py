"""
NSE India data scraper.
Fetches: options chain, FII/DII, indices, market breadth, corporate actions,
         F&O bhavcopy, delivery data.

Uses nsepython library + direct NSE API calls (public endpoints, no auth needed).
NSE rate-limits aggressively — all requests go through a throttled session with
proper headers mimicking a browser request.
"""

import asyncio
import logging
import time
from datetime import datetime, date
from typing import Dict, List, Optional
import httpx
try:
    from nsepython import nse_optionchain_scrapper, nse_eq, nse_fno, nse_index, fnolist
except ImportError:
    nse_optionchain_scrapper = nse_eq = nse_fno = nse_index = fnolist = None

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

# Proper headers required — NSE blocks requests without these
NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}

_last_request_time: float = 0
_MIN_REQUEST_INTERVAL = 0.5  # 500ms between NSE requests


class NSEScraper:
    """Async NSE data fetcher with session management and rate limiting."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._cookies: dict = {}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=NSE_HEADERS,
                timeout=15.0,
                follow_redirects=True,
                http2=False,
            )
            # Warm up session — NSE requires a homepage hit first to set cookies
            try:
                r = await self._client.get(NSE_BASE)
                self._cookies = dict(r.cookies)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning("NSE session warmup failed: %s", e)
        return self._client

    async def _get(self, endpoint: str) -> Optional[dict]:
        """Rate-limited GET against NSE API."""
        global _last_request_time
        elapsed = time.monotonic() - _last_request_time
        if elapsed < _MIN_REQUEST_INTERVAL:
            await asyncio.sleep(_MIN_REQUEST_INTERVAL - elapsed)

        client = await self._get_client()
        try:
            resp = await client.get(
                f"{NSE_API}{endpoint}",
                cookies=self._cookies,
                headers={**NSE_HEADERS, "Accept-Encoding": "gzip, deflate"},
            )
            _last_request_time = time.monotonic()
            if resp.status_code == 200:
                try:
                    return resp.json()
                except Exception:
                    # Try decoding as text if JSON parse fails
                    import json
                    return json.loads(resp.text)
            elif resp.status_code in (401, 403):
                # Session expired — force re-init on next call
                await self._client.aclose()
                self._client = None
                self._cookies = {}
            logger.warning("NSE API returned %s for %s", resp.status_code, endpoint)
            return None
        except Exception as e:
            logger.error("NSE request failed [%s]: %s", endpoint, e)
            return None

    # ─── Options Chain ─────────────────────────────────────────────────────────

    async def get_options_chain(self, symbol: str = "NIFTY") -> Optional[dict]:
        """
        Fetch full options chain for index or stock.
        symbol: NIFTY, BANKNIFTY, FINNIFTY, or stock symbol
        """
        endpoint = f"/option-chain-indices?symbol={symbol}" \
                   if symbol in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY") \
                   else f"/option-chain-equities?symbol={symbol}"
        data = await self._get(endpoint)
        if not data:
            return None
        return self._parse_options_chain(data, symbol)

    def _parse_options_chain(self, raw: dict, symbol: str) -> dict:
        """Normalize NSE options chain response."""
        records = raw.get("records", {})
        data = records.get("data", [])
        expiry_dates = records.get("expiryDates", [])
        underlying_value = records.get("underlyingValue", 0)

        parsed_rows = []
        for row in data:
            expiry = row.get("expiryDate", "")
            strike = row.get("strikePrice", 0)
            ce = row.get("CE", {})
            pe = row.get("PE", {})
            parsed_rows.append({
                "expiry": expiry,
                "strike": strike,
                "CE": {
                    "ltp": ce.get("lastPrice", 0),
                    "oi": ce.get("openInterest", 0),
                    "oi_change": ce.get("changeinOpenInterest", 0),
                    "volume": ce.get("totalTradedVolume", 0),
                    "iv": ce.get("impliedVolatility", 0),
                    "bid": ce.get("bidprice", 0),
                    "ask": ce.get("askPrice", 0),
                    "delta": ce.get("delta", 0),
                    "theta": ce.get("theta", 0),
                    "gamma": ce.get("gamma", 0),
                    "vega": ce.get("vega", 0),
                },
                "PE": {
                    "ltp": pe.get("lastPrice", 0),
                    "oi": pe.get("openInterest", 0),
                    "oi_change": pe.get("changeinOpenInterest", 0),
                    "volume": pe.get("totalTradedVolume", 0),
                    "iv": pe.get("impliedVolatility", 0),
                    "bid": pe.get("bidprice", 0),
                    "ask": pe.get("askPrice", 0),
                    "delta": pe.get("delta", 0),
                    "theta": pe.get("theta", 0),
                    "gamma": pe.get("gamma", 0),
                    "vega": pe.get("vega", 0),
                },
            })

        # Calculate PCR and Max Pain
        total_ce_oi = sum(r["CE"]["oi"] for r in parsed_rows)
        total_pe_oi = sum(r["PE"]["oi"] for r in parsed_rows)
        pcr = round(total_pe_oi / total_ce_oi, 3) if total_ce_oi else 0
        max_pain = self._calc_max_pain(parsed_rows, underlying_value)

        return {
            "symbol": symbol,
            "underlying": underlying_value,
            "expiry_dates": expiry_dates,
            "pcr": pcr,
            "max_pain": max_pain,
            "total_ce_oi": total_ce_oi,
            "total_pe_oi": total_pe_oi,
            "data": parsed_rows,
            "timestamp": datetime.now(IST).isoformat(),
        }

    def _calc_max_pain(self, rows: list, spot: float) -> float:
        """
        Max Pain = strike where total option buyer loss is maximum
        (i.e., where the option seller/writer profits most).
        """
        strikes = sorted(set(r["strike"] for r in rows))
        if not strikes:
            return spot

        pain = {}
        row_map = {r["strike"]: r for r in rows}
        for test_strike in strikes:
            total_loss = 0
            for strike, row in row_map.items():
                # CE writer profit when spot < strike (CE expires worthless)
                if test_strike < strike:
                    total_loss += row["CE"]["oi"] * (strike - test_strike)
                # PE writer profit when spot > strike (PE expires worthless)
                if test_strike > strike:
                    total_loss += row["PE"]["oi"] * (test_strike - strike)
            pain[test_strike] = total_loss

        return min(pain, key=pain.get)

    # ─── Market Breadth ────────────────────────────────────────────────────────

    async def get_market_breadth(self) -> Optional[dict]:
        """Advance/Decline for NSE."""
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
        """All Nifty 50 stocks with current quote."""
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
        """All NSE indices."""
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
        """FII/DII net buy/sell for today."""
        data = await self._get("/fiidiiTradeReact")
        if not data:
            return None
        rows = data if isinstance(data, list) else data.get("data", [])
        result = {"timestamp": datetime.now(IST).isoformat()}
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
        """Dividends, splits, bonuses, rights."""
        endpoint = f"/corporateActions?index=equities&symbol={symbol}&from_date=&to_date=&csv=false"
        data = await self._get(endpoint)
        if not data:
            return []
        return data if isinstance(data, list) else []

    async def get_earnings_calendar(self) -> List[dict]:
        """Upcoming results announcements."""
        data = await self._get("/corporate-announcements?index=equities&type=Result")
        if not data:
            return []
        if isinstance(data, list):
            return [d for d in data[:50] if isinstance(d, dict)]
        return [d for d in (data.get("data") or [])[:50] if isinstance(d, dict)]

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
