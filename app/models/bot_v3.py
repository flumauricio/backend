"""
Bots V3 — deployment, env vars, and persistent log models.

These tables prepare the execution layer without implementing real Docker yet.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# ─── Enum values ──────────────────────────────────────────────────────────────

DEPLOYMENT_STATUSES = ("pending", "prepared", "deploying", "deployed", "failed", "stopped")
DEPLOYMENT_SOURCE_TYPES = ("manual", "git", "upload")
LOG_LEVELS = ("info", "warning", "error", "debug")


# ─── BotDeployment ────────────────────────────────────────────────────────────

class BotDeployment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Represents one deployment attempt for a bot.

    V3: status stays at 'prepared' — real execution comes in V4.

    Lifecycle (future):
        pending → prepared → deploying → deployed → stopped
                                       └──────────► failed
    """
    __tablename__ = "bot_deployments"

    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        SAEnum(*DEPLOYMENT_STATUSES, name="deployment_status"),
        nullable=False,
        default="pending",
        index=True,
    )
    source_type: Mapped[str] = mapped_column(
        SAEnum(*DEPLOYMENT_SOURCE_TYPES, name="deployment_source_type"),
        nullable=False,
        default="manual",
    )
    source_url: Mapped[str | None]    = mapped_column(String(500), nullable=True)
    commit_hash: Mapped[str | None]   = mapped_column(String(100), nullable=True)
    runtime: Mapped[str | None]       = mapped_column(String(100), nullable=True)
    main_file: Mapped[str | None]     = mapped_column(String(255), nullable=True)
    storage_path: Mapped[str | None]  = mapped_column(String(500), nullable=True)
    message: Mapped[str | None]       = mapped_column(Text, nullable=True)

    deployed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stopped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ─── Relationships ────────────────────────────────────────────────────────
    bot: Mapped["Bot"] = relationship(  # noqa: F821
        "Bot", lazy="select", foreign_keys=[bot_id]
    )
    logs: Mapped[list["BotLog"]] = relationship(
        "BotLog",
        back_populates="deployment",
        cascade="all, delete-orphan",
        lazy="select",
        foreign_keys="BotLog.deployment_id",
    )

    def __repr__(self) -> str:
        return f"<BotDeployment id={self.id} bot_id={self.bot_id} status={self.status}>"


# ─── BotEnvVar ────────────────────────────────────────────────────────────────

class BotEnvVar(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Per-bot environment variable.

    is_secret=True  → value is NEVER returned in API responses (masked).
    is_secret=False → value returned as-is.

    Note: V3 stores values in plaintext. Encryption at rest comes in V4.
    """
    __tablename__ = "bot_env_vars"

    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str]   = mapped_column(String(200), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ─── Relationships ────────────────────────────────────────────────────────
    bot: Mapped["Bot"] = relationship(  # noqa: F821
        "Bot", lazy="select", foreign_keys=[bot_id]
    )

    def __repr__(self) -> str:
        return f"<BotEnvVar bot_id={self.bot_id} key={self.key!r} secret={self.is_secret}>"


# ─── BotLog ───────────────────────────────────────────────────────────────────

class BotLog(UUIDPrimaryKeyMixin, Base):
    """
    Persistent log entry for a bot (and optionally a deployment).

    Does NOT use TimestampMixin — only created_at is needed,
    log entries are immutable once written.
    """
    __tablename__ = "bot_logs"

    # created_at as simple datetime, no updated_at needed
    from sqlalchemy import func
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bot_deployments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    level: Mapped[str] = mapped_column(
        SAEnum(*LOG_LEVELS, name="bot_log_level"),
        nullable=False,
        default="info",
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # ─── Relationships ────────────────────────────────────────────────────────
    bot: Mapped["Bot"] = relationship(  # noqa: F821
        "Bot", lazy="select", foreign_keys=[bot_id]
    )
    deployment: Mapped["BotDeployment | None"] = relationship(
        "BotDeployment",
        back_populates="logs",
        lazy="select",
        foreign_keys=[deployment_id],
    )

    def __repr__(self) -> str:
        return f"<BotLog bot_id={self.bot_id} level={self.level} msg={self.message[:40]!r}>"
