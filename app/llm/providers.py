"""
LLM provider abstraction.

Supports Anthropic (claude-*), OpenAI (gpt-*), and Ollama (local models)
behind a common interface. Provider is selected by settings.LLM_PROVIDER:
  "anthropic" | "openai" | "ollama"

Each provider exposes:
  - complete(prompt, context) -> (str, dict)   (non-streaming)
  - stream(prompt, context) -> AsyncIterator[str]  (token-by-token)
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Optional

from app.config import settings


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    SYSTEM_PROMPT = (
        "You are a helpful assistant. Answer the user's question using only the "
        "context provided below. If the context does not contain enough information "
        "to answer, say so clearly. Do not fabricate facts.\n\n"
        "Context:\n{context}"
    )

    def _build_system(self, context: str) -> str:
        return self.SYSTEM_PROMPT.format(context=context)

    @abstractmethod
    async def complete(self, query: str, context: str) -> tuple[str, dict]:
        """Return (response_text, token_usage)."""

    @abstractmethod
    async def stream(self, query: str, context: str) -> AsyncIterator[str]:
        """Yield response tokens one by one."""


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

class AnthropicProvider(LLMProvider):
    def __init__(self) -> None:
        import anthropic  # lazy import so missing key doesn't break startup
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def complete(self, query: str, context: str) -> tuple[str, dict]:
        msg = await self._client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=settings.LLM_MAX_TOKENS,
            system=self._build_system(context),
            messages=[{"role": "user", "content": query}],
        )
        text = msg.content[0].text
        usage = {
            "input_tokens": msg.usage.input_tokens,
            "output_tokens": msg.usage.output_tokens,
        }
        return text, usage

    async def stream(self, query: str, context: str) -> AsyncIterator[str]:
        async with self._client.messages.stream(
            model=settings.LLM_MODEL,
            max_tokens=settings.LLM_MAX_TOKENS,
            system=self._build_system(context),
            messages=[{"role": "user", "content": query}],
        ) as s:
            async for token in s.text_stream:
                yield token


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

class OpenAIProvider(LLMProvider):
    def __init__(self) -> None:
        import openai  # lazy import
        self._client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self._model = settings.LLM_MODEL if settings.LLM_MODEL.startswith("gpt") else "gpt-4o-mini"

    async def complete(self, query: str, context: str) -> tuple[str, dict]:
        resp = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=settings.LLM_MAX_TOKENS,
            temperature=settings.LLM_TEMPERATURE,
            messages=[
                {"role": "system", "content": self._build_system(context)},
                {"role": "user", "content": query},
            ],
        )
        text = resp.choices[0].message.content or ""
        usage = {
            "input_tokens": resp.usage.prompt_tokens,
            "output_tokens": resp.usage.completion_tokens,
        }
        return text, usage

    async def stream(self, query: str, context: str) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=settings.LLM_MAX_TOKENS,
            temperature=settings.LLM_TEMPERATURE,
            stream=True,
            messages=[
                {"role": "system", "content": self._build_system(context)},
                {"role": "user", "content": query},
            ],
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


# ---------------------------------------------------------------------------
# Ollama (local — OpenAI-compatible API at /v1)
# ---------------------------------------------------------------------------

class OllamaProvider(LLMProvider):
    """
    Ollama local LLM provider.

    Ollama exposes an OpenAI-compatible REST API at /v1/chat/completions,
    so the openai Python client works with a custom base_url.

    No API key is required. Set OLLAMA_BASE_URL (default: http://localhost:11434)
    and OLLAMA_MODEL (default: llama3.2) in your environment.
    """

    def __init__(self) -> None:
        import openai  # lazy import — openai is already a project dependency
        self._client = openai.AsyncOpenAI(
            api_key="ollama",  # Ollama ignores the key but the client requires a non-empty value
            base_url=f"{settings.OLLAMA_BASE_URL.rstrip('/')}/v1",
        )
        self._model = settings.OLLAMA_MODEL

    async def complete(self, query: str, context: str) -> tuple[str, dict]:
        resp = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=settings.LLM_MAX_TOKENS,
            temperature=settings.LLM_TEMPERATURE,
            messages=[
                {"role": "system", "content": self._build_system(context)},
                {"role": "user", "content": query},
            ],
        )
        text = resp.choices[0].message.content or ""
        # Ollama may omit usage; default to empty dict if missing
        usage: dict = {}
        if resp.usage:
            usage = {
                "input_tokens": resp.usage.prompt_tokens,
                "output_tokens": resp.usage.completion_tokens,
            }
        return text, usage

    async def stream(self, query: str, context: str) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=settings.LLM_MAX_TOKENS,
            temperature=settings.LLM_TEMPERATURE,
            stream=True,
            messages=[
                {"role": "system", "content": self._build_system(context)},
                {"role": "user", "content": query},
            ],
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_provider: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        if settings.LLM_PROVIDER == "openai":
            _provider = OpenAIProvider()
        elif settings.LLM_PROVIDER == "ollama":
            _provider = OllamaProvider()
        else:
            _provider = AnthropicProvider()
    return _provider
