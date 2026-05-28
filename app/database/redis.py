from collections.abc import AsyncGenerator

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Module-level pool — created once, reused across requests
_redis_pool: aioredis.Redis | None = None


async def get_redis_pool() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
        logger.info("Redis pool created", url=settings.REDIS_URL)
    return _redis_pool


async def close_redis_pool() -> None:
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None
        logger.info("Redis pool closed")


# ─── FastAPI Dependency ───────────────────────────────────────────────────────

async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    pool = await get_redis_pool()
    yield pool
