"""
Query service — Phase 3.

Steps:
1. Check Redis cache (tenant_id + query_text hash).
2. Embed the query with OpenAI (same model used for chunks).
3. pgvector cosine similarity search — top-k chunks for the tenant.
4. Assemble context string from retrieved chunks.
5. Call LLM provider (streaming or blocking).
6. Persist QueryLog row.
7. Write result to cache.
"""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis import (
    get_cached_response,
    set_cached_response,
    get_cached_embedding,
    set_cached_embedding,
)
from app.ingestion.embedder import get_embedder
from app.llm.providers import get_llm_provider


TOP_K = 5  # number of chunks to retrieve
CONTEXT_SEPARATOR = "\n\n---\n\n"


# ---------------------------------------------------------------------------
# Vector search
# ---------------------------------------------------------------------------

async def _search_chunks(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int = TOP_K,
) -> list[dict]:
    """Return top-k chunks ordered by cosine similarity.

    The embedding is inlined as a literal (not a bind param) because asyncpg
    cannot parse :name::vector — the :: cast conflicts with SQLAlchemy's
    named-parameter syntax. The literal is safe: it is machine-generated
    float values, not user input.
    """
    embedding_literal = "[" + ",".join(str(x) for x in query_embedding) + "]"
    sql = text(
        f"""
        SELECT
            dc.id,
            dc.content,
            dc.chunk_index,
            dc.document_id,
            d.filename,
            1 - (dc.embedding <=> '{embedding_literal}'::vector) AS similarity
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        WHERE dc.tenant_id = :tenant_id
          AND dc.embedding IS NOT NULL
          AND d.status = 'ready'
        ORDER BY dc.embedding <=> '{embedding_literal}'::vector
        LIMIT :top_k
        """
    )
    result = await db.execute(
        sql,
        {
            "tenant_id": str(tenant_id),
            "top_k": top_k,
        },
    )
    rows = result.mappings().all()
    return [dict(r) for r in rows]


def _build_context(chunks: list[dict]) -> str:
    parts = []
    for chunk in chunks:
        header = f"[{chunk['filename']} — chunk {chunk['chunk_index']}]"
        parts.append(f"{header}\n{chunk['content']}")
    return CONTEXT_SEPARATOR.join(parts) if parts else "No relevant context found."


# ---------------------------------------------------------------------------
# QueryLog persistence
# ---------------------------------------------------------------------------

async def _log_query(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    query_text: str,
    response_text: str,
    latency_ms: int,
    token_usage: dict,
    cache_hit: bool,
) -> uuid.UUID:
    log_id = uuid.uuid4()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    await db.execute(
        text(
            """
            INSERT INTO query_log
                (id, tenant_id, user_id, query_text, response_text, latency_ms, token_usage, cache_hit, created_at)
            VALUES
                (:id, :tenant_id, :user_id, :query_text, :response_text, :latency_ms, :token_usage, :cache_hit, :created_at)
            """
        ),
        {
            "id": str(log_id),
            "tenant_id": str(tenant_id),
            "user_id": str(user_id),
            "query_text": query_text,
            "response_text": response_text,
            "latency_ms": latency_ms,
            "token_usage": json.dumps(token_usage),  # asyncpg requires JSON string for JSONB
            "cache_hit": cache_hit,
            "created_at": now,
        },
    )
    await db.commit()
    return log_id


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def query_sync(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    query_text: str,
) -> dict:
    """Blocking query — returns full response dict."""
    t0 = time.monotonic()

    # 1. Cache check
    cached = await get_cached_response(str(tenant_id), query_text)
    if cached:
        latency_ms = int((time.monotonic() - t0) * 1000)
        await _log_query(
            db, tenant_id, user_id, query_text,
            cached["answer"], latency_ms, cached.get("token_usage", {}), cache_hit=True,
        )
        cached["cache_hit"] = True
        cached["latency_ms"] = latency_ms
        return cached

    # 2. Embed query (check cache first)
    query_embedding = await get_cached_embedding(query_text)
    if query_embedding is None:
        embedder = get_embedder()
        [query_embedding] = await embedder.embed_many([query_text])
        await set_cached_embedding(query_text, query_embedding)

    # 3. Vector search
    chunks = await _search_chunks(db, tenant_id, query_embedding)
    context = _build_context(chunks)

    # 4. LLM call
    llm = get_llm_provider()
    answer, token_usage = await llm.complete(query_text, context)

    latency_ms = int((time.monotonic() - t0) * 1000)

    # 5. Persist log
    log_id = await _log_query(
        db, tenant_id, user_id, query_text, answer, latency_ms, token_usage, cache_hit=False,
    )

    result = {
        "query_id": str(log_id),
        "answer": answer,
        "sources": [
            {
                "document_id": str(c["document_id"]),
                "filename": c["filename"],
                "chunk_index": c["chunk_index"],
                "similarity": round(float(c["similarity"]), 4),
            }
            for c in chunks
        ],
        "token_usage": token_usage,
        "cache_hit": False,
        "latency_ms": latency_ms,
    }

    # 6. Cache result
    await set_cached_response(str(tenant_id), query_text, result)
    return result


async def query_stream(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    query_text: str,
) -> AsyncIterator[str]:
    """
    Streaming query. Yields SSE-formatted strings:
      data: <token>\n\n
    and a final:
      data: [DONE]\n\n
    """
    t0 = time.monotonic()
    collected: list[str] = []

    def _sse(payload: dict) -> str:
        return f"data: {json.dumps(payload)}\n\n"

    # Cache check — still stream from cache to keep interface consistent
    cached = await get_cached_response(str(tenant_id), query_text)
    if cached:
        if cached.get("sources"):
            yield _sse({"type": "sources", "sources": cached["sources"]})
        for word in cached["answer"].split(" "):
            yield _sse({"type": "token", "data": word + " "})
        yield _sse({"type": "done"})
        yield "data: [DONE]\n\n"
        latency_ms = int((time.monotonic() - t0) * 1000)
        await _log_query(
            db, tenant_id, user_id, query_text,
            cached["answer"], latency_ms, cached.get("token_usage", {}), cache_hit=True,
        )
        return

    # Embed + search (check embedding cache first)
    query_embedding = await get_cached_embedding(query_text)
    if query_embedding is None:
        embedder = get_embedder()
        [query_embedding] = await embedder.embed_many([query_text])
        await set_cached_embedding(query_text, query_embedding)
    chunks = await _search_chunks(db, tenant_id, query_embedding)
    context = _build_context(chunks)

    # Send sources before streaming tokens
    sources_payload = [
        {
            "document_id": str(c["document_id"]),
            "filename": c["filename"],
            "chunk_index": c["chunk_index"],
            "similarity": round(float(c["similarity"]), 4),
        }
        for c in chunks
    ]
    yield _sse({"type": "sources", "sources": sources_payload})

    # Stream LLM tokens as JSON — newlines in tokens are safely encoded
    llm = get_llm_provider()
    async for token in llm.stream(query_text, context):
        collected.append(token)
        yield _sse({"type": "token", "data": token})

    yield _sse({"type": "done"})
    yield "data: [DONE]\n\n"

    full_answer = "".join(collected)
    latency_ms = int((time.monotonic() - t0) * 1000)
    token_usage: dict[str, int] = {}  # streaming APIs don't always return usage inline

    log_id = await _log_query(
        db, tenant_id, user_id, query_text, full_answer, latency_ms, token_usage, cache_hit=False,
    )

    cache_payload = {
        "query_id": str(log_id),
        "answer": full_answer,
        "sources": [
            {
                "document_id": str(c["document_id"]),
                "filename": c["filename"],
                "chunk_index": c["chunk_index"],
                "similarity": round(float(c["similarity"]), 4),
            }
            for c in chunks
        ],
        "token_usage": token_usage,
        "cache_hit": False,
        "latency_ms": latency_ms,
    }
    await set_cached_response(str(tenant_id), query_text, cache_payload)


async def get_query_history(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    offset = (page - 1) * page_size
    count_result = await db.execute(
        text(
            "SELECT COUNT(*) FROM query_log WHERE tenant_id = :tid AND user_id = :uid"
        ),
        {"tid": str(tenant_id), "uid": str(user_id)},
    )
    total = count_result.scalar_one()

    rows_result = await db.execute(
        text(
            """
            SELECT id, query_text, response_text, latency_ms, token_usage, cache_hit, created_at
            FROM query_log
            WHERE tenant_id = :tid AND user_id = :uid
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"tid": str(tenant_id), "uid": str(user_id), "limit": page_size, "offset": offset},
    )
    items = [dict(r) for r in rows_result.mappings().all()]
    # Convert UUIDs and datetimes to strings for JSON serialisation
    for item in items:
        item["id"] = str(item["id"])
        if item["created_at"]:
            item["created_at"] = item["created_at"].isoformat()

    return {"items": items, "total": total, "page": page, "page_size": page_size}
