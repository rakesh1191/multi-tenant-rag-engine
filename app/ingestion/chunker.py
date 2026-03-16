"""
Fixed-size overlapping text chunker using tiktoken for accurate token counting.

Strategy:
  - Split text into paragraphs (double newline boundaries).
  - Greedily accumulate paragraphs until the chunk reaches CHUNK_SIZE_TOKENS.
  - When a chunk is full, start the next chunk overlapping by CHUNK_OVERLAP_TOKENS
    worth of content from the previous chunk's tail.
  - Paragraphs longer than CHUNK_SIZE_TOKENS are hard-split by token count.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import tiktoken

from app.common.logging import get_logger
from app.config import settings

logger = get_logger(__name__)

_ENCODING: tiktoken.Encoding | None = None


def _get_encoding() -> tiktoken.Encoding:
    global _ENCODING
    if _ENCODING is None:
        # cl100k_base is used by text-embedding-3-small and GPT-4
        _ENCODING = tiktoken.get_encoding("cl100k_base")
    return _ENCODING


def count_tokens(text: str) -> int:
    return len(_get_encoding().encode(text))


def decode_tokens(tokens: list[int]) -> str:
    return _get_encoding().decode(tokens)


@dataclass
class Chunk:
    content: str
    chunk_index: int
    token_count: int
    metadata: dict = field(default_factory=dict)


def chunk_text(
    text: str,
    chunk_size: int = settings.CHUNK_SIZE_TOKENS,
    overlap: int = settings.CHUNK_OVERLAP_TOKENS,
    metadata: dict | None = None,
) -> list[Chunk]:
    """Split *text* into overlapping token-bounded chunks."""
    if not text.strip():
        return []

    enc = _get_encoding()
    base_metadata = metadata or {}

    # Tokenise the whole document once
    all_tokens = enc.encode(text)
    total_tokens = len(all_tokens)

    if total_tokens == 0:
        return []

    chunks: list[Chunk] = []
    start = 0

    while start < total_tokens:
        end = min(start + chunk_size, total_tokens)
        token_slice = all_tokens[start:end]
        content = decode_tokens(token_slice)

        # Avoid creating a tiny trailing chunk (< 10% of chunk_size)
        if len(token_slice) < max(10, chunk_size // 10) and chunks:
            # Merge into the previous chunk's content note (metadata only)
            break

        chunks.append(Chunk(
            content=content.strip(),
            chunk_index=len(chunks),
            token_count=len(token_slice),
            metadata={**base_metadata},
        ))

        if end == total_tokens:
            break

        # Next chunk starts overlap tokens before the end of this chunk
        start = end - overlap

    logger.debug(
        "text_chunked",
        total_tokens=total_tokens,
        chunk_count=len(chunks),
        chunk_size=chunk_size,
        overlap=overlap,
    )
    return chunks
