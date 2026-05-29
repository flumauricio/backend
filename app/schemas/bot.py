import uuid
from datetime import datetime
from math import ceil
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ─── Status type ──────────────────────────────────────────────────────────────
BotStatus = Literal["draft", "stopped", "starting", "running", "stopping", "error"]
BotLanguage = Literal["javascript", "typescript", "python"]

# Human-readable PT-BR labels (used by frontend, kept here as single source)
STATUS_LABELS_PTBR: dict[str, str] = {
    "draft":    "Rascunho",
    "stopped":  "Parado",
    "starting": "Iniciando",
    "running":  "Rodando",
    "stopping": "Parando",
    "error":    "Erro",
}


# ─── Request ──────────────────────────────────────────────────────────────────

class BotCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=1000)
    language: BotLanguage = "javascript"
    runtime_version: str | None = Field(None, max_length=50)
    main_file: str | None = Field(None, max_length=255)
    repository_url: str | None = Field(None, max_length=500)
    discord_token: str | None = Field(None, max_length=200)
    env_vars: dict[str, str] | None = None


class BotUpdate(BaseModel):
    """All fields optional — PATCH semantics."""
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=1000)
    language: BotLanguage | None = None
    runtime_version: str | None = Field(None, max_length=50)
    main_file: str | None = Field(None, max_length=255)
    repository_url: str | None = Field(None, max_length=500)
    discord_token: str | None = Field(None, max_length=200)
    env_vars: dict[str, str] | None = None
    # Status is intentionally NOT in BotUpdate for regular users.
    # Status transitions happen via dedicated action endpoints.
    # Admins can force status via BotAdminUpdate below.


class BotAdminUpdate(BotUpdate):
    """Admin-only update — allows forcing status."""
    status: BotStatus | None = None


# ─── Response ─────────────────────────────────────────────────────────────────

def _mask_token(token: str | None) -> str | None:
    """Return last 4 chars masked: ••••••••ABCD, or None."""
    if not token:
        return None
    visible = token[-4:] if len(token) >= 4 else token
    return f"{'•' * (len(token) - len(visible))}{visible}"


class BotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    status: str
    language: str
    runtime_version: str | None
    main_file: str | None
    repository_url: str | None
    # discord_token NEVER returned raw — always masked
    discord_token_masked: str | None = None
    env_vars: dict | None
    last_started_at: datetime | None
    last_stopped_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_masked(cls, bot) -> "BotRead":
        """Build BotRead from ORM, masking discord_token."""
        data = {
            "id": bot.id,
            "owner_id": bot.owner_id,
            "name": bot.name,
            "description": bot.description,
            "status": bot.status,
            "language": bot.language,
            "runtime_version": bot.runtime_version,
            "main_file": bot.main_file,
            "repository_url": bot.repository_url,
            "discord_token_masked": _mask_token(bot.discord_token),
            "env_vars": bot.env_vars,
            "last_started_at": bot.last_started_at,
            "last_stopped_at": bot.last_stopped_at,
            "created_at": bot.created_at,
            "updated_at": bot.updated_at,
        }
        return cls(**data)


# ─── Action responses ─────────────────────────────────────────────────────────

class BotActionResponse(BaseModel):
    """Returned by start / stop / restart endpoints."""
    bot_id: uuid.UUID
    action: str
    previous_status: str
    current_status: str
    message: str
    timestamp: datetime


class BotLogsResponse(BaseModel):
    """Simulated log output for V2."""
    bot_id: uuid.UUID
    bot_name: str
    lines: list[str]
    generated_at: datetime
    note: str = "Simulated logs — real execution not implemented yet."


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
        return cls(
            items=[BotRead.from_orm_masked(b) for b in items],
            total=total,
            page=page,
            size=limit,
            pages=pages,
        )
