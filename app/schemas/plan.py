import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ─── Request ──────────────────────────────────────────────────────────────────

class PlanCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=1000)

    # Zero is valid: the admin may intentionally make the Free plan very
    # restrictive, including disabling a resource by setting its limit to 0.
    cloud_storage_mb: int = Field(..., ge=0, description="Total cloud storage in MB")
    max_bots: int = Field(..., ge=0, description="Maximum number of bots")
    max_ram_per_bot_mb: int = Field(..., ge=0, description="RAM cap per bot in MB")
    max_storage_per_bot_mb: int = Field(..., ge=0, description="Storage cap per bot in MB")

    is_active: bool = True


class PlanUpdate(BaseModel):
    """All fields optional — PATCH semantics."""
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=1000)

    cloud_storage_mb: int | None = Field(None, ge=0)
    max_bots: int | None = Field(None, ge=0)
    max_ram_per_bot_mb: int | None = Field(None, ge=0)
    max_storage_per_bot_mb: int | None = Field(None, ge=0)

    is_active: bool | None = None


# ─── Response ─────────────────────────────────────────────────────────────────

class PlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    cloud_storage_mb: int
    max_bots: int
    max_ram_per_bot_mb: int
    max_storage_per_bot_mb: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
