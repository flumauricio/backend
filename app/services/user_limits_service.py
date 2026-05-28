import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.user_limits import UserLimits
from app.schemas.user_limits import EffectiveUserLimitsRead, UserLimitsUpdate

logger = get_logger(__name__)

# ─── Hardcoded fallback defaults (Free / no plan) ─────────────────────────────
# Override these once you add a "Free" plan to the DB.
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

    # ─── Effective limits (resolved) ──────────────────────────────────────────

    async def get_effective(self, user_id: uuid.UUID) -> EffectiveUserLimitsRead:
        """
        Resolves the effective limits for a user:
            1. Per-user override (non-null column on UserLimits)
            2. Plan value (if plan is assigned)
            3. Hardcoded free-tier default

        Returns an EffectiveUserLimitsRead with a `sources` dict for transparency.
        """
        row = await self.get_row_by_user(user_id)

        resolved: dict[str, int] = {}
        sources: dict[str, str] = {}

        for field in _LIMIT_FIELDS:
            override = getattr(row, field, None) if row else None
            plan_val = getattr(row.plan, field, None) if (row and row.plan) else None
            default_val = _FREE_DEFAULTS[field]

            if override is not None:
                resolved[field] = override
                sources[field] = "override"
            elif plan_val is not None:
                resolved[field] = plan_val
                sources[field] = "plan"
            else:
                resolved[field] = default_val
                sources[field] = "default"

        return EffectiveUserLimitsRead(
            user_id=user_id,
            plan_id=row.plan_id if row else None,
            plan_name=row.plan.name if (row and row.plan) else None,
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
