import uuid

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserLimits(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Per-user limit overrides.

    Resolution order (highest priority first):
        1. Non-null value on this row  → custom override
        2. plan_id set → inherit from Plan
        3. Neither     → caller falls back to a hardcoded default / Free plan

    This table has at most one row per user (enforced by the unique constraint).
    """
    __tablename__ = "user_limits"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_limits_user_id"),
    )

    # ─── FK ───────────────────────────────────────────────────────────────────
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ─── Per-user overrides (null = inherit from plan) ────────────────────────
    cloud_storage_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_bots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_ram_per_bot_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_storage_per_bot_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ─── Relationships ────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", lazy="select")  # noqa: F821
    plan: Mapped["Plan | None"] = relationship(  # noqa: F821
        "Plan", back_populates="user_limits", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<UserLimits user_id={self.user_id} plan_id={self.plan_id}>"
