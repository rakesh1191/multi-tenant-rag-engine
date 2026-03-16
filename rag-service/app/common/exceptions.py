"""Custom exception classes for the RAG service."""
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    """Base application exception."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    message: str = "An internal error occurred"

    def __init__(
        self,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message or self.__class__.message
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.error_code,
            "message": self.message,
            "details": self.details,
        }


class UnauthorizedException(AppException):
    status_code = 401
    error_code = "UNAUTHORIZED"
    message = "Authentication required"


class ForbiddenException(AppException):
    status_code = 403
    error_code = "FORBIDDEN"
    message = "You do not have permission to perform this action"


class NotFoundException(AppException):
    status_code = 404
    error_code = "NOT_FOUND"
    message = "Resource not found"


class ConflictException(AppException):
    status_code = 409
    error_code = "CONFLICT"
    message = "Resource already exists"


class ValidationException(AppException):
    status_code = 422
    error_code = "VALIDATION_ERROR"
    message = "Validation failed"


class RateLimitException(AppException):
    status_code = 429
    error_code = "RATE_LIMITED"
    message = "Too many requests. Please try again later."


class StorageException(AppException):
    status_code = 503
    error_code = "STORAGE_ERROR"
    message = "Storage operation failed"


class LLMException(AppException):
    status_code = 503
    error_code = "LLM_ERROR"
    message = "LLM provider error"


class InvalidTokenException(UnauthorizedException):
    error_code = "INVALID_TOKEN"
    message = "Invalid or expired token"


class InactiveUserException(UnauthorizedException):
    error_code = "INACTIVE_USER"
    message = "User account is inactive"


class TenantNotFoundException(NotFoundException):
    error_code = "TENANT_NOT_FOUND"
    message = "Tenant not found"


class UserNotFoundException(NotFoundException):
    error_code = "USER_NOT_FOUND"
    message = "User not found"


class DocumentNotFoundException(NotFoundException):
    error_code = "DOCUMENT_NOT_FOUND"
    message = "Document not found"


class FileTooLargeException(AppException):
    status_code = 413
    error_code = "FILE_TOO_LARGE"
    message = "File size exceeds the maximum allowed limit"


class UnsupportedFileTypeException(AppException):
    status_code = 415
    error_code = "UNSUPPORTED_FILE_TYPE"
    message = "File type is not supported"


class StorageQuotaExceededException(AppException):
    status_code = 402
    error_code = "STORAGE_QUOTA_EXCEEDED"
    message = "Tenant storage quota has been exceeded"


# Exception handlers for FastAPI
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle all AppException subclasses."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTPException and format as structured JSON."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTP_ERROR",
            "message": exc.detail,
            "details": {},
        },
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Handle unexpected exceptions."""
    from app.common.logging import get_logger

    logger = get_logger(__name__)
    logger.error(
        "unhandled_exception",
        exc_type=type(exc).__name__,
        exc_message=str(exc),
        path=request.url.path,
        method=request.method,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "details": {},
        },
    )
