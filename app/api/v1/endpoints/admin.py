from fastapi import APIRouter, Depends

from app.api.dependencies import get_db_session
from app.core.rbac import Role, require_role
from app.schemas.admin import AdminStatsResponse
from app.services.admin_stats_service import AdminStatsService

router = APIRouter(prefix="/admin", tags=["Admin"])


def _get_stats_service(db=Depends(get_db_session)) -> AdminStatsService:
    return AdminStatsService(db)


@router.get(
    "/stats",
    response_model=AdminStatsResponse,
    summary="Estatísticas gerais da plataforma [admin]",
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def get_admin_stats(
    service: AdminStatsService = Depends(_get_stats_service),
) -> AdminStatsResponse:
    """
    Returns aggregate counts across users, plans and bots.
    Restricted to admin role.
    """
    return await service.get_stats()
