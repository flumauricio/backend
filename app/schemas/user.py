import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ─── Base ────────────────────────────────────────────────────────────────────

class UserBase(BaseModel):
    email: EmailStr
    full_name: str | None = Field(None, max_length=255)


# ─── Request ─────────────────────────────────────────────────────────────────

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, max_length=255)
    password: str | None = Field(None, min_length=8, max_length=128)


class UserUpdateAdmin(UserUpdate):
    """Admin-only fields."""
    role: str | None = None
    is_active: bool | None = None
    is_verified: bool | None = None


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
    """Minimal public profile."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str | None
