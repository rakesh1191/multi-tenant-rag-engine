"""
Redis cache layer for query results and embeddings.

Keys:
  Query cache:    rag:query:{version}:{sha256(tenant_id:query)}   TTL: 1 hour
  Embedding cache: emb:{sha256(text)}                              TTL: 24 hours
  Cache version:  rag:cv:{tenant_id}
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

import redis.asyncio as aioredis

from app.config import settings

_redis: Optional[aioredis.Redis] = None

CACHE_TTL_SECONDS = 3600       # 1 hour for query cache
EMBEDDING_TTL_SECONDS = 86400  # 24 hours for embedding cache


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


# ---------------------------------------------------------------------------
# Cache version helpers (for cache invalidation on document ingestion)
# ---------------------------------------------------------------------------

def _version_key(tenant_id: str) -> str:
    return f"rag:cv:{tenant_id}"


async def get_tenant_cache_version(tenant_id: str) -> int:
    """Get current cache version for tenant (default 0)."""
    try:
        r = _get_redis()
        value = await r.get(_version_key(tenant_id))
        return int(value) if value is not None else 0
    except Exception:
        return 0


async def invalidate_tenant_query_cache(tenant_id: str) -> None:
    """Increment tenant cache version, making all existing cached queries stale."""
    try:
        r = _get_redis()
        await r.incr(_version_key(tenant_id))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Query cache
# ---------------------------------------------------------------------------

async def _cache_key(tenant_id: str, query: str) -> str:
    version = await get_tenant_cache_version(tenant_id)
    raw = f"{tenant_id}:{query.strip().lower()}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"rag:query:{version}:{digest}"


async def get_cached_response(tenant_id: str, query: str) -> Optional[dict]:
    """Return cached response dict or None."""
    try:
        r = _get_redis()
        key = await _cache_key(tenant_id, query)
        value = await r.get(key)
        if value:
            return json.loads(value)
    except Exception:
        pass  # cache miss on any error
    return None


async def set_cached_response(tenant_id: str, query: str, response: dict) -> None:
    """Cache response dict. Silently ignores errors."""
    try:
        r = _get_redis()
        key = await _cache_key(tenant_id, query)
        await r.setex(key, CACHE_TTL_SECONDS, json.dumps(response))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Embedding cache
# ---------------------------------------------------------------------------

def _embedding_key(text: str) -> str:
    digest = hashlib.sha256(text.encode()).hexdigest()
    return f"emb:{digest}"


async def get_cached_embedding(text: str) -> Optional[list[float]]:
    """Return cached embedding or None. Key: emb:{sha256(text)}. TTL: 24h."""
    try:
        r = _get_redis()
        value = await r.get(_embedding_key(text))
        if value:
            return json.loads(value)
    except Exception:
        pass
    return None


async def set_cached_embedding(text: str, embedding: list[float]) -> None:
    """Cache embedding. Silently ignores errors."""
    try:
        r = _get_redis()
        await r.setex(_embedding_key(text), EMBEDDING_TTL_SECONDS, json.dumps(embedding))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
