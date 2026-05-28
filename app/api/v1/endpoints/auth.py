from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_user_service
from app.core.logging import get_logger
from app.database.session import get_db
from app.schemas.token import RefreshTokenRequest, Token
from app.schemas.user import UserCreate, UserRead
from app.services.auth_service import AuthService
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["Auth"])
logger = get_logger(__name__)


@router.post("/login", response_model=Token, summary="Obtain access & refresh tokens")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    user_service: UserService = Depends(get_user_service),
):
    auth_service = AuthService(user_service)
    return await auth_service.login(form_data.username, form_data.password)


@router.post("/refresh", response_model=Token, summary="Refresh access token")
async def refresh_token(
    body: RefreshTokenRequest,
    user_service: UserService = Depends(get_user_service),
):
    auth_service = AuthService(user_service)
    return await auth_service.refresh(body.refresh_token)


@router.post("/register", response_model=UserRead, status_code=201, summary="Register new user")
async def register(
    payload: UserCreate,
    user_service: UserService = Depends(get_user_service),
):
    return await user_service.create(payload)
