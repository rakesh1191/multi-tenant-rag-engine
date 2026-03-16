"""Pydantic schemas for the admin module."""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class TenantStats(BaseModel):
    """Usage statistics for the current tenant."""

    tenant_id: uuid.UUID
    tenant_name: str
    tenant_slug: str
    total_users: int
    total_documents: int
    total_chunks: int
    total_queries_30d: int
    storage_used_bytes: int
    storage_limit_bytes: int
    document_limit: int
    # Placeholder fields — real values computed in Phase 2
    avg_query_latency_ms: Optional[float] = None
    cache_hit_rate: Optional[float] = None


class UserAdminView(BaseModel):
    """Admin view of a user record."""

    id: uuid.UUID
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """Paginated list of users for admin view."""

    items: List[UserAdminView]
    total: int
    page: int
    page_size: int
