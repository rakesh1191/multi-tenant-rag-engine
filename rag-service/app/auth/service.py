"""Auth business logic: user/tenant creation, JWT issuance, password hashing."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Tenant, User
from app.auth.schemas import (
    InviteUserRequest,
    LoginRequest,
    TenantRegisterRequest,
    TokenResponse,
)
from app.common.exceptions import (
    ConflictException,
    InactiveUserException,
    InvalidTokenException,
    TenantNotFoundException,
    UnauthorizedException,
    UserNotFoundException,
)
from app.common.logging import get_logger
from app.config import settings

logger = get_logger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str,
) -> str:
    """Create a signed JWT access token."""
    now = datetime.now(tz=timezone.utc)
    expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str,
) -> str:
    """Create a signed JWT refresh token with a longer TTL."""
    now = datetime.now(tz=timezone.utc)
    expire = now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "type": "refresh",
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Dict:
    """Decode and validate a JWT token. Raises InvalidTokenException on failure."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError as exc:
        raise InvalidTokenException(f"Token validation failed: {exc}") from exc


def build_token_response(user: User) -> TokenResponse:
    """Build a TokenResponse for a given user."""
    access_token = create_access_token(user.id, user.tenant_id, user.role)
    refresh_token = create_refresh_token(user.id, user.tenant_id, user.role)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


class AuthService:
    """Handles all authentication and registration logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def register(
        self, payload: TenantRegisterRequest
    ) -> Tuple[Tenant, User, TokenResponse]:
        """Create a new tenant and an admin user. Return the tenant, user, and tokens."""
        # Check for duplicate slug
        existing_tenant = await self.db.scalar(
            select(Tenant).where(Tenant.slug == payload.tenant_slug)
        )
        if existing_tenant:
            raise ConflictException(
                f"Tenant slug '{payload.tenant_slug}' is already taken",
                details={"slug": payload.tenant_slug},
            )

        # Create tenant
        tenant = Tenant(
            id=uuid.uuid4(),
            name=payload.tenant_name,
            slug=payload.tenant_slug,
        )
        self.db.add(tenant)
        await self.db.flush()  # Get tenant.id without committing

        # Create admin user
        user = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email=payload.admin_email.lower(),
            password_hash=hash_password(payload.admin_password),
            role="admin",
            is_active=True,
        )
        self.db.add(user)
        await self.db.flush()

        tokens = build_token_response(user)

        logger.info(
            "tenant_registered",
            tenant_id=str(tenant.id),
            slug=tenant.slug,
            user_id=str(user.id),
        )
        return tenant, user, tokens

    async def login(self, payload: LoginRequest) -> Tuple[User, TokenResponse]:
        """Authenticate a user by email/password and return tokens."""
        user = await self.db.scalar(
            select(User).where(User.email == payload.email.lower())
        )
        if not user:
            raise UnauthorizedException("Invalid email or password")

        if not verify_password(payload.password, user.password_hash):
            raise UnauthorizedException("Invalid email or password")

        if not user.is_active:
            raise InactiveUserException()

        tokens = build_token_response(user)
        logger.info("user_logged_in", user_id=str(user.id), tenant_id=str(user.tenant_id))
        return user, tokens

    async def refresh(self, refresh_token: str) -> TokenResponse:
        """Issue a new access token from a valid refresh token."""
        payload = decode_token(refresh_token)

        if payload.get("type") != "refresh":
            raise InvalidTokenException("Token is not a refresh token")

        user_id = payload.get("sub")
        user = await self.db.get(User, uuid.UUID(user_id))
        if not user:
            raise UserNotFoundException()

        if not user.is_active:
            raise InactiveUserException()

        return build_token_response(user)

    async def invite_user(
        self, payload: InviteUserRequest, tenant_id: uuid.UUID
    ) -> User:
        """Create a new member user in the given tenant (invited by an admin)."""
        # Check for existing user in this tenant
        existing = await self.db.scalar(
            select(User).where(
                User.tenant_id == tenant_id,
                User.email == payload.email.lower(),
            )
        )
        if existing:
            raise ConflictException(
                f"User with email '{payload.email}' already exists in this tenant",
                details={"email": payload.email},
            )

        # For invite, generate a temporary random password — in production
        # you'd send an email with a password-reset link.
        temp_password = str(uuid.uuid4())
        user = User(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            email=payload.email.lower(),
            password_hash=hash_password(temp_password),
            role=payload.role,
            is_active=True,
        )
        self.db.add(user)
        await self.db.flush()

        logger.info(
            "user_invited",
            user_id=str(user.id),
            tenant_id=str(tenant_id),
            role=user.role,
        )
        return user

    async def get_user_by_id(self, user_id: uuid.UUID) -> User:
        """Fetch a user by ID. Raises UserNotFoundException if not found."""
        user = await self.db.get(User, user_id)
        if not user:
            raise UserNotFoundException()
        return user

    async def get_tenant_by_id(self, tenant_id: uuid.UUID) -> Tenant:
        """Fetch a tenant by ID. Raises TenantNotFoundException if not found."""
        tenant = await self.db.get(Tenant, tenant_id)
        if not tenant:
            raise TenantNotFoundException()
        return tenant
