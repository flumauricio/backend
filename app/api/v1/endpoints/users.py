import uuid

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_current_active_user, get_user_service
from app.core.rbac import Role, require_role
from app.models.user import User
from app.schemas.user import UserPage, UserRead, UserUpdate, UserUpdateAdmin
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserRead, summary="Get current user profile")
async def get_me(current_user: User = Depends(get_current_active_user)):
    return current_user


@router.patch("/me", response_model=UserRead, summary="Update current user profile")
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service),
):
    return await user_service.update(current_user, payload)


@router.get(
    "/",
    response_model=UserPage,
    summary="List users [admin]",
)
async def list_users(
    user_service: UserService = Depends(get_user_service),
    _actor: User = Depends(require_role(Role.ADMIN)),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
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


@router.get(
    "/{user_id}",
    response_model=UserRead,
    summary="Get user by ID [moderator+]",
)
async def get_user(
    user_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
    _actor: User = Depends(require_role(Role.MODERATOR)),
):
    return await user_service.get_by_id(user_id)


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    summary="Update user [admin]",
)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateAdmin,
    user_service: UserService = Depends(get_user_service),
    _actor: User = Depends(require_role(Role.ADMIN)),
):
    user = await user_service.get_by_id(user_id)
    return await user_service.update(user, payload)


@router.delete(
    "/{user_id}",
    status_code=204,
    summary="Deactivate user [admin]",
)
async def deactivate_user(
    user_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
    _actor: User = Depends(require_role(Role.ADMIN)),
):
    user = await user_service.get_by_id(user_id)
    await user_service.deactivate(user)


@router.post(
    "/{user_id}/reactivate",
    response_model=UserRead,
    summary="Reactivate user [admin]",
)
async def reactivate_user(
    user_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
    _actor: User = Depends(require_role(Role.ADMIN)),
):
    user = await user_service.get_by_id(user_id)
    return await user_service.reactivate(user)
