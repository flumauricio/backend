"""
Schemas — Storage V2

StorageVolume  : CRUD + health fields (admin)
BotWorkspace   : prepare + read — now includes volume health_status
StorageSummary : platform-wide aggregate
"""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ─── Purpose / Health labels ──────────────────────────────────────────────────

VolumePurpose = Literal["bots", "cloud", "mixed"]
VolumeHealth  = Literal["unknown", "online", "offline", "warning", "error"]

_PURPOSE_LABEL: dict[str, str] = {
    "bots":  "Bots",
    "cloud": "Cloud",
    "mixed": "Misto",
}
_HEALTH_LABEL: dict[str, str] = {
    "unknown": "Desconhecido",
    "online":  "Online",
    "offline": "Offline",
    "warning": "Atenção",
    "error":   "Erro",
}


# ─── StorageVolume ────────────────────────────────────────────────────────────

class StorageVolumeCreate(BaseModel):
    name:               str           = Field(..., min_length=1, max_length=200)
    mount_path:         str           = Field(..., min_length=1, max_length=500)
    purpose:            VolumePurpose = "mixed"
    total_mb:           int | None    = Field(None, ge=1)
    is_active:          bool          = True
    priority:           int           = Field(100, ge=1, le=9999)
    # V2 additions
    reserved_system_mb: int | None    = Field(1024, ge=0)
    reserve_percent:    int | None    = Field(10,   ge=0, le=100)


class StorageVolumeUpdate(BaseModel):
    """PATCH — all fields optional."""
    name:               str | None           = Field(None, min_length=1, max_length=200)
    mount_path:         str | None           = Field(None, min_length=1, max_length=500)
    purpose:            VolumePurpose | None = None
    total_mb:           int | None           = Field(None, ge=1)
    is_active:          bool | None          = None
    priority:           int | None           = Field(None, ge=1, le=9999)
    # V2 additions
    reserved_system_mb: int | None           = Field(None, ge=0)
    reserve_percent:    int | None           = Field(None, ge=0, le=100)


class StorageVolumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:          uuid.UUID
    name:        str
    mount_path:  str
    purpose:     str
    purpose_label: str = ""

    # V1 space fields
    total_mb:    int | None
    used_mb:     int
    free_mb:     int | None = None

    is_active:   bool
    priority:    int

    # V2 detection + health
    detected_total_mb:    int | None = None
    detected_free_mb:     int | None = None
    reserved_system_mb:   int | None = None
    reserve_percent:      int | None = None
    available_for_allocation_mb: int | None = None

    health_status:        str       = "unknown"
    health_status_label:  str       = "Desconhecido"
    health_message:       str | None = None
    last_health_check_at: datetime | None = None
    auto_detected:        bool      = False

    created_at:  datetime
    updated_at:  datetime

    @classmethod
    def from_orm(cls, v) -> "StorageVolumeRead":
        return cls(
            id=v.id,
            name=v.name,
            mount_path=v.mount_path,
            purpose=v.purpose,
            purpose_label=_PURPOSE_LABEL.get(v.purpose, v.purpose),
            total_mb=v.total_mb,
            used_mb=v.used_mb,
            free_mb=v.free_mb,
            is_active=v.is_active,
            priority=v.priority,
            # V2
            detected_total_mb=v.detected_total_mb,
            detected_free_mb=v.detected_free_mb,
            reserved_system_mb=v.reserved_system_mb,
            reserve_percent=v.reserve_percent,
            available_for_allocation_mb=v.available_for_allocation_mb,
            health_status=v.health_status or "unknown",
            health_status_label=_HEALTH_LABEL.get(v.health_status or "unknown", v.health_status or "unknown"),
            health_message=v.health_message,
            last_health_check_at=v.last_health_check_at,
            auto_detected=v.auto_detected or False,
            created_at=v.created_at,
            updated_at=v.updated_at,
        )


# ─── BotWorkspace ─────────────────────────────────────────────────────────────

class BotWorkspaceCreate(BaseModel):
    storage_volume_id: uuid.UUID | None = None
    allocated_mb:      int | None       = Field(None, ge=1)


class BotWorkspaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                uuid.UUID
    bot_id:            uuid.UUID
    storage_volume_id: uuid.UUID

    volume_name:    str  = ""
    volume_path:    str  = ""
    volume_active:  bool = True
    # V2: surface volume health so frontend can warn user
    volume_health:  str  = "unknown"
    volume_health_label: str = "Desconhecido"

    relative_path: str
    full_path:     str = ""
    allocated_mb:  int
    used_mb:       int
    created_at:    datetime
    updated_at:    datetime

    @classmethod
    def from_orm(cls, ws) -> "BotWorkspaceRead":
        vol = ws.volume
        health = (vol.health_status or "unknown") if vol else "unknown"
        return cls(
            id=ws.id,
            bot_id=ws.bot_id,
            storage_volume_id=ws.storage_volume_id,
            volume_name=vol.name if vol else "",
            volume_path=vol.mount_path if vol else "",
            volume_active=vol.is_active if vol else False,
            volume_health=health,
            volume_health_label=_HEALTH_LABEL.get(health, health),
            relative_path=ws.relative_path,
            full_path=f"{vol.mount_path}/{ws.relative_path}" if vol else ws.relative_path,
            allocated_mb=ws.allocated_mb,
            used_mb=ws.used_mb,
            created_at=ws.created_at,
            updated_at=ws.updated_at,
        )


# ─── Storage Summary ──────────────────────────────────────────────────────────

class StorageSummaryRead(BaseModel):
    """Platform-wide storage aggregate — GET /api/v1/storage/summary"""
    volumes_total:   int
    volumes_online:  int
    volumes_offline: int
    volumes_warning: int
    volumes_error:   int
    volumes_unknown: int

    # MB totals (None = not enough data to compute)
    capacity_registered_mb:      int | None  # sum of total_mb where set
    detected_total_mb:           int | None  # sum of detected_total_mb
    detected_free_mb:            int | None  # sum of detected_free_mb
    reserved_for_bots_mb:        int         # sum of used_mb (workspace reservations)
    available_for_allocation_mb: int | None  # sum of available_for_allocation_mb
