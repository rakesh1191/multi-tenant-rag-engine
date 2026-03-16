"""Test configuration, fixtures, and helpers."""
import asyncio
import uuid
from typing import AsyncGenerator, Dict, Tuple

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.models import Tenant, User
from app.common.database import Base, get_db
from app.config import settings
from app.main import app

# ---------------------------------------------------------------------------
# Test database setup
# ---------------------------------------------------------------------------

# Use a separate test database to avoid polluting the development DB.
# Override DATABASE_URL via environment variable TEST_DATABASE_URL, or
# append "_test" to the configured database name automatically.
def _get_test_db_url() -> str:
    import os
    test_url = os.environ.get("TEST_DATABASE_URL")
    if test_url:
        return test_url
    # Derive test DB from configured URL: replace DB name with <name>_test
    url = settings.DATABASE_URL
    if "/" in url:
        base, db_name = url.rsplit("/", 1)
        return f"{base}/{db_name}_test"
    return url


TEST_DATABASE_URL = _get_test_db_url()

# Async engine pointing at the test database
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

TestAsyncSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ---------------------------------------------------------------------------
# Session-scoped: create tables once, drop after the entire test session
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_database():
    """Create all tables at the start of the test session and drop them afterwards."""
    # Enable pgvector extension first (no-op if already enabled)
    async with test_engine.begin() as conn:
        await conn.execute(
            __import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS vector")
        )
        await conn.execute(
            __import__("sqlalchemy").text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
        )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


# ---------------------------------------------------------------------------
# Function-scoped DB session with automatic rollback for test isolation
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional test session that rolls back after each test."""
    async with test_engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()


# ---------------------------------------------------------------------------
# Override get_db to use the test session
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client with the app's DB dependency overridden."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------

def _make_register_payload(slug: str | None = None) -> Dict:
    unique = str(uuid.uuid4()).replace("-", "")[:8]
    return {
        "tenant_name": f"Test Org {unique}",
        "tenant_slug": slug or f"test-org-{unique}",
        "admin_email": f"admin-{unique}@example.com",
        "admin_password": "SecurePass123!",
    }


@pytest_asyncio.fixture()
async def registered_tenant(client: AsyncClient) -> Dict:
    """Register a tenant and return the full response JSON."""
    payload = _make_register_payload()
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest_asyncio.fixture()
async def auth_headers(registered_tenant: Dict) -> Dict[str, str]:
    """Return Authorization headers for the admin user of a freshly registered tenant."""
    access_token = registered_tenant["tokens"]["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


async def register_and_get_token(client: AsyncClient, slug: str | None = None) -> Tuple[Dict, str]:
    """Helper: register a tenant, return (response_json, access_token)."""
    payload = _make_register_payload(slug)
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    return data, data["tokens"]["access_token"]
