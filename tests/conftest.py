"""
Test configuration.

Strategy: override DATABASE_URL to point at ragdb_test so the app's own
async engine and session pool handle connections normally. This avoids
asyncpg cross-loop issues that occur when a single session is shared across
async test boundaries.

Tables are created once per session. Between tests, all rows are deleted
(truncate-style) to keep tests isolated without recreating the schema.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

from app.config import settings

# ---------------------------------------------------------------------------
# Point all app DB access at the test database
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = settings.DATABASE_URL.replace("/ragdb", "/ragdb_test")
settings.DATABASE_URL = TEST_DATABASE_URL  # mutate before engine is lazily created

# Now import app internals — engine is lazy so it picks up the patched URL
from app.main import app  # noqa: E402
from app.common.database import Base  # noqa: E402
import app.common.database as _db_module  # noqa: E402

# Reset singletons so they rebuild against TEST_DATABASE_URL
_db_module._engine = None
_db_module._session_factory = None

# Dedicated engine just for fixture setup/teardown
_setup_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


# ---------------------------------------------------------------------------
# Session-scoped: create schema once
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    async with _setup_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        # pgvector extension must exist before create_all (vector column type)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        # Alembic migration adds the vector column via raw SQL; replicate here
        await conn.execute(text(
            "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding vector(1536)"
        ))
    yield
    async with _setup_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _setup_engine.dispose()


# ---------------------------------------------------------------------------
# Function-scoped: truncate all tables between tests
# ---------------------------------------------------------------------------
_TABLES = ["query_log", "document_chunks", "documents", "users", "tenants"]


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    """Delete all rows and reset the app engine after each test."""
    yield
    # Truncate all tables via the setup engine
    async with _setup_engine.begin() as conn:
        for table in _TABLES:
            await conn.execute(text(f'DELETE FROM "{table}"'))
    # Dispose the app's connection pool so the next test gets fresh connections
    import app.common.database as _db_module
    if _db_module._engine is not None:
        await _db_module._engine.dispose()
        _db_module._session_factory = None


# ---------------------------------------------------------------------------
# HTTP client — uses the real app with its own DB pool (no session override)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def create_tenant_and_admin(client: AsyncClient, slug: str = "test-tenant") -> dict:
    """Register a tenant + admin user and return tokens + user + tenant."""
    resp = await client.post("/api/v1/auth/register", json={
        "tenant_name": "Test Tenant",
        "tenant_slug": slug,
        "email": f"admin@{slug}.com",
        "password": "password123",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return {
        "access_token": data["tokens"]["access_token"],
        "refresh_token": data["tokens"]["refresh_token"],
        "user": data["user"],
        "tenant": data["tenant"],
    }


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
