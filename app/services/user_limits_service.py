import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.plan import Plan
from app.models.user_limits import UserLimits
from app.schemas.user_limits import EffectiveUserLimitsRead, UserLimitsUpdate
from app.services.plan_service import DEFAULT_PLAN_NAME

logger = get_logger(__name__)

# ─── Emergency fallback defaults ─────────────────────────────────────────────
# Used only if the Free plan is unexpectedly absent.
_FREE_DEFAULTS: dict[str, int] = {
    "cloud_storage_mb": 512,
    "max_bots": 1,
    "max_ram_per_bot_mb": 256,
    "max_storage_per_bot_mb": 256,
}

# Limit field names — single source of truth to avoid typos
_LIMIT_FIELDS: tuple[str, ...] = (
    "cloud_storage_mb",
    "max_bots",
    "max_ram_per_bot_mb",
    "max_storage_per_bot_mb",
)


class UserLimitsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── Finders ──────────────────────────────────────────────────────────────

    async def get_row_by_user(self, user_id: uuid.UUID) -> UserLimits | None:
        """
        Returns the raw UserLimits row (with plan eagerly loaded), or None
        if no row exists yet for this user.
        """
        stmt = (
            select(UserLimits)
            .where(UserLimits.user_id == user_id)
            .options(selectinload(UserLimits.plan))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_default_free_plan(self) -> Plan | None:
        result = await self.db.execute(
            select(Plan).where(Plan.name == DEFAULT_PLAN_NAME)
        )
        return result.scalar_one_or_none()

    # ─── Effective limits (resolved) ──────────────────────────────────────────

    async def get_effective(self, user_id: uuid.UUID) -> EffectiveUserLimitsRead:
        """
        Resolves the effective limits for a user:
            1. Per-user override (non-null column on UserLimits)
            2. Assigned plan value
            3. System Free plan value
            4. Emergency hardcoded fallback

        Returns an EffectiveUserLimitsRead with a `sources` dict for transparency.
        """
        row = await self.get_row_by_user(user_id)
        free_plan = await self._get_default_free_plan()

        resolved: dict[str, int] = {}
        sources: dict[str, str] = {}

        for field in _LIMIT_FIELDS:
            override = getattr(row, field, None) if row else None
            plan_val = getattr(row.plan, field, None) if (row and row.plan) else None
            free_val = getattr(free_plan, field, None) if free_plan else None
            default_val = _FREE_DEFAULTS[field]

            if override is not None:
                resolved[field] = override
                sources[field] = "override"
            elif plan_val is not None:
                resolved[field] = plan_val
                sources[field] = "plan"
            elif free_val is not None:
                resolved[field] = free_val
                sources[field] = "free_default"
            else:
                resolved[field] = default_val
                sources[field] = "fallback"

        effective_plan = row.plan if (row and row.plan) else free_plan

        return EffectiveUserLimitsRead(
            user_id=user_id,
            plan_id=effective_plan.id if effective_plan else None,
            plan_name=effective_plan.name if effective_plan else None,
            sources=sources,
            **resolved,
        )

    # ─── Upsert ───────────────────────────────────────────────────────────────

    async def upsert(
        self, user_id: uuid.UUID, payload: UserLimitsUpdate
    ) -> UserLimits:
        """
        Creates or updates the UserLimits row for a user.
        Only fields explicitly included in the payload are changed.
        """
        row = await self.get_row_by_user(user_id)

        if row is None:
            row = UserLimits(user_id=user_id)
            self.db.add(row)

        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(row, field, value)

        await self.db.flush()
        # Reload with plan relationship
        await self.db.refresh(row)
        stmt = (
            select(UserLimits)
            .where(UserLimits.id == row.id)
            .options(selectinload(UserLimits.plan))
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one()

        logger.info(
            "UserLimits upserted",
            user_id=str(user_id),
            fields=list(update_data.keys()),
        )
        return row
