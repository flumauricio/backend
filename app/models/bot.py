import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# ─── Status values ────────────────────────────────────────────────────────────
# Expanded in V2: starting / stopping added for async lifecycle transitions.
BOT_STATUSES = ("draft", "stopped", "starting", "running", "stopping", "error")

# ─── Language presets (informational, not enforced at DB level) ───────────────
BOT_LANGUAGES = ("javascript", "typescript", "python")


class Bot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Bot instance — V2.

    Lifecycle:
        draft ──► stopped ──► starting ──► running ──► stopping ──► stopped
                                                  └──────────────► error
    """
    __tablename__ = "bots"

    # ─── Core ─────────────────────────────────────────────────────────────────
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

    # ─── V2: Runtime configuration ────────────────────────────────────────────
    language: Mapped[str] = mapped_column(
        String(50), nullable=False, default="javascript"
    )
    runtime_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    main_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    repository_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Stored in plaintext for now — encrypt at rest in V3 (e.g. via Fernet).
    # NEVER returned in public API responses (masked in BotRead).
    discord_token: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Arbitrary key/value pairs: {"KEY": "value", ...}
    env_vars: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ─── V2: Lifecycle timestamps ─────────────────────────────────────────────
    last_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_stopped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ─── Relationships ─────────────────────────────────────────────────────────
    owner: Mapped["User"] = relationship(  # noqa: F821
        "User",
        lazy="select",
        foreign_keys=[owner_id],
    )

    def __repr__(self) -> str:
        return f"<Bot id={self.id} name={self.name!r} status={self.status}>"
