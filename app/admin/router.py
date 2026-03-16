from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_tenant, require_admin
from app.auth.models import Tenant, User
from app.auth.schemas import UserOut
from app.common.database import get_db
from app.documents.models import Document, DocumentChunk, QueryLog
from app.admin.schemas import AdminUsersResponse, TenantStats

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats", response_model=TenantStats)
async def get_stats(
    current_tenant: Tenant = Depends(get_current_tenant),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    doc_count = await db.scalar(
        select(func.count()).select_from(Document).where(Document.tenant_id == current_tenant.id)
    ) or 0

    chunk_count = await db.scalar(
        select(func.count()).select_from(DocumentChunk).where(DocumentChunk.tenant_id == current_tenant.id)
    ) or 0

    storage_bytes = await db.scalar(
        select(func.coalesce(func.sum(Document.file_size_bytes), 0))
        .where(Document.tenant_id == current_tenant.id)
    ) or 0

    user_count = await db.scalar(
        select(func.count()).select_from(User).where(User.tenant_id == current_tenant.id)
    ) or 0

    query_count = await db.scalar(
        select(func.count()).select_from(QueryLog).where(QueryLog.tenant_id == current_tenant.id)
    ) or 0

    return TenantStats(
        tenant_id=current_tenant.id,
        tenant_name=current_tenant.name,
        document_count=doc_count,
        chunk_count=chunk_count,
        total_storage_bytes=storage_bytes,
        user_count=user_count,
        query_count=query_count,
    )


@router.get("/users", response_model=AdminUsersResponse)
async def list_users(
    current_tenant: Tenant = Depends(get_current_tenant),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.tenant_id == current_tenant.id).order_by(User.created_at)
    )
    users = list(result.scalars().all())
    return AdminUsersResponse(
        items=[UserOut.model_validate(u) for u in users],
        total=len(users),
    )
