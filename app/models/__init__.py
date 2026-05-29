# Import all models here so Alembic auto-detects them via Base.metadata
from app.models.bot import Bot
from app.models.user import User

__all__ = ["User", "Bot"]
