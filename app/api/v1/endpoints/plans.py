import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_db_session
from app.core.rbac import Role, require_role
from app.models.user import User
from app.schemas.plan import PlanCreate, PlanRead, PlanUpdate
from app.services.plan_service import PlanService

router = APIRouter(prefix="/plans", tags=["Plans"])


def _get_plan_service(db=Depends(get_db_session)) -> PlanService:
    return PlanService(db)


# ─── Admin CRUD ───────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=list[PlanRead],
    summary="List all plans [admin]",
)
async def list_plans(
    active_only: bool = Query(default=False, description="Return only active plans"),
    service: PlanService = Depends(_get_plan_service),
    _actor: User = Depends(require_role(Role.ADMIN)),
) -> list:
    return await service.list_all(active_only=active_only)


@router.post(
    "/",
    response_model=PlanRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a plan [admin]",
)
async def create_plan(
    payload: PlanCreate,
    service: PlanService = Depends(_get_plan_service),
    _actor: User = Depends(require_role(Role.ADMIN)),
):
    return await service.create(payload)


@router.get(
    "/{plan_id}",
    response_model=PlanRead,
    summary="Get plan by ID [admin]",
)
async def get_plan(
    plan_id: uuid.UUID,
    service: PlanService = Depends(_get_plan_service),
    _actor: User = Depends(require_role(Role.ADMIN)),
):
    return await service.get_by_id(plan_id)


@router.patch(
    "/{plan_id}",
    response_model=PlanRead,
    summary="Update a plan [admin]",
)
async def update_plan(
    plan_id: uuid.UUID,
    payload: PlanUpdate,
    service: PlanService = Depends(_get_plan_service),
    _actor: User = Depends(require_role(Role.ADMIN)),
):
    plan = await service.get_by_id(plan_id)
    return await service.update(plan, payload)


@router.delete(
    "/{plan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a plan [admin]",
)
async def delete_plan(
    plan_id: uuid.UUID,
    service: PlanService = Depends(_get_plan_service),
    _actor: User = Depends(require_role(Role.ADMIN)),
) -> None:
    plan = await service.get_by_id(plan_id)
    await service.delete(plan)
