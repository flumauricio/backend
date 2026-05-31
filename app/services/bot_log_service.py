"""
BotLogService
─────────────
Read-only access to persistent bot logs stored in the bot_logs table.

Writing logs is done directly by other services (e.g. BotDeploymentService).
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.bot_v3 import BotLog
from app.schemas.bot_v3 import BotLogRead

logger = get_logger(__name__)


class BotLogService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_bot(
        self,
        bot_id: uuid.UUID,
        skip: int = 0,
        limit: int = 200,
        level: str | None = None,
    ) -> list[BotLogRead]:
        stmt = select(BotLog).where(BotLog.bot_id == bot_id)
        if level:
            stmt = stmt.where(BotLog.level == level)
        stmt = stmt.order_by(BotLog.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return [BotLogRead.model_validate(r) for r in rows]
