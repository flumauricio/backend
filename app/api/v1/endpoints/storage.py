"""
Storage V2 — Endpoints

Admin volumes:
  GET    /api/v1/storage/volumes
  POST   /api/v1/storage/volumes
  GET    /api/v1/storage/volumes/{volume_id}
  PATCH  /api/v1/storage/volumes/{volume_id}
  DELETE /api/v1/storage/volumes/{volume_id}
  POST   /api/v1/storage/volumes/{volume_id}/health-check   [V2]
  POST   /api/v1/storage/volumes/health-check               [V2]
  GET    /api/v1/storage/summary                            [V2]

Bot workspace:
  GET  /api/v1/bots/{bot_id}/workspace
  POST /api/v1/bots/{bot_id}/workspace/prepare

Future stub (Storage V3 — wizard):
  GET  /api/v1/storage/devices  (disabled — placeholder only)
"""
import uuid

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_current_active_user, get_db_session
from app.core.rbac import Role, has_min_role, require_role
from app.models.user import User
from app.schemas.storage import (
    BotWorkspaceCreate,
    BotWorkspaceRead,
    StorageSummaryRead,
    StorageVolumeCreate,
    StorageVolumeRead,
    StorageVolumeUpdate,
)
from app.services.bot_service import BotService
from app.services.bot_workspace_service import BotWorkspaceService
from app.services.storage_health_service import StorageHealthService
from app.services.storage_volume_service import StorageVolumeService

volumes_router   = APIRouter(prefix="/storage",  tags=["Storage — Admin"])
workspace_router = APIRouter(prefix="/bots",      tags=["Storage — Workspace"])


# ─── Dependency factories ─────────────────────────────────────────────────────

def _vol_svc(db=Depends(get_db_session))    -> StorageVolumeService:  return StorageVolumeService(db)
def _health_svc(db=Depends(get_db_session)) -> StorageHealthService:  return StorageHealthService(db)
def _ws_svc(db=Depends(get_db_session))     -> BotWorkspaceService:   return BotWorkspaceService(db)
def _bot_svc(db=Depends(get_db_session))    -> BotService:            return BotService(db)


def _is_admin(user: User) -> bool:
    return has_min_role(user.role, Role.ADMIN)


async def _resolve_bot(bot_id: uuid.UUID, current_user: User, svc: BotService):
    if _is_admin(current_user):
        return await svc.get_by_id(bot_id)
    return await svc.get_by_id_for_user(bot_id, current_user.id)


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN — Volumes CRUD
# ═══════════════════════════════════════════════════════════════════════════════

@volumes_router.get(
    "/volumes",
    response_model=list[StorageVolumeRead],
    summary="Listar volumes [admin]",
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def list_volumes(svc: StorageVolumeService = Depends(_vol_svc)):
    return await svc.list_all()


@volumes_router.post(
    "/volumes",
    response_model=StorageVolumeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Criar volume [admin]",
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def create_volume(
    payload: StorageVolumeCreate,
    svc: StorageVolumeService = Depends(_vol_svc),
):
    return await svc.create(payload)


@volumes_router.get(
    "/volumes/{volume_id}",
    response_model=StorageVolumeRead,
    summary="Buscar volume [admin]",
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def get_volume(
    volume_id: uuid.UUID,
    svc: StorageVolumeService = Depends(_vol_svc),
):
    vol = await svc.get_by_id(volume_id)
    return StorageVolumeRead.from_orm(vol)


@volumes_router.patch(
    "/volumes/{volume_id}",
    response_model=StorageVolumeRead,
    summary="Atualizar volume [admin]",
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def update_volume(
    volume_id: uuid.UUID,
    payload: StorageVolumeUpdate,
    svc: StorageVolumeService = Depends(_vol_svc),
):
    return await svc.update(volume_id, payload)


@volumes_router.delete(
    "/volumes/{volume_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir volume [admin]",
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def delete_volume(
    volume_id: uuid.UUID,
    svc: StorageVolumeService = Depends(_vol_svc),
) -> None:
    await svc.delete(volume_id)


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN — Health Check  [V2]
# ═══════════════════════════════════════════════════════════════════════════════

@volumes_router.post(
    "/volumes/{volume_id}/health-check",
    response_model=StorageVolumeRead,
    summary="Verificar saúde de um volume [admin]",
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def health_check_volume(
    volume_id: uuid.UUID,
    vol_svc:    StorageVolumeService = Depends(_vol_svc),
    health_svc: StorageHealthService  = Depends(_health_svc),
):
    """
    Runs shutil.disk_usage() on the volume's mount_path.
    Updates detected_total_mb, detected_free_mb, health_status, health_message.
    Never returns 500 — errors are stored in health_status=error/offline.
    """
    volume = await vol_svc.get_by_id(volume_id)
    return await health_svc.check_volume_health(volume)


@volumes_router.post(
    "/volumes/health-check",
    response_model=list[StorageVolumeRead],
    summary="Verificar saúde de todos os volumes [admin]",
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def health_check_all(
    health_svc: StorageHealthService = Depends(_health_svc),
):
    """
    Runs health check on every volume in parallel.
    Always returns 200 — per-volume failures are reflected in health_status.
    """
    return await health_svc.check_all_volumes()


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN — Summary  [V2]
# ═══════════════════════════════════════════════════════════════════════════════

@volumes_router.get(
    "/summary",
    response_model=StorageSummaryRead,
    summary="Resumo geral do armazenamento [admin]",
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def storage_summary(svc: StorageVolumeService = Depends(_vol_svc)):
    return await svc.summary()


# ═══════════════════════════════════════════════════════════════════════════════
# STORAGE V3 STUB — Device Discovery (NOT IMPLEMENTED)
# ═══════════════════════════════════════════════════════════════════════════════
# TODO(V3): Implement device auto-discovery wizard.
#
# Planned endpoint:
#   GET /api/v1/storage/devices
#
# Will list raw block devices (lsblk) and unmounted partitions so the admin
# can select one to add via the wizard.
#
# NOT implemented in V2:
#   - lsblk / blkid scanning
#   - mkfs formatting
#   - mount / umount automation
#   - SMART health polling
#   - Workspace rebalancing between volumes
#   - Automatic workspace migration when a volume fails


# ═══════════════════════════════════════════════════════════════════════════════
# BOT WORKSPACE
# ═══════════════════════════════════════════════════════════════════════════════

@workspace_router.get(
    "/{bot_id}/workspace",
    response_model=BotWorkspaceRead | None,
    summary="Ver workspace do bot",
)
async def get_workspace(
    bot_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    bot_svc: BotService           = Depends(_bot_svc),
    ws_svc:  BotWorkspaceService  = Depends(_ws_svc),
):
    bot = await _resolve_bot(bot_id, current_user, bot_svc)
    return await ws_svc.get_for_bot(bot.id)


@workspace_router.post(
    "/{bot_id}/workspace/prepare",
    response_model=BotWorkspaceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Preparar workspace do bot",
)
async def prepare_workspace(
    bot_id:  uuid.UUID,
    payload: BotWorkspaceCreate,
    current_user: User = Depends(get_current_active_user),
    bot_svc: BotService           = Depends(_bot_svc),
    ws_svc:  BotWorkspaceService  = Depends(_ws_svc),
):
    bot = await _resolve_bot(bot_id, current_user, bot_svc)
    return await ws_svc.prepare(bot, payload, is_admin=_is_admin(current_user))
