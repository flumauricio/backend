"""
BotWorkspaceService — V2
────────────────────────
V2 changes:
  - Rejects volumes with health_status in ('offline', 'error')
  - Checks available_for_allocation_mb against requested allocation
  - Returns BotWorkspaceRead with volume_health field populated
  - GET workspace continues to work even when the volume is offline
"""
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.core.logging import get_logger
from app.models.bot import Bot
from app.models.storage import HEALTH_BLOCKED, BotWorkspace, StorageVolume
from app.schemas.storage import BotWorkspaceCreate, BotWorkspaceRead
from app.services.storage_volume_service import StorageVolumeService
from app.services.user_limits_service import UserLimitsService

logger = get_logger(__name__)


class BotWorkspaceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._vol_svc = StorageVolumeService(db)
        self._lim_svc = UserLimitsService(db)

    # ─── Get workspace ────────────────────────────────────────────────────────

    async def get_for_bot(self, bot_id: uuid.UUID) -> BotWorkspaceRead | None:
        """
        Returns workspace for a bot, or None if not yet prepared.
        Works even when the volume is offline — schema carries health info.
        """
        result = await self.db.execute(
            select(BotWorkspace)
            .where(BotWorkspace.bot_id == bot_id)
            .options(selectinload(BotWorkspace.volume))
        )
        ws = result.scalar_one_or_none()
        return BotWorkspaceRead.from_orm(ws) if ws else None

    # ─── Prepare workspace ────────────────────────────────────────────────────

    async def prepare(
        self,
        bot: Bot,
        payload: BotWorkspaceCreate,
        *,
        is_admin: bool = False,
    ) -> BotWorkspaceRead:
        # ── 1. Already has workspace? ─────────────────────────────────────────
        existing = await self.db.execute(
            select(BotWorkspace)
            .where(BotWorkspace.bot_id == bot.id)
            .options(selectinload(BotWorkspace.volume))
        )
        if (ws := existing.scalar_one_or_none()) is not None:
            raise BadRequestException(
                f"O bot '{bot.name}' já possui um workspace em "
                f"'{ws.volume.mount_path}/{ws.relative_path}'. "
                "Cada bot pode ter apenas um workspace."
            )

        # ── 2. Resolve allocated_mb ───────────────────────────────────────────
        if payload.allocated_mb is not None:
            allocated_mb = payload.allocated_mb
            if not is_admin:
                limits = await self._lim_svc.get_effective(bot.owner_id)
                plan_limit = limits.max_storage_per_bot_mb
                if plan_limit == 0:
                    raise BadRequestException(
                        "Seu plano não permite criar workspaces de bot."
                    )
                if allocated_mb > plan_limit:
                    raise BadRequestException(
                        f"Alocação solicitada ({allocated_mb} MB) excede o limite "
                        f"do seu plano ({plan_limit} MB por bot)."
                    )
        else:
            if is_admin:
                allocated_mb = 512
            else:
                limits = await self._lim_svc.get_effective(bot.owner_id)
                allocated_mb = limits.max_storage_per_bot_mb
                if allocated_mb == 0:
                    raise BadRequestException(
                        "Seu plano não permite criar workspaces de bot."
                    )

        # ── 3. Resolve volume ─────────────────────────────────────────────────
        if payload.storage_volume_id is not None:
            try:
                volume = await self._vol_svc.get_by_id(payload.storage_volume_id)
            except NotFoundException:
                raise BadRequestException(
                    f"Volume '{payload.storage_volume_id}' não encontrado."
                )
            # V2: reject unhealthy volumes
            if volume.health_status in HEALTH_BLOCKED:
                raise BadRequestException(
                    f"O volume '{volume.name}' está com status "
                    f"'{volume.health_status}' e não pode receber novos workspaces. "
                    f"Mensagem: {volume.health_message or 'sem detalhes'}. "
                    "Verifique o volume e tente novamente."
                )
            if not volume.is_active:
                raise BadRequestException(
                    f"O volume '{volume.name}' está inativo."
                )
            if volume.purpose not in ("bots", "mixed"):
                raise BadRequestException(
                    f"O volume '{volume.name}' tem propósito '{volume.purpose}' "
                    "e não aceita workspaces de bots."
                )
        else:
            volume = await self._vol_svc.pick_best_for_bots(needed_mb=allocated_mb)
            if volume is None:
                raise BadRequestException(
                    "Nenhum volume de armazenamento ativo e saudável disponível para bots. "
                    "Verifique se existe um volume com propósito 'bots' ou 'misto', "
                    "que esteja ativo e com status online/unknown."
                )

        # ── 4. Check available space (V2) ─────────────────────────────────────
        avail = volume.available_for_allocation_mb
        if avail is not None and avail < allocated_mb:
            raise BadRequestException(
                f"O volume '{volume.name}' não tem espaço disponível suficiente após reservas. "
                f"Disponível: {avail} MB | Solicitado: {allocated_mb} MB."
            )

        # ── 5. Verify mount_path exists on disk ───────────────────────────────
        if not Path(volume.mount_path).exists():
            raise BadRequestException(
                f"O diretório do volume '{volume.name}' não existe: '{volume.mount_path}'. "
                "Verifique se o dispositivo está montado."
            )

        # ── 6. Create physical directory ──────────────────────────────────────
        relative_path = f"bots/{bot.id}"
        full_path = Path(volume.mount_path) / relative_path
        try:
            full_path.mkdir(parents=True, exist_ok=True)
            logger.info("BotWorkspace directory created", path=str(full_path), bot_id=str(bot.id))
        except OSError as exc:
            raise BadRequestException(
                f"Não foi possível criar o diretório '{full_path}': {exc}."
            ) from exc

        # ── 7. Persist workspace row ──────────────────────────────────────────
        ws = BotWorkspace(
            bot_id=bot.id,
            storage_volume_id=volume.id,
            relative_path=relative_path,
            allocated_mb=allocated_mb,
            used_mb=0,
        )
        self.db.add(ws)
        await self.db.flush()

        # ── 8. Update volume.used_mb ──────────────────────────────────────────
        volume.used_mb = (volume.used_mb or 0) + allocated_mb
        await self.db.flush()

        # Reload with volume relationship
        result = await self.db.execute(
            select(BotWorkspace)
            .where(BotWorkspace.id == ws.id)
            .options(selectinload(BotWorkspace.volume))
        )
        ws = result.scalar_one()

        logger.info(
            "BotWorkspace prepared",
            bot_id=str(bot.id),
            workspace_id=str(ws.id),
            volume=volume.name,
            path=str(full_path),
            allocated_mb=allocated_mb,
        )
        return BotWorkspaceRead.from_orm(ws)
