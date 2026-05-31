"""
BotEnvVarService
────────────────
CRUD for per-bot environment variables with transparent encryption.

Encryption contract
───────────────────
  Write (create / update):
    - is_secret=True  → value is encrypted with Fernet before DB insert/update
    - is_secret=False → value is stored as plaintext

  Read (list / get):
    - is_secret=True  → value_masked = "••••••••"  (raw value NEVER returned)
    - is_secret=False → value_masked = plaintext value as stored

  The raw DB value is never surfaced in API responses — it only lives in the
  ORM object that stays inside this service.

Legacy compatibility
────────────────────
  Rows written before encryption was introduced contain plaintext secrets.
  decrypt_secret() detects this transparently (see app/core/crypto.py).
  mask_secret() works the same regardless — it always returns "••••••••".

  When a secret row is updated via PATCH, the new value is always encrypted,
  migrating that row to the encrypted format automatically.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_secret, encrypt_secret, mask_secret
from app.core.exceptions import ConflictException, NotFoundException
from app.core.logging import get_logger
from app.models.bot_v3 import BotEnvVar
from app.schemas.bot_v3 import BotEnvVarCreate, BotEnvVarRead, BotEnvVarUpdate

logger = get_logger(__name__)


class BotEnvVarService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── Internal: build read schema (always masked) ──────────────────────────

    @staticmethod
    def _to_read(ev: BotEnvVar) -> BotEnvVarRead:
        """
        Convert ORM row → BotEnvVarRead.

        - is_secret=True  → value_masked = "••••••••"
        - is_secret=False → value_masked = raw plaintext (no decrypt needed)

        We intentionally do NOT call decrypt_secret() here — the masked read
        schema never needs the real value.
        """
        return BotEnvVarRead(
            id=ev.id,
            bot_id=ev.bot_id,
            key=ev.key,
            value_masked=mask_secret(ev.value) if ev.is_secret else ev.value,
            is_secret=ev.is_secret,
            created_at=ev.created_at,
            updated_at=ev.updated_at,
        )

    # ─── Internal: prepare value for storage ──────────────────────────────────

    @staticmethod
    def _prepare_value(value: str, is_secret: bool) -> str:
        """
        Return the value that should be written to the DB column.

          is_secret=True  → encrypt (Fernet token string)
          is_secret=False → plaintext as-is
        """
        if is_secret:
            return encrypt_secret(value)
        return value

    # ─── List ─────────────────────────────────────────────────────────────────

    async def list_for_bot(self, bot_id: uuid.UUID) -> list[BotEnvVarRead]:
        stmt = (
            select(BotEnvVar)
            .where(BotEnvVar.bot_id == bot_id)
            .order_by(BotEnvVar.created_at.asc())
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return [self._to_read(r) for r in rows]

    # ─── Create ───────────────────────────────────────────────────────────────

    async def create(
        self,
        bot_id: uuid.UUID,
        payload: BotEnvVarCreate,
    ) -> BotEnvVarRead:
        # Prevent duplicate keys per bot
        existing = await self.db.execute(
            select(BotEnvVar).where(
                BotEnvVar.bot_id == bot_id,
                BotEnvVar.key == payload.key,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictException(
                f"Variável '{payload.key}' já existe para este bot. "
                "Use PATCH para atualizar."
            )

        stored_value = self._prepare_value(payload.value, payload.is_secret)

        ev = BotEnvVar(
            bot_id=bot_id,
            key=payload.key,
            value=stored_value,
            is_secret=payload.is_secret,
        )
        self.db.add(ev)
        await self.db.flush()
        await self.db.refresh(ev)

        # Log key + is_secret only — never the value (encrypted or not)
        logger.info(
            "EnvVar created",
            bot_id=str(bot_id),
            key=payload.key,
            secret=payload.is_secret,
            encrypted=payload.is_secret,  # always True when is_secret
        )
        return self._to_read(ev)

    # ─── Update ───────────────────────────────────────────────────────────────

    async def update(
        self,
        env_id: uuid.UUID,
        bot_id: uuid.UUID,
        payload: BotEnvVarUpdate,
    ) -> BotEnvVarRead:
        ev = await self._get_or_404(env_id, bot_id)

        # Check key uniqueness if key is being changed
        if payload.key is not None and payload.key != ev.key:
            conflict = await self.db.execute(
                select(BotEnvVar).where(
                    BotEnvVar.bot_id == bot_id,
                    BotEnvVar.key == payload.key,
                )
            )
            if conflict.scalar_one_or_none() is not None:
                raise ConflictException(
                    f"Variável '{payload.key}' já existe para este bot."
                )

        update_data = payload.model_dump(exclude_unset=True)

        # Determine the effective is_secret for this row after the update.
        # If is_secret is being changed, use the new value; otherwise keep existing.
        effective_is_secret: bool = (
            payload.is_secret
            if payload.is_secret is not None
            else ev.is_secret
        )

        # Handle key update
        if "key" in update_data:
            ev.key = update_data["key"]

        # Handle is_secret update (may require re-encrypting the existing value)
        if "is_secret" in update_data:
            old_is_secret = ev.is_secret
            new_is_secret = update_data["is_secret"]

            if old_is_secret != new_is_secret:
                # Secret flag toggled — need to re-encode the stored value.
                # Decrypt current stored value (handles legacy plaintext too).
                if old_is_secret:
                    current_plaintext = decrypt_secret(ev.value)
                else:
                    current_plaintext = ev.value  # was plaintext already

                # Re-encode under the new is_secret setting
                ev.value = self._prepare_value(current_plaintext, new_is_secret)

            ev.is_secret = new_is_secret

        # Handle value update (if a new value was provided)
        if "value" in update_data and update_data["value"] is not None:
            ev.value = self._prepare_value(update_data["value"], effective_is_secret)

        await self.db.flush()
        await self.db.refresh(ev)

        logged_fields = [k for k in update_data if k != "value"]  # never log value
        logger.info(
            "EnvVar updated",
            env_id=str(env_id),
            bot_id=str(bot_id),
            fields=logged_fields,
            secret=effective_is_secret,
        )
        return self._to_read(ev)

    # ─── Delete ───────────────────────────────────────────────────────────────

    async def delete(self, env_id: uuid.UUID, bot_id: uuid.UUID) -> None:
        ev = await self._get_or_404(env_id, bot_id)
        await self.db.delete(ev)
        await self.db.flush()
        logger.info("EnvVar deleted", env_id=str(env_id), bot_id=str(bot_id))

    # ─── Internal ─────────────────────────────────────────────────────────────

    async def _get_or_404(self, env_id: uuid.UUID, bot_id: uuid.UUID) -> BotEnvVar:
        result = await self.db.execute(
            select(BotEnvVar).where(
                BotEnvVar.id == env_id,
                BotEnvVar.bot_id == bot_id,
            )
        )
        ev = result.scalar_one_or_none()
        if ev is None:
            raise NotFoundException("Variável de ambiente")
        return ev
