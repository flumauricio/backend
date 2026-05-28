"""
RBAC — Role-Based Access Control
Roles (least → most privileged): user < moderator < admin
"""
from enum import StrEnum

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
        return ROLE_HIERARCHY.index(Role(role))
    except ValueError:
        return -1


def has_min_role(user_role: str | Role, required_role: Role) -> bool:
    return role_rank(user_role) >= role_rank(required_role)


def require_role(minimum_role: Role):
    """
    FastAPI dependency factory — enforces role hierarchy.

    Injects the authenticated, active user into the route so it can be
    used directly without a second Depends(get_current_active_user).

    Usage:
        # dependency-only (access check, user discarded)
        @router.get("/admin", dependencies=[Depends(require_role(Role.ADMIN))])

        # user available in route
        @router.get("/mod-area")
        async def mod_route(actor: User = Depends(require_role(Role.MODERATOR))):
            ...
    """
    # Late import avoids the circular:
    #   rbac → dependencies → rbac
    from app.api.dependencies import get_current_active_user

    async def _check_role(current_user=Depends(get_current_active_user)):
        if not has_min_role(current_user.role, minimum_role):
            raise PermissionDeniedException(
                f"Requires role '{minimum_role}' or higher "
                f"(current: '{current_user.role}')."
            )
        return current_user

    # Give the inner function a unique name so FastAPI's dependency cache
    # treats each require_role(X) call as a distinct dependency.
    _check_role.__name__ = f"_require_{minimum_role}"

    return _check_role
