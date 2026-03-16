import uuid
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Tenant, User
from app.auth.schemas import RegisterRequest, LoginRequest, TokenResponse
from app.common.exceptions import ConflictError, UnauthorizedError, NotFoundError
from app.common.logging import get_logger
from app.config import settings

logger = get_logger(__name__)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _create_token(payload: dict, expires_delta: timedelta) -> str:
    data = payload.copy()
    data["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(data, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: uuid.UUID, tenant_id: uuid.UUID, role: str) -> str:
    return _create_token(
        {"sub": str(user_id), "tenant_id": str(tenant_id), "role": role, "type": "access"},
        timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: uuid.UUID, tenant_id: uuid.UUID, role: str) -> str:
    return _create_token(
        {"sub": str(user_id), "tenant_id": str(tenant_id), "role": role, "type": "refresh"},
        timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: str = "access") -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != expected_type:
            raise UnauthorizedError("Invalid token type")
        return payload
    except JWTError as e:
        raise UnauthorizedError("Invalid or expired token") from e


def make_tokens(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, user.tenant_id, user.role),
        refresh_token=create_refresh_token(user.id, user.tenant_id, user.role),
    )


async def register(db: AsyncSession, data: RegisterRequest) -> tuple[Tenant, User, TokenResponse]:
    # Check slug uniqueness
    existing = await db.execute(select(Tenant).where(Tenant.slug == data.tenant_slug))
    if existing.scalar_one_or_none():
        raise ConflictError(f"Tenant slug '{data.tenant_slug}' is already taken")

    tenant = Tenant(name=data.tenant_name, slug=data.tenant_slug)
    db.add(tenant)
    await db.flush()  # get tenant.id

    user = User(
        tenant_id=tenant.id,
        email=data.email,
        password_hash=hash_password(data.password),
        role="admin",
    )
    db.add(user)
    await db.flush()

    tokens = make_tokens(user)
    logger.info("tenant_registered", tenant_id=str(tenant.id), tenant_slug=tenant.slug)
    return tenant, user, tokens


async def login(db: AsyncSession, data: LoginRequest) -> tuple[User, TokenResponse]:
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        raise UnauthorizedError("Invalid email or password")

    if not user.is_active:
        raise UnauthorizedError("Account is disabled")

    tokens = make_tokens(user)
    logger.info("user_login", user_id=str(user.id), tenant_id=str(user.tenant_id))
    return user, tokens


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> TokenResponse:
    payload = decode_token(refresh_token, expected_type="refresh")
    user_id = uuid.UUID(payload["sub"])

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    return make_tokens(user)


async def invite_user(db: AsyncSession, tenant_id: uuid.UUID, email: str, role: str) -> User:
    # Check if email already exists in this tenant
    result = await db.execute(
        select(User).where(User.tenant_id == tenant_id, User.email == email)
    )
    if result.scalar_one_or_none():
        raise ConflictError(f"User with email '{email}' already exists in this tenant")

    # Create user with a random temporary password (they'd reset via email in production)
    temp_password = str(uuid.uuid4())
    user = User(
        tenant_id=tenant_id,
        email=email,
        password_hash=hash_password(temp_password),
        role=role,
    )
    db.add(user)
    await db.flush()
    logger.info("user_invited", user_id=str(user.id), tenant_id=str(tenant_id), email=email)
    return user


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User", str(user_id))
    return user


async def get_tenant_by_id(db: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise NotFoundError("Tenant", str(tenant_id))
    return tenant
