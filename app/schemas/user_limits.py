import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.plan import PlanRead


# ─── Request ──────────────────────────────────────────────────────────────────

class UserLimitsUpdate(BaseModel):
    """
    Admin-facing PATCH body.
    Set a field to an integer to override it for this user.
    Set a field to null to clear the override (falls back to the plan).
    Set plan_id to assign or change a plan.
    """
    plan_id: uuid.UUID | None = Field(
        default=...,  # required key, but value can be null
        description="Assign a plan. Pass null to detach from any plan.",
    )
    cloud_storage_mb: int | None = Field(None, gt=0)
    max_bots: int | None = Field(None, gt=0)
    max_ram_per_bot_mb: int | None = Field(None, gt=0)
    max_storage_per_bot_mb: int | None = Field(None, gt=0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "plan_id": "550e8400-e29b-41d4-a716-446655440000",
                "max_bots": 10,
                "cloud_storage_mb": None,
                "max_ram_per_bot_mb": None,
                "max_storage_per_bot_mb": None,
            }
        }
    )


# ─── Response ─────────────────────────────────────────────────────────────────

class UserLimitsRead(BaseModel):
    """Raw UserLimits row — shows what is stored (overrides + plan ref)."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    plan_id: uuid.UUID | None
    plan: PlanRead | None

    cloud_storage_mb: int | None
    max_bots: int | None
    max_ram_per_bot_mb: int | None
    max_storage_per_bot_mb: int | None

    created_at: datetime
    updated_at: datetime


class EffectiveUserLimitsRead(BaseModel):
    """
    Resolved limits — what actually applies to this user after
    merging per-user overrides with the assigned plan.
    Clients should use this for enforcement decisions.
    """
    user_id: uuid.UUID
    plan_id: uuid.UUID | None
    plan_name: str | None

    # Resolved values — never null once resolved (caller guarantees a default)
    cloud_storage_mb: int
    max_bots: int
    max_ram_per_bot_mb: int
    max_storage_per_bot_mb: int

    # Indicates where each value came from (useful for debug / admin UI)
    sources: dict[str, str] = Field(
        default_factory=dict,
        description="Maps field name to 'override' | 'plan' | 'default'",
        examples=[
            {
                "cloud_storage_mb": "plan",
                "max_bots": "override",
                "max_ram_per_bot_mb": "default",
                "max_storage_per_bot_mb": "plan",
            }
        ],
    )
