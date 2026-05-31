from fastapi import APIRouter

from app.api.v1.endpoints import auth, health, users, plans
from app.api.v1.endpoints.admin import router as admin_router
from app.api.v1.endpoints.bots import router as bots_router
from app.api.v1.endpoints.bots_v3 import router as bots_v3_router
from app.api.v1.endpoints.storage import volumes_router, workspace_router

api_router = APIRouter()

# Health
api_router.include_router(health.router)

# Auth
api_router.include_router(auth.router)

# Users
api_router.include_router(users.router)

# Plans
api_router.include_router(plans.router)

# Bots V2 (existing CRUD + actions)
api_router.include_router(bots_router)

# Bots V3 (deployments, env vars, persisted logs)
api_router.include_router(bots_v3_router)

# Storage — admin volumes
api_router.include_router(volumes_router)

# Storage — bot workspace (mounted under /bots)
api_router.include_router(workspace_router)

# Admin stats
api_router.include_router(admin_router)
