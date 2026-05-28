from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.database.redis import get_redis
from app.database.session import get_db

router = APIRouter(tags=["Health"])
logger = get_logger(__name__)


@router.get("/health", summary="Healthcheck", include_in_schema=False)
async def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/detailed", summary="Detailed healthcheck [checks DB + Redis]")
async def health_detailed(
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    checks: dict[str, str] = {}

    # PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        logger.error("Postgres health check failed", error=str(exc))
        checks["postgres"] = "error"

    # Redis
    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        logger.error("Redis health check failed", error=str(exc))
        checks["redis"] = "error"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"

    return {
        "status": overall,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
