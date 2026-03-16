"""
Embedding provider abstraction.

Supports OpenAI text-embedding-3-small (default).
Batches up to 100 texts per API call.
Retries with exponential backoff on rate-limit / transient errors.
"""
from __future__ import annotations

import asyncio
import time
from typing import Protocol

from app.common.logging import get_logger
from app.config import settings

logger = get_logger(__name__)

# Max texts per OpenAI embedding API call
_OPENAI_BATCH_SIZE = 100
# Retry configuration
_MAX_RETRIES = 5
_BASE_DELAY = 1.0  # seconds


class EmbeddingProvider(Protocol):
    async def embed_many(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_one(self, text: str) -> list[float]: ...


class OpenAIEmbedder:
    """OpenAI embeddings with batching and exponential-backoff retry."""

    def __init__(self) -> None:
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self._model = settings.EMBEDDING_MODEL

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        for batch_start in range(0, len(texts), _OPENAI_BATCH_SIZE):
            batch = texts[batch_start: batch_start + _OPENAI_BATCH_SIZE]
            embeddings = await self._embed_batch_with_retry(batch)
            all_embeddings.extend(embeddings)

        logger.info("embeddings_created", count=len(texts), model=self._model)
        return all_embeddings

    async def embed_one(self, text: str) -> list[float]:
        results = await self.embed_many([text])
        return results[0]

    async def _embed_batch_with_retry(self, texts: list[str]) -> list[list[float]]:
        from openai import RateLimitError, APIError

        delay = _BASE_DELAY
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self._client.embeddings.create(
                    model=self._model,
                    input=texts,
                )
                # Sort by index to guarantee ordering
                items = sorted(response.data, key=lambda d: d.index)
                return [item.embedding for item in items]

            except RateLimitError:
                if attempt == _MAX_RETRIES:
                    raise
                logger.warning("embedding_rate_limited", attempt=attempt, retry_in=delay)
                await asyncio.sleep(delay)
                delay *= 2

            except APIError as e:
                if attempt == _MAX_RETRIES:
                    raise
                logger.warning("embedding_api_error", error=str(e), attempt=attempt, retry_in=delay)
                await asyncio.sleep(delay)
                delay *= 2

        raise RuntimeError("Embedding failed after all retries")  # unreachable


class OllamaEmbedder:
    """Ollama local embeddings via /api/embed endpoint."""

    def __init__(self) -> None:
        import httpx
        self._base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self._model = settings.OLLAMA_EMBEDDING_MODEL
        self._client = httpx.AsyncClient(timeout=120.0)

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        results: list[list[float]] = []
        for text in texts:
            embedding = await self._embed_one_with_retry(text)
            results.append(embedding)
        logger.info("ollama_embeddings_created", count=len(texts), model=self._model)
        return results

    async def embed_one(self, text: str) -> list[float]:
        return await self._embed_one_with_retry(text)

    async def _embed_one_with_retry(self, text: str) -> list[float]:
        delay = _BASE_DELAY
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = await self._client.post(
                    f"{self._base_url}/api/embed",
                    json={"model": self._model, "input": text},
                )
                resp.raise_for_status()
                data = resp.json()
                return data["embeddings"][0]
            except Exception as exc:
                if attempt == _MAX_RETRIES:
                    raise
                logger.warning("ollama_embed_error", error=str(exc), attempt=attempt)
                await asyncio.sleep(delay)
                delay *= 2
        raise RuntimeError("Ollama embedding failed after all retries")  # unreachable


def get_embedder() -> EmbeddingProvider:
    """Factory — extend here to add Voyage, Cohere, etc."""
    provider = settings.EMBEDDING_PROVIDER.lower()
    if provider == "openai":
        return OpenAIEmbedder()
    if provider == "ollama":
        return OllamaEmbedder()
    raise ValueError(f"Unknown embedding provider: {provider}")
