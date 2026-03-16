import pytest
from httpx import AsyncClient
from tests.conftest import create_tenant_and_admin, auth_headers


@pytest.mark.asyncio
async def test_list_documents_empty(client: AsyncClient):
    tokens = await create_tenant_and_admin(client, slug="docs-list-test")
    resp = await client.get(
        "/api/v1/documents",
        headers=auth_headers(tokens["access_token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_get_nonexistent_document(client: AsyncClient):
    tokens = await create_tenant_and_admin(client, slug="docs-404-test")
    fake_id = "00000000-0000-0000-0000-000000000001"
    resp = await client.get(
        f"/api/v1/documents/{fake_id}",
        headers=auth_headers(tokens["access_token"]),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_no_file_returns_422(client: AsyncClient):
    tokens = await create_tenant_and_admin(client, slug="docs-upload-test")
    resp = await client.post(
        "/api/v1/documents/upload",
        headers=auth_headers(tokens["access_token"]),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_documents_require_auth(client: AsyncClient):
    resp = await client.get("/api/v1/documents")
    assert resp.status_code == 401
