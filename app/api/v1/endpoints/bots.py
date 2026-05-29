import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_current_active_user, get_db_session
from app.core.rbac import Role, has_min_role
from app.models.user import User
from app.schemas.bot import (
    BotActionResponse,
    BotAdminUpdate,
    BotCreate,
    BotListResponse,
    BotLogsResponse,
    BotRead,
    BotUpdate,
)
from app.services.bot_service import BotService

router = APIRouter(prefix="/bots", tags=["Bots"])


def _svc(db=Depends(get_db_session)) -> BotService:
    return BotService(db)


def _is_admin(user: User) -> bool:
    return has_min_role(user.role, Role.ADMIN)


async def _resolve_bot(
    bot_id: uuid.UUID,
    current_user: User,
    service: BotService,
):
    """Return bot — admin sees any, user sees own only."""
    if _is_admin(current_user):
        return await service.get_by_id(bot_id)
    return await service.get_by_id_for_user(bot_id, current_user.id)


# ─── CRUD ─────────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=BotRead,
    status_code=status.HTTP_201_CREATED,
    summary="Criar novo bot",
)
async def create_bot(
    payload: BotCreate,
    current_user: User = Depends(get_current_active_user),
    service: BotService = Depends(_svc),
):
    bot = await service.create(
        owner_id=current_user.id,
        payload=payload,
        is_admin=_is_admin(current_user),
    )
    return BotRead.from_orm_masked(bot)


@router.get(
    "/",
    response_model=BotListResponse,
    summary="Listar bots",
)
async def list_bots(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="Filtrar por status: draft | stopped | starting | running | stopping | error",
    ),
    current_user: User = Depends(get_current_active_user),
    service: BotService = Depends(_svc),
) -> BotListResponse:
    if _is_admin(current_user):
        items, total = await service.list_all(skip=skip, limit=limit, status=status_filter)
    else:
        items, total = await service.list_user_bots(
            owner_id=current_user.id, skip=skip, limit=limit
        )
    return BotListResponse.build(items=items, total=total, skip=skip, limit=limit)


@router.get(
    "/{bot_id}",
    response_model=BotRead,
    summary="Buscar bot por ID",
)
async def get_bot(
    bot_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: BotService = Depends(_svc),
):
    bot = await _resolve_bot(bot_id, current_user, service)
    return BotRead.from_orm_masked(bot)


@router.patch(
    "/{bot_id}",
    response_model=BotRead,
    summary="Atualizar bot",
)
async def update_bot(
    bot_id: uuid.UUID,
    payload: BotUpdate,
    current_user: User = Depends(get_current_active_user),
    service: BotService = Depends(_svc),
):
    # Admins can also force status; cast payload to admin variant
    if _is_admin(current_user) and isinstance(payload, dict):
        payload = BotAdminUpdate(**payload)
    bot = await _resolve_bot(bot_id, current_user, service)
    updated = await service.update(bot, payload)
    return BotRead.from_orm_masked(updated)


@router.delete(
    "/{bot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir bot",
)
async def delete_bot(
    bot_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: BotService = Depends(_svc),
) -> None:
    bot = await _resolve_bot(bot_id, current_user, service)
    await service.delete(bot)


# ─── Actions ──────────────────────────────────────────────────────────────────

@router.post(
    "/{bot_id}/start",
    response_model=BotActionResponse,
    summary="Iniciar bot",
)
async def start_bot(
    bot_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: BotService = Depends(_svc),
):
    bot = await _resolve_bot(bot_id, current_user, service)
    return await service.start(bot)


@router.post(
    "/{bot_id}/stop",
    response_model=BotActionResponse,
    summary="Parar bot",
)
async def stop_bot(
    bot_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: BotService = Depends(_svc),
):
    bot = await _resolve_bot(bot_id, current_user, service)
    return await service.stop(bot)


@router.post(
    "/{bot_id}/restart",
    response_model=BotActionResponse,
    summary="Reiniciar bot",
)
async def restart_bot(
    bot_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: BotService = Depends(_svc),
):
    bot = await _resolve_bot(bot_id, current_user, service)
    return await service.restart(bot)


@router.get(
    "/{bot_id}/logs",
    response_model=BotLogsResponse,
    summary="Logs do bot (simulado)",
)
async def get_bot_logs(
    bot_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: BotService = Depends(_svc),
):
    bot = await _resolve_bot(bot_id, current_user, service)
    return await service.get_logs(bot)
