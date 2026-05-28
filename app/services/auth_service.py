from jose import JWTError

from app.core.exceptions import BadRequestException, CredentialsException
from app.core.logging import get_logger
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.user import User
from app.schemas.token import Token
from app.services.user_service import UserService

logger = get_logger(__name__)


class AuthService:
    def __init__(self, user_service: UserService) -> None:
        self.user_service = user_service

    async def login(self, email: str, password: str) -> Token:
        user = await self.user_service.authenticate(email, password)
        if not user:
            raise CredentialsException()
        if not user.is_active:
            raise BadRequestException("Account is deactivated.")

        return self._build_tokens(user)

    async def refresh(self, refresh_token: str) -> Token:
        try:
            payload = decode_token(refresh_token)
        except JWTError:
            raise CredentialsException()

        if payload.get("type") != "refresh":
            raise CredentialsException()

        user = await self.user_service.get_by_email(payload["sub"])
        if not user or not user.is_active:
            raise CredentialsException()

        logger.info("Token refreshed", user_id=str(user.id))
        return self._build_tokens(user)

    def _build_tokens(self, user: User) -> Token:
        access = create_access_token(
            subject=str(user.id),
            extra_claims={"role": user.role, "email": user.email},
        )
        refresh = create_refresh_token(subject=str(user.email))
        return Token(access_token=access, refresh_token=refresh)
