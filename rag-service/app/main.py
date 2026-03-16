"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.admin.router import router as admin_router
from app.auth.router import router as auth_router
from app.common.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
)
from app.common.logging import configure_logging, get_logger
from app.common.middleware import RequestContextMiddleware
from app.config import settings
from app.documents.router import router as documents_router

# Configure structured logging before anything else
configure_logging(
    log_level=settings.APP_LOG_LEVEL,
    is_production=settings.is_production,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    logger.info(
        "application_starting",
        env=settings.APP_ENV,
        version="0.1.0",
    )
    yield
    logger.info("application_stopping")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Multi-Tenant RAG Service",
        version="0.1.0",
        description="Production-grade multi-tenant Retrieval-Augmented Generation service",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ---- Middleware (order matters: outermost first) ----
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_development else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)

    # ---- Exception handlers ----
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # ---- Routers ----
    API_PREFIX = "/api/v1"
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(documents_router, prefix=API_PREFIX)
    app.include_router(admin_router, prefix=API_PREFIX)

    # ---- Health check (no auth) ----
    @app.get("/health", tags=["health"], summary="Health check")
    async def health() -> dict:
        """Returns service health status. Used by load balancers and orchestrators."""
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {"service": "rag-service", "version": "0.1.0", "docs": "/docs"}

    return app


app = create_app()
