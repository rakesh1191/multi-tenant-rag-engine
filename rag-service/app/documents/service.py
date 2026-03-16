"""Document service: upload, list, retrieve, delete (Phase 2 will add ingestion)."""
import uuid
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Tenant, User
from app.common.exceptions import DocumentNotFoundException, ForbiddenException
from app.common.logging import get_logger
from app.common.storage import build_s3_key, upload_file
from app.documents.models import Document

logger = get_logger(__name__)


class DocumentService:
    """Handles document lifecycle within a tenant scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def upload(
        self,
        tenant: Tenant,
        user: User,
        filename: str,
        content_type: str,
        file_content: bytes,
    ) -> Document:
        """Store a document in S3 and create its DB record."""
        doc_id = uuid.uuid4()
        s3_key = build_s3_key(tenant.id, doc_id, filename)

        await upload_file(file_content, s3_key, content_type)

        document = Document(
            id=doc_id,
            tenant_id=tenant.id,
            uploaded_by=user.id,
            filename=filename,
            content_type=content_type,
            file_size_bytes=len(file_content),
            s3_key=s3_key,
            status="pending",
        )
        self.db.add(document)
        await self.db.flush()

        logger.info(
            "document_uploaded",
            document_id=str(document.id),
            tenant_id=str(tenant.id),
            filename=filename,
            size_bytes=len(file_content),
        )
        return document

    async def list_documents(
        self,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status_filter: Optional[str] = None,
    ) -> Tuple[List[Document], int]:
        """Return a paginated list of documents for a tenant."""
        query = select(Document).where(Document.tenant_id == tenant_id)
        count_query = select(func.count()).select_from(Document).where(Document.tenant_id == tenant_id)

        if status_filter:
            query = query.where(Document.status == status_filter)
            count_query = count_query.where(Document.status == status_filter)

        total = await self.db.scalar(count_query) or 0
        offset = (page - 1) * page_size
        result = await self.db.execute(
            query.order_by(Document.created_at.desc()).offset(offset).limit(page_size)
        )
        documents = list(result.scalars().all())
        return documents, total

    async def get_document(
        self, document_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Document:
        """Fetch a single document, enforcing tenant isolation."""
        document = await self.db.get(Document, document_id)
        if not document or document.tenant_id != tenant_id:
            raise DocumentNotFoundException()
        return document

    async def delete_document(
        self, document_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> None:
        """Soft-delete (or hard-delete) a document, enforcing tenant isolation."""
        document = await self.get_document(document_id, tenant_id)
        await self.db.delete(document)
        logger.info(
            "document_deleted",
            document_id=str(document_id),
            tenant_id=str(tenant_id),
        )
