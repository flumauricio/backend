"""
BotService V2
─────────────
Adds start / stop / restart / logs on top of V1 CRUD.
Execution is simulated — no real containers yet.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.core.logging import get_logger
from app.models.bot import Bot
from app.schemas.bot import (
    BotActionResponse,
    BotCreate,
    BotListResponse,
    BotLogsResponse,
    BotUpdate,
)

logger = get_logger(__name__)

_FALLBACK_MAX_BOTS: int = 1

# Valid transitions: {current_status: [allowed_actions]}
_STARTABLE  = {"draft", "stopped", "error"}
_STOPPABLE  = {"running", "starting"}
_RESTARTABLE = {"running", "stopped", "error"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BotService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── Limit helpers ────────────────────────────────────────────────────────

    async def _get_max_bots_for_user(self, user_id: uuid.UUID) -> int:
        try:
            row = await self.db.execute(
                text("""
                    SELECT COALESCE(ul.max_bots, p.max_bots, :fallback)
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
            logger.warning(
                "Could not resolve max_bots, using fallback",
                user_id=str(user_id),
            )
            return _FALLBACK_MAX_BOTS

    async def _count_user_bots(self, user_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(Bot).where(Bot.owner_id == user_id)
        )
        return result.scalar_one()

    # ─── Finders ──────────────────────────────────────────────────────────────

    async def get_by_id(self, bot_id: uuid.UUID) -> Bot:
        result = await self.db.execute(select(Bot).where(Bot.id == bot_id))
        bot = result.scalar_one_or_none()
        if bot is None:
            raise NotFoundException("Bot")
        return bot

    async def get_by_id_for_user(self, bot_id: uuid.UUID, owner_id: uuid.UUID) -> Bot:
        """404 for both non-existent and foreign bots — avoids existence leak."""
        result = await self.db.execute(
            select(Bot).where(Bot.id == bot_id, Bot.owner_id == owner_id)
        )
        bot = result.scalar_one_or_none()
        if bot is None:
            raise NotFoundException("Bot")
        return bot

    # ─── List ─────────────────────────────────────────────────────────────────

    async def list_user_bots(
        self,
        owner_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Bot], int]:
        stmt = (
            select(Bot)
            .where(Bot.owner_id == owner_id)
            .order_by(Bot.created_at.desc())
            .offset(skip).limit(limit)
        )
        count_stmt = (
            select(func.count()).select_from(Bot).where(Bot.owner_id == owner_id)
        )
        items = await self.db.execute(stmt)
        count = await self.db.execute(count_stmt)
        return list(items.scalars().all()), count.scalar_one()

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 50,
        *,
        owner_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> tuple[list[Bot], int]:
        base        = select(Bot)
        count_base  = select(func.count()).select_from(Bot)
        if owner_id:
            base       = base.where(Bot.owner_id == owner_id)
            count_base = count_base.where(Bot.owner_id == owner_id)
        if status:
            base       = base.where(Bot.status == status)
            count_base = count_base.where(Bot.status == status)
        stmt = base.order_by(Bot.created_at.desc()).offset(skip).limit(limit)
        items = await self.db.execute(stmt)
        count = await self.db.execute(count_base)
        return list(items.scalars().all()), count.scalar_one()

    # ─── CRUD ─────────────────────────────────────────────────────────────────

    async def create(
        self,
        owner_id: uuid.UUID,
        payload: BotCreate,
        *,
        is_admin: bool = False,
    ) -> Bot:
        if not is_admin:
            max_bots = await self._get_max_bots_for_user(owner_id)
            count    = await self._count_user_bots(owner_id)
            if count >= max_bots:
                raise BadRequestException(
                    f"Limite de bots atingido ({count}/{max_bots}). "
                    "Faça upgrade do seu plano para criar mais bots."
                )
        data = payload.model_dump(exclude={"discord_token"})
        bot  = Bot(
            owner_id=owner_id,
            status="draft",
            discord_token=payload.discord_token,
            **data,
        )
        self.db.add(bot)
        await self.db.flush()
        await self.db.refresh(bot)
        logger.info("Bot created", bot_id=str(bot.id), owner_id=str(owner_id))
        return bot

    async def update(self, bot: Bot, payload: BotUpdate) -> Bot:
        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(bot, field, value)
        await self.db.flush()
        await self.db.refresh(bot)
        logger.info("Bot updated", bot_id=str(bot.id), fields=list(update_data.keys()))
        return bot

    async def delete(self, bot: Bot) -> None:
        await self.db.delete(bot)
        await self.db.flush()
        logger.info("Bot deleted", bot_id=str(bot.id))

    # ─── Actions ──────────────────────────────────────────────────────────────

    async def start(self, bot: Bot) -> BotActionResponse:
        if bot.status not in _STARTABLE:
            raise BadRequestException(
                f"Não é possível iniciar um bot com status '{bot.status}'. "
                f"Status permitidos: {', '.join(sorted(_STARTABLE))}."
            )
        prev = bot.status
        bot.status = "running"
        bot.last_started_at = _now()
        await self.db.flush()
        await self.db.refresh(bot)
        logger.info("Bot started (simulated)", bot_id=str(bot.id))
        return BotActionResponse(
            bot_id=bot.id,
            action="start",
            previous_status=prev,
            current_status=bot.status,
            message=f"Bot '{bot.name}' iniciado com sucesso (simulado).",
            timestamp=_now(),
        )

    async def stop(self, bot: Bot) -> BotActionResponse:
        if bot.status not in _STOPPABLE:
            raise BadRequestException(
                f"Não é possível parar um bot com status '{bot.status}'. "
                f"Status permitidos: {', '.join(sorted(_STOPPABLE))}."
            )
        prev = bot.status
        bot.status = "stopped"
        bot.last_stopped_at = _now()
        await self.db.flush()
        await self.db.refresh(bot)
        logger.info("Bot stopped (simulated)", bot_id=str(bot.id))
        return BotActionResponse(
            bot_id=bot.id,
            action="stop",
            previous_status=prev,
            current_status=bot.status,
            message=f"Bot '{bot.name}' parado com sucesso (simulado).",
            timestamp=_now(),
        )

    async def restart(self, bot: Bot) -> BotActionResponse:
        if bot.status not in _RESTARTABLE:
            raise BadRequestException(
                f"Não é possível reiniciar um bot com status '{bot.status}'. "
                f"Status permitidos: {', '.join(sorted(_RESTARTABLE))}."
            )
        prev = bot.status
        bot.status = "running"
        bot.last_started_at = _now()
        await self.db.flush()
        await self.db.refresh(bot)
        logger.info("Bot restarted (simulated)", bot_id=str(bot.id))
        return BotActionResponse(
            bot_id=bot.id,
            action="restart",
            previous_status=prev,
            current_status=bot.status,
            message=f"Bot '{bot.name}' reiniciado com sucesso (simulado).",
            timestamp=_now(),
        )

    async def get_logs(self, bot: Bot) -> BotLogsResponse:
        """Return simulated log lines for V2."""
        now_str = _now().strftime("%Y-%m-%dT%H:%M:%SZ")
        lines = [
            f"[{now_str}] INFO  ServerDronics runtime v2.0 (simulado)",
            f"[{now_str}] INFO  Bot ID: {bot.id}",
            f"[{now_str}] INFO  Nome: {bot.name}",
            f"[{now_str}] INFO  Linguagem: {bot.language}",
            f"[{now_str}] INFO  Status atual: {bot.status}",
        ]
        if bot.last_started_at:
            lines.append(
                f"[{now_str}] INFO  Último start: {bot.last_started_at.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            )
        if bot.last_stopped_at:
            lines.append(
                f"[{now_str}] INFO  Último stop: {bot.last_stopped_at.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            )
        if bot.status == "running":
            lines += [
                f"[{now_str}] INFO  ✓ Conectado ao Discord Gateway",
                f"[{now_str}] INFO  ✓ Aguardando eventos...",
            ]
        elif bot.status == "error":
            lines.append(f"[{now_str}] ERROR ✗ Bot encerrado com erro — verifique a configuração.")
        elif bot.status == "draft":
            lines.append(f"[{now_str}] WARN  Bot em rascunho — configure e inicie.")
        else:
            lines.append(f"[{now_str}] INFO  Bot inativo.")

        return BotLogsResponse(
            bot_id=bot.id,
            bot_name=bot.name,
            lines=lines,
            generated_at=_now(),
        )
