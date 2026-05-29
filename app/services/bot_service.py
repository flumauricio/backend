"""
BotService — business logic for bot CRUD.

Limit enforcement
─────────────────
UserLimits / Plan models may or may not be present (they were added in a
separate session).  To avoid a hard import dependency that would break
projects that haven't applied those migrations yet, the limit check is done
via a raw SQL query that gracefully falls back when the tables don't exist.

Resolution order (mirrors UserLimitsService.get_effective):
  1. user_limits.max_bots  (per-user override)
  2. plans.max_bots        (plan default)
  3. _FALLBACK_MAX_BOTS    (hardcoded free-tier default)

Admins bypass all limits.
"""
import uuid
from typing import Literal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.core.logging import get_logger
from app.models.bot import Bot
from app.schemas.bot import BotCreate, BotListResponse, BotUpdate

logger = get_logger(__name__)

# Hardcoded fallback — matches the Free plan defined in seed.py
_FALLBACK_MAX_BOTS: int = 1


class BotService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── Limit helpers ────────────────────────────────────────────────────────

    async def _get_max_bots_for_user(self, user_id: uuid.UUID) -> int:
        """
        Resolve the effective max_bots for a user without importing
        UserLimitsService directly (avoids circular imports and hard coupling).

        Falls back to _FALLBACK_MAX_BOTS if user_limits / plans tables don't
        exist yet (e.g. migration not yet applied).
        """
        try:
            row = await self.db.execute(
                text("""
                    SELECT
                        COALESCE(ul.max_bots, p.max_bots, :fallback) AS effective_max_bots
                    FROM (SELECT :user_id::uuid AS uid) base
                    LEFT JOIN user_limits ul ON ul.user_id = base.uid
                    LEFT JOIN plans p        ON p.id = ul.plan_id
                    LIMIT 1
                """),
                {"user_id": str(user_id), "fallback": _FALLBACK_MAX_BOTS},
            )
            val = row.scalar_one_or_none()
            return int(val) if val is not None else _FALLBACK_MAX_BOTS
        except Exception:
            # Tables may not exist in all environments — degrade gracefully.
            logger.warning(
                "Could not resolve max_bots from user_limits/plans, "
                "using fallback",
                user_id=str(user_id),
                fallback=_FALLBACK_MAX_BOTS,
            )
            return _FALLBACK_MAX_BOTS

    async def _count_user_bots(self, user_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(Bot).where(Bot.owner_id == user_id)
        )
        return result.scalar_one()

    # ─── CRUD ─────────────────────────────────────────────────────────────────

    async def create(self, owner_id: uuid.UUID, payload: BotCreate, *, is_admin: bool = False) -> Bot:
        """
        Create a new bot for owner_id.

        Raises BadRequestException if the user has reached their max_bots
        limit (admins are exempt).
        """
        if not is_admin:
            max_bots = await self._get_max_bots_for_user(owner_id)
            current_count = await self._count_user_bots(owner_id)
            if current_count >= max_bots:
                raise BadRequestException(
                    f"Bot limit reached ({current_count}/{max_bots}). "
                    "Upgrade your plan to create more bots."
                )

        bot = Bot(
            owner_id=owner_id,
            name=payload.name,
            description=payload.description,
            status="draft",
        )
        self.db.add(bot)
        await self.db.flush()
        await self.db.refresh(bot)
        logger.info(
            "Bot created",
            bot_id=str(bot.id),
            owner_id=str(owner_id),
            name=bot.name,
        )
        return bot

    async def get_by_id(self, bot_id: uuid.UUID) -> Bot:
        """Return bot by ID or raise 404."""
        result = await self.db.execute(select(Bot).where(Bot.id == bot_id))
        bot = result.scalar_one_or_none()
        if bot is None:
            raise NotFoundException("Bot")
        return bot

    async def get_by_id_for_user(self, bot_id: uuid.UUID, owner_id: uuid.UUID) -> Bot:
        """
        Return bot only if it belongs to owner_id.
        Raises 404 (not 403) to avoid leaking existence of other users' bots.
        """
        result = await self.db.execute(
            select(Bot).where(Bot.id == bot_id, Bot.owner_id == owner_id)
        )
        bot = result.scalar_one_or_none()
        if bot is None:
            raise NotFoundException("Bot")
        return bot

    async def list_user_bots(
        self,
        owner_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Bot], int]:
        """Paginated list of bots belonging to owner_id."""
        stmt = (
            select(Bot)
            .where(Bot.owner_id == owner_id)
            .order_by(Bot.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        count_stmt = (
            select(func.count())
            .select_from(Bot)
            .where(Bot.owner_id == owner_id)
        )
        items_result = await self.db.execute(stmt)
        count_result = await self.db.execute(count_stmt)
        return list(items_result.scalars().all()), count_result.scalar_one()

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 50,
        *,
        owner_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> tuple[list[Bot], int]:
        """
        Paginated list of all bots (admin use).
        Optional filters: owner_id, status.
        """
        base = select(Bot)
        count_base = select(func.count()).select_from(Bot)

        if owner_id is not None:
            base = base.where(Bot.owner_id == owner_id)
            count_base = count_base.where(Bot.owner_id == owner_id)
        if status is not None:
            base = base.where(Bot.status == status)
            count_base = count_base.where(Bot.status == status)

        stmt = base.order_by(Bot.created_at.desc()).offset(skip).limit(limit)

        items_result = await self.db.execute(stmt)
        count_result = await self.db.execute(count_base)
        return list(items_result.scalars().all()), count_result.scalar_one()

    async def update(self, bot: Bot, payload: BotUpdate) -> Bot:
        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(bot, field, value)
        await self.db.flush()
        await self.db.refresh(bot)
        logger.info(
            "Bot updated",
            bot_id=str(bot.id),
            fields=list(update_data.keys()),
        )
        return bot

    async def delete(self, bot: Bot) -> None:
        await self.db.delete(bot)
        await self.db.flush()
        logger.info("Bot deleted", bot_id=str(bot.id), owner_id=str(bot.owner_id))
