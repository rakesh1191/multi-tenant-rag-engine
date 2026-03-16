"""Pydantic schemas for auth endpoints."""
import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class TenantRegisterRequest(BaseModel):
    """Request body for POST /auth/register."""

    tenant_name: str = Field(..., min_length=2, max_length=255, description="Organization name")
    tenant_slug: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="URL-safe identifier (lowercase letters, digits, hyphens)",
    )
    admin_email: EmailStr = Field(..., description="Admin user email")
    admin_password: str = Field(..., min_length=8, max_length=128, description="Admin user password")

    @field_validator("tenant_slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9][a-z0-9\-]{1,98}[a-z0-9]$", v):
            raise ValueError(
                "Slug must be 2-100 chars, lowercase alphanumeric and hyphens only, "
                "cannot start or end with a hyphen"
            )
        return v

    @field_validator("admin_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    """Request body for POST /auth/login."""

    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    """Request body for POST /auth/refresh."""

    refresh_token: str


class InviteUserRequest(BaseModel):
    """Request body for POST /auth/invite."""

    email: EmailStr
    role: str = Field(default="member", pattern="^(admin|member)$")


class TokenResponse(BaseModel):
    """JWT token pair returned after successful auth."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access token TTL in seconds")


class UserResponse(BaseModel):
    """Public representation of a user."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TenantResponse(BaseModel):
    """Public representation of a tenant."""

    id: uuid.UUID
    name: str
    slug: str
    max_documents: int
    max_storage_bytes: int
    created_at: datetime

    model_config = {"from_attributes": True}


class RegisterResponse(BaseModel):
    """Response for successful registration."""

    tenant: TenantResponse
    user: UserResponse
    tokens: TokenResponse


class InviteResponse(BaseModel):
    """Response for successful invite."""

    user: UserResponse
    message: str = "Invitation sent successfully"
