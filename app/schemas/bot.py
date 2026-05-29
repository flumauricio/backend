import uuid
from datetime import datetime
from math import ceil
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BotStatus = Literal["draft", "stopped", "running", "error"]


# ─── Request ──────────────────────────────────────────────────────────────────

class BotCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Bot display name")
    description: str | None = Field(None, max_length=1000)


class BotUpdate(BaseModel):
    """All fields optional — PATCH semantics."""
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=1000)
    # Status is exposed here so admins can manually correct stuck bots.
    # Normal start/stop flows will be handled by dedicated endpoints in V2.
    status: BotStatus | None = None


# ─── Response ─────────────────────────────────────────────────────────────────

class BotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


# ─── Paginated list ───────────────────────────────────────────────────────────

class BotListResponse(BaseModel):
    items: list[BotRead]
    total: int
    page: int
    size: int
    pages: int

    @classmethod
    def build(
        cls, items: list, total: int, skip: int, limit: int
    ) -> "BotListResponse":
        page = (skip // limit) + 1 if limit else 1
        pages = ceil(total / limit) if limit else 1
        return cls(items=items, total=total, page=page, size=limit, pages=pages)
