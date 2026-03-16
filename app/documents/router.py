from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, Query, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_current_tenant
from app.auth.models import Tenant, User
from app.common.database import get_db
from app.common.exceptions import ValidationError
from app.common.rate_limit import RateLimit
from app.documents import service as doc_service
from app.documents.schemas import ChunkOut, DocumentListResponse, DocumentOut, UploadResponse
from app.config import settings

router = APIRouter(prefix="/documents", tags=["documents"])

_upload_rate_limit = RateLimit(max_calls=20, window_seconds=60, key="upload")


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED, dependencies=[_upload_rate_limit])
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document. Returns 202 immediately; ingestion runs asynchronously."""
    from app.common import storage

    # Validate content type — browsers often send application/octet-stream or
    # text/plain for .md files, so fall back to extension-based detection.
    import mimetypes
    content_type = file.content_type or "application/octet-stream"
    if content_type in ("application/octet-stream", "text/plain") and file.filename:
        guessed, _ = mimetypes.guess_type(file.filename)
        if guessed:
            content_type = guessed
    # text/plain covers .txt and is also acceptable for .md on some OS
    allowed = settings.allowed_content_types_list
    if content_type not in allowed:
        raise ValidationError(
            f"Unsupported file type '{content_type}'. Allowed: {', '.join(allowed)}"
        )

    # Read and size-check
    data = await file.read()
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise ValidationError(f"File exceeds the {settings.MAX_FILE_SIZE_MB} MB limit")
    if len(data) == 0:
        raise ValidationError("Uploaded file is empty")

    # Ensure S3 bucket exists
    await storage.ensure_bucket_exists()

    # Build S3 key scoped to tenant
    doc_id = uuid.uuid4()
    s3_key = f"{current_tenant.id}/docs/{doc_id}/{file.filename}"

    # Upload to S3 / MinIO
    await storage.upload_file(s3_key, data, content_type)

    # Create DB record (status=pending)
    doc = await doc_service.create_document(
        db=db,
        tenant_id=current_tenant.id,
        user_id=current_user.id,
        filename=file.filename or "unnamed",
        content_type=content_type,
        file_size_bytes=len(data),
        s3_key=s3_key,
    )

    # Override the auto-generated UUID so S3 key matches
    # (flush already happened in create_document; update the id)
    # Actually we pre-generated doc_id above — sync it
    # Simpler: use the DB-assigned doc.id and update the s3_key
    correct_key = f"{current_tenant.id}/docs/{doc.id}/{file.filename}"
    if correct_key != s3_key:
        # Move the S3 object to the correct key
        await storage.upload_file(correct_key, data, content_type)
        await storage.delete_file(s3_key)
        doc.s3_key = correct_key
        s3_key = correct_key

    # Dispatch Celery ingestion task (non-blocking)
    from app.ingestion.tasks import process_document
    process_document.delay(str(doc.id))

    return UploadResponse(document_id=doc.id, status=doc.status, filename=doc.filename)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    docs, total = await doc_service.list_documents(db, current_tenant.id, page, page_size)
    return DocumentListResponse(
        items=[DocumentOut.model_validate(d) for d in docs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    doc = await doc_service.get_document(db, document_id, current_tenant.id)
    return DocumentOut.model_validate(doc)


@router.get("/{document_id}/chunks", response_model=list[ChunkOut])
async def list_chunks(
    document_id: uuid.UUID,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    chunks = await doc_service.list_chunks(db, document_id, current_tenant.id)
    return [ChunkOut.model_validate(c) for c in chunks]


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    from app.common import storage
    s3_key = await doc_service.delete_document(db, document_id, current_tenant.id)
    try:
        await storage.delete_file(s3_key)
    except Exception:
        pass  # S3 cleanup is best-effort
