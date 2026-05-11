from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List
import json


class Settings(BaseSettings):
    # App
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    # DEV_MODE=true → SQLite + in-memory cache (no Docker/PostgreSQL/Redis needed)
    DEV_MODE: bool = True

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://algotrade:algotrade_secret@localhost:5432/algotrade"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_TICKS: str = "market.ticks"
    KAFKA_TOPIC_SIGNALS: str = "market.signals"
    KAFKA_TOPIC_ORDERS: str = "trading.orders"

    # Security
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # CORS
    CORS_ORIGINS: str = '["http://localhost:5173","http://localhost:80"]'

    @property
    def cors_origins_list(self) -> List[str]:
        return json.loads(self.CORS_ORIGINS)

    # Angel One SmartAPI
    ANGEL_API_KEY: str = ""
    ANGEL_CLIENT_ID: str = ""
    ANGEL_PASSWORD: str = ""
    ANGEL_TOTP_SECRET: str = ""

    # Zerodha Kite
    ZERODHA_API_KEY: str = ""
    ZERODHA_API_SECRET: str = ""
    ZERODHA_ACCESS_TOKEN: str = ""

    # Upstox
    UPSTOX_API_KEY: str = ""
    UPSTOX_ACCESS_TOKEN: str = ""

    # Fyers
    FYERS_APP_ID: str = ""
    FYERS_ACCESS_TOKEN: str = ""

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # Email
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    # Paper Trading
    PAPER_TRADE_MODE: bool = True
    PAPER_TRADE_CAPITAL: float = 1_000_000.0

    # Risk Controls
    MAX_DAILY_LOSS_PCT: float = 2.0
    MAX_POSITION_SIZE_PCT: float = 5.0
    MAX_OPEN_POSITIONS: int = 5
    MAX_ORDER_VALUE_INR: float = 50_000.0

    # Market Hours (IST)
    MARKET_OPEN: str = "09:15"
    MARKET_CLOSE: str = "15:30"
    PRE_MARKET_OPEN: str = "09:00"
    FNO_CLOSE: str = "15:30"
    COMMODITY_CLOSE: str = "23:30"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
