"""
Phase 3: Query pipeline.

POST /query       — Server-Sent Events streaming response
POST /query/sync  — Blocking JSON response
GET  /query/history — Paginated query history for current user
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_current_tenant
from app.auth.models import User, Tenant
from app.common.database import get_db
from app.common.rate_limit import RateLimit
from app.query import service as query_service
from app.query.schemas import QueryRequest, QueryResponse, QueryHistoryResponse

router = APIRouter(prefix="/query", tags=["query"])

_query_rate_limit = RateLimit(max_calls=60, window_seconds=60, key="query")


@router.post("", response_class=StreamingResponse, dependencies=[_query_rate_limit])
async def query_stream(
    body: QueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """
    Submit a query and receive a streaming Server-Sent Events response.

    Each chunk is in the form:
        data: <token>\n\n

    The final event is:
        data: [DONE]\n\n
    """
    async def _event_generator():
        async for chunk in query_service.query_stream(
            db=db,
            tenant_id=tenant.id,
            user_id=current_user.id,
            query_text=body.query,
        ):
            yield chunk

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sync", response_model=QueryResponse, dependencies=[_query_rate_limit])
async def query_sync(
    body: QueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Submit a query and receive a complete JSON response (non-streaming)."""
    result = await query_service.query_sync(
        db=db,
        tenant_id=tenant.id,
        user_id=current_user.id,
        query_text=body.query,
    )
    return result


@router.get("/history", response_model=QueryHistoryResponse)
async def query_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Return paginated query history for the authenticated user."""
    return await query_service.get_query_history(
        db=db,
        tenant_id=tenant.id,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
    )
