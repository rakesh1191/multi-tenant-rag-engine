"""Pydantic schemas for the documents module."""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    """Public representation of a document."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    uploaded_by: uuid.UUID
    filename: str
    content_type: str
    file_size_bytes: int
    status: str
    error_message: Optional[str] = None
    chunk_count: int
    metadata: Dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    """Paginated list of documents."""

    items: List[DocumentResponse]
    total: int
    page: int
    page_size: int


class DocumentStatusUpdate(BaseModel):
    """Internal schema for updating document status (used by workers)."""

    status: str = Field(..., pattern="^(pending|processing|ready|failed)$")
    error_message: Optional[str] = None
    chunk_count: Optional[int] = None
