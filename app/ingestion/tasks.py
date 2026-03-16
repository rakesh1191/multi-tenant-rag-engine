"""
Celery tasks for async document ingestion pipeline.

process_document(document_id)
  1. Download raw file from MinIO
  2. Extract text
  3. Chunk text
  4. Embed chunks (batched, with retry)
  5. Persist chunks + vectors to PostgreSQL
  6. Update document status
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from celery import Celery
from sqlalchemy import select, update, delete

from app.config import settings

celery_app = Celery(
    "rag_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    task_acks_late=True,           # acknowledge only after task completes
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,   # one task at a time per worker
)


def _run(coro):
    """Run an async coroutine from a sync Celery task."""
    return asyncio.get_event_loop().run_until_complete(coro)


@celery_app.task(
    bind=True,
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
    default_retry_delay=30,
    name="ingestion.process_document",
)
def process_document(self, document_id: str) -> dict:
    """
    Orchestrates the full ingestion pipeline for a single document.
    Runs synchronously inside Celery; uses asyncio.run for async DB/S3 calls.
    """
    try:
        return _run(_process(document_id))
    except Exception as exc:
        raise self.retry(exc=exc)


async def _process(document_id_str: str) -> dict:
    """Async implementation of the ingestion pipeline."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    # Import ALL models so SQLAlchemy can resolve cross-table foreign keys
    import app.auth.models  # noqa: F401 — registers Tenant, User in metadata
    from app.documents.models import Document, DocumentChunk
    from app.common import storage
    from app.ingestion.extractor import extract
    from app.ingestion.chunker import chunk_text
    from app.ingestion.embedder import get_embedder
    from app.common.logging import get_logger

    logger = get_logger(__name__)
    doc_id = uuid.UUID(document_id_str)

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with Session() as db:
            # Fetch document
            result = await db.execute(select(Document).where(Document.id == doc_id))
            doc = result.scalar_one_or_none()
            if not doc:
                logger.error("process_document_not_found", document_id=document_id_str)
                return {"status": "not_found"}

            # Mark as processing
            doc.status = "processing"
            doc.updated_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("ingestion_started", document_id=document_id_str, filename=doc.filename)

            # 1. Download raw bytes from MinIO
            raw_bytes = await storage.download_file(doc.s3_key)

            # 2. Extract text
            extracted = extract(raw_bytes, doc.content_type, doc.filename)
            if not extracted.text.strip():
                raise ValueError("Extracted text is empty — document may be image-only or corrupt")

            # 3. Chunk text
            chunks = chunk_text(
                extracted.text,
                metadata={"source": doc.filename, **extracted.metadata},
            )
            if not chunks:
                raise ValueError("No chunks produced from document")

            # 4. Embed chunks
            embedder = get_embedder()
            texts = [c.content for c in chunks]
            vectors = await embedder.embed_many(texts)

            # 5. Delete any stale chunks (re-processing case)
            await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))

            # 6. Persist chunks + vectors
            # embedding and metadata are inlined as literals to avoid asyncpg
            # named-param / ::cast syntax conflicts ($n vs :name)
            import json as _json
            from sqlalchemy import text as sa_text

            for chunk, vector in zip(chunks, vectors):
                vector_literal = "[" + ",".join(str(v) for v in vector) + "]"
                metadata_literal = _json.dumps(chunk.metadata).replace("'", "''")
                sql = (
                    "INSERT INTO document_chunks "
                    "(id, document_id, tenant_id, chunk_index, content, embedding, token_count, metadata, created_at) "
                    f"VALUES (:id, :document_id, :tenant_id, :chunk_index, :content, '{vector_literal}'::vector, "
                    f":token_count, '{metadata_literal}'::jsonb, :created_at)"
                )
                await db.execute(
                    sa_text(sql),
                    {
                        "id": str(uuid.uuid4()),
                        "document_id": str(doc_id),
                        "tenant_id": str(doc.tenant_id),
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.content,
                        "token_count": chunk.token_count,
                        "created_at": datetime.now(timezone.utc),
                    },
                )

            # 7. Update document to ready
            doc.status = "ready"
            doc.chunk_count = len(chunks)
            doc.metadata_ = {**doc.metadata_, **extracted.metadata}
            doc.updated_at = datetime.now(timezone.utc)
            await db.commit()

            # 8. Post-ingestion: emit metrics and invalidate query cache
            try:
                from app.common.metrics import documents_ingested_total, inc_tokens
                documents_ingested_total.labels(tenant_id=str(doc.tenant_id)).inc()
                # Approximate token count from embedding texts
                total_tokens = sum(len(t.split()) for t in texts)
                inc_tokens(settings.EMBEDDING_PROVIDER, total_tokens, 0)
            except Exception:
                pass

            try:
                from app.cache.redis import invalidate_tenant_query_cache
                await invalidate_tenant_query_cache(str(doc.tenant_id))
            except Exception:
                pass

            logger.info(
                "ingestion_complete",
                document_id=document_id_str,
                chunks=len(chunks),
                filename=doc.filename,
            )
            return {"status": "ready", "chunks": len(chunks)}

    except Exception as exc:
        # Mark document as failed
        try:
            async with Session() as db:
                result = await db.execute(select(Document).where(Document.id == doc_id))
                doc = result.scalar_one_or_none()
                if doc:
                    doc.status = "failed"
                    doc.error_message = str(exc)[:1000]
                    doc.updated_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            pass

        get_logger(__name__).error(
            "ingestion_failed", document_id=document_id_str, error=str(exc)
        )
        raise

    finally:
        await engine.dispose()
