import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, ConflictException, NotFoundException
from app.core.logging import get_logger
from app.models.plan import Plan
from app.schemas.plan import PlanCreate, PlanUpdate

logger = get_logger(__name__)

DEFAULT_PLAN_NAME = "Free"


def is_default_plan(plan: Plan) -> bool:
    return plan.name.strip().lower() == DEFAULT_PLAN_NAME.lower()


class PlanService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── Finders ──────────────────────────────────────────────────────────────

    async def get_by_id(self, plan_id: uuid.UUID) -> Plan:
        result = await self.db.execute(select(Plan).where(Plan.id == plan_id))
        plan = result.scalar_one_or_none()
        if plan is None:
            raise NotFoundException("Plan")
        return plan

    async def get_by_name(self, name: str) -> Plan | None:
        result = await self.db.execute(select(Plan).where(Plan.name == name))
        return result.scalar_one_or_none()

    async def get_default_plan(self) -> Plan | None:
        return await self.get_by_name(DEFAULT_PLAN_NAME)

    async def list_all(self, *, active_only: bool = False) -> list[Plan]:
        stmt = select(Plan).order_by(Plan.name)
        if active_only:
            stmt = stmt.where(Plan.is_active.is_(True))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ─── Mutations ────────────────────────────────────────────────────────────

    async def create(self, payload: PlanCreate) -> Plan:
        if await self.get_by_name(payload.name):
            raise ConflictException(f"Plan '{payload.name}' already exists.")

        plan = Plan(**payload.model_dump())
        self.db.add(plan)
        await self.db.flush()
        await self.db.refresh(plan)
        logger.info("Plan created", plan_id=str(plan.id), name=plan.name)
        return plan

    async def update(self, plan: Plan, payload: PlanUpdate) -> Plan:
        update_data = payload.model_dump(exclude_unset=True)

        # The Free plan is the system default. It may have its limits edited,
        # but it must remain named "Free" and active so new users always have
        # a valid entry plan.
        if is_default_plan(plan):
            new_name = update_data.get("name")
            if new_name is not None and new_name.strip() != plan.name:
                raise BadRequestException(
                    "The Free plan is the system default and cannot be renamed."
                )
            if update_data.get("is_active") is False:
                raise BadRequestException(
                    "The Free plan is the system default and cannot be deactivated."
                )
            update_data.pop("name", None)
            update_data.pop("is_active", None)

        # Guard: if name is changing, check uniqueness
        new_name = update_data.get("name")
        if new_name and new_name != plan.name:
            if await self.get_by_name(new_name):
                raise ConflictException(f"Plan '{new_name}' already exists.")

        for field, value in update_data.items():
            setattr(plan, field, value)

        await self.db.flush()
        await self.db.refresh(plan)
        logger.info("Plan updated", plan_id=str(plan.id), fields=list(update_data.keys()))
        return plan

    async def delete(self, plan: Plan) -> None:
        """
        Hard delete for normal plans.

        The Free plan is protected because it is the system default used for
        new users and fallback limits. Admins may edit its limits, but cannot
        delete it.
        """
        if is_default_plan(plan):
            raise BadRequestException(
                "The Free plan is the system default and cannot be deleted."
            )

        await self.db.delete(plan)
        await self.db.flush()
        logger.info("Plan deleted", plan_id=str(plan.id), name=plan.name)
