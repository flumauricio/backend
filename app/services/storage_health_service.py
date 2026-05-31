"""
StorageHealthService
────────────────────
Detects real disk usage for each volume using shutil.disk_usage().

Design principles
─────────────────
1. NEVER raises an exception that crashes the API.
   Every failure is caught, logged, and stored as health_status=error/offline.
2. Works asynchronously — disk I/O runs in a thread-pool via asyncio.to_thread()
   so the event loop is not blocked.
3. Completely isolated from bot execution logic — a sick volume does not
   affect volumes that are healthy.

Health status transitions
─────────────────────────
  Path missing / OSError(ENOENT)     → offline  "Caminho não encontrado"
  PermissionError                    → error    "Sem permissão para acessar o volume"
  detected_free_mb < reserve_total   → warning  "Espaço disponível abaixo da reserva"
  detected_free_mb >= reserve_total  → online   "Volume operacional"
  Any unexpected exception           → error    "<exception type>: <message>"

What is NOT implemented here (V3+)
───────────────────────────────────
  - lsblk / blkid auto-discovery
  - mount / umount automation
  - mkfs formatting
  - SMART health polling
  - rebalancing workspace data between volumes
"""
import asyncio
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.storage import (
    HEALTH_ERROR, HEALTH_OFFLINE, HEALTH_ONLINE, HEALTH_WARNING,
    StorageVolume,
)
from app.schemas.storage import StorageVolumeRead

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sync_check_path(mount_path: str) -> dict:
    """
    Runs in a thread pool — never called directly from async code.
    Returns a plain dict with detection results.
    """
    path = Path(mount_path)

    # ── Path existence ────────────────────────────────────────────────────────
    try:
        exists = path.exists()
    except PermissionError:
        return {
            "health_status":    HEALTH_ERROR,
            "health_message":   "Sem permissão para verificar o caminho do volume",
            "detected_total_mb": None,
            "detected_free_mb":  None,
            "auto_detected":     False,
        }
    except OSError as exc:
        return {
            "health_status":    HEALTH_ERROR,
            "health_message":   f"Erro ao acessar caminho: {exc}",
            "detected_total_mb": None,
            "detected_free_mb":  None,
            "auto_detected":     False,
        }

    if not exists:
        return {
            "health_status":    HEALTH_OFFLINE,
            "health_message":   "Caminho não encontrado — volume pode estar desmontado",
            "detected_total_mb": None,
            "detected_free_mb":  None,
            "auto_detected":     False,
        }

    # ── Disk usage ────────────────────────────────────────────────────────────
    try:
        usage = shutil.disk_usage(mount_path)
        total_mb = usage.total // (1024 * 1024)
        free_mb  = usage.free  // (1024 * 1024)
        return {
            "health_status":     HEALTH_ONLINE,   # refined below by caller
            "health_message":    None,
            "detected_total_mb": total_mb,
            "detected_free_mb":  free_mb,
            "auto_detected":     True,
        }
    except PermissionError:
        return {
            "health_status":    HEALTH_ERROR,
            "health_message":   "Sem permissão para acessar o volume",
            "detected_total_mb": None,
            "detected_free_mb":  None,
            "auto_detected":     False,
        }
    except OSError as exc:
        return {
            "health_status":    HEALTH_ERROR,
            "health_message":   f"Erro de I/O ao ler disco: {exc}",
            "detected_total_mb": None,
            "detected_free_mb":  None,
            "auto_detected":     False,
        }
    except Exception as exc:
        return {
            "health_status":    HEALTH_ERROR,
            "health_message":   f"{type(exc).__name__}: {exc}",
            "detected_total_mb": None,
            "detected_free_mb":  None,
            "auto_detected":     False,
        }


class StorageHealthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── Check one volume ─────────────────────────────────────────────────────

    async def check_volume_health(self, volume: StorageVolume) -> StorageVolumeRead:
        """
        Run health check for a single volume.
        Updates the volume row in-place and returns the updated schema.
        Never raises — all errors are stored in health_status/health_message.
        """
        try:
            result = await asyncio.to_thread(_sync_check_path, volume.mount_path)
        except Exception as exc:
            # to_thread itself failed somehow — extremely unlikely
            logger.error(
                "StorageHealthService: to_thread failed",
                volume_id=str(volume.id),
                error=str(exc),
            )
            result = {
                "health_status":    HEALTH_ERROR,
                "health_message":   f"Falha interna ao verificar volume: {exc}",
                "detected_total_mb": None,
                "detected_free_mb":  None,
                "auto_detected":     False,
            }

        # Apply disk detection results to the ORM object
        volume.detected_total_mb = result["detected_total_mb"]
        volume.detected_free_mb  = result["detected_free_mb"]
        volume.auto_detected     = result["auto_detected"]

        # Refine health: if we got disk data, check reserves
        if result["health_status"] == HEALTH_ONLINE and result["detected_free_mb"] is not None:
            volume.health_status, volume.health_message = self._evaluate_space(volume)
        else:
            volume.health_status  = result["health_status"]
            volume.health_message = result["health_message"]

        volume.last_health_check_at = _now()

        await self.db.flush()
        await self.db.refresh(volume)

        logger.info(
            "Volume health checked",
            volume_id=str(volume.id),
            name=volume.name,
            status=volume.health_status,
            detected_total_mb=volume.detected_total_mb,
            detected_free_mb=volume.detected_free_mb,
        )

        return StorageVolumeRead.from_orm(volume)

    # ─── Check all volumes ────────────────────────────────────────────────────

    async def check_all_volumes(self) -> list[StorageVolumeRead]:
        """
        Run health check on every volume.
        Each volume is checked independently — failure in one does not abort others.
        """
        result = await self.db.execute(select(StorageVolume))
        volumes = list(result.scalars().all())

        results: list[StorageVolumeRead] = []
        for vol in volumes:
            try:
                read = await self.check_volume_health(vol)
                results.append(read)
            except Exception as exc:
                # Absolute last resort — should never happen since check_volume_health
                # already swallows all errors, but belt-and-suspenders here
                logger.error(
                    "StorageHealthService: unexpected error on volume",
                    volume_id=str(vol.id),
                    error=str(exc),
                )
        return results

    # ─── Space evaluation ─────────────────────────────────────────────────────

    @staticmethod
    def _evaluate_space(volume: StorageVolume) -> tuple[str, str | None]:
        """
        Given a volume with detected_free_mb populated, decide if it's
        online (enough free space) or warning (below reserves).
        Returns (health_status, health_message).
        """
        free_mb  = volume.detected_free_mb or 0
        total_mb = volume.detected_total_mb or 0

        system_reserve  = volume.reserved_system_mb or 0
        percent_reserve = int(total_mb * (volume.reserve_percent or 0) / 100)
        total_reserve   = system_reserve + percent_reserve

        if free_mb < total_reserve:
            msg = (
                f"Espaço livre ({free_mb} MB) abaixo da reserva de segurança "
                f"({total_reserve} MB = {system_reserve} MB fixo + {percent_reserve} MB percentual)"
            )
            return HEALTH_WARNING, msg

        avail = volume.available_for_allocation_mb
        if avail is not None and avail <= 0:
            return HEALTH_WARNING, "Sem espaço disponível para novos workspaces após reservas"

        return HEALTH_ONLINE, f"Volume operacional — {free_mb} MB livre detectado"
