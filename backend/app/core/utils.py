import pytz

IST = pytz.timezone("Asia/Kolkata")

EXCHANGE_NUM_TO_STR: dict[int, str] = {
    1: "NSE",
    2: "NFO",
    3: "BSE",
    5: "MCX",
    7: "BFO",
    13: "CDS",
}

EXCHANGE_STR_TO_NUM: dict[str, int] = {v: k for k, v in EXCHANGE_NUM_TO_STR.items()}

SEGMENT_BY_EXCHANGE: dict[str, str] = {
    "NSE": "EQ",
    "BSE": "EQ",
    "NFO": "FNO",
    "MCX": "COM",
    "CDS": "CUR",
    "BFO": "FNO",
}

LOT_SIZES: dict[str, int] = {
    "NIFTY": 25, "BANKNIFTY": 15, "FINNIFTY": 40, "MIDCPNIFTY": 75, "SENSEX": 20,
}

STRIKE_GAPS: dict[str, int] = {
    "NIFTY": 50, "BANKNIFTY": 100, "FINNIFTY": 50, "MIDCPNIFTY": 25, "SENSEX": 100,
}

# Canonical timeframe → seconds mapping used across market.py and signal generation
TIMEFRAME_SECONDS: dict[str, int] = {
    "1m":  60,    "3m":  180,  "5m":  300,  "10m": 600,
    "15m": 900,   "30m": 1800, "1h":  3600, "2h":  7200,
    "4h":  14400, "1d":  86400, "1w": 604800,
}
