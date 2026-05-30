"""
AdminStatsService
─────────────────
Aggregates platform-wide counts for the admin dashboard.

All queries are fire-and-forget COUNT()s — no full table scans of rows,
just index-only counts.  Plans and Bots tables are queried defensively:
if a migration hasn't been applied yet, the count falls back to 0 so the
API never returns 500 just because a table is missing.
"""
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.user import User
from app.schemas.admin import AdminStatsResponse

logger = get_logger(__name__)


class AdminStatsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── Internal helpers ─────────────────────────────────────────────────────

    async def _count(self, stmt) -> int:
        """Execute a scalar COUNT statement, returning 0 on any error."""
        try:
            result = await self.db.execute(stmt)
            return result.scalar_one() or 0
        except Exception as exc:
            logger.warning("AdminStatsService._count failed", error=str(exc))
            return 0

    async def _count_sql(self, sql: str, params: dict | None = None) -> int:
        """Execute a raw-SQL scalar COUNT, returning 0 if the table doesn't exist."""
        try:
            result = await self.db.execute(text(sql), params or {})
            return result.scalar_one() or 0
        except Exception as exc:
            logger.warning("AdminStatsService._count_sql failed", sql=sql, error=str(exc))
            return 0

    # ─── User counts (ORM — table is always present) ──────────────────────────

    async def _users_total(self) -> int:
        return await self._count(
            select(func.count()).select_from(User)
        )

    async def _users_active(self) -> int:
        return await self._count(
            select(func.count()).select_from(User).where(User.is_active.is_(True))
        )

    # ─── Plan counts (raw SQL — table added in migration a3f8c2d1e094) ────────

    async def _plans_total(self) -> int:
        return await self._count_sql("SELECT COUNT(*) FROM plans")

    async def _plans_active(self) -> int:
        return await self._count_sql(
            "SELECT COUNT(*) FROM plans WHERE is_active = TRUE"
        )

    # ─── Bot counts (raw SQL — table added in migration b7e4d2f1a039) ─────────

    async def _bots_total(self) -> int:
        return await self._count_sql("SELECT COUNT(*) FROM bots")

    async def _bots_by_status(self, status: str) -> int:
        return await self._count_sql(
            "SELECT COUNT(*) FROM bots WHERE status = :status",
            {"status": status},
        )

    # ─── Public entrypoint ────────────────────────────────────────────────────

    async def get_stats(self) -> AdminStatsResponse:
        """
        Run all count queries and return the aggregated stats.
        Each query is independent — a failure in one returns 0 for that
        field instead of aborting the whole response.
        """
        (
            users_total,
            users_active,
            plans_total,
            plans_active,
            bots_total,
            bots_running,
            bots_stopped,
            bots_error,
        ) = (
            await self._users_total(),
            await self._users_active(),
            await self._plans_total(),
            await self._plans_active(),
            await self._bots_total(),
            await self._bots_by_status("running"),
            await self._bots_by_status("stopped"),
            await self._bots_by_status("error"),
        )

        logger.info(
            "Admin stats collected",
            users_total=users_total,
            bots_total=bots_total,
            bots_running=bots_running,
        )

        return AdminStatsResponse(
            users_total=users_total,
            users_active=users_active,
            plans_total=plans_total,
            plans_active=plans_active,
            bots_total=bots_total,
            bots_running=bots_running,
            bots_stopped=bots_stopped,
            bots_error=bots_error,
        )
