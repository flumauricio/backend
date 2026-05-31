"""
BotEnvVarService
────────────────
CRUD for per-bot environment variables.

Security rule: is_secret=True values are NEVER returned raw.
The service layer returns masked BotEnvVarRead objects — raw values
only exist in the DB row.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.core.logging import get_logger
from app.models.bot_v3 import BotEnvVar
from app.schemas.bot_v3 import BotEnvVarCreate, BotEnvVarRead, BotEnvVarUpdate

logger = get_logger(__name__)


class BotEnvVarService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── List ─────────────────────────────────────────────────────────────────

    async def list_for_bot(self, bot_id: uuid.UUID) -> list[BotEnvVarRead]:
        stmt = (
            select(BotEnvVar)
            .where(BotEnvVar.bot_id == bot_id)
            .order_by(BotEnvVar.created_at.asc())
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return [BotEnvVarRead.from_orm_masked(r) for r in rows]

    # ─── Create ───────────────────────────────────────────────────────────────

    async def create(
        self,
        bot_id: uuid.UUID,
        payload: BotEnvVarCreate,
    ) -> BotEnvVarRead:
        # Prevent duplicate keys per bot
        existing = await self.db.execute(
            select(BotEnvVar).where(
                BotEnvVar.bot_id == bot_id,
                BotEnvVar.key == payload.key,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictException(
                f"Variável '{payload.key}' já existe para este bot. "
                "Use PATCH para atualizar."
            )
        ev = BotEnvVar(
            bot_id=bot_id,
            key=payload.key,
            value=payload.value,
            is_secret=payload.is_secret,
        )
        self.db.add(ev)
        await self.db.flush()
        await self.db.refresh(ev)
        logger.info("EnvVar created", bot_id=str(bot_id), key=payload.key, secret=payload.is_secret)
        return BotEnvVarRead.from_orm_masked(ev)

    # ─── Update ───────────────────────────────────────────────────────────────

    async def update(
        self,
        env_id: uuid.UUID,
        bot_id: uuid.UUID,
        payload: BotEnvVarUpdate,
    ) -> BotEnvVarRead:
        ev = await self._get_or_404(env_id, bot_id)

        # Check key uniqueness if key is being changed
        if payload.key is not None and payload.key != ev.key:
            conflict = await self.db.execute(
                select(BotEnvVar).where(
                    BotEnvVar.bot_id == bot_id,
                    BotEnvVar.key == payload.key,
                )
            )
            if conflict.scalar_one_or_none() is not None:
                raise ConflictException(
                    f"Variável '{payload.key}' já existe para este bot."
                )

        update_data = payload.model_dump(exclude_unset=True)
        for field, val in update_data.items():
            setattr(ev, field, val)

        await self.db.flush()
        await self.db.refresh(ev)
        logger.info("EnvVar updated", env_id=str(env_id), fields=list(update_data.keys()))
        return BotEnvVarRead.from_orm_masked(ev)

    # ─── Delete ───────────────────────────────────────────────────────────────

    async def delete(self, env_id: uuid.UUID, bot_id: uuid.UUID) -> None:
        ev = await self._get_or_404(env_id, bot_id)
        await self.db.delete(ev)
        await self.db.flush()
        logger.info("EnvVar deleted", env_id=str(env_id), bot_id=str(bot_id))

    # ─── Internal ─────────────────────────────────────────────────────────────

    async def _get_or_404(self, env_id: uuid.UUID, bot_id: uuid.UUID) -> BotEnvVar:
        result = await self.db.execute(
            select(BotEnvVar).where(
                BotEnvVar.id == env_id,
                BotEnvVar.bot_id == bot_id,
            )
        )
        ev = result.scalar_one_or_none()
        if ev is None:
            raise NotFoundException("Variável de ambiente")
        return ev
