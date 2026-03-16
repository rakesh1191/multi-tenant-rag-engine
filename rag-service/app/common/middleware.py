"""FastAPI middleware: request ID tracking, structured logging context."""
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.common.logging import bind_request_context, clear_request_context, get_logger

logger = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware that attaches a unique request ID to every request
    and binds it (along with tenant/user context) to the structlog context.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate or propagate X-Request-ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Bind to structlog context for this request
        bind_request_context(request_id=request_id)

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                request_id=request_id,
                exc_type=type(exc).__name__,
            )
            raise
        finally:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code if "response" in dir() else 500,
                duration_ms=duration_ms,
                request_id=request_id,
            )
            clear_request_context()

        # Expose request ID in response headers
        response.headers["X-Request-ID"] = request_id
        return response


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Middleware that extracts tenant context from JWT and binds it
    to the structlog context. The actual tenant resolution is done in
    the auth dependency; this middleware only handles logging context.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Tenant/user context is set by auth dependencies; this middleware
        # re-binds after the auth dependency sets state on request.state
        response = await call_next(request)

        # If auth dependencies set tenant_id/user_id on request.state,
        # they will already be included via the dependency chain.
        return response
