"""Admin API router: tenant stats and user management."""
import uuid
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import TenantStats, UserAdminView, UserListResponse
from app.auth.dependencies import get_current_tenant, get_current_user, require_admin
from app.auth.models import Tenant, User
from app.common.database import get_db
from app.documents.models import Document

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get(
    "/stats",
    response_model=TenantStats,
    summary="Get tenant usage statistics",
)
async def get_stats(
    current_user: User = Depends(require_admin),
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> TenantStats:
    """Return aggregated usage stats for the current tenant.

    Some metrics (avg latency, cache hit rate) are placeholders until
    Phase 2 query logging is complete.
    """
    # Count users in tenant
    total_users = await db.scalar(
        select(func.count()).select_from(User).where(User.tenant_id == current_tenant.id)
    ) or 0

    # Count documents in tenant
    total_documents = await db.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.tenant_id == current_tenant.id)
    ) or 0

    # Sum storage used
    storage_used = await db.scalar(
        select(func.coalesce(func.sum(Document.file_size_bytes), 0))
        .where(Document.tenant_id == current_tenant.id)
    ) or 0

    # Chunk count would require joining document_chunks; placeholder for now
    total_chunks = 0

    return TenantStats(
        tenant_id=current_tenant.id,
        tenant_name=current_tenant.name,
        tenant_slug=current_tenant.slug,
        total_users=total_users,
        total_documents=total_documents,
        total_chunks=total_chunks,
        total_queries_30d=0,  # Phase 2: query from query_log
        storage_used_bytes=int(storage_used),
        storage_limit_bytes=current_tenant.max_storage_bytes,
        document_limit=current_tenant.max_documents,
        avg_query_latency_ms=None,
        cache_hit_rate=None,
    )


@router.get(
    "/users",
    response_model=UserListResponse,
    summary="List users in the current tenant",
)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_admin),
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    """Admin-only: list all users in the current tenant with pagination.

    Enforces tenant isolation — only returns users belonging to the
    authenticated user's tenant.
    """
    offset = (page - 1) * page_size

    total = await db.scalar(
        select(func.count())
        .select_from(User)
        .where(User.tenant_id == current_tenant.id)
    ) or 0

    result = await db.execute(
        select(User)
        .where(User.tenant_id == current_tenant.id)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    users = list(result.scalars().all())

    return UserListResponse(
        items=[UserAdminView.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )
