import uuid

from sqlalchemy import Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# ─── Status enum ──────────────────────────────────────────────────────────────
# Defined as a plain string-set so the DB column uses a native PG ENUM,
# while Python code can compare against the string literals directly.
BOT_STATUSES = ("draft", "stopped", "running", "error")


class Bot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Represents a user's bot instance.

    Lifecycle:  draft → stopped ↔ running
                               ↘ error
    """
    __tablename__ = "bots"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        SAEnum(*BOT_STATUSES, name="bot_status"),
        nullable=False,
        default="draft",
        index=True,
    )

    # ─── Relationships ────────────────────────────────────────────────────────
    # Back-populate intentionally omitted from User model to avoid touching
    # the existing user.py file.  Access owner via owner_id when needed.
    owner: Mapped["User"] = relationship(  # noqa: F821
        "User",
        lazy="select",
        foreign_keys=[owner_id],
    )

    def __repr__(self) -> str:
        return f"<Bot id={self.id} name={self.name!r} status={self.status}>"
