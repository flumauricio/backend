import uuid
from datetime import datetime
from math import ceil

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.rbac import Role


# ─── Base ─────────────────────────────────────────────────────────────────────

class UserBase(BaseModel):
    email: EmailStr
    full_name: str | None = Field(None, max_length=255)


# ─── Request ──────────────────────────────────────────────────────────────────

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)


class UserUpdate(BaseModel):
    """Fields a user can change about themselves."""
    full_name: str | None = Field(None, max_length=255)
    password: str | None = Field(None, min_length=8, max_length=128)


class UserUpdateAdmin(UserUpdate):
    """
    Superset of UserUpdate — additional fields only an admin may change.
    Inherits full_name and password from UserUpdate.
    """
    role: Role | None = None
    is_active: bool | None = None
    is_verified: bool | None = None

    @field_validator("role", mode="before")
    @classmethod
    def validate_role(cls, v):
        if v is None:
            return v
        try:
            return Role(v)
        except ValueError:
            valid = ", ".join(r.value for r in Role)
            raise ValueError(f"Invalid role '{v}'. Valid options: {valid}.")


# ─── Response ─────────────────────────────────────────────────────────────────

class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime


class UserReadPublic(BaseModel):
    """Minimal public-facing profile (no PII)."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str | None


# ─── Pagination ───────────────────────────────────────────────────────────────

class UserPage(BaseModel):
    """Paginated list of users."""
    items: list[UserRead]
    total: int
    page: int
    size: int
    pages: int

    @classmethod
    def build(cls, items: list, total: int, skip: int, limit: int) -> "UserPage":
        page = (skip // limit) + 1 if limit else 1
        pages = ceil(total / limit) if limit else 1
        return cls(items=items, total=total, page=page, size=limit, pages=pages)
