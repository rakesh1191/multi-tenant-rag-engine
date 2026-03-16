"""
Phase 4 tests — Production Polish.

Covers:
  1. Rate limiting (allow / block)
  2. Prometheus /metrics endpoint
  3. Deep health check /health/ready (all healthy, DB down, Redis down)
  4. Embedding cache (hit skips embedder, miss calls embedder)
"""
from __future__ import annotations

import uuid
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import create_tenant_and_admin, auth_headers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_EMBEDDING = [0.1] * 1536
FAKE_LLM_ANSWER = "Test answer."
FAKE_TOKEN_USAGE = {"input_tokens": 10, "output_tokens": 5}


def _patch_embedder(mocker):
    mock_embedder = MagicMock()
    mock_embedder.embed_many = AsyncMock(return_value=[FAKE_EMBEDDING])
    mocker.patch("app.query.service.get_embedder", return_value=mock_embedder)
    return mock_embedder


def _patch_llm_sync(mocker):
    mock_provider = MagicMock()
    mock_provider.complete = AsyncMock(return_value=(FAKE_LLM_ANSWER, FAKE_TOKEN_USAGE))
    mocker.patch("app.query.service.get_llm_provider", return_value=mock_provider)
    return mock_provider


def _patch_cache_miss(mocker):
    mocker.patch("app.query.service.get_cached_response", new_callable=AsyncMock, return_value=None)
    mocker.patch("app.query.service.set_cached_response", new_callable=AsyncMock)
    mocker.patch("app.query.service.get_cached_embedding", new_callable=AsyncMock, return_value=None)
    mocker.patch("app.query.service.set_cached_embedding", new_callable=AsyncMock)


# ---------------------------------------------------------------------------
# Feature 1: Rate Limiting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rate_limit_allows_under_threshold(client, mocker):
    """When under the limit, queries go through normally."""
    _patch_embedder(mocker)
    _patch_llm_sync(mocker)
    _patch_cache_miss(mocker)

    # Patch Redis pipeline to simulate zero existing entries (under threshold)
    mock_pipeline = AsyncMock()
    mock_pipeline.zremrangebyscore = AsyncMock()
    mock_pipeline.zcard = AsyncMock()
    mock_pipeline.zadd = AsyncMock()
    mock_pipeline.expire = AsyncMock()
    # zcard returns 0 (no previous requests in window)
    mock_pipeline.execute = AsyncMock(return_value=[None, 0, None, None])

    mock_redis = MagicMock()
    mock_redis.pipeline = MagicMock(return_value=mock_pipeline)

    mocker.patch("app.cache.redis._get_redis", return_value=mock_redis)

    tokens = await create_tenant_and_admin(client, slug="rl-allow-test")
    resp = await client.post(
        "/api/v1/query/sync",
        json={"query": "What is RAG?"},
        headers=auth_headers(tokens["access_token"]),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_rate_limit_blocks_over_threshold(client, mocker):
    """When over the limit, the endpoint returns 429."""
    # Patch Redis pipeline to simulate limit already exceeded
    mock_pipeline = AsyncMock()
    mock_pipeline.zremrangebyscore = AsyncMock()
    mock_pipeline.zcard = AsyncMock()
    mock_pipeline.zadd = AsyncMock()
    mock_pipeline.expire = AsyncMock()
    # zcard returns 60 (already at max_calls=60)
    mock_pipeline.execute = AsyncMock(return_value=[None, 60, None, None])

    mock_redis = MagicMock()
    mock_redis.pipeline = MagicMock(return_value=mock_pipeline)

    mocker.patch("app.cache.redis._get_redis", return_value=mock_redis)

    tokens = await create_tenant_and_admin(client, slug="rl-block-test")
    resp = await client.post(
        "/api/v1/query/sync",
        json={"query": "What is RAG?"},
        headers=auth_headers(tokens["access_token"]),
    )
    assert resp.status_code == 429


# ---------------------------------------------------------------------------
# Feature 2: Prometheus Metrics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_metrics_endpoint_returns_200(client):
    """GET /metrics should return 200 with Prometheus text format."""
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    # prometheus_client generates text/plain; charset=utf-8
    assert "text/plain" in resp.headers["content-type"]
    # The response should contain at least some prometheus-format lines
    assert "# HELP" in resp.text or "# TYPE" in resp.text or resp.text == ""


# ---------------------------------------------------------------------------
# Feature 3: Deep Health Check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_ready_all_healthy(client, mocker):
    """When DB, Redis, and S3 all respond OK, return 200 with all statuses ok."""
    # Mock DB engine connect — patch where get_engine is imported from
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    mock_engine = MagicMock()
    mock_engine.connect = MagicMock(return_value=mock_conn)

    mocker.patch("app.common.database.get_engine", return_value=mock_engine)

    # Mock Redis ping
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mocker.patch("app.cache.redis._get_redis", return_value=mock_redis)

    # Mock S3 head_bucket
    mock_s3_client = AsyncMock()
    mock_s3_client.head_bucket = AsyncMock()
    mock_s3_client.__aenter__ = AsyncMock(return_value=mock_s3_client)
    mock_s3_client.__aexit__ = AsyncMock(return_value=False)

    mocker.patch("app.common.storage.get_s3_client", MagicMock(return_value=mock_s3_client))

    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["checks"]["database"]["status"] == "ok"
    assert data["checks"]["redis"]["status"] == "ok"
    assert data["checks"]["storage"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_ready_db_down(client, mocker):
    """When DB is down, return 503 with database status error."""
    # Mock DB engine to raise
    mock_engine = MagicMock()
    mock_engine.connect = MagicMock(side_effect=Exception("Connection refused"))
    mocker.patch("app.common.database.get_engine", return_value=mock_engine)

    # Mock Redis ping OK
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mocker.patch("app.cache.redis._get_redis", return_value=mock_redis)

    # Mock S3 OK
    mock_s3_client = AsyncMock()
    mock_s3_client.head_bucket = AsyncMock()
    mock_s3_client.__aenter__ = AsyncMock(return_value=mock_s3_client)
    mock_s3_client.__aexit__ = AsyncMock(return_value=False)
    mocker.patch("app.common.storage.get_s3_client", MagicMock(return_value=mock_s3_client))

    resp = await client.get("/health/ready")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["checks"]["database"]["status"] == "error"


@pytest.mark.asyncio
async def test_health_ready_redis_down(client, mocker):
    """When Redis is down, return 503 with redis status error."""
    # Mock DB OK
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_engine = MagicMock()
    mock_engine.connect = MagicMock(return_value=mock_conn)
    mocker.patch("app.common.database.get_engine", return_value=mock_engine)

    # Mock Redis to raise
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(side_effect=Exception("Redis connection refused"))
    mocker.patch("app.cache.redis._get_redis", return_value=mock_redis)

    # Mock S3 OK
    mock_s3_client = AsyncMock()
    mock_s3_client.head_bucket = AsyncMock()
    mock_s3_client.__aenter__ = AsyncMock(return_value=mock_s3_client)
    mock_s3_client.__aexit__ = AsyncMock(return_value=False)
    mocker.patch("app.common.storage.get_s3_client", MagicMock(return_value=mock_s3_client))

    resp = await client.get("/health/ready")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["checks"]["redis"]["status"] == "error"


# ---------------------------------------------------------------------------
# Feature 4: Embedding Cache
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_embedding_cache_hit_skips_embedder(client, mocker):
    """When embedding cache returns a vector, the embedder is NOT called."""
    # Patch embedding cache to return a cached vector
    mocker.patch(
        "app.query.service.get_cached_embedding",
        new_callable=AsyncMock,
        return_value=FAKE_EMBEDDING,
    )
    mocker.patch("app.query.service.set_cached_embedding", new_callable=AsyncMock)

    # Patch query cache (miss so the full pipeline runs)
    mocker.patch("app.query.service.get_cached_response", new_callable=AsyncMock, return_value=None)
    mocker.patch("app.query.service.set_cached_response", new_callable=AsyncMock)

    # Patch LLM
    _patch_llm_sync(mocker)

    # Patch embedder — should NOT be called
    mock_embedder = MagicMock()
    mock_embedder.embed_many = AsyncMock(return_value=[FAKE_EMBEDDING])
    mock_get_embedder = mocker.patch("app.query.service.get_embedder", return_value=mock_embedder)

    tokens = await create_tenant_and_admin(client, slug="emb-cache-hit")
    resp = await client.post(
        "/api/v1/query/sync",
        json={"query": "What is RAG?"},
        headers=auth_headers(tokens["access_token"]),
    )
    assert resp.status_code == 200
    # get_embedder should not have been called because cache returned embedding
    mock_get_embedder.assert_not_called()


@pytest.mark.asyncio
async def test_embedding_cache_miss_calls_embedder(client, mocker):
    """When embedding cache returns None, the embedder IS called."""
    # Patch embedding cache to return None (miss)
    mocker.patch(
        "app.query.service.get_cached_embedding",
        new_callable=AsyncMock,
        return_value=None,
    )
    mocker.patch("app.query.service.set_cached_embedding", new_callable=AsyncMock)

    # Patch query cache (miss)
    mocker.patch("app.query.service.get_cached_response", new_callable=AsyncMock, return_value=None)
    mocker.patch("app.query.service.set_cached_response", new_callable=AsyncMock)

    # Patch LLM
    _patch_llm_sync(mocker)

    # Patch embedder — SHOULD be called
    mock_embedder = MagicMock()
    mock_embedder.embed_many = AsyncMock(return_value=[FAKE_EMBEDDING])
    mock_get_embedder = mocker.patch("app.query.service.get_embedder", return_value=mock_embedder)

    tokens = await create_tenant_and_admin(client, slug="emb-cache-miss")
    resp = await client.post(
        "/api/v1/query/sync",
        json={"query": "What is RAG?"},
        headers=auth_headers(tokens["access_token"]),
    )
    assert resp.status_code == 200
    # get_embedder should have been called because cache was a miss
    mock_get_embedder.assert_called_once()
    mock_embedder.embed_many.assert_awaited_once()
