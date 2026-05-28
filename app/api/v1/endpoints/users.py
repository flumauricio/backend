import uuid

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_active_user, get_user_service
from app.core.rbac import Role, require_role
from app.models.user import User
from app.schemas.user import UserRead, UserUpdate, UserUpdateAdmin
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


# ─── Current user ─────────────────────────────────────────────────────────────

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


# ─── Admin-only ───────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=list[UserRead],
    summary="List all users [admin]",
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def list_users(
    user_service: UserService = Depends(get_user_service),
    skip: int = 0,
    limit: int = 50,
):
    # Minimal implementation — extend with pagination helper later
    from sqlalchemy import select
    from app.database.session import AsyncSessionLocal
    # NOTE: replace with proper paginated query in service layer
    return []


@router.get(
    "/{user_id}",
    response_model=UserRead,
    summary="Get user by ID [moderator+]",
    dependencies=[Depends(require_role(Role.MODERATOR))],
)
async def get_user(
    user_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
):
    return await user_service.get_by_id(user_id)


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
):
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
):
    user = await user_service.get_by_id(user_id)
    await user_service.deactivate(user)
