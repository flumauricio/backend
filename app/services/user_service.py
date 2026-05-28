import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.core.logging import get_logger
from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate

logger = get_logger(__name__)


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── Finders ──────────────────────────────────────────────────────────────

    async def get_by_id(self, user_id: uuid.UUID) -> User:
        """Returns User or raises 404. Use in user-facing endpoints."""
        user = await self.get_by_id_or_none(user_id)
        if user is None:
            raise NotFoundException("User")
        return user

    async def get_by_id_or_none(self, user_id: uuid.UUID) -> User | None:
        """Returns User or None. Use internally (e.g. auth) to avoid 404 leaks."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    # ─── List / count ─────────────────────────────────────────────────────────

    async def list_paginated(
        self,
        skip: int = 0,
        limit: int = 50,
        *,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> list[User]:
        """
        Returns a page of users.
        Optional filters: role, is_active.
        """
        stmt = select(User).order_by(User.created_at.desc())

        if role is not None:
            stmt = stmt.where(User.role == role)
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)

        stmt = stmt.offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        *,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(User)

        if role is not None:
            stmt = stmt.where(User.role == role)
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)

        result = await self.db.execute(stmt)
        return result.scalar_one()

    # ─── Mutations ────────────────────────────────────────────────────────────

    async def create(self, payload: UserCreate, role: str = "user") -> User:
        if await self.get_by_email(payload.email):
            raise ConflictException("Email already registered.")

        user = User(
            email=payload.email,
            hashed_password=get_password_hash(payload.password),
            full_name=payload.full_name,
            role=role,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        logger.info("User created", user_id=str(user.id), email=user.email, role=role)
        return user

    async def authenticate(self, email: str, password: str) -> User | None:
        user = await self.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            return None
        return user

    async def update(self, user: User, payload: UserUpdate) -> User:
        """
        Applies any set fields from the payload to the user.
        Works for both UserUpdate (self-service) and UserUpdateAdmin (admin).
        """
        update_data = payload.model_dump(exclude_unset=True)

        if "password" in update_data:
            update_data["hashed_password"] = get_password_hash(
                update_data.pop("password")
            )

        for field, value in update_data.items():
            setattr(user, field, value)

        await self.db.flush()
        await self.db.refresh(user)
        logger.info("User updated", user_id=str(user.id), fields=list(update_data.keys()))
        return user

    async def deactivate(self, user: User) -> User:
        user.is_active = False
        await self.db.flush()
        await self.db.refresh(user)
        logger.info("User deactivated", user_id=str(user.id))
        return user

    async def reactivate(self, user: User) -> User:
        user.is_active = True
        await self.db.flush()
        await self.db.refresh(user)
        logger.info("User reactivated", user_id=str(user.id))
        return user
