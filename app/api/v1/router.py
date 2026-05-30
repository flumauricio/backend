from fastapi import APIRouter

from app.api.v1.endpoints import auth, health, users, plans
from app.api.v1.endpoints.admin import router as admin_router
from app.api.v1.endpoints.bots import router as bots_router

api_router = APIRouter()

# Health (no prefix — accessible at /health and /health/detailed)
api_router.include_router(health.router)

# Auth
api_router.include_router(auth.router)

# Users
api_router.include_router(users.router)

# Plans
api_router.include_router(plans.router)

# Bots
api_router.include_router(bots_router)

# Admin
api_router.include_router(admin_router)
