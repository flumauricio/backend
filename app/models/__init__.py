# Import all models here so Alembic auto-detects them via Base.metadata
from app.models.bot import Bot
from app.models.bot_v3 import BotDeployment, BotEnvVar, BotLog
from app.models.storage import BotWorkspace, StorageVolume
from app.models.user import User

__all__ = [
    "User",
    "Bot",
    "BotDeployment",
    "BotEnvVar",
    "BotLog",
    "StorageVolume",
    "BotWorkspace",
]
