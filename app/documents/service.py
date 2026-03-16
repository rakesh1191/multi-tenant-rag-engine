from __future__ import annotations

import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Document, DocumentChunk
from app.common.exceptions import NotFoundError, ValidationError
from app.common.logging import get_logger
from app.config import settings

logger = get_logger(__name__)


async def create_document(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    filename: str,
    content_type: str,
    file_size_bytes: int,
    s3_key: str,
) -> Document:
    """Create a document record with status=pending."""
    # Enforce tenant quota
    count = await db.scalar(
        select(func.count()).select_from(Document).where(Document.tenant_id == tenant_id)
    ) or 0
    # Fetch max_documents from tenant
    from app.auth.models import Tenant
    tenant = await db.get(Tenant, tenant_id)
    if tenant and count >= tenant.max_documents:
        raise ValidationError(
            f"Document quota exceeded ({count}/{tenant.max_documents}). "
            "Delete existing documents or contact support to increase your limit."
        )

    doc = Document(
        tenant_id=tenant_id,
        uploaded_by=user_id,
        filename=filename,
        content_type=content_type,
        file_size_bytes=file_size_bytes,
        s3_key=s3_key,
        status="pending",
    )
    db.add(doc)
    await db.flush()  # get doc.id without committing
    logger.info("document_created", document_id=str(doc.id), tenant_id=str(tenant_id), filename=filename)
    return doc


async def get_document(db: AsyncSession, document_id: uuid.UUID, tenant_id: uuid.UUID) -> Document:
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document", str(document_id))
    return doc


async def list_documents(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Document], int]:
    offset = (page - 1) * page_size
    count_result = await db.execute(
        select(func.count()).select_from(Document).where(Document.tenant_id == tenant_id)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(Document)
        .where(Document.tenant_id == tenant_id)
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    docs = list(result.scalars().all())
    return docs, total


async def delete_document(db: AsyncSession, document_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    doc = await get_document(db, document_id, tenant_id)
    s3_key = doc.s3_key
    await db.delete(doc)
    logger.info("document_deleted", document_id=str(document_id), tenant_id=str(tenant_id))
    return s3_key


async def list_chunks(
    db: AsyncSession, document_id: uuid.UUID, tenant_id: uuid.UUID
) -> list[DocumentChunk]:
    # First verify document belongs to tenant
    await get_document(db, document_id, tenant_id)
    result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return list(result.scalars().all())
