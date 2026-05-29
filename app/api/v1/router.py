from fastapi import APIRouter

from app.api.v1.endpoints import auth, health, users
from app.api.v1.endpoints.bots import router as bots_router

api_router = APIRouter()

# Health (no prefix — accessible at /health and /health/detailed)
api_router.include_router(health.router)

# Auth
api_router.include_router(auth.router)

# Users
api_router.include_router(users.router)

# Bots
api_router.include_router(bots_router)
