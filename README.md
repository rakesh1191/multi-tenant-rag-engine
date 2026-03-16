# Multi-Tenant RAG Engine

> A production-grade Retrieval-Augmented Generation service built to demonstrate full-stack backend engineering depth — multi-tenancy, async pipelines, vector search, streaming LLM responses, and a complete web UI.

---

## What This Project Demonstrates

This is not a tutorial project or a weekend script. It is a deliberately over-engineered system designed to showcase the kind of engineering thinking expected in senior backend and full-stack roles:

- **Multi-tenant SaaS architecture** with strict data isolation — every query is scoped to a tenant, BOLA attacks are structurally impossible
- **Async-first Python** — FastAPI, SQLAlchemy async, asyncpg, Celery — no blocking I/O anywhere
- **Production-grade ingestion pipeline** — upload → object storage → async worker → text extraction → chunking → embedding → vector database
- **Streaming LLM integration** — real-time Server-Sent Events from the backend to the browser, token by token
- **Redis caching at multiple layers** — query response cache, embedding cache, cache invalidation on data changes
- **Local LLM stack, zero API costs** — runs entirely on-device with Ollama (`qwen2.5:14b` for generation, `nomic-embed-text` for embeddings)
- **Full-stack delivery** — REST API + Celery workers + Next.js 14 UI, all wired together

---

## Live Features

| Feature | Detail |
|---------|--------|
| Tenant registration | Creates an isolated organisation with an admin user and JWT tokens |
| Document upload | PDF, Markdown, TXT — validated, stored in MinIO, ingested asynchronously |
| Async ingestion pipeline | Celery worker: extract → chunk (tiktoken) → embed → pgvector |
| Document status tracking | `pending → processing → ready / failed` with polling UI |
| Vector similarity search | pgvector HNSW index, cosine similarity, top-5 chunk retrieval |
| Streaming chat | SSE stream, markdown-rendered response, live source attribution |
| Query cache | Redis-backed, tenant-scoped, 1h TTL, invalidated on new document |
| Embedding cache | Redis, 24h TTL, keyed on SHA-256 of text |
| Rate limiting | Redis sliding-window per-tenant, enforced at route level |
| Query history | Paginated, with latency, cache hit/miss, full response detail |
| Admin dashboard | Tenant stats: documents, chunks, users, total queries |
| Health endpoints | `/health` (liveness) + `/health/ready` (DB + Redis + S3 readiness) |
| Prometheus metrics | Request latency, cache hit rate, document counts, LLM token usage |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     Next.js 14 UI                            │
│   Register · Documents · Chat (SSE) · History · Admin        │
└─────────────────────────┬────────────────────────────────────┘
                          │ HTTP / SSE
┌─────────────────────────▼────────────────────────────────────┐
│                  FastAPI  (app/)                              │
│                                                              │
│   /auth      /documents      /query       /admin             │
│     │              │            │             │              │
│     └──────────────┴────────────┴─────────────┘             │
│                      Service Layer                           │
│           (all queries scoped by tenant_id)                  │
└────┬───────────────┬───────────────┬──────────────────────── ┘
     │               │               │
┌────▼────┐   ┌──────▼──────┐  ┌────▼──────────────────────┐
│Postgres │   │    Redis     │  │         MinIO              │
│+pgvector│   │cache · broker│  │  S3-compatible storage     │
└─────────┘   └──────┬───── ┘  └────────────────────────────┘
                     │
              ┌──────▼──────┐
              │    Celery    │
              │    Worker    │
              └──────┬───── ┘
                     │
            ┌────────▼────────┐
            │     Ollama       │
            │  qwen2.5:14b    │  LLM generation (streaming)
            │ nomic-embed-text │  768-dim embeddings
            └─────────────────┘
```

### Key Design Decisions

**Why Celery for ingestion?**
Document ingestion (extraction + embedding) can take 5–30 seconds. Doing this synchronously in the HTTP request would block the connection and give a poor user experience. The API returns `202 Accepted` immediately; a Celery worker processes the document asynchronously and updates the status. The UI polls for completion.

**Why pgvector over a dedicated vector DB?**
Pinecone, Weaviate, and Qdrant add operational complexity and cost. pgvector keeps the vector index co-located with the relational data, enabling tenant-scoped filtering in a single query without cross-service joins. For most production workloads up to tens of millions of vectors, pgvector's HNSW index performs competitively.

**Why SSE over WebSocket for streaming?**
SSE is unidirectional (server → client), HTTP/1.1 compatible, automatically reconnects, and works through standard proxies and load balancers without special configuration. For a chat interface that only streams responses, SSE is simpler and more reliable than WebSocket.

**Why Redis for multiple concerns?**
Redis serves three roles here: Celery broker, query/embedding cache, and rate-limit counters. Using one infrastructure component for multiple purposes reduces operational surface area. Each concern uses a distinct key namespace and database index.

**Why local LLM?**
Ollama with `qwen2.5:14b` eliminates per-token API costs during development and evaluation, removes network latency from the LLM call, and keeps data entirely on-device. The LLM provider is abstracted behind a `Protocol` interface — switching to Anthropic or OpenAI requires only a config change.

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| API | FastAPI | Async-native, automatic OpenAPI, dependency injection |
| ORM | SQLAlchemy 2.0 async | Type-safe async queries, no blocking I/O |
| Database | PostgreSQL 16 + pgvector | Vector similarity search alongside relational data |
| Cache / Queue | Redis 7 | Multi-purpose: cache, broker, rate limiting |
| Task queue | Celery | Reliable async ingestion with retries and dead-letter handling |
| Object storage | MinIO | S3-compatible — swap to AWS S3 / GCS / Azure Blob via config |
| LLM | Ollama (`qwen2.5:14b`) | Local, zero cost, hot-swappable via provider abstraction |
| Embeddings | Ollama (`nomic-embed-text`) | 768-dim, fits pgvector HNSW ≤ 2000-dim limit |
| Auth | JWT + bcrypt | Stateless, tenant-scoped access and refresh tokens |
| Config | pydantic-settings | Typed env var config, fails fast on missing values |
| Logging | structlog | Structured JSON logs with `tenant_id`, `user_id`, `request_id` |
| Metrics | prometheus-client | Latency histograms, cache hit rates, document counts |
| Migrations | Alembic | Schema-as-code, async-compatible |
| UI framework | Next.js 14 App Router | SSR, streaming-compatible, file-based routing |
| UI styling | Tailwind CSS + shadcn/ui | Utility-first CSS, Radix UI primitives |

---

## Project Structure

```
.
├── app/
│   ├── main.py                # App factory, middleware, lifespan, exception handlers
│   ├── config.py              # pydantic-settings — single source of truth for all config
│   ├── auth/                  # JWT creation, bcrypt, register, login, invite, RBAC
│   ├── documents/             # Upload, list, get, delete — all tenant-scoped
│   ├── ingestion/
│   │   ├── tasks.py           # Celery task: orchestrates the full ingestion pipeline
│   │   ├── extractor.py       # PDF (pypdf) + markdown + plain text extraction
│   │   ├── chunker.py         # tiktoken-based overlapping chunk with metadata
│   │   └── embedder.py        # OpenAI + Ollama embedding providers with retry
│   ├── query/
│   │   ├── service.py         # Cache check → embed → search → LLM → log → cache write
│   │   └── router.py          # POST /query (SSE), POST /query/sync, GET /query/history
│   ├── llm/
│   │   └── providers.py       # LLMProvider Protocol + Anthropic / OpenAI / Ollama adapters
│   ├── cache/
│   │   └── redis.py           # Query cache, embedding cache, cache versioning + invalidation
│   └── common/
│       ├── database.py        # Async engine, session factory, get_db dependency
│       ├── storage.py         # S3/MinIO abstraction (upload, download, delete)
│       ├── middleware.py      # Request ID injection, structlog context binding
│       ├── exceptions.py      # AppError hierarchy, structured error responses
│       ├── rate_limit.py      # Redis ZSET sliding-window rate limiter (FastAPI Depends)
│       └── metrics.py         # Prometheus counters and histograms
├── ui/
│   └── src/
│       ├── app/               # Pages: login, register, documents, chat, history, admin
│       ├── components/
│       │   ├── chat/          # ChatWindow (markdown SSE rendering), ChatInput, SourceCard
│       │   ├── documents/     # DocumentTable with status badges, UploadZone with drag-drop
│       │   ├── admin/         # StatsCards
│       │   └── layout/        # DashboardLayout, AppSidebar (role-aware nav)
│       └── lib/
│           ├── api.ts         # Typed API client for all backend endpoints
│           ├── auth.ts        # JWT decode, token storage, auth guards
│           └── types.ts       # TypeScript types matching backend schemas
├── alembic/versions/
│   ├── 001_initial.py         # Full schema with pgvector extension
│   └── 002_update_embedding_dim.py  # Adjusts vector column for nomic-embed-text
└── tests/
    ├── conftest.py            # Async test DB, AsyncClient fixture, auth helpers
    ├── test_auth.py           # 11 tests: registration, login, RBAC, tenant isolation
    ├── test_documents.py      # Document CRUD, upload, auth enforcement
    ├── test_query.py          # Query pipeline, streaming, Ollama provider unit tests
    └── test_phase4.py         # Rate limiting, metrics, health checks, embedding cache
```

---

## Security Considerations

This project was built with OWASP API Security Top 10 in mind:

| Risk | Mitigation |
|------|-----------|
| **BOLA** (Broken Object Level Auth) | Every DB query includes `WHERE tenant_id = :tenant_id` — structurally impossible to access another tenant's data |
| **Broken Auth** | JWT with short TTL (30 min), refresh token rotation, `type` claim validated to prevent token reuse |
| **Excessive Data Exposure** | Response schemas defined explicitly — no `**dict()` mass assignment |
| **Injection** | SQLAlchemy parameterised queries throughout; vector literals are machine-generated floats, not user input |
| **Mass Assignment** | Pydantic models with explicit fields only |
| **Rate Limiting** | Redis sliding-window enforced at the route level via FastAPI `Depends` |
| **File Upload** | MIME type validation + extension fallback, max size enforced, UUID-keyed S3 paths (never user-supplied filename) |
| **Secrets** | Never hardcoded; loaded from env vars at startup; app fails fast if missing |

---

## Running Locally

### Prerequisites

- Docker + Docker Compose
- Python 3.9+
- [Ollama](https://ollama.com) with models pulled
- Node.js 18+

```bash
# Pull models
ollama pull qwen2.5:14b
ollama pull nomic-embed-text

# Start infrastructure
docker compose up -d postgres redis minio

# Install Python deps
pip install -e ".[dev]"

# Run migrations
python3 -m alembic upgrade head

# Terminal 1 — API
uvicorn app.main:app --reload --port 8000

# Terminal 2 — Celery worker
celery -A app.ingestion.tasks worker --loglevel=info --concurrency=2

# Terminal 3 — UI
cd ui && npm install && npm run dev
```

Open http://localhost:3000, register a tenant, upload a document, and query it.

---

## Configuration

Key environment variables (see `.env.example` for the full list):

```bash
# LLM — local Ollama, no API key required
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:14b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSION=768

# Switch to cloud providers with a single line change
# LLM_PROVIDER=anthropic  ANTHROPIC_API_KEY=sk-ant-...
# EMBEDDING_PROVIDER=openai  OPENAI_API_KEY=sk-...  EMBEDDING_DIMENSION=1536
```

The LLM and embedding providers are injected via config — no `if provider == "ollama"` scattered through business logic. Switching providers requires only `.env` changes.

---

## Testing

```bash
# Create test database
docker exec <postgres-container> psql -U rag -c "CREATE DATABASE ragdb_test;"

# Run all tests
pytest tests/ -v --cov=app --cov-report=term-missing

# Lint + type check + security scan
ruff check app/ tests/
mypy app/ --strict
bandit -r app/ -ll
```

Test coverage includes: registration, login, JWT refresh, RBAC, tenant isolation (BOLA), document CRUD, upload, rate limiting, cache hit/miss, health checks, and Ollama provider unit tests.

---

## What I Would Add Next

- **Re-ranking**: cross-encoder reranker (e.g. `cross-encoder/ms-marco-MiniLM-L-6-v2`) between retrieval and generation to improve answer quality
- **Kubernetes manifests**: Helm chart with HPA for the API and Celery worker
- **Multi-modal ingestion**: image extraction from PDFs via `pdfplumber`
- **Evaluation pipeline**: RAGAS metrics (faithfulness, answer relevancy, context recall) to measure RAG quality
- **WebSocket for chat**: replace SSE with WebSocket for bidirectional communication (e.g. follow-up questions mid-stream)

---

## Licence

MIT
