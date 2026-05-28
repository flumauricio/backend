# Import all models here so Alembic auto-detects them via Base.metadata
from app.models.plan import Plan
from app.models.user import User
from app.models.user_limits import UserLimits

__all__ = ["User", "Plan", "UserLimits"]
