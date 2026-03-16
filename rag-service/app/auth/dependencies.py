"""FastAPI auth dependencies: token extraction, user/tenant resolution."""
import uuid

import structlog
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Tenant, User
from app.auth.service import AuthService, decode_token
from app.common.database import get_db
from app.common.exceptions import (
    ForbiddenException,
    InactiveUserException,
    InvalidTokenException,
    TenantNotFoundException,
    UserNotFoundException,
)
from app.common.logging import bind_request_context

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

logger = structlog.get_logger(__name__)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Decode the Bearer JWT and return the authenticated User.

    Raises InvalidTokenException if the token is missing, malformed, or expired.
    Raises UserNotFoundException if the user no longer exists.
    Raises InactiveUserException if the user is deactivated.
    """
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise InvalidTokenException("Token is not an access token")

    raw_user_id = payload.get("sub")
    if not raw_user_id:
        raise InvalidTokenException("Token missing 'sub' claim")

    try:
        user_id = uuid.UUID(raw_user_id)
    except ValueError:
        raise InvalidTokenException("Token 'sub' claim is not a valid UUID")

    service = AuthService(db)
    user = await service.get_user_by_id(user_id)

    if not user.is_active:
        raise InactiveUserException()

    # Bind user/tenant context to structlog for the duration of this request
    bind_request_context(
        request_id="",  # already set by middleware
        tenant_id=str(user.tenant_id),
        user_id=str(user.id),
    )

    return user


async def get_current_tenant(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """Return the Tenant associated with the authenticated user.

    This is the primary tenant-scoping dependency — every protected route
    that needs tenant-scoped data should depend on this.
    """
    service = AuthService(db)
    tenant = await service.get_tenant_by_id(current_user.tenant_id)
    return tenant


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Assert that the authenticated user has the 'admin' role.

    Raises ForbiddenException otherwise.
    """
    if current_user.role != "admin":
        raise ForbiddenException("Admin role required")
    return current_user
