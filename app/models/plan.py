from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Plan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Defines a named tier of resource limits (e.g. Free, Starter, Pro).
    All limit fields are required on a plan — nullable overrides live on UserLimits.
    """
    __tablename__ = "plans"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ─── Resource limits ──────────────────────────────────────────────────────
    cloud_storage_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    max_bots: Mapped[int] = mapped_column(Integer, nullable=False)
    max_ram_per_bot_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    max_storage_per_bot_mb: Mapped[int] = mapped_column(Integer, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ─── Relationships ────────────────────────────────────────────────────────
    user_limits: Mapped[list["UserLimits"]] = relationship(  # noqa: F821
        "UserLimits", back_populates="plan", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Plan id={self.id} name={self.name!r}>"
