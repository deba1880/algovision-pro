"""
Database and cache layer.
Dev mode (DEV_MODE=true): SQLite + in-memory dict cache — no external services needed.
Prod mode:                 PostgreSQL/TimescaleDB + Redis.
"""

import json
import time
from typing import Any
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


# ─── SQLAlchemy Engine ────────────────────────────────────────────────────────

def _make_engine():
    if settings.DEV_MODE:
        # SQLite — zero-config, file-based, great for dev
        db_url = "sqlite+aiosqlite:///./algotrade_dev.db"
        return create_async_engine(db_url, echo=False, connect_args={"check_same_thread": False})
    else:
        return create_async_engine(
            settings.DATABASE_URL,
            pool_size=20,
            max_overflow=10,
            pool_pre_ping=True,
            echo=False,
        )


engine = _make_engine()

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


# ─── In-Memory Cache (dev) / Redis (prod) ─────────────────────────────────────

class _MemoryCache:
    """Simple TTL-aware in-memory cache that mirrors the Redis interface we use."""

    def __init__(self):
        self._store: dict[str, tuple[str, float]] = {}  # key → (value, expires_at)

    async def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at and time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: str) -> None:
        self._store[key] = (value, 0.0)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> None:
        self._store[key] = (value, time.monotonic() + ttl_seconds)

    async def publish(self, channel: str, message: str) -> None:
        pass  # no-op in dev mode; WebSocket pushes happen via tick_pipeline directly

    async def delete(self, *keys) -> None:
        for k in keys:
            self._store.pop(k, None)

    def __repr__(self):
        return f"<MemoryCache keys={len(self._store)}>"


_mem_cache = _MemoryCache()
_redis_client = None


async def get_redis():
    """Return Redis client (prod) or in-memory cache (dev)."""
    global _redis_client
    if settings.DEV_MODE:
        return _mem_cache

    if _redis_client is None:
        import redis.asyncio as aioredis
        _redis_client = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
    return _redis_client


# ─── Session Dependency ────────────────────────────────────────────────────────

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ─── DB Initialization ────────────────────────────────────────────────────────

async def init_db():
    """Create all tables. In dev mode uses SQLite, in prod uses PostgreSQL."""
    from app.models.market import Base as MarketBase  # noqa: import triggers model registration
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
