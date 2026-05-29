import uuid

from fastapi import APIRouter, Depends, Query, status
from app.models.bot import Bot
from app.api.dependencies import get_current_active_user, get_db_session
from app.core.rbac import Role, has_min_role, require_role
from app.models.user import User
from app.schemas.bot import BotCreate, BotListResponse, BotRead, BotUpdate
from app.services.bot_service import BotService

router = APIRouter(prefix="/bots", tags=["Bots"])


def _get_bot_service(db=Depends(get_db_session)) -> BotService:
    return BotService(db)


# ─── Create ───────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=BotRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new bot",
)
async def create_bot(
    payload: BotCreate,
    current_user: User = Depends(get_current_active_user),
    service: BotService = Depends(_get_bot_service),
) -> Bot:
    is_admin = has_min_role(current_user.role, Role.ADMIN)
    return await service.create(
        owner_id=current_user.id,
        payload=payload,
        is_admin=is_admin,
    )


# ─── List ─────────────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=BotListResponse,
    summary="List bots (own bots for users, all bots for admins)",
)
async def list_bots(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="Filter by status: draft | stopped | running | error",
    ),
    current_user: User = Depends(get_current_active_user),
    service: BotService = Depends(_get_bot_service),
) -> BotListResponse:
    if has_min_role(current_user.role, Role.ADMIN):
        items, total = await service.list_all(
            skip=skip, limit=limit, status=status_filter
        )
    else:
        # Non-admins always see only their own bots
        items, total = await service.list_user_bots(
            owner_id=current_user.id, skip=skip, limit=limit
        )
    return BotListResponse.build(items=items, total=total, skip=skip, limit=limit)


# ─── Get by ID ────────────────────────────────────────────────────────────────

@router.get(
    "/{bot_id}",
    response_model=BotRead,
    summary="Get bot by ID",
)
async def get_bot(
    bot_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: BotService = Depends(_get_bot_service),
) -> Bot:
    if has_min_role(current_user.role, Role.ADMIN):
        return await service.get_by_id(bot_id)
    # Regular users: 404 if bot doesn't exist OR doesn't belong to them
    return await service.get_by_id_for_user(bot_id, current_user.id)


# ─── Update ───────────────────────────────────────────────────────────────────

@router.patch(
    "/{bot_id}",
    response_model=BotRead,
    summary="Update bot",
)
async def update_bot(
    bot_id: uuid.UUID,
    payload: BotUpdate,
    current_user: User = Depends(get_current_active_user),
    service: BotService = Depends(_get_bot_service),
) -> Bot:
    if has_min_role(current_user.role, Role.ADMIN):
        bot = await service.get_by_id(bot_id)
    else:
        bot = await service.get_by_id_for_user(bot_id, current_user.id)
    return await service.update(bot, payload)


# ─── Delete ───────────────────────────────────────────────────────────────────

@router.delete(
    "/{bot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete bot",
)
async def delete_bot(
    bot_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: BotService = Depends(_get_bot_service),
) -> None:
    if has_min_role(current_user.role, Role.ADMIN):
        bot = await service.get_by_id(bot_id)
    else:
        bot = await service.get_by_id_for_user(bot_id, current_user.id)
    await service.delete(bot)
