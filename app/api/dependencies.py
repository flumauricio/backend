import uuid

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, CredentialsException
from app.core.security import decode_token
from app.database.session import get_db
from app.models.user import User
from app.services.user_service import UserService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ─── Service dependency ───────────────────────────────────────────────────────

async def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)


# ─── Auth dependencies ────────────────────────────────────────────────────────

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    user_service: UserService = Depends(get_user_service),
) -> User:
    """
    Decode the JWT and return the matching User.
    Raises 401 for any credential problem (bad token, wrong type,
    unknown user). Never raises 404 — a missing user is still a
    credential failure from the client's perspective.
    """
    try:
        payload = decode_token(token)
    except JWTError:
        raise CredentialsException()

    if payload.get("type") != "access":
        raise CredentialsException()

    raw_sub: str | None = payload.get("sub")
    if not raw_sub:
        raise CredentialsException()

    try:
        user_id = uuid.UUID(raw_sub)
    except ValueError:
        raise CredentialsException()

    # Use the service directly (not get_by_id) so we return 401, not 404.
    user = await user_service.get_by_id_or_none(user_id)
    if user is None:
        raise CredentialsException()

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Extends get_current_user by also rejecting deactivated accounts.
    Raises 400 (not 401) so the client knows the token is valid but
    the account is blocked — avoids misleading re-auth loops.
    """
    if not current_user.is_active:
        raise BadRequestException("Account is deactivated.")
    return current_user
