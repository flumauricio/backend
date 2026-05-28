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


# ─── DB session (re-exported for use in other modules) ────────────────────────

async def get_db_session(db: AsyncSession = Depends(get_db)) -> AsyncSession:
    """
    Thin wrapper around get_db so other modules can depend on this
    instead of importing get_db directly from app.database.session.
    Keeps the import graph clean.
    """
    return db


# ─── Service dependency ───────────────────────────────────────────────────────

async def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)


# ─── Auth dependencies ────────────────────────────────────────────────────────

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    user_service: UserService = Depends(get_user_service),
) -> User:
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise CredentialsException()
        user_id: str = payload.get("sub")
        if not user_id:
            raise CredentialsException()
    except JWTError:
        raise CredentialsException()

    user = await user_service.get_by_id(uuid.UUID(user_id))

    if not user:
        raise CredentialsException()

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise BadRequestException("Account is deactivated.")
    return current_user
