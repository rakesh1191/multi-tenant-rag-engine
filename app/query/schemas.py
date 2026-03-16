from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(5, ge=1, le=20)


class SourceChunk(BaseModel):
    document_id: uuid.UUID
    filename: str
    chunk_index: int
    similarity: float


class QueryResponse(BaseModel):
    query_id: uuid.UUID
    answer: str
    sources: list[SourceChunk]
    token_usage: dict
    cache_hit: bool
    latency_ms: int


class QueryHistoryItem(BaseModel):
    id: uuid.UUID
    query_text: str
    response_text: Optional[str] = None
    latency_ms: Optional[int] = None
    token_usage: dict
    cache_hit: bool
    created_at: datetime


class QueryHistoryResponse(BaseModel):
    items: list[dict]
    total: int
    page: int
    page_size: int
