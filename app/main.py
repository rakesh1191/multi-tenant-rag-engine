from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse

from app.common.logging import setup_logging
from app.common.middleware import RequestLoggingMiddleware
from app.common.exceptions import (
    AppError,
    app_error_handler,
    validation_error_handler,
    unhandled_error_handler,
)
from app.auth.router import router as auth_router
from app.documents.router import router as documents_router
from app.admin.router import router as admin_router
from app.query.router import router as query_router
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    # Ensure S3 bucket exists on startup (best-effort)
    try:
        from app.common.storage import ensure_bucket_exists
        await ensure_bucket_exists()
    except Exception:
        pass
    yield
    # Cleanup
    try:
        from app.cache.redis import close_redis
        await close_redis()
    except Exception:
        pass


app = FastAPI(
    title="Multi-Tenant RAG Service",
    version="0.1.0",
    description="Production-grade multi-tenant Retrieval-Augmented Generation service",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)

# Routers
API_PREFIX = "/api/v1"
app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(documents_router, prefix=API_PREFIX)
app.include_router(admin_router, prefix=API_PREFIX)
app.include_router(query_router, prefix=API_PREFIX)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "version": "0.1.0", "env": settings.APP_ENV}


@app.get("/health/ready", tags=["health"])
async def health_ready():
    """Deep health check — verifies connectivity to Postgres, Redis, and S3."""
    from sqlalchemy import text
    from app.common.database import get_engine
    from app.cache.redis import _get_redis
    from app.common.storage import get_s3_client

    checks: dict = {}
    all_ok = True

    # --- PostgreSQL ---
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as exc:
        checks["database"] = {"status": "error", "detail": str(exc)}
        all_ok = False

    # --- Redis ---
    try:
        r = _get_redis()
        await r.ping()
        checks["redis"] = {"status": "ok"}
    except Exception as exc:
        checks["redis"] = {"status": "error", "detail": str(exc)}
        all_ok = False

    # --- S3 / MinIO ---
    try:
        async with get_s3_client() as s3:
            await s3.head_bucket(Bucket=settings.S3_BUCKET)
        checks["storage"] = {"status": "ok"}
    except Exception as exc:
        checks["storage"] = {"status": "error", "detail": str(exc)}
        all_ok = False

    status_str = "healthy" if all_ok else "degraded"
    http_status = 200 if all_ok else 503
    return JSONResponse(
        status_code=http_status,
        content={"status": status_str, "checks": checks},
    )


@app.get("/metrics", include_in_schema=False)
async def metrics():
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
