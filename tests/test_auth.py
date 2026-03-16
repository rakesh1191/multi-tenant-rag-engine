import pytest
from httpx import AsyncClient
from tests.conftest import create_tenant_and_admin, auth_headers


@pytest.mark.asyncio
async def test_register_creates_tenant_and_admin_user(client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "tenant_name": "Acme Corp",
        "tenant_slug": "acme-corp",
        "email": "admin@acme.com",
        "password": "securepass",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["tenant"]["slug"] == "acme-corp"
    assert data["user"]["role"] == "admin"
    assert data["user"]["email"] == "admin@acme.com"
    assert "access_token" in data["tokens"]
    assert "refresh_token" in data["tokens"]


@pytest.mark.asyncio
async def test_register_duplicate_slug_fails(client: AsyncClient):
    payload = {
        "tenant_name": "Dup",
        "tenant_slug": "dup-slug",
        "email": "a@dup.com",
        "password": "password123",
    }
    r1 = await client.post("/api/v1/auth/register", json=payload)
    assert r1.status_code == 201

    payload["email"] = "b@dup.com"
    r2 = await client.post("/api/v1/auth/register", json=payload)
    assert r2.status_code == 409
    assert r2.json()["error"] == "conflict"


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    await create_tenant_and_admin(client, slug="login-test")
    resp = await client.post("/api/v1/auth/login", json={
        "email": "admin@login-test.com",
        "password": "password123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await create_tenant_and_admin(client, slug="wrong-pw")
    resp = await client.post("/api/v1/auth/login", json={
        "email": "admin@wrong-pw.com",
        "password": "badpassword",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_wrong_email(client: AsyncClient):
    resp = await client.post("/api/v1/auth/login", json={
        "email": "nonexistent@example.com",
        "password": "password123",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    tokens = await create_tenant_and_admin(client, slug="refresh-test")
    resp = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": tokens["refresh_token"],
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_access_protected_route_with_token(client: AsyncClient):
    tokens = await create_tenant_and_admin(client, slug="protected-test")
    resp = await client.get(
        "/api/v1/admin/stats",
        headers=auth_headers(tokens["access_token"]),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_access_protected_route_no_token(client: AsyncClient):
    resp = await client.get("/api/v1/admin/stats")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_tenant_isolation(client: AsyncClient):
    """User from tenant A cannot see tenant B's admin stats."""
    tenant_a = await create_tenant_and_admin(client, slug="tenant-a")
    tenant_b = await create_tenant_and_admin(client, slug="tenant-b")

    # Tenant A sees their own stats
    resp_a = await client.get(
        "/api/v1/admin/stats",
        headers=auth_headers(tenant_a["access_token"]),
    )
    assert resp_a.status_code == 200
    assert resp_a.json()["tenant_id"] == tenant_a["tenant"]["id"]

    # Tenant B sees their own stats — not tenant A's
    resp_b = await client.get(
        "/api/v1/admin/stats",
        headers=auth_headers(tenant_b["access_token"]),
    )
    assert resp_b.status_code == 200
    assert resp_b.json()["tenant_id"] == tenant_b["tenant"]["id"]
    assert resp_b.json()["tenant_id"] != tenant_a["tenant"]["id"]


@pytest.mark.asyncio
async def test_invite_member(client: AsyncClient):
    tokens = await create_tenant_and_admin(client, slug="invite-test")
    resp = await client.post(
        "/api/v1/auth/invite",
        json={"email": "member@invite-test.com", "role": "member"},
        headers=auth_headers(tokens["access_token"]),
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "member"


@pytest.mark.asyncio
async def test_invite_requires_admin(client: AsyncClient):
    """A member cannot invite other users."""
    # Register tenant and get admin token
    tokens = await create_tenant_and_admin(client, slug="invite-auth-test")

    # Invite a member
    await client.post(
        "/api/v1/auth/invite",
        json={"email": "member@invite-auth-test.com", "role": "member"},
        headers=auth_headers(tokens["access_token"]),
    )

    # Login as that member (need to set their password first — use service directly)
    from app.auth import service as auth_service
    from app.common.database import get_session_factory
    from sqlalchemy import select
    from app.auth.models import User

    async with get_session_factory()() as db:
        result = await db.execute(select(User).where(User.email == "member@invite-auth-test.com"))
        member = result.scalar_one()
        member.password_hash = auth_service.hash_password("memberpass")
        await db.commit()

    member_login = await client.post("/api/v1/auth/login", json={
        "email": "member@invite-auth-test.com",
        "password": "memberpass",
    })
    member_token = member_login.json()["access_token"]

    resp = await client.post(
        "/api/v1/auth/invite",
        json={"email": "another@invite-auth-test.com", "role": "member"},
        headers=auth_headers(member_token),
    )
    assert resp.status_code == 403
