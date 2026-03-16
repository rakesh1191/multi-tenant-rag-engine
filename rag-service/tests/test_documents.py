"""Document endpoint tests - Phase 2 placeholder."""
import pytest
from httpx import AsyncClient
from typing import Dict

pytestmark = pytest.mark.asyncio


async def test_documents_upload_returns_501(client: AsyncClient, auth_headers: Dict):
    """Phase 2 placeholder: upload endpoint should return 501 Not Implemented."""
    response = await client.post(
        "/api/v1/documents/",
        headers=auth_headers,
        # Minimal multipart form — the endpoint returns 501 before processing
        content=b"",
    )
    # 501 or 422 (missing required 'file' field) are both acceptable for Phase 1
    assert response.status_code in (501, 422), response.text


async def test_documents_list_returns_501(client: AsyncClient, auth_headers: Dict):
    """Phase 2 placeholder: list endpoint should return 501 Not Implemented."""
    response = await client.get("/api/v1/documents/", headers=auth_headers)
    assert response.status_code == 501
    body = response.json()
    assert body["error"] == "NOT_IMPLEMENTED"


async def test_documents_get_returns_501(client: AsyncClient, auth_headers: Dict):
    """Phase 2 placeholder: get endpoint should return 501 Not Implemented."""
    import uuid
    response = await client.get(
        f"/api/v1/documents/{uuid.uuid4()}", headers=auth_headers
    )
    assert response.status_code == 501


async def test_documents_delete_returns_501(client: AsyncClient, auth_headers: Dict):
    """Phase 2 placeholder: delete endpoint should return 501 Not Implemented."""
    import uuid
    response = await client.delete(
        f"/api/v1/documents/{uuid.uuid4()}", headers=auth_headers
    )
    assert response.status_code == 501


async def test_documents_require_auth(client: AsyncClient):
    """Document endpoints require authentication."""
    response = await client.get("/api/v1/documents/")
    assert response.status_code == 401
