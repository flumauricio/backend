"""
StorageVolumeService — V2
─────────────────────────
Admin CRUD + volume selection with health-aware logic.

V2 changes vs V1:
  - pick_best_for_bots: now excludes offline/error volumes
  - pick_best_for_bots: checks available_for_allocation_mb when known
  - create/update: accept reserved_system_mb, reserve_percent
  - ensure_default_volume: seeds V2 fields (reserved_system_mb, reserve_percent, health_status)
  - summary(): returns StorageSummaryRead aggregate
"""
import uuid

from sqlalchemy import asc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, ConflictException, NotFoundException
from app.core.logging import get_logger
from app.models.storage import HEALTH_BLOCKED, HEALTH_UNKNOWN, StorageVolume
from app.schemas.storage import (
    StorageSummaryRead,
    StorageVolumeCreate,
    StorageVolumeRead,
    StorageVolumeUpdate,
)

logger = get_logger(__name__)

_BOT_PURPOSES = {"bots", "mixed"}


class StorageVolumeService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── List ─────────────────────────────────────────────────────────────────

    async def list_all(self) -> list[StorageVolumeRead]:
        result = await self.db.execute(
            select(StorageVolume).order_by(asc(StorageVolume.priority), StorageVolume.name)
        )
        return [StorageVolumeRead.from_orm(v) for v in result.scalars().all()]

    # ─── Get one ──────────────────────────────────────────────────────────────

    async def get_by_id(self, volume_id: uuid.UUID) -> StorageVolume:
        result = await self.db.execute(
            select(StorageVolume).where(StorageVolume.id == volume_id)
        )
        vol = result.scalar_one_or_none()
        if vol is None:
            raise NotFoundException("Volume de armazenamento")
        return vol

    # ─── Create ───────────────────────────────────────────────────────────────

    async def create(self, payload: StorageVolumeCreate) -> StorageVolumeRead:
        existing = await self.db.execute(
            select(StorageVolume).where(StorageVolume.mount_path == payload.mount_path)
        )
        if existing.scalar_one_or_none():
            raise ConflictException(
                f"Já existe um volume com mount_path '{payload.mount_path}'."
            )
        data = payload.model_dump()
        # New volumes start as unknown — admin must run health-check
        data.setdefault("health_status", HEALTH_UNKNOWN)
        vol = StorageVolume(**data)
        self.db.add(vol)
        await self.db.flush()
        await self.db.refresh(vol)
        logger.info("StorageVolume created", volume_id=str(vol.id), path=vol.mount_path)
        return StorageVolumeRead.from_orm(vol)

    # ─── Update ───────────────────────────────────────────────────────────────

    async def update(
        self, volume_id: uuid.UUID, payload: StorageVolumeUpdate
    ) -> StorageVolumeRead:
        vol = await self.get_by_id(volume_id)

        if payload.mount_path is not None and payload.mount_path != vol.mount_path:
            conflict = await self.db.execute(
                select(StorageVolume).where(
                    StorageVolume.mount_path == payload.mount_path,
                    StorageVolume.id != volume_id,
                )
            )
            if conflict.scalar_one_or_none():
                raise ConflictException(
                    f"Já existe um volume com mount_path '{payload.mount_path}'."
                )

        for field, val in payload.model_dump(exclude_unset=True).items():
            setattr(vol, field, val)

        # Reset health to unknown if mount_path was changed
        if payload.mount_path is not None and payload.mount_path != vol.mount_path:
            vol.health_status        = HEALTH_UNKNOWN
            vol.health_message       = "Caminho alterado — execute uma verificação de saúde"
            vol.detected_total_mb    = None
            vol.detected_free_mb     = None
            vol.auto_detected        = False
            vol.last_health_check_at = None

        await self.db.flush()
        await self.db.refresh(vol)
        logger.info("StorageVolume updated", volume_id=str(vol.id))
        return StorageVolumeRead.from_orm(vol)

    # ─── Delete ───────────────────────────────────────────────────────────────

    async def delete(self, volume_id: uuid.UUID) -> None:
        vol = await self.get_by_id(volume_id)
        if vol.workspaces:
            raise BadRequestException(
                f"Volume '{vol.name}' possui {len(vol.workspaces)} workspace(s) vinculado(s). "
                "Remova os workspaces antes de excluir o volume."
            )
        await self.db.delete(vol)
        await self.db.flush()
        logger.info("StorageVolume deleted", volume_id=str(volume_id))

    # ─── Volume selection (used by BotWorkspaceService) ───────────────────────

    async def pick_best_for_bots(self, needed_mb: int | None = None) -> StorageVolume | None:
        """
        V2: health-aware volume selection.

        Filters:
          1. is_active = True
          2. health_status NOT in ('offline', 'error')
          3. purpose in ('bots', 'mixed')
          4. available_for_allocation_mb >= needed_mb  (only checked if both are known)

        Sorting: priority ASC, then detected_free_mb DESC (most free space first).
        """
        result = await self.db.execute(
            select(StorageVolume)
            .where(
                StorageVolume.is_active.is_(True),
                StorageVolume.purpose.in_(list(_BOT_PURPOSES)),
                ~StorageVolume.health_status.in_(list(HEALTH_BLOCKED)),
            )
            .order_by(
                asc(StorageVolume.priority),
                # Most free detected space first; NULL last
                StorageVolume.detected_free_mb.desc().nullslast(),
            )
        )
        candidates = list(result.scalars().all())

        if not candidates:
            return None

        # If we know how much space is needed, filter by availability
        if needed_mb is not None:
            eligible = [
                v for v in candidates
                if v.available_for_allocation_mb is None  # unknown → optimistic
                or v.available_for_allocation_mb >= needed_mb
            ]
            if eligible:
                return eligible[0]
            # If none have confirmed space, fall through to best guess
            # (service layer will decide whether to block or proceed)

        return candidates[0]

    # ─── Summary ──────────────────────────────────────────────────────────────

    async def summary(self) -> StorageSummaryRead:
        """Platform-wide storage summary."""
        result = await self.db.execute(select(StorageVolume))
        volumes = list(result.scalars().all())

        def _none_sum(vals) -> int | None:
            known = [v for v in vals if v is not None]
            return sum(known) if known else None

        return StorageSummaryRead(
            volumes_total=len(volumes),
            volumes_online=sum(1 for v in volumes if v.health_status == "online"),
            volumes_offline=sum(1 for v in volumes if v.health_status == "offline"),
            volumes_warning=sum(1 for v in volumes if v.health_status == "warning"),
            volumes_error=sum(1 for v in volumes if v.health_status == "error"),
            volumes_unknown=sum(1 for v in volumes if v.health_status in (None, "unknown")),
            capacity_registered_mb=_none_sum(v.total_mb for v in volumes),
            detected_total_mb=_none_sum(v.detected_total_mb for v in volumes),
            detected_free_mb=_none_sum(v.detected_free_mb for v in volumes),
            reserved_for_bots_mb=sum(v.used_mb for v in volumes),
            available_for_allocation_mb=_none_sum(
                v.available_for_allocation_mb for v in volumes
            ),
        )

    # ─── Seed helper ──────────────────────────────────────────────────────────

    async def ensure_default_volume(self) -> StorageVolume:
        """
        Idempotent seed of the default local storage volume.
        V2: also populates reserved_system_mb, reserve_percent, health_status.
        Does NOT fail startup if /app/storage is unreachable.
        """
        import os

        default_path = "/app/storage"

        result = await self.db.execute(
            select(StorageVolume).where(StorageVolume.mount_path == default_path)
        )
        vol = result.scalar_one_or_none()

        if vol is not None:
            # Migrate existing row: fill V2 fields if they're still at defaults
            changed = False
            if vol.reserved_system_mb is None:
                vol.reserved_system_mb = 1024; changed = True
            if vol.reserve_percent is None:
                vol.reserve_percent = 10; changed = True
            if not vol.health_status:
                vol.health_status = HEALTH_UNKNOWN; changed = True
            if changed:
                await self.db.flush()
                logger.info("Seed: V2 fields migrated on default volume", volume_id=str(vol.id))
            else:
                logger.info("Seed: default storage volume already up-to-date", volume_id=str(vol.id))
            return vol

        # Try to create physical directory
        try:
            os.makedirs(default_path, exist_ok=True)
            logger.info("Seed: created storage directory", path=default_path)
        except OSError as exc:
            logger.warning(
                "Seed: could not create storage directory (non-fatal)",
                path=default_path,
                error=str(exc),
            )

        vol = StorageVolume(
            name="Local Storage",
            mount_path=default_path,
            purpose="mixed",
            total_mb=None,
            is_active=True,
            priority=100,
            reserved_system_mb=1024,
            reserve_percent=10,
            health_status=HEALTH_UNKNOWN,
        )
        self.db.add(vol)
        await self.db.flush()
        await self.db.refresh(vol)
        logger.info("Seed: default storage volume created (V2)", volume_id=str(vol.id))
        return vol
