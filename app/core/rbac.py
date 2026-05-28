"""
RBAC — Role-Based Access Control
Roles (least → most privileged): user < moderator < admin
"""
from enum import StrEnum
from functools import wraps

from fastapi import Depends

from app.core.exceptions import PermissionDeniedException


class Role(StrEnum):
    USER = "user"
    MODERATOR = "moderator"
    ADMIN = "admin"


# Ordered hierarchy — higher index = more privileged
ROLE_HIERARCHY: list[Role] = [Role.USER, Role.MODERATOR, Role.ADMIN]


def role_rank(role: Role) -> int:
    try:
        return ROLE_HIERARCHY.index(role)
    except ValueError:
        return -1


def has_min_role(user_role: Role, required_role: Role) -> bool:
    return role_rank(user_role) >= role_rank(required_role)


def require_role(minimum_role: Role):
    """
    FastAPI dependency factory.

    Usage:
        @router.get("/admin-only")
        async def admin_route(current_user = Depends(require_role(Role.ADMIN))):
            ...
    """
    from app.api.dependencies import get_current_active_user  # late import to avoid circular

    async def _check(current_user=Depends(get_current_active_user)):
        if not has_min_role(Role(current_user.role), minimum_role):
            raise PermissionDeniedException(
                f"Role '{minimum_role}' or higher required."
            )
        return current_user

    return _check
