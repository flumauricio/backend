"""
Pydantic schemas for Bots V3:
  - BotDeployment (prepare / read / list)
  - BotEnvVar     (create / update / read — secrets masked)
  - BotLog        (read only)
"""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ─── Deployment ───────────────────────────────────────────────────────────────

DeploymentStatus     = Literal["pending", "prepared", "deploying", "deployed", "failed", "stopped"]
DeploymentSourceType = Literal["manual", "git", "upload"]


class BotDeploymentCreate(BaseModel):
    """Body accepted by POST /bots/{bot_id}/deployments/prepare."""
    source_type:  DeploymentSourceType = "manual"
    source_url:   str | None = Field(None, max_length=500)
    commit_hash:  str | None = Field(None, max_length=100)
    runtime:      str | None = Field(None, max_length=100)
    main_file:    str | None = Field(None, max_length=255)
    storage_path: str | None = Field(None, max_length=500)


class BotDeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:           uuid.UUID
    bot_id:       uuid.UUID
    status:       str
    source_type:  str
    source_url:   str | None
    commit_hash:  str | None
    runtime:      str | None
    main_file:    str | None
    storage_path: str | None
    message:      str | None
    deployed_at:  datetime | None
    stopped_at:   datetime | None
    created_at:   datetime
    updated_at:   datetime


class BotPrepareResponse(BaseModel):
    """Returned by prepare endpoint — wraps deployment + human message."""
    deployment:  BotDeploymentRead
    ok:          bool = True
    detail:      str


# ─── Env Vars ─────────────────────────────────────────────────────────────────

_SECRET_MASK = "••••••••"


class BotEnvVarCreate(BaseModel):
    key:       str  = Field(..., min_length=1, max_length=200)
    value:     str  = Field(..., max_length=4096)
    is_secret: bool = True


class BotEnvVarUpdate(BaseModel):
    """PATCH — all fields optional."""
    key:       str | None  = Field(None, min_length=1, max_length=200)
    value:     str | None  = Field(None, max_length=4096)
    is_secret: bool | None = None


class BotEnvVarRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:           uuid.UUID
    bot_id:       uuid.UUID
    key:          str
    value_masked: str        # NEVER returns raw value when is_secret=True
    is_secret:    bool
    created_at:   datetime
    updated_at:   datetime

    @classmethod
    def from_orm_masked(cls, ev) -> "BotEnvVarRead":
        return cls(
            id=ev.id,
            bot_id=ev.bot_id,
            key=ev.key,
            value_masked=_SECRET_MASK if ev.is_secret else ev.value,
            is_secret=ev.is_secret,
            created_at=ev.created_at,
            updated_at=ev.updated_at,
        )


# ─── Bot Logs ────────────────────────────────────────────────────────────────

BotLogLevel = Literal["info", "warning", "error", "debug"]


class BotLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:            uuid.UUID
    bot_id:        uuid.UUID
    deployment_id: uuid.UUID | None
    level:         str
    message:       str
    created_at:    datetime
