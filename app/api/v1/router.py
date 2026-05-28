from fastapi import APIRouter

from app.api.v1.endpoints import auth, health, users

api_router = APIRouter()

# Health (no prefix — accessible at /health)
api_router.include_router(health.router)

# Auth
api_router.include_router(auth.router)

# Users
api_router.include_router(users.router)
