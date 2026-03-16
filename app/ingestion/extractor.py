"""
Text extraction from uploaded documents.
Supported formats: PDF, Markdown, plain text.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

from app.common.exceptions import ValidationError
from app.common.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ExtractedDocument:
    text: str
    page_count: int = 1
    metadata: dict = field(default_factory=dict)


def extract(data: bytes, content_type: str, filename: str) -> ExtractedDocument:
    """Dispatch to the right extractor based on content_type."""
    if content_type == "application/pdf":
        return _extract_pdf(data, filename)
    if content_type in ("text/markdown", "text/plain", "text/x-markdown"):
        return _extract_text(data, filename)
    raise ValidationError(f"Unsupported content type: {content_type}")


def _extract_pdf(data: bytes, filename: str) -> ExtractedDocument:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError("pypdf is required for PDF extraction") from e

    reader = PdfReader(io.BytesIO(data))
    pages: list[str] = []

    for page in reader.pages:
        text = page.extract_text() or ""
        # Normalise whitespace without destroying paragraph breaks
        lines = [line.strip() for line in text.splitlines()]
        cleaned = "\n".join(line for line in lines if line)
        if cleaned:
            pages.append(cleaned)

    full_text = "\n\n".join(pages)
    logger.info("pdf_extracted", filename=filename, pages=len(reader.pages), chars=len(full_text))
    return ExtractedDocument(
        text=full_text,
        page_count=len(reader.pages),
        metadata={"page_count": len(reader.pages)},
    )


def _extract_text(data: bytes, filename: str) -> ExtractedDocument:
    # Try UTF-8 first, fall back to latin-1
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")

    logger.info("text_extracted", filename=filename, chars=len(text))
    return ExtractedDocument(text=text, page_count=1, metadata={})
