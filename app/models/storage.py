"""
Storage V2 — Models

StorageVolume  : physical mount point with health monitoring fields
BotWorkspace   : logical reservation per bot (unchanged from V1)

V2 additions to StorageVolume:
  - detected_total_mb   : real disk size from shutil.disk_usage
  - detected_free_mb    : real free space from shutil.disk_usage
  - reserved_system_mb  : fixed safety reserve (default 1024 MB)
  - reserve_percent     : percentage safety reserve (default 10)
  - health_status       : string — unknown/online/offline/warning/error
  - health_message      : human-readable last check result
  - last_health_check_at: when health was last checked
  - auto_detected       : True when disk size was read automatically

health_status uses String(30), not a PG ENUM, to avoid migration conflicts.
"""
import uuid

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from datetime import datetime

# ─── Constants ────────────────────────────────────────────────────────────────

VOLUME_PURPOSES = ("bots", "cloud", "mixed")

HEALTH_UNKNOWN  = "unknown"
HEALTH_ONLINE   = "online"
HEALTH_OFFLINE  = "offline"
HEALTH_WARNING  = "warning"
HEALTH_ERROR    = "error"

# Volumes in these states are NOT eligible for new workspace allocation
HEALTH_BLOCKED  = {HEALTH_OFFLINE, HEALTH_ERROR}


# ─── StorageVolume ────────────────────────────────────────────────────────────

class StorageVolume(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Represents one storage device / mount point available to the platform.

    Space accounting
    ────────────────
    total_mb            : cap the admin wants to expose to ServerDronics
    detected_total_mb   : real physical size read from disk
    detected_free_mb    : real free space read from disk
    used_mb             : sum of BotWorkspace.allocated_mb (our reservation counter)
    reserved_system_mb  : fixed MB to keep free so OS/services don't starve
    reserve_percent     : additional % of total to keep free

    Available for allocation  =
        effective_total_mb        (min of total_mb and detected_total_mb, prefer lower)
        - used_mb                 (already reserved)
        - reserved_system_mb      (fixed system reserve)
        - percent_reserve_mb      (reserve_percent % of effective_total_mb)

    Selection order for new workspaces:
        1. is_active = True
        2. health_status NOT in ('offline', 'error')
        3. purpose in ('bots', 'mixed')
        4. available_for_allocation_mb >= requested_mb  (if known)
        5. lowest priority value
        6. most free detected space
    """
    __tablename__ = "storage_volumes"

    name:       Mapped[str] = mapped_column(String(200), nullable=False)
    mount_path: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)

    purpose: Mapped[str] = mapped_column(
        SAEnum(*VOLUME_PURPOSES, name="volume_purpose"),
        nullable=False,
        default="mixed",
    )

    # ── V1 space fields ───────────────────────────────────────────────────────
    # Admin-set capacity cap (None = no cap, use full disk)
    total_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Logical reservation counter (sum of workspace allocations)
    used_mb:  Mapped[int]        = mapped_column(Integer, nullable=False, default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority:  Mapped[int]  = mapped_column(Integer, nullable=False, default=100)

    # ── V2 detection fields ───────────────────────────────────────────────────
    detected_total_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detected_free_mb:  Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Safety reserves — defaults ensure the main disk is never filled
    reserved_system_mb: Mapped[int | None] = mapped_column(Integer, nullable=True, default=1024)
    reserve_percent:    Mapped[int | None] = mapped_column(Integer, nullable=True, default=10)

    # Health monitoring — String(30) avoids PG ENUM migration headaches
    health_status:       Mapped[str]            = mapped_column(String(30), nullable=False, default=HEALTH_UNKNOWN)
    health_message:      Mapped[str | None]      = mapped_column(Text, nullable=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # True once disk_usage auto-detected at least one successful reading
    auto_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ─── Relationships ────────────────────────────────────────────────────────
    workspaces: Mapped[list["BotWorkspace"]] = relationship(
        "BotWorkspace",
        back_populates="volume",
        cascade="all, delete-orphan",
        lazy="select",
    )

    # ─── Computed properties ──────────────────────────────────────────────────

    @property
    def effective_total_mb(self) -> int | None:
        """
        The capacity ceiling to use for allocation decisions.
        Takes the minimum of admin cap and detected size (both must be known).
        """
        caps = [c for c in (self.total_mb, self.detected_total_mb) if c is not None]
        return min(caps) if caps else None

    @property
    def free_mb(self) -> int | None:
        """V1 compat: capacity - used (admin cap only). None if unknown."""
        if self.total_mb is None:
            return None
        return max(0, self.total_mb - self.used_mb)

    @property
    def available_for_allocation_mb(self) -> int | None:
        """
        Space available to assign to new workspaces, after all reserves.
        Returns None if we can't determine capacity.
        """
        total = self.effective_total_mb
        if total is None:
            return None

        system_reserve  = self.reserved_system_mb or 0
        percent_reserve = int(total * (self.reserve_percent or 0) / 100)

        available = total - self.used_mb - system_reserve - percent_reserve
        return max(0, available)

    @property
    def is_healthy(self) -> bool:
        return self.health_status not in HEALTH_BLOCKED

    def __repr__(self) -> str:
        return (
            f"<StorageVolume id={self.id} name={self.name!r} "
            f"health={self.health_status} active={self.is_active}>"
        )


# ─── BotWorkspace ─────────────────────────────────────────────────────────────

class BotWorkspace(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Logical workspace reservation for a single bot inside a StorageVolume.
    Unchanged from V1 — health is tracked on the volume, not the workspace.
    """
    __tablename__ = "bot_workspaces"
    __table_args__ = (
        UniqueConstraint("bot_id", name="uq_bot_workspace_bot_id"),
    )

    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_volume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("storage_volumes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    relative_path: Mapped[str] = mapped_column(String(500), nullable=False)
    allocated_mb:  Mapped[int] = mapped_column(Integer, nullable=False)
    used_mb:       Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    bot:    Mapped["Bot"] = relationship(  # noqa: F821
        "Bot", lazy="select", foreign_keys=[bot_id]
    )
    volume: Mapped["StorageVolume"] = relationship(
        "StorageVolume",
        back_populates="workspaces",
        lazy="select",
    )

    @property
    def full_path(self) -> str:
        return f"{self.volume.mount_path}/{self.relative_path}"

    def __repr__(self) -> str:
        return (
            f"<BotWorkspace bot_id={self.bot_id} "
            f"volume_id={self.storage_volume_id} path={self.relative_path!r}>"
        )
