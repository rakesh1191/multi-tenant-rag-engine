from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service as auth_service
from app.auth.dependencies import get_current_user, require_admin
from app.auth.schemas import (
    InviteRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TenantOut,
    TokenResponse,
    UserOut,
)
from app.common.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    tenant, user, tokens = await auth_service.register(db, data)
    return RegisterResponse(
        user=UserOut.model_validate(user),
        tenant=TenantOut.model_validate(tenant),
        tokens=tokens,
    )


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    _user, tokens = await auth_service.login(db, data)
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return await auth_service.refresh_tokens(db, data.refresh_token)


@router.post("/invite", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def invite(
    data: InviteRequest,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await auth_service.invite_user(db, current_user.tenant_id, data.email, data.role)
    return UserOut.model_validate(user)
