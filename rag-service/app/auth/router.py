"""Auth API router: register, login, refresh, invite."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_tenant, get_current_user, require_admin
from app.auth.models import Tenant, User
from app.auth.schemas import (
    InviteResponse,
    InviteUserRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterResponse,
    TenantRegisterRequest,
    TenantResponse,
    TokenResponse,
    UserResponse,
)
from app.auth.service import AuthService
from app.common.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new tenant and admin user",
)
async def register(
    payload: TenantRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """Create a new tenant along with an initial admin user.

    Returns JWT access and refresh tokens on success.
    Returns 409 Conflict if the slug is already taken.
    """
    service = AuthService(db)
    tenant, user, tokens = await service.register(payload)
    return RegisterResponse(
        tenant=TenantResponse.model_validate(tenant),
        user=UserResponse.model_validate(user),
        tokens=tokens,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive JWT tokens",
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate with email + password.

    Returns 401 Unauthorized for invalid credentials.
    """
    service = AuthService(db)
    _, tokens = await service.login(payload)
    return tokens


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token using a refresh token",
)
async def refresh_token(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Exchange a valid refresh token for a new access token.

    Returns 401 Unauthorized if the refresh token is invalid or expired.
    """
    service = AuthService(db)
    return await service.refresh(payload.refresh_token)


@router.post(
    "/invite",
    response_model=InviteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a new member to the tenant (admin only)",
)
async def invite_user(
    payload: InviteUserRequest,
    current_user: User = Depends(require_admin),
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> InviteResponse:
    """Admin-only: invite a new user to the current tenant.

    Creates the user with a temporary password. In production,
    an email with a password-reset link would be sent.
    Returns 409 Conflict if the email already exists in the tenant.
    Returns 403 Forbidden for non-admin users.
    """
    service = AuthService(db)
    user = await service.invite_user(payload, current_tenant.id)
    return InviteResponse(user=UserResponse.model_validate(user))


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return the profile of the currently authenticated user."""
    return UserResponse.model_validate(current_user)
