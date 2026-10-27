"""Translation of domain and security errors into HTTP responses ({"detail", "code"})."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from core.errors import ConflictError, DomainError, ForbiddenError, NotFoundError, ValidationError
from core.security import AuthenticationError, AuthNotConfiguredError

logger = logging.getLogger("fincontrol_api")


def error_body(exc: DomainError) -> dict[str, Any]:
    """Standard serialized payload for a domain error across HTTP and MCP channels."""
    return {"detail": exc.message, "code": exc.code}


def _error_response(status_code: int, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=error_body(exc))


def install_error_handlers(app: FastAPI) -> None:
    """Register the exception handlers that map errors to status codes."""

    @app.exception_handler(NotFoundError)
    async def not_found_handler(_request: Request, exc: NotFoundError) -> JSONResponse:
        return _error_response(status.HTTP_404_NOT_FOUND, exc)

    @app.exception_handler(ValidationError)
    async def validation_error_handler(_request: Request, exc: ValidationError) -> JSONResponse:
        return _error_response(status.HTTP_400_BAD_REQUEST, exc)

    @app.exception_handler(ConflictError)
    async def conflict_error_handler(_request: Request, exc: ConflictError) -> JSONResponse:
        return _error_response(status.HTTP_409_CONFLICT, exc)

    @app.exception_handler(ForbiddenError)
    async def forbidden_error_handler(_request: Request, exc: ForbiddenError) -> JSONResponse:
        return _error_response(status.HTTP_403_FORBIDDEN, exc)

    @app.exception_handler(AuthenticationError)
    async def unauthenticated_handler(_request: Request, exc: AuthenticationError) -> JSONResponse:
        return _error_response(status.HTTP_401_UNAUTHORIZED, exc)

    @app.exception_handler(AuthNotConfiguredError)
    async def auth_not_configured_handler(
        _request: Request, exc: AuthNotConfiguredError
    ) -> JSONResponse:
        logger.error(exc.message)
        return _error_response(status.HTTP_503_SERVICE_UNAVAILABLE, exc)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Internal server error",
                "code": "INTERNAL_ERROR",
                "request_id": request_id,
            },
        )
