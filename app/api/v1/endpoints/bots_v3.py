"""
Bots V3 — Deploy, EnvVars, and Persisted Logs endpoints.

Mounted under the existing /bots prefix via include_router in router.py.
All endpoints reuse the same _resolve_bot() permission pattern from bots.py.
"""
import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_current_active_user, get_db_session
from app.core.rbac import Role, has_min_role
from app.models.user import User
from app.schemas.bot_v3 import (
    BotDeploymentCreate,
    BotDeploymentRead,
    BotEnvVarCreate,
    BotEnvVarRead,
    BotEnvVarUpdate,
    BotLogRead,
    BotPrepareResponse,
)
from app.services.bot_deployment_service import BotDeploymentService
from app.services.bot_env_var_service import BotEnvVarService
from app.services.bot_log_service import BotLogService
from app.services.bot_service import BotService

router = APIRouter(prefix="/bots", tags=["Bots V3"])


# ─── Shared helpers ───────────────────────────────────────────────────────────

def _is_admin(user: User) -> bool:
    return has_min_role(user.role, Role.ADMIN)


async def _resolve_bot(bot_id: uuid.UUID, current_user: User, service: BotService):
    """Admin sees any bot; regular user sees only their own."""
    if _is_admin(current_user):
        return await service.get_by_id(bot_id)
    return await service.get_by_id_for_user(bot_id, current_user.id)


def _bot_svc(db=Depends(get_db_session)) -> BotService:
    return BotService(db)


def _deploy_svc(db=Depends(get_db_session)) -> BotDeploymentService:
    return BotDeploymentService(db)


def _env_svc(db=Depends(get_db_session)) -> BotEnvVarService:
    return BotEnvVarService(db)


def _log_svc(db=Depends(get_db_session)) -> BotLogService:
    return BotLogService(db)


# ═══════════════════════════════════════════════════════════════════════════════
# DEPLOYMENTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/{bot_id}/deployments/prepare",
    response_model=BotPrepareResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Preparar deploy do bot [V3]",
)
async def prepare_deployment(
    bot_id: uuid.UUID,
    payload: BotDeploymentCreate,
    current_user: User = Depends(get_current_active_user),
    bot_svc: BotService = Depends(_bot_svc),
    deploy_svc: BotDeploymentService = Depends(_deploy_svc),
):
    """
    Cria um registro de deployment com status='prepared'.
    Nenhuma execução real ocorre — V3 é a camada de preparação.
    """
    bot = await _resolve_bot(bot_id, current_user, bot_svc)
    return await deploy_svc.prepare(bot, payload)


@router.get(
    "/{bot_id}/deployments",
    response_model=list[BotDeploymentRead],
    summary="Listar deployments do bot [V3]",
)
async def list_deployments(
    bot_id: uuid.UUID,
    skip:  int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    bot_svc:    BotService           = Depends(_bot_svc),
    deploy_svc: BotDeploymentService = Depends(_deploy_svc),
):
    bot = await _resolve_bot(bot_id, current_user, bot_svc)
    deps = await deploy_svc.list_for_bot(bot.id, skip=skip, limit=limit)
    return [BotDeploymentRead.model_validate(d) for d in deps]


@router.get(
    "/{bot_id}/deployments/{deployment_id}",
    response_model=BotDeploymentRead,
    summary="Buscar deployment por ID [V3]",
)
async def get_deployment(
    bot_id:        uuid.UUID,
    deployment_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    bot_svc:    BotService           = Depends(_bot_svc),
    deploy_svc: BotDeploymentService = Depends(_deploy_svc),
):
    bot = await _resolve_bot(bot_id, current_user, bot_svc)
    dep = await deploy_svc.get_by_id(deployment_id, bot.id)
    return BotDeploymentRead.model_validate(dep)


# ═══════════════════════════════════════════════════════════════════════════════
# ENV VARS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/{bot_id}/env",
    response_model=list[BotEnvVarRead],
    summary="Listar variáveis de ambiente do bot [V3]",
)
async def list_env_vars(
    bot_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    bot_svc: BotService     = Depends(_bot_svc),
    env_svc: BotEnvVarService = Depends(_env_svc),
):
    bot = await _resolve_bot(bot_id, current_user, bot_svc)
    return await env_svc.list_for_bot(bot.id)


@router.post(
    "/{bot_id}/env",
    response_model=BotEnvVarRead,
    status_code=status.HTTP_201_CREATED,
    summary="Criar variável de ambiente [V3]",
)
async def create_env_var(
    bot_id:  uuid.UUID,
    payload: BotEnvVarCreate,
    current_user: User = Depends(get_current_active_user),
    bot_svc: BotService      = Depends(_bot_svc),
    env_svc: BotEnvVarService = Depends(_env_svc),
):
    bot = await _resolve_bot(bot_id, current_user, bot_svc)
    return await env_svc.create(bot.id, payload)


@router.patch(
    "/{bot_id}/env/{env_id}",
    response_model=BotEnvVarRead,
    summary="Atualizar variável de ambiente [V3]",
)
async def update_env_var(
    bot_id:  uuid.UUID,
    env_id:  uuid.UUID,
    payload: BotEnvVarUpdate,
    current_user: User = Depends(get_current_active_user),
    bot_svc: BotService      = Depends(_bot_svc),
    env_svc: BotEnvVarService = Depends(_env_svc),
):
    bot = await _resolve_bot(bot_id, current_user, bot_svc)
    return await env_svc.update(env_id, bot.id, payload)


@router.delete(
    "/{bot_id}/env/{env_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir variável de ambiente [V3]",
)
async def delete_env_var(
    bot_id: uuid.UUID,
    env_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    bot_svc: BotService      = Depends(_bot_svc),
    env_svc: BotEnvVarService = Depends(_env_svc),
) -> None:
    bot = await _resolve_bot(bot_id, current_user, bot_svc)
    await env_svc.delete(env_id, bot.id)


# ═══════════════════════════════════════════════════════════════════════════════
# PERSISTED LOGS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/{bot_id}/logs/persisted",
    response_model=list[BotLogRead],
    summary="Logs persistidos do bot [V3]",
)
async def get_persisted_logs(
    bot_id: uuid.UUID,
    skip:   int = Query(default=0, ge=0),
    limit:  int = Query(default=200, ge=1, le=500),
    level:  str | None = Query(
        default=None,
        description="Filtrar por nível: info | warning | error | debug",
    ),
    current_user: User = Depends(get_current_active_user),
    bot_svc: BotService    = Depends(_bot_svc),
    log_svc: BotLogService = Depends(_log_svc),
):
    bot = await _resolve_bot(bot_id, current_user, bot_svc)
    return await log_svc.list_for_bot(bot.id, skip=skip, limit=limit, level=level)
