"""
Unit tests for ingestion pipeline components.
No real S3, DB, or LLM calls — all I/O is mocked or in-memory.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.ingestion.extractor import extract, ExtractedDocument
from app.ingestion.chunker import chunk_text, count_tokens, Chunk


# ---------------------------------------------------------------------------
# Extractor tests
# ---------------------------------------------------------------------------

class TestExtractor:
    def test_extract_plain_text(self):
        data = b"Hello world. This is a test document."
        result = extract(data, "text/plain", "test.txt")
        assert isinstance(result, ExtractedDocument)
        assert "Hello world" in result.text
        assert result.page_count == 1

    def test_extract_markdown(self):
        data = b"# Title\n\nSome **markdown** content."
        result = extract(data, "text/markdown", "doc.md")
        assert "Title" in result.text
        assert result.page_count == 1

    def test_extract_latin1_fallback(self):
        data = "caf\xe9".encode("latin-1")  # 'café' in latin-1
        result = extract(data, "text/plain", "latin.txt")
        assert "caf" in result.text

    def test_extract_unsupported_type_raises(self):
        from app.common.exceptions import ValidationError
        with pytest.raises(ValidationError):
            extract(b"data", "application/zip", "file.zip")

    def test_extract_pdf(self):
        """Integration: create a minimal PDF in memory and extract it."""
        try:
            from pypdf import PdfWriter
            import io
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            buf = io.BytesIO()
            writer.write(buf)
            pdf_bytes = buf.getvalue()
            result = extract(pdf_bytes, "application/pdf", "blank.pdf")
            assert result.page_count == 1
            # Blank page has no text — just assert no exception
        except ImportError:
            pytest.skip("pypdf not installed")


# ---------------------------------------------------------------------------
# Chunker tests
# ---------------------------------------------------------------------------

class TestChunker:
    def test_empty_text_returns_no_chunks(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_short_text_single_chunk(self):
        text = "This is a short sentence."
        chunks = chunk_text(text, chunk_size=512, overlap=64)
        assert len(chunks) == 1
        assert chunks[0].chunk_index == 0
        assert "short sentence" in chunks[0].content

    def test_chunk_indices_are_sequential(self):
        text = " ".join(["word"] * 2000)
        chunks = chunk_text(text, chunk_size=200, overlap=20)
        assert len(chunks) > 1
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_chunk_token_counts_within_bounds(self):
        text = " ".join(["token"] * 1000)
        chunk_size = 100
        chunks = chunk_text(text, chunk_size=chunk_size, overlap=10)
        for chunk in chunks:
            assert chunk.token_count <= chunk_size
            assert chunk.token_count > 0

    def test_overlap_means_content_repeats(self):
        """Consecutive chunks must share tokens due to overlap."""
        text = " ".join([f"word{i}" for i in range(500)])
        chunks = chunk_text(text, chunk_size=100, overlap=20)
        if len(chunks) < 2:
            pytest.skip("Not enough chunks to test overlap")
        # The tail of chunk[0] should appear in the head of chunk[1]
        tail_words = chunks[0].content.split()[-5:]
        head_text = chunks[1].content
        assert any(w in head_text for w in tail_words)

    def test_metadata_propagated_to_all_chunks(self):
        text = " ".join(["word"] * 600)
        meta = {"source": "test.txt", "page_count": 3}
        chunks = chunk_text(text, chunk_size=100, overlap=10, metadata=meta)
        for chunk in chunks:
            assert chunk.metadata["source"] == "test.txt"
            assert chunk.metadata["page_count"] == 3

    def test_count_tokens_accuracy(self):
        text = "hello world"
        n = count_tokens(text)
        assert isinstance(n, int)
        assert n >= 2  # at least 2 tokens

    def test_large_document_produces_many_chunks(self):
        # ~5000 words ≈ ~6500 tokens → expect ~13 chunks at size=512
        text = " ".join(["word"] * 5000)
        chunks = chunk_text(text, chunk_size=512, overlap=64)
        assert len(chunks) >= 10

    def test_chunk_content_is_not_empty(self):
        text = "Hello. " * 200
        chunks = chunk_text(text, chunk_size=50, overlap=10)
        for chunk in chunks:
            assert chunk.content.strip() != ""


# ---------------------------------------------------------------------------
# Upload endpoint tests (integration — real test DB, mocked S3 + Celery)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_valid_text_file(client, mocker):
    """Upload a plain text file — S3 upload and Celery task are mocked."""
    mocker.patch("app.common.storage.ensure_bucket_exists", new_callable=AsyncMock)
    mocker.patch("app.common.storage.upload_file", new_callable=AsyncMock, return_value="key")
    mocker.patch("app.common.storage.delete_file", new_callable=AsyncMock)
    mocker.patch("app.ingestion.tasks.process_document.delay", return_value=MagicMock())

    from tests.conftest import create_tenant_and_admin, auth_headers
    tokens = await create_tenant_and_admin(client, slug="upload-test")

    content = b"This is a test document with some content for ingestion."
    resp = await client.post(
        "/api/v1/documents/upload",
        headers=auth_headers(tokens["access_token"]),
        files={"file": ("test.txt", content, "text/plain")},
    )
    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert data["status"] == "pending"
    assert data["filename"] == "test.txt"
    assert "document_id" in data


@pytest.mark.asyncio
async def test_upload_unsupported_type_rejected(client, mocker):
    mocker.patch("app.common.storage.ensure_bucket_exists", new_callable=AsyncMock)

    from tests.conftest import create_tenant_and_admin, auth_headers
    tokens = await create_tenant_and_admin(client, slug="upload-type-test")

    resp = await client.post(
        "/api/v1/documents/upload",
        headers=auth_headers(tokens["access_token"]),
        files={"file": ("evil.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_empty_file_rejected(client, mocker):
    mocker.patch("app.common.storage.ensure_bucket_exists", new_callable=AsyncMock)

    from tests.conftest import create_tenant_and_admin, auth_headers
    tokens = await create_tenant_and_admin(client, slug="upload-empty-test")

    resp = await client.post(
        "/api/v1/documents/upload",
        headers=auth_headers(tokens["access_token"]),
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_requires_auth(client):
    content = b"some content"
    resp = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("doc.txt", content, "text/plain")},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_uploaded_document_appears_in_list(client, mocker):
    mocker.patch("app.common.storage.ensure_bucket_exists", new_callable=AsyncMock)
    mocker.patch("app.common.storage.upload_file", new_callable=AsyncMock, return_value="key")
    mocker.patch("app.common.storage.delete_file", new_callable=AsyncMock)
    mocker.patch("app.ingestion.tasks.process_document.delay", return_value=MagicMock())

    from tests.conftest import create_tenant_and_admin, auth_headers
    tokens = await create_tenant_and_admin(client, slug="upload-list-test")

    await client.post(
        "/api/v1/documents/upload",
        headers=auth_headers(tokens["access_token"]),
        files={"file": ("report.txt", b"Report content.", "text/plain")},
    )

    resp = await client.get(
        "/api/v1/documents",
        headers=auth_headers(tokens["access_token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["filename"] == "report.txt"
    assert data["items"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_delete_document(client, mocker):
    mocker.patch("app.common.storage.ensure_bucket_exists", new_callable=AsyncMock)
    mocker.patch("app.common.storage.upload_file", new_callable=AsyncMock, return_value="key")
    mocker.patch("app.common.storage.delete_file", new_callable=AsyncMock)
    mocker.patch("app.ingestion.tasks.process_document.delay", return_value=MagicMock())

    from tests.conftest import create_tenant_and_admin, auth_headers
    tokens = await create_tenant_and_admin(client, slug="delete-doc-test")

    upload = await client.post(
        "/api/v1/documents/upload",
        headers=auth_headers(tokens["access_token"]),
        files={"file": ("todel.txt", b"delete me", "text/plain")},
    )
    doc_id = upload.json()["document_id"]

    del_resp = await client.delete(
        f"/api/v1/documents/{doc_id}",
        headers=auth_headers(tokens["access_token"]),
    )
    assert del_resp.status_code == 204

    get_resp = await client.get(
        f"/api/v1/documents/{doc_id}",
        headers=auth_headers(tokens["access_token"]),
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_document_tenant_isolation(client, mocker):
    """Tenant A cannot access or delete tenant B's documents."""
    mocker.patch("app.common.storage.ensure_bucket_exists", new_callable=AsyncMock)
    mocker.patch("app.common.storage.upload_file", new_callable=AsyncMock, return_value="key")
    mocker.patch("app.common.storage.delete_file", new_callable=AsyncMock)
    mocker.patch("app.ingestion.tasks.process_document.delay", return_value=MagicMock())

    from tests.conftest import create_tenant_and_admin, auth_headers
    tenant_a = await create_tenant_and_admin(client, slug="doc-iso-a")
    tenant_b = await create_tenant_and_admin(client, slug="doc-iso-b")

    # Tenant B uploads a document
    upload = await client.post(
        "/api/v1/documents/upload",
        headers=auth_headers(tenant_b["access_token"]),
        files={"file": ("secret.txt", b"tenant B secret", "text/plain")},
    )
    doc_id = upload.json()["document_id"]

    # Tenant A cannot read it
    resp = await client.get(
        f"/api/v1/documents/{doc_id}",
        headers=auth_headers(tenant_a["access_token"]),
    )
    assert resp.status_code == 404

    # Tenant A cannot delete it
    resp = await client.delete(
        f"/api/v1/documents/{doc_id}",
        headers=auth_headers(tenant_a["access_token"]),
    )
    assert resp.status_code == 404
