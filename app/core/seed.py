"""
app/core/seed.py
────────────────
Idempotent startup seed.

Execution order inside a single transaction:
  1. Ensure Free plan exists.
  2. Ensure superuser (admin) exists.
  3. Ensure superuser has a UserLimits row linked to the Free plan.
  4. Backfill UserLimits for any existing users without limits.

Rules:
  • Every step is guarded by a "does it already exist?" check — safe to
    run on every startup, in any environment.
  • The Free plan is the permanent system default.
  • If the seed fails:
      - development  → exception is re-raised (loud, intentional crash).
      - staging / production → error is logged, startup continues.
        A broken seed must never take down a production node.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import get_password_hash
from app.database.session import AsyncSessionLocal
from app.models.plan import Plan
from app.models.user import User
from app.models.user_limits import UserLimits
from app.services.plan_service import DEFAULT_PLAN_NAME

logger = get_logger(__name__)

# ─── Free plan specification ──────────────────────────────────────────────────

_FREE_PLAN: dict = {
    "name": DEFAULT_PLAN_NAME,
    "description": "Plano gratuito inicial",
    "cloud_storage_mb": 512,
    "max_bots": 1,
    "max_ram_per_bot_mb": 256,
    "max_storage_per_bot_mb": 256,
    "is_active": True,
}


# ─── Individual seed steps ────────────────────────────────────────────────────

async def _seed_free_plan(db: AsyncSession) -> Plan:
    """
    Returns the Free plan, creating it if it doesn't exist.
    Keyed on name='Free'.
    """
    result = await db.execute(select(Plan).where(Plan.name == DEFAULT_PLAN_NAME))
    plan = result.scalar_one_or_none()

    if plan is not None:
        changed = False
        if not plan.is_active:
            plan.is_active = True
            changed = True
        if changed:
            await db.flush()
            await db.refresh(plan)
            logger.info("Seed: Free plan reactivated", plan_id=str(plan.id))
        else:
            logger.info("Seed: Free plan already exists", plan_id=str(plan.id))
        return plan

    plan = Plan(**_FREE_PLAN)
    db.add(plan)
    await db.flush()
    await db.refresh(plan)
    logger.info("Seed: Free plan created", plan_id=str(plan.id))
    return plan


async def _seed_superuser(db: AsyncSession) -> User:
    """
    Returns the superuser, creating it if it doesn't exist.
    Keyed on FIRST_SUPERUSER_EMAIL — will not create a duplicate.
    """
    result = await db.execute(
        select(User).where(User.email == settings.FIRST_SUPERUSER_EMAIL)
    )
    user = result.scalar_one_or_none()

    if user is not None:
        logger.info(
            "Seed: Superuser already exists",
            user_id=str(user.id),
            email=user.email,
        )
        return user

    user = User(
        email=settings.FIRST_SUPERUSER_EMAIL,
        hashed_password=get_password_hash(settings.FIRST_SUPERUSER_PASSWORD),
        full_name="Super Admin",
        role="admin",
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    logger.info(
        "Seed: Superuser created",
        user_id=str(user.id),
        email=user.email,
    )
    return user


async def _seed_superuser_limits(
    db: AsyncSession, user: User, plan: Plan
) -> UserLimits:
    """
    Ensures the superuser has a UserLimits row linked to the Free plan.
    If the row already exists, leaves it untouched (admin may have
    manually assigned a better plan — we don't want to downgrade them).
    """
    result = await db.execute(
        select(UserLimits).where(UserLimits.user_id == user.id)
    )
    limits = result.scalar_one_or_none()

    if limits is not None:
        logger.info(
            "Seed: Superuser limits already exist",
            user_id=str(user.id),
            plan_id=str(limits.plan_id),
        )
        return limits

    limits = UserLimits(
        user_id=user.id,
        plan_id=plan.id,
        # All override fields left null → values inherited from plan
    )
    db.add(limits)
    await db.flush()
    await db.refresh(limits)
    logger.info(
        "Seed: Superuser limits created",
        user_id=str(user.id),
        plan_id=str(plan.id),
    )
    return limits


async def _backfill_missing_user_limits(db: AsyncSession, plan: Plan) -> int:
    """
    Creates UserLimits rows for existing users that still do not have one.
    Does not overwrite any existing limits or assigned plans.
    """
    stmt = (
        select(User)
        .outerjoin(UserLimits, UserLimits.user_id == User.id)
        .where(UserLimits.id.is_(None))
    )
    result = await db.execute(stmt)
    users_without_limits = list(result.scalars().all())

    for user in users_without_limits:
        db.add(UserLimits(user_id=user.id, plan_id=plan.id))

    if users_without_limits:
        await db.flush()
        logger.info(
            "Seed: UserLimits backfilled for users without limits",
            count=len(users_without_limits),
            plan_id=str(plan.id),
        )
    else:
        logger.info("Seed: No missing UserLimits rows to backfill")

    return len(users_without_limits)


# ─── Public entrypoint ────────────────────────────────────────────────────────

async def run_seed() -> None:
    """
    Main seed entrypoint — called from the app lifespan.

    All steps run inside a single transaction.
    On failure the transaction is rolled back atomically,
    leaving the DB in a consistent state.
    """
    logger.info("Seed: starting")

    try:
        async with AsyncSessionLocal() as db:
            try:
                plan = await _seed_free_plan(db)
                user = await _seed_superuser(db)
                await _seed_superuser_limits(db, user, plan)
                await _backfill_missing_user_limits(db, plan)
                await db.commit()
                logger.info("Seed: completed successfully")

            except Exception:
                await db.rollback()
                raise  # let the outer except decide what to do

    except Exception as exc:
        logger.error(
            "Seed: FAILED",
            error=str(exc),
            exc_info=True,
        )
        if settings.is_development:
            # Crash loudly in development so the issue is impossible to miss.
            raise RuntimeError(
                f"Startup seed failed in development environment: {exc}"
            ) from exc

        # In staging/production: log and carry on.
        # A partial seed is recoverable; a crashed API node is not.
        logger.warning(
            "Seed: continuing startup despite seed failure "
            "(non-development environment)"
        )
