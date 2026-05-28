from fastapi import APIRouter

from app.api.v1.endpoints import auth, health, plans, users

api_router = APIRouter()

# Health (no prefix — accessible at /health and /health/detailed)
api_router.include_router(health.router)

# Auth
api_router.include_router(auth.router)

# Users (includes /users/me/limits)
api_router.include_router(users.router)

# Plans
api_router.include_router(plans.router)
