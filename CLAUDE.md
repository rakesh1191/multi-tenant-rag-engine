# CLAUDE.md — AI Development Guide for Multi-Tenant RAG Service

> This file governs how Claude assists on this project.
> Every rule here is backed by production incidents or research from 2024-2025.

---

## 1. Project Context

A **production-grade, multi-tenant RAG (Retrieval-Augmented Generation) service** built with:
- FastAPI + SQLAlchemy async + PostgreSQL + pgvector
- Celery + Redis for async ingestion
- MinIO (S3-compatible) for document storage
- Anthropic Claude API as the primary LLM
- Docker Compose for local dev; Kubernetes-ready for all cloud targets

Python runtime: **3.12** (use `X | None` and `list[T]` — no `Optional[X]` or `List[T]`).

---

## 2. Coding Style Rules

### 2.1 Naming

| Symbol | Convention | Example |
|--------|-----------|---------|
| Functions, variables | `snake_case` | `get_current_user` |
| Classes | `PascalCase` | `DocumentChunk` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_CHUNK_SIZE` |
| Private / internal | `_single_underscore` | `_build_prompt` |
| Module-level private | `__double_underscore` | only for dunder methods |

- No single-letter variables outside loop counters (`i`, `j`) or math (`x`, `y`).
- Boolean variables/functions: `is_`, `has_`, `can_`, `should_` prefix (`is_active`, `has_permission`).

### 2.2 Type Safety — Non-Negotiable

- **All** functions must have full type annotations on parameters and return values.
- Never use bare `Any`. If unavoidable, add `# type: ignore[misc]  # reason: ...`.
- Never use `# type: ignore` without a comment explaining why.
- Use `X | None` (Python 3.10+ union syntax) — not `Optional[X]`.
- Use `list[str]`, `dict[str, int]` — not `List[str]`, `Dict[str, int]`.
- Use `TypeAlias` for complex type aliases: `TenantID: TypeAlias = uuid.UUID`.
- Use `Protocol` (not ABCs) for port/interface definitions — enables structural typing.

### 2.3 Function Size and Complexity

- **Max function length: 40 lines.** If longer, split into private helpers.
- **Max cyclomatic complexity: 10** per function. (Target: ≤7 for public APIs.)
- One function, one purpose. If the docstring needs "and", split it.
- No nested functions more than 2 levels deep.
- Prefer explicit iteration over recursion in production code.

### 2.4 Async Everywhere

- Every route handler and service method is `async def`.
- Use `await` for all I/O: DB queries, S3 calls, Redis, HTTP requests.
- Never call blocking I/O in an `async def` without `asyncio.run_in_executor`.
- Use `httpx.AsyncClient` for outbound HTTP. Never use `requests` in async context.
- Use `asyncpg`/`sqlalchemy[asyncio]` for database. Never use sync SQLAlchemy in async routes.

### 2.5 No Business Logic in Routers

```
Router → validates input, calls service, formats response
Service → contains all business logic, calls repositories
Repository → database I/O only, no business logic
```

Routers must not contain: conditionals based on business rules, direct DB queries, or calls to external APIs.

### 2.6 Environment-Based Config

- All secrets and config via `pydantic-settings` `BaseSettings`.
- **Never hardcode** API keys, URLs, passwords, or magic numbers.
- App must fail fast at startup if required config is missing.
- Named constants in `config.py` — not scattered magic values.

### 2.7 Error Handling

- All custom exceptions inherit from `AppError` in `app/common/exceptions.py`.
- **Never** raise raw `Exception` or `ValueError` from service layer — use domain exceptions.
- **Never** return bare 500 — always structured JSON: `{"error": "code", "message": "...", "details": {}}`.
- Never let stack traces leak in API responses.
- `try/except` must catch specific exceptions, not bare `except:` or `except Exception:` without re-raise.

### 2.8 Tenant Isolation — Inviolable

- **Every** database query in service/repository layer **must** include `WHERE tenant_id = :tenant_id`.
- Never write a query that could return cross-tenant data.
- The `get_current_tenant` dependency is mandatory on every protected route.
- Tests for tenant isolation are **required** — not optional.

### 2.9 Structured Logging

- Use `structlog` for all logging. Never use `print()` in production code.
- Every log line must include `tenant_id`, `user_id`, and `request_id` (bound via contextvars in middleware).
- Log **events**, not messages: `logger.info("document_uploaded", document_id=..., size_bytes=...)`.
- Never log PII: mask emails, never log query text in production, never log JWT tokens.
- Log levels: `DEBUG` for dev, `INFO` for events, `WARNING` for recoverable errors, `ERROR` for failures.

---

## 3. Architecture Rules

### 3.1 Layer Boundaries

```
app/
├── auth/           # Auth domain: models, service, router, schemas, dependencies
├── documents/      # Documents domain: models, service, router, schemas
├── ingestion/      # Ingestion domain: Celery tasks, chunker, extractor, embedder
├── query/          # Query domain: retriever, reranker, prompt builder, streaming
├── llm/            # LLM abstraction: provider interface + Anthropic/OpenAI adapters
├── cache/          # Cache abstraction: Redis service + key builders
├── admin/          # Admin domain: stats, user management
└── common/         # Infrastructure: database, storage, middleware, exceptions, logging
```

**Rules:**
- Domain modules (`auth`, `documents`, etc.) must **not** import from each other directly. Share via schemas or dependency injection.
- `common/` is infrastructure — it must not contain business logic.
- `llm/` and `cache/` are adapters — business logic lives in `query/`.

### 3.2 Dependency Injection

- Use FastAPI's `Depends()` for all shared dependencies: DB session, current user, current tenant.
- Never use module-level globals for stateful services (DB connections, HTTP clients).
- Lifespan context manager (`@asynccontextmanager`) for startup/shutdown resource management.
- Test overrides via `app.dependency_overrides` — never monkey-patch.

### 3.3 LLM Provider Abstraction

```python
# app/llm/provider.py
class LLMProvider(Protocol):
    async def generate(self, messages: list[Message], **kwargs) -> LLMResponse: ...
    async def stream(self, messages: list[Message], **kwargs) -> AsyncIterator[str]: ...
```

- Business logic in `query/service.py` calls `LLMProvider` — never `anthropic.Anthropic()` directly.
- Provider is injected via config at startup. Switching to OpenAI requires only config change.
- Same pattern for `EmbeddingProvider` and `StoragePort`.

### 3.4 Repository Pattern for DB Access

- All DB queries go through service functions in `**/service.py`.
- Service functions take `AsyncSession` as a parameter — they do not create sessions.
- Session lifecycle managed by `get_db()` dependency (commit on success, rollback on exception).
- Never call `session.execute(text(...))` with string interpolation — always use parameterized queries.

### 3.5 Idempotency

- All Celery tasks must be idempotent: processing the same task twice produces the same result.
- Use `task_id` or `document_id` to detect and skip already-processed tasks.
- All write endpoints should handle duplicate submissions gracefully.

---

## 4. Cloud-Agnostic Design Rules

### 4.1 No Cloud SDK in Business Logic

| DO | DON'T |
|----|-------|
| Call `storage.upload_file(key, data)` | Call `boto3.client('s3').put_object(...)` in service layer |
| Read secrets from env vars | Call `boto3.client('secretsmanager')` in app code |
| Use `DATABASE_URL` env var | Hardcode RDS endpoint |
| Use `REDIS_URL` env var | Hardcode ElastiCache endpoint |

All cloud-specific SDKs live exclusively in `app/common/storage.py` and infrastructure adapters.

### 4.2 Kubernetes-First

- All services must expose `GET /health` (liveness) — returns `{"status": "ok"}`.
- All services must expose `GET /health/ready` (readiness) — checks DB and Redis connectivity.
- Services are stateless: no local disk writes, no in-process session state.
- Graceful shutdown: handle `SIGTERM`, drain in-flight requests, close DB connections.
- All containers must define `resource.requests` and `resource.limits` in Kubernetes manifests.

### 4.3 Storage Abstraction

`app/common/storage.py` wraps S3/MinIO via the same interface. Swapping to GCS or Azure Blob requires only a new adapter implementing:
```python
async def upload_file(key: str, data: bytes, content_type: str) -> str: ...
async def download_file(key: str) -> bytes: ...
async def delete_file(key: str) -> None: ...
```

### 4.4 Secrets

- Dev: `.env` file loaded by `pydantic-settings`.
- Production: Environment variables injected by Kubernetes (via External Secrets Operator syncing from AWS Secrets Manager, GCP Secret Manager, or Vault).
- The app code never knows which secret store is in use.

### 4.5 Observability Stack (Cloud-Agnostic)

| Signal | Library | Sink |
|--------|---------|------|
| Metrics | `prometheus-fastapi-instrumentator` | Prometheus (any cloud) |
| Tracing | `opentelemetry-sdk` + `opentelemetry-instrumentation-fastapi` | Jaeger / Tempo / cloud trace |
| Logs | `structlog` → JSON → stdout | Loki / ELK / CloudWatch / Cloud Logging |

Never use cloud-specific observability SDKs (e.g., AWS X-Ray SDK, GCP Cloud Trace SDK) in application code.

---

## 5. Testing Rules

### 5.1 Test Pyramid

```
Unit tests:        60-70%  — pure functions, domain logic, no I/O
Integration tests: 20-30%  — DB, Redis, S3 with real infra (test containers)
E2E tests:          5-10%  — full request-response via AsyncClient
```

### 5.2 Every AI-Generated Function Needs Tests For

1. **Happy path** — expected input, expected output.
2. **Boundary values** — empty string, empty list, zero, None, max value.
3. **Auth bypass** — every protected endpoint returns 401 with no token, 403 with wrong role.
4. **Tenant isolation (BOLA)** — user from tenant A cannot access tenant B's resources.
5. **Error path** — invalid input returns structured error, never 500.
6. **Idempotency** — duplicate write returns same result, not duplicate records.

### 5.3 Property-Based Testing

Use `hypothesis` for any function that:
- Processes user input or arbitrary strings
- Performs data transformation with invariants
- Handles serialization/deserialization

```python
from hypothesis import given, settings
from hypothesis import strategies as st

@given(st.text(min_size=1, max_size=512))
def test_chunker_never_loses_content(text: str) -> None:
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    reassembled = " ".join(c.content for c in chunks)
    # The original content must be fully present in chunks
    assert all(word in reassembled for word in text.split())
```

### 5.4 Test Structure

```python
# Pattern: Arrange / Act / Assert — always clear sections
async def test_register_creates_tenant_and_admin_user(client: AsyncClient) -> None:
    # Arrange
    payload = {"tenant_name": "Acme", "tenant_slug": "acme", ...}

    # Act
    resp = await client.post("/api/v1/auth/register", json=payload)

    # Assert
    assert resp.status_code == 201
    data = resp.json()
    assert data["user"]["role"] == "admin"
    assert data["tenant"]["slug"] == "acme"
```

### 5.5 Test Database Rules

- Tests use a dedicated `ragdb_test` database — never the development database.
- Schema created fresh at test session start via `Base.metadata.create_all`.
- Use `app.dependency_overrides[get_db]` to inject the test session — never mock SQLAlchemy.
- Each test function gets a clean session; use fixtures for shared setup.
- External APIs (LLM, embedding) are mocked in unit/integration tests. Only E2E tests call real APIs.

### 5.6 What To Mock vs. What To Use Real

| Component | Unit Tests | Integration Tests | E2E Tests |
|-----------|-----------|-------------------|-----------|
| PostgreSQL | Mock (return fixtures) | Real (`ragdb_test`) | Real |
| Redis | Mock | Real (local Redis) | Real |
| S3/MinIO | Mock | Real (local MinIO) | Real |
| LLM API | Mock (fixed responses) | Mock | Real (with API key) |
| Embedding API | Mock (zero vectors) | Mock | Real |
| Celery | Eager mode (`task_always_eager=True`) | Eager | Real workers |

---

## 6. Security Rules

### 6.1 BOLA (Broken Object Level Authorization) — #1 API Vulnerability

**Every** query fetching tenant data must filter by `tenant_id`:
```python
# CORRECT
result = await db.execute(
    select(Document).where(
        Document.id == document_id,
        Document.tenant_id == current_tenant.id,  # <-- required
    )
)

# WRONG — trusting URL param alone
result = await db.execute(select(Document).where(Document.id == document_id))
```

### 6.2 Input Validation Layers

1. **Schema layer**: Pydantic `Field` constraints — `min_length`, `max_length`, `pattern`, `ge`, `le`.
2. **Sanitization layer**: Strip dangerous content before storage or display.
3. **Business rules layer**: Domain validation in service layer.

Never use `**request.dict()` to mass-assign fields to models.

### 6.3 JWT Rules

- Access tokens: 30-minute TTL, algorithm `HS256` (dev) → upgrade to `RS256` in production.
- Refresh tokens: 7-day TTL, stored server-side for revocation.
- Payload must contain: `sub`, `tenant_id`, `role`, `type`, `exp`, `iat`.
- Always validate `type` claim to prevent refresh tokens being used as access tokens.
- Auth endpoints rate-limited at 5 requests/minute.

### 6.4 Dependency Safety

- Verify every new package exists on PyPI before installing.
- Check package creation date, download count, maintainer history for new/unfamiliar packages.
- Pin all dependencies to exact versions.
- Run `pip-audit` in CI — block merges on known CVEs with available fixes.

### 6.5 File Upload Security

- Validate `Content-Type` header.
- Validate magic bytes (file signature), not just extension.
- Enforce max file size at middleware level (before reading body).
- Never execute or `eval()` uploaded content.
- Store with a generated UUID key — never use the user-supplied filename as the S3 key.

### 6.6 Production Hardening

- Disable Swagger UI / ReDoc in production: `docs_url=None, redoc_url=None` unless intentional.
- Set CORS `allow_origins` to explicit list — never `["*"]` in production.
- Set security headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security`.
- Never log: passwords, tokens, PII (email in prod logs), raw query text.

---

## 7. Package Safety Rules (Critical for AI-Assisted Development)

> AI language models hallucinate package names at rates of 5-20%. Installing a hallucinated
> package name can lead to supply chain attacks ("slopsquatting").

**Before any `pip install <package>`:**

1. Verify the package exists at `https://pypi.org/project/<name>/`.
2. Check download count — packages with <1,000 downloads/week for a new dependency are suspicious.
3. Check creation date — a package created last week that an AI confidently recommends is a red flag.
4. Check for typosquatting — compare to known packages with similar names.
5. Review the package source on PyPI for any malicious-looking install scripts.

**In CI:**
- `pip-audit` runs on every PR.
- `bandit` runs on every PR (blocks HIGH severity findings).
- `ruff` runs on every PR (blocks E/F/W violations).
- Dependency licenses reviewed via `pip-licenses`.

---

## 8. Implementation Phases

### Phase 1: Foundation ✅
Auth, tenant isolation, DB schema, migrations, health endpoint, admin stats, tests.

### Phase 2: Document Ingestion
- `POST /documents/upload` — multipart, S3 upload, Celery task dispatch
- Celery: text extraction (PDF/md/txt), chunking, embedding, pgvector write
- Document status lifecycle: `pending → processing → ready | failed`
- `DELETE /documents/{id}` — cascade chunks + S3 object

### Phase 3: Query Pipeline
- Query embedding (same model as ingestion)
- pgvector similarity search with tenant filter
- LLM provider abstraction (Anthropic stream + OpenAI fallback)
- `POST /query` — streaming SSE with `{"type": "token", "data": "..."}`
- `POST /query/sync` — blocking JSON for testing
- Source attribution in response
- Query logging to `query_log`

### Phase 4: Production Polish
- Redis query cache (tenant-scoped keys, 1h TTL)
- Cache invalidation on new document ingestion
- Rate limiting per tenant (Redis sliding window)
- Request tracing (correlation IDs, OpenTelemetry)
- Prometheus metrics endpoint
- `scripts/seed_data.py` and `scripts/benchmark.py`

---

## 9. Code Review Checklist (AI-Generated Code)

Before accepting any AI-generated code:

- [ ] All functions have complete type annotations
- [ ] No bare `Any` types
- [ ] No `print()` — only `structlog`
- [ ] Every new dependency verified on PyPI
- [ ] Every DB query includes `tenant_id` filter
- [ ] Auth is enforced (protected routes have `Depends(get_current_user)`)
- [ ] Input validation via Pydantic `Field` constraints
- [ ] No stack traces can leak in API responses
- [ ] Error paths are tested (not just happy path)
- [ ] No hardcoded secrets, URLs, or credentials
- [ ] Function length ≤ 40 lines, complexity ≤ 10
- [ ] Async patterns correct (no blocking I/O in async functions)

---

## 10. Running the Project

```bash
# Start all infra services
docker compose up -d postgres redis minio

# Apply database migrations
alembic upgrade head

# Start API server (dev with hot reload)
uvicorn app.main:app --reload --port 8000

# Start Celery worker (Phase 2+)
celery -A app.ingestion.tasks worker --loglevel=info --concurrency=2

# Run tests (requires ragdb_test database)
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=term-missing

# Lint and type check
ruff check app/ tests/
mypy app/ --strict

# Security scan
bandit -r app/ -ll
pip-audit
```

---

## 11. Key Files

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI app, middleware, exception handlers, lifespan |
| `app/config.py` | All configuration via `pydantic-settings` |
| `app/common/database.py` | Async SQLAlchemy engine + `get_db` dependency |
| `app/common/exceptions.py` | Custom exception hierarchy + handlers |
| `app/common/middleware.py` | Request logging + `request_id` binding |
| `app/auth/service.py` | JWT creation, password hashing, user/tenant management |
| `app/auth/dependencies.py` | `get_current_user`, `get_current_tenant`, `require_admin` |
| `alembic/versions/001_initial.py` | Full DB schema with pgvector |
| `tests/conftest.py` | Test DB setup, `client` fixture, `auth_headers` helper |
