import uuid

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_current_active_user, get_db_session, get_user_service
from app.core.rbac import Role, require_role
from app.models.user import User
from app.schemas.user import UserPage, UserRead, UserUpdate, UserUpdateAdmin
from app.schemas.user_limits import EffectiveUserLimitsRead, UserLimitsRead, UserLimitsUpdate
from app.services.user_limits_service import UserLimitsService
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


def _get_limits_service(db=Depends(get_db_session)) -> UserLimitsService:
    return UserLimitsService(db)


# ─── Self-service ─────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserRead,
    summary="Get my profile",
)
async def get_me(
    current_user: User = Depends(get_current_active_user),
) -> User:
    return current_user


@router.patch(
    "/me",
    response_model=UserRead,
    summary="Update my profile",
)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service),
) -> User:
    return await user_service.update(current_user, payload)


@router.get(
    "/me/limits",
    response_model=EffectiveUserLimitsRead,
    summary="Get my effective resource limits",
)
async def get_my_limits(
    current_user: User = Depends(get_current_active_user),
    limits_service: UserLimitsService = Depends(_get_limits_service),
) -> EffectiveUserLimitsRead:
    """
    Returns the fully resolved limits that apply to the authenticated user.
    Merges per-user overrides → assigned plan → free-tier defaults.
    """
    return await limits_service.get_effective(current_user.id)


# ─── Admin: user limits ───────────────────────────────────────────────────────

@router.get(
    "/{user_id}/limits",
    response_model=UserLimitsRead,
    summary="Get raw limits row for a user [admin]",
)
async def get_user_limits(
    user_id: uuid.UUID,
    limits_service: UserLimitsService = Depends(_get_limits_service),
    _actor: User = Depends(require_role(Role.ADMIN)),
) -> UserLimitsRead:
    """
    Returns the stored UserLimits row, showing exactly what is overridden
    and which plan is assigned. Null fields mean 'inherit from plan'.
    Use /{user_id}/limits/effective for fully resolved values.
    """
    row = await limits_service.get_row_by_user(user_id)
    if row is None:
        # Return an empty shell so admins can see the user has no config yet
        from app.schemas.user_limits import UserLimitsRead as _ULR
        from datetime import datetime, timezone
        _now = datetime.now(timezone.utc)
        return _ULR(
            id=uuid.uuid4(),
            user_id=user_id,
            plan_id=None,
            plan=None,
            cloud_storage_mb=None,
            max_bots=None,
            max_ram_per_bot_mb=None,
            max_storage_per_bot_mb=None,
            created_at=_now,
            updated_at=_now,
        )
    return row


@router.patch(
    "/{user_id}/limits",
    response_model=UserLimitsRead,
    summary="Set limits / assign plan for a user [admin]",
)
async def update_user_limits(
    user_id: uuid.UUID,
    payload: UserLimitsUpdate,
    limits_service: UserLimitsService = Depends(_get_limits_service),
    user_service: UserService = Depends(get_user_service),
    _actor: User = Depends(require_role(Role.ADMIN)),
) -> UserLimitsRead:
    """
    Creates or updates the UserLimits row for the target user.
    Pass `plan_id: null` to detach from any plan.
    Pass a limit field as `null` to clear the override (fall back to plan).
    """
    # Validate that the target user exists (raises 404 if not)
    await user_service.get_by_id(user_id)
    return await limits_service.upsert(user_id, payload)


# ─── Moderator+ ──────────────────────────────────────────────────────────────

@router.get(
    "/{user_id}",
    response_model=UserRead,
    summary="Get user by ID [moderator+]",
    dependencies=[Depends(require_role(Role.MODERATOR))],
)
async def get_user(
    user_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
) -> User:
    return await user_service.get_by_id(user_id)


# ─── Admin: user CRUD ─────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=UserPage,
    summary="List users [admin]",
)
async def list_users(
    user_service: UserService = Depends(get_user_service),
    _actor: User = Depends(require_role(Role.ADMIN)),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    role: Role | None = None,
    is_active: bool | None = None,
):
    items = await user_service.list_paginated(
        skip=skip,
        limit=limit,
        role=role,
        is_active=is_active,
    )
    total = await user_service.count(role=role, is_active=is_active)

    return UserPage.build(items=items, total=total, skip=skip, limit=limit)

@router.patch(
    "/{user_id}",
    response_model=UserRead,
    summary="Update user [admin]",
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateAdmin,
    user_service: UserService = Depends(get_user_service),
) -> User:
    user = await user_service.get_by_id(user_id)
    return await user_service.update(user, payload)


@router.delete(
    "/{user_id}",
    status_code=204,
    summary="Deactivate user [admin]",
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def deactivate_user(
    user_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
) -> None:
    user = await user_service.get_by_id(user_id)
    await user_service.deactivate(user)
