"""Domain errors and global exception handlers.

Every error leaving the API has the same shape:

    {"error": {"code": "not_found", "message": "...", "details": ..., "request_id": "..."}}

Service code raises the AppError subclasses below; it never builds HTTP responses itself.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.middleware import REQUEST_ID_HEADER

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for expected, client-facing errors."""

    status_code: int = 500
    code: str = "internal_error"
    message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, *, details: Any = None) -> None:
        self.message = message or self.message
        self.details = details
        super().__init__(self.message)


class AuthenticationError(AppError):
    status_code, code, message = 401, "not_authenticated", "Authentication required."


class PermissionDeniedError(AppError):
    status_code, code, message = 403, "permission_denied", "You cannot access this resource."


class NotFoundError(AppError):
    status_code, code, message = 404, "not_found", "Resource not found."


class ConflictError(AppError):
    status_code, code, message = 409, "conflict", "Resource conflict."


class ServiceUnavailableError(AppError):
    status_code, code, message = 503, "service_unavailable", "A required service is unavailable."


_HTTP_STATUS_CODES = {
    400: "bad_request",
    401: "not_authenticated",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    429: "rate_limited",
}


def error_response(
    request: Request, status_code: int, code: str, message: str, details: Any = None
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": jsonable_encoder(details),
                "request_id": request_id,
            }
        },
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(request, exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_STATUS_CODES.get(exc.status_code, "http_error")
        return error_response(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            request, 422, "validation_error", "Request validation failed.", exc.errors()
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Log the full traceback, but never leak internals to the client.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return error_response(request, 500, "internal_error", "An unexpected error occurred.")
