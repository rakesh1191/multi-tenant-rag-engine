"""
Phase 3 tests — Query pipeline.

Strategy:
  - LLM provider, embedder, and Redis cache are all mocked.
  - A real test DB is used (via conftest fixtures).
  - We insert document_chunks directly via raw SQL (same approach as the
    Celery task) so vector search has data to work with.
  - Tests cover: sync query, streaming query, cache hit, history, auth,
    tenant isolation, and Ollama provider unit tests.
"""
from __future__ import annotations

import json
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, AsyncMock

from tests.conftest import create_tenant_and_admin, auth_headers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_EMBEDDING = [0.1] * 1536  # 1536-dim zero-ish vector

FAKE_LLM_ANSWER = "The answer is 42."
FAKE_TOKEN_USAGE = {"input_tokens": 100, "output_tokens": 20}


def _patch_embedder(mocker):
    """Mock embedder.embed_many to return FAKE_EMBEDDING."""
    mock_embedder = MagicMock()
    mock_embedder.embed_many = AsyncMock(return_value=[FAKE_EMBEDDING])
    mocker.patch("app.query.service.get_embedder", return_value=mock_embedder)
    return mock_embedder


def _patch_llm_sync(mocker):
    """Mock LLM provider.complete to return FAKE_LLM_ANSWER."""
    mock_provider = MagicMock()
    mock_provider.complete = AsyncMock(return_value=(FAKE_LLM_ANSWER, FAKE_TOKEN_USAGE))
    mocker.patch("app.query.service.get_llm_provider", return_value=mock_provider)
    return mock_provider


async def _patch_llm_stream(mocker):
    """Mock LLM provider.stream to yield tokens."""
    tokens = ["The ", "answer ", "is ", "42."]

    async def _fake_stream(query, context):
        for t in tokens:
            yield t

    mock_provider = MagicMock()
    mock_provider.stream = _fake_stream
    mocker.patch("app.query.service.get_llm_provider", return_value=mock_provider)
    return mock_provider


def _patch_cache_miss(mocker):
    mocker.patch("app.query.service.get_cached_response", new_callable=AsyncMock, return_value=None)
    mocker.patch("app.query.service.set_cached_response", new_callable=AsyncMock)


def _patch_cache_hit(mocker, payload: dict):
    mocker.patch("app.query.service.get_cached_response", new_callable=AsyncMock, return_value=payload)
    mocker.patch("app.query.service.set_cached_response", new_callable=AsyncMock)
    mocker.patch("app.query.service._log_query", new_callable=AsyncMock, return_value=uuid.uuid4())


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_sync_requires_auth(client):
    resp = await client.post("/api/v1/query/sync", json={"query": "hello"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_query_stream_requires_auth(client):
    resp = await client.post("/api/v1/query", json={"query": "hello"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_query_history_requires_auth(client):
    resp = await client.get("/api/v1/query/history")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Sync query
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_sync_no_documents(client, mocker):
    """Query with no ingested documents returns an answer with empty sources."""
    _patch_embedder(mocker)
    _patch_llm_sync(mocker)
    _patch_cache_miss(mocker)

    tokens = await create_tenant_and_admin(client, slug="query-sync-empty")
    resp = await client.post(
        "/api/v1/query/sync",
        json={"query": "What is the meaning of life?"},
        headers=auth_headers(tokens["access_token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == FAKE_LLM_ANSWER
    assert data["cache_hit"] is False
    assert "sources" in data
    assert "latency_ms" in data
    assert "query_id" in data


@pytest.mark.asyncio
async def test_query_sync_cache_hit(client, mocker):
    """Second identical query is served from cache."""
    cached_payload = {
        "query_id": str(uuid.uuid4()),
        "answer": "Cached answer.",
        "sources": [],
        "token_usage": {},
        "cache_hit": False,
        "latency_ms": 50,
    }
    _patch_cache_hit(mocker, cached_payload)

    tokens = await create_tenant_and_admin(client, slug="query-cache-test")
    resp = await client.post(
        "/api/v1/query/sync",
        json={"query": "What is the meaning of life?"},
        headers=auth_headers(tokens["access_token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["cache_hit"] is True
    assert data["answer"] == "Cached answer."


@pytest.mark.asyncio
async def test_query_sync_empty_query_rejected(client, mocker):
    tokens = await create_tenant_and_admin(client, slug="query-empty-test")
    resp = await client.post(
        "/api/v1/query/sync",
        json={"query": ""},
        headers=auth_headers(tokens["access_token"]),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Streaming query
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_stream_returns_sse(client, mocker):
    """POST /query returns text/event-stream with data: tokens and [DONE]."""
    _patch_embedder(mocker)
    await _patch_llm_stream(mocker)
    _patch_cache_miss(mocker)

    tokens = await create_tenant_and_admin(client, slug="query-stream-test")
    resp = await client.post(
        "/api/v1/query",
        json={"query": "What is the answer?"},
        headers=auth_headers(tokens["access_token"]),
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert "data:" in body
    assert "[DONE]" in body


@pytest.mark.asyncio
async def test_query_stream_cache_hit_streams_words(client, mocker):
    """Cache hit in streaming mode still yields data: lines."""
    cached_payload = {
        "query_id": str(uuid.uuid4()),
        "answer": "Hello world cached.",
        "sources": [],
        "token_usage": {},
        "cache_hit": True,
        "latency_ms": 5,
    }
    _patch_cache_hit(mocker, cached_payload)

    tokens = await create_tenant_and_admin(client, slug="query-stream-cache")
    resp = await client.post(
        "/api/v1/query",
        json={"query": "cached query"},
        headers=auth_headers(tokens["access_token"]),
    )
    assert resp.status_code == 200
    body = resp.text
    assert "data:" in body
    assert "[DONE]" in body


# ---------------------------------------------------------------------------
# Query history
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_history_empty(client):
    tokens = await create_tenant_and_admin(client, slug="history-empty-test")
    resp = await client.get(
        "/api/v1/query/history",
        headers=auth_headers(tokens["access_token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_query_history_records_query(client, mocker):
    """After a sync query, history returns one entry."""
    _patch_embedder(mocker)
    _patch_llm_sync(mocker)
    _patch_cache_miss(mocker)

    tokens = await create_tenant_and_admin(client, slug="history-record-test")
    await client.post(
        "/api/v1/query/sync",
        json={"query": "Tell me about history."},
        headers=auth_headers(tokens["access_token"]),
    )
    resp = await client.get(
        "/api/v1/query/history",
        headers=auth_headers(tokens["access_token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["query_text"] == "Tell me about history."


@pytest.mark.asyncio
async def test_query_history_tenant_isolation(client, mocker):
    """Tenant A's history is not visible to tenant B."""
    _patch_embedder(mocker)
    _patch_llm_sync(mocker)
    _patch_cache_miss(mocker)

    tenant_a = await create_tenant_and_admin(client, slug="hist-iso-a")
    tenant_b = await create_tenant_and_admin(client, slug="hist-iso-b")

    # Tenant A makes a query
    await client.post(
        "/api/v1/query/sync",
        json={"query": "Tenant A secret query."},
        headers=auth_headers(tenant_a["access_token"]),
    )

    # Tenant B sees 0 history
    resp = await client.get(
        "/api/v1/query/history",
        headers=auth_headers(tenant_b["access_token"]),
    )
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_query_history_pagination(client, mocker):
    """page_size parameter is respected."""
    _patch_embedder(mocker)
    _patch_llm_sync(mocker)
    _patch_cache_miss(mocker)

    tokens = await create_tenant_and_admin(client, slug="hist-page-test")
    # Make 3 queries
    for i in range(3):
        await client.post(
            "/api/v1/query/sync",
            json={"query": f"Query number {i}"},
            headers=auth_headers(tokens["access_token"]),
        )

    resp = await client.get(
        "/api/v1/query/history?page=1&page_size=2",
        headers=auth_headers(tokens["access_token"]),
    )
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["page_size"] == 2


# ---------------------------------------------------------------------------
# Ollama provider unit tests (no network — openai client is mocked)
# ---------------------------------------------------------------------------

class TestOllamaProvider:
    """Unit tests for OllamaProvider — the openai client is fully mocked."""

    def _make_provider(self, mocker, base_url="http://localhost:11434", model="llama3.2"):
        mocker.patch("app.config.settings.OLLAMA_BASE_URL", base_url)
        mocker.patch("app.config.settings.OLLAMA_MODEL", model)
        from app.llm.providers import OllamaProvider
        return OllamaProvider()

    def _mock_completion_response(self, text: str, prompt_tokens: int = 10, completion_tokens: int = 5):
        usage = MagicMock()
        usage.prompt_tokens = prompt_tokens
        usage.completion_tokens = completion_tokens
        choice = MagicMock()
        choice.message.content = text
        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = usage
        return resp

    @pytest.mark.asyncio
    async def test_complete_returns_text_and_usage(self, mocker):
        provider = self._make_provider(mocker)
        fake_resp = self._mock_completion_response("Hello from Ollama!")
        provider._client.chat.completions.create = AsyncMock(return_value=fake_resp)

        text, usage = await provider.complete("What is 2+2?", "context here")

        assert text == "Hello from Ollama!"
        assert usage["input_tokens"] == 10
        assert usage["output_tokens"] == 5

    @pytest.mark.asyncio
    async def test_complete_handles_missing_usage(self, mocker):
        """Ollama sometimes omits usage; provider should return empty dict."""
        provider = self._make_provider(mocker)
        fake_resp = self._mock_completion_response("Answer")
        fake_resp.usage = None
        provider._client.chat.completions.create = AsyncMock(return_value=fake_resp)

        _, usage = await provider.complete("q", "ctx")
        assert usage == {}

    @pytest.mark.asyncio
    async def test_stream_yields_tokens(self, mocker):
        provider = self._make_provider(mocker)

        def _make_chunk(content):
            chunk = MagicMock()
            chunk.choices[0].delta.content = content
            return chunk

        fake_chunks = [_make_chunk(t) for t in ["Hello", " world", "!"]]

        async def _fake_aiter(*args, **kwargs):
            for c in fake_chunks:
                yield c

        provider._client.chat.completions.create = AsyncMock(return_value=_fake_aiter())

        collected = []
        async for token in provider.stream("q", "ctx"):
            collected.append(token)

        assert collected == ["Hello", " world", "!"]

    @pytest.mark.asyncio
    async def test_stream_skips_none_deltas(self, mocker):
        """Chunks with None content (e.g. final chunk) are silently skipped."""
        provider = self._make_provider(mocker)

        chunks = []
        for content in ["Hi", None, "!"]:
            c = MagicMock()
            c.choices[0].delta.content = content
            chunks.append(c)

        async def _fake_aiter(*args, **kwargs):
            for c in chunks:
                yield c

        provider._client.chat.completions.create = AsyncMock(return_value=_fake_aiter())

        collected = [t async for t in provider.stream("q", "ctx")]
        assert collected == ["Hi", "!"]

    def test_factory_returns_ollama_provider(self, mocker):
        """get_llm_provider() returns OllamaProvider when LLM_PROVIDER=ollama."""
        import app.llm.providers as pmod
        pmod._provider = None  # reset singleton
        mocker.patch("app.config.settings.LLM_PROVIDER", "ollama")
        provider = pmod.get_llm_provider()
        from app.llm.providers import OllamaProvider
        assert isinstance(provider, OllamaProvider)
        pmod._provider = None  # clean up for other tests

    def test_ollama_uses_custom_base_url(self, mocker):
        """OllamaProvider points the openai client at OLLAMA_BASE_URL/v1."""
        mocker.patch("app.config.settings.OLLAMA_BASE_URL", "http://myserver:11434")
        mocker.patch("app.config.settings.OLLAMA_MODEL", "mistral")
        from app.llm.providers import OllamaProvider
        p = OllamaProvider()
        assert "myserver:11434" in str(p._client.base_url)
        assert p._model == "mistral"
