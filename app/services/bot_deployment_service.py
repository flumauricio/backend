"""
BotDeploymentService
────────────────────
Manages BotDeployment records.

V3: prepare() creates a deployment in status='prepared' and writes a
persistent BotLog entry.  No real Docker/execution happens here.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.core.logging import get_logger
from app.models.bot import Bot
from app.models.bot_v3 import BotDeployment, BotLog
from app.schemas.bot_v3 import BotDeploymentCreate, BotDeploymentRead, BotPrepareResponse

logger = get_logger(__name__)

_DEFAULT_RUNTIMES: dict[str, str] = {
    "javascript": "node18",
    "typescript": "node18",
    "python":     "python311",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BotDeploymentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── Prepare ──────────────────────────────────────────────────────────────

    async def prepare(
        self,
        bot: Bot,
        payload: BotDeploymentCreate,
    ) -> BotPrepareResponse:
        """
        Create a deployment record in status='prepared'.

        Rules:
        - main_file must come from bot or payload — error if neither present.
        - runtime defaults to language-based preset when absent everywhere.
        - Discord token is NEVER stored in logs.
        """
        # ── Resolve main_file ─────────────────────────────────────────────────
        main_file = payload.main_file or bot.main_file
        if not main_file:
            raise BadRequestException(
                "Nenhum arquivo principal (main_file) definido. "
                "Configure o bot ou informe main_file no corpo da requisição."
            )

        # ── Resolve runtime ───────────────────────────────────────────────────
        runtime = (
            payload.runtime
            or bot.runtime_version
            or _DEFAULT_RUNTIMES.get(bot.language, "node18")
        )

        # ── Create deployment record ──────────────────────────────────────────
        deployment = BotDeployment(
            bot_id=bot.id,
            status="prepared",
            source_type=payload.source_type,
            source_url=payload.source_url,
            commit_hash=payload.commit_hash,
            runtime=runtime,
            main_file=main_file,
            storage_path=payload.storage_path,
            message=(
                f"Deploy preparado — runtime={runtime}, "
                f"main_file={main_file}, source={payload.source_type}"
            ),
        )
        self.db.add(deployment)
        await self.db.flush()          # assign deployment.id before log FK

        # ── Write persistent log ──────────────────────────────────────────────
        log_entry = BotLog(
            bot_id=bot.id,
            deployment_id=deployment.id,
            level="info",
            message=(
                f"[PREPARE] Bot '{bot.name}' — deploy preparado com sucesso. "
                f"Linguagem: {bot.language}, Runtime: {runtime}, "
                f"Arquivo principal: {main_file}, Fonte: {payload.source_type}."
            ),
        )
        self.db.add(log_entry)
        await self.db.flush()
        await self.db.refresh(deployment)

        logger.info(
            "Deployment prepared",
            bot_id=str(bot.id),
            deployment_id=str(deployment.id),
            runtime=runtime,
            main_file=main_file,
        )

        return BotPrepareResponse(
            deployment=BotDeploymentRead.model_validate(deployment),
            ok=True,
            detail=(
                f"Deploy preparado com sucesso para o bot '{bot.name}'. "
                "Nenhuma execução real foi iniciada (V3 — simulado)."
            ),
        )

    # ─── List ─────────────────────────────────────────────────────────────────

    async def list_for_bot(
        self,
        bot_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[BotDeployment]:
        stmt = (
            select(BotDeployment)
            .where(BotDeployment.bot_id == bot_id)
            .order_by(BotDeployment.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ─── Get one ──────────────────────────────────────────────────────────────

    async def get_by_id(
        self,
        deployment_id: uuid.UUID,
        bot_id: uuid.UUID,
    ) -> BotDeployment:
        result = await self.db.execute(
            select(BotDeployment).where(
                BotDeployment.id == deployment_id,
                BotDeployment.bot_id == bot_id,
            )
        )
        dep = result.scalar_one_or_none()
        if dep is None:
            raise NotFoundException("Deployment")
        return dep
