"""Documents API router. Upload/list/get/delete are Phase 2; stubs return 501."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import JSONResponse

from app.auth.dependencies import get_current_tenant, get_current_user
from app.auth.models import Tenant, User
from app.documents.schemas import DocumentListResponse, DocumentResponse

router = APIRouter(prefix="/documents", tags=["documents"])

_NOT_IMPLEMENTED = JSONResponse(
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    content={
        "error": "NOT_IMPLEMENTED",
        "message": "Document endpoints are implemented in Phase 2",
        "details": {},
    },
)


@router.post(
    "/",
    summary="Upload a document (Phase 2)",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """Phase 2: Upload and enqueue a document for ingestion."""
    return _NOT_IMPLEMENTED


@router.get(
    "/",
    summary="List documents (Phase 2)",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """Phase 2: List documents for the current tenant."""
    return _NOT_IMPLEMENTED


@router.get(
    "/{document_id}",
    summary="Get a document (Phase 2)",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """Phase 2: Retrieve document metadata by ID."""
    return _NOT_IMPLEMENTED


@router.delete(
    "/{document_id}",
    summary="Delete a document (Phase 2)",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """Phase 2: Delete a document and its chunks."""
    return _NOT_IMPLEMENTED
