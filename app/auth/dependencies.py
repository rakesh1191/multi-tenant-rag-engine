import uuid
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Tenant, User
from app.auth import service as auth_service
from app.common.database import get_db
from app.common.exceptions import UnauthorizedError, ForbiddenError
import structlog

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

logger = structlog.get_logger(__name__)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = auth_service.decode_token(token, expected_type="access")
    user_id = uuid.UUID(payload["sub"])
    user = await auth_service.get_user_by_id(db, user_id)
    if not user.is_active:
        raise UnauthorizedError("Account is disabled")

    structlog.contextvars.bind_contextvars(
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
    )
    return user


async def get_current_tenant(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    return await auth_service.get_tenant_by_id(db, current_user.tenant_id)


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise ForbiddenError("Admin role required")
    return current_user
