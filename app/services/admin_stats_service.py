"""
AdminStatsService
─────────────────
Aggregates platform-wide counts for the admin dashboard.

All queries are fire-and-forget COUNT()s — no full table scans of rows,
just index-only counts.  Plans and Bots tables are queried defensively:
if a migration hasn't been applied yet, the count falls back to 0 so the
API never returns 500 just because a table is missing.

Capacity estimates are derived from the sum of effective limits across all
users — they represent total *allocated* capacity, not actual disk/RAM usage.
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

    async def _scalar_sql(self, sql: str, params: dict | None = None) -> int:
        """Execute a raw-SQL scalar query (e.g. SUM), returning 0 on error or NULL."""
        try:
            result = await self.db.execute(text(sql), params or {})
            val = result.scalar_one()
            return int(val) if val is not None else 0
        except Exception as exc:
            logger.warning("AdminStatsService._scalar_sql failed", sql=sql, error=str(exc))
            return 0

    # ─── User counts (ORM — table is always present) ──────────────────────────

    async def _users_total(self) -> int:
        return await self._count(select(func.count()).select_from(User))

    async def _users_active(self) -> int:
        return await self._count(
            select(func.count()).select_from(User).where(User.is_active.is_(True))
        )

    # ─── Plan counts (raw SQL — table added in migration a3f8c2d1e094) ────────

    async def _plans_total(self) -> int:
        return await self._count_sql("SELECT COUNT(*) FROM plans")

    async def _plans_active(self) -> int:
        return await self._count_sql("SELECT COUNT(*) FROM plans WHERE is_active = TRUE")

    # ─── Bot counts (raw SQL — table added in migration b7e4d2f1a039) ─────────

    async def _bots_total(self) -> int:
        return await self._count_sql("SELECT COUNT(*) FROM bots")

    async def _bots_by_status(self, status: str) -> int:
        return await self._count_sql(
            "SELECT COUNT(*) FROM bots WHERE status = :status",
            {"status": status},
        )

    # ─── Capacity estimates ───────────────────────────────────────────────────
    # Strategy: for each user, resolve the effective cloud_storage_mb,
    # max_storage_per_bot_mb, and max_ram_per_bot_mb using the same
    # priority order as the limits service:
    #   1. Per-user override (user_limits row with non-null value)
    #   2. Plan value (if a plan is assigned)
    #   3. Default fallback (same defaults as user_limits_service)
    #
    # The SQL coalesces the three sources and SUMs across all users.
    # If user_limits or plans tables don't exist yet, falls back to 0.

    _DEFAULT_CLOUD_STORAGE_MB    = 5_120   # 5 GB  — matches Free plan default
    _DEFAULT_RAM_PER_BOT_MB      = 512
    _DEFAULT_STORAGE_PER_BOT_MB  = 1_024

    async def _estimated_cloud_storage_mb(self) -> int:
        sql = """
            SELECT COALESCE(SUM(
                COALESCE(
                    ul.cloud_storage_mb,
                    p.cloud_storage_mb,
                    :default_cloud
                )
            ), 0)
            FROM users u
            LEFT JOIN user_limits ul ON ul.user_id = u.id
            LEFT JOIN plans p        ON p.id = ul.plan_id
            WHERE u.is_active = TRUE
        """
        return await self._scalar_sql(sql, {"default_cloud": self._DEFAULT_CLOUD_STORAGE_MB})

    async def _estimated_bot_storage_mb(self) -> int:
        """
        SUM of (max_storage_per_bot_mb × max_bots) across all active users.
        Represents total storage capacity reserved by all running/allocated bots.
        """
        sql = """
            SELECT COALESCE(SUM(
                COALESCE(ul.max_storage_per_bot_mb, p.max_storage_per_bot_mb, :default_storage)
                *
                COALESCE(ul.max_bots, p.max_bots, 1)
            ), 0)
            FROM users u
            LEFT JOIN user_limits ul ON ul.user_id = u.id
            LEFT JOIN plans p        ON p.id = ul.plan_id
            WHERE u.is_active = TRUE
        """
        return await self._scalar_sql(sql, {"default_storage": self._DEFAULT_STORAGE_PER_BOT_MB})

    async def _estimated_ram_reserved_mb(self) -> int:
        """
        SUM of (max_ram_per_bot_mb × bots_running) across all users.
        Only running bots actually consume RAM reservations.
        """
        sql = """
            SELECT COALESCE(SUM(
                COALESCE(ul.max_ram_per_bot_mb, p.max_ram_per_bot_mb, :default_ram)
            ), 0)
            FROM bots b
            LEFT JOIN users u        ON u.id = b.owner_id
            LEFT JOIN user_limits ul ON ul.user_id = u.id
            LEFT JOIN plans p        ON p.id = ul.plan_id
            WHERE b.status = 'running'
        """
        return await self._scalar_sql(sql, {"default_ram": self._DEFAULT_RAM_PER_BOT_MB})

    # ─── Public entrypoint ────────────────────────────────────────────────────

    async def get_stats(self) -> AdminStatsResponse:
        """
        Run all count/aggregate queries and return the aggregated stats.
        Each query is independent — a failure in one returns 0 for that
        field instead of aborting the whole response.
        """
        users_total  = await self._users_total()
        users_active = await self._users_active()

        plans_total  = await self._plans_total()
        plans_active = await self._plans_active()

        bots_total    = await self._bots_total()
        bots_running  = await self._bots_by_status("running")
        bots_stopped  = await self._bots_by_status("stopped")
        bots_error    = await self._bots_by_status("error")
        bots_draft    = await self._bots_by_status("draft")
        bots_starting = await self._bots_by_status("starting")
        bots_stopping = await self._bots_by_status("stopping")

        estimated_cloud_storage_mb = await self._estimated_cloud_storage_mb()
        estimated_bot_storage_mb   = await self._estimated_bot_storage_mb()
        estimated_ram_reserved_mb  = await self._estimated_ram_reserved_mb()

        logger.info(
            "Admin stats collected",
            users_total=users_total,
            bots_total=bots_total,
            bots_running=bots_running,
            estimated_cloud_storage_mb=estimated_cloud_storage_mb,
        )

        return AdminStatsResponse(
            users_total=users_total,
            users_active=users_active,
            users_inactive=users_total - users_active,
            plans_total=plans_total,
            plans_active=plans_active,
            bots_total=bots_total,
            bots_running=bots_running,
            bots_stopped=bots_stopped,
            bots_error=bots_error,
            bots_draft=bots_draft,
            bots_starting=bots_starting,
            bots_stopping=bots_stopping,
            estimated_cloud_storage_mb=estimated_cloud_storage_mb,
            estimated_bot_storage_mb=estimated_bot_storage_mb,
            estimated_ram_reserved_mb=estimated_ram_reserved_mb,
        )
