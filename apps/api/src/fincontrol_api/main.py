"""FastAPI application factory, exception translation, and router registration."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fincontrol_config.logging import configure_logging, request_id_var
from fincontrol_core.errors import ConflictError, DomainError, NotFoundError, ValidationError

from fincontrol_api.config import get_settings
from fincontrol_api.controllers import (
    assets_router,
    earnings_router,
    health_router,
    market_router,
    portfolio_router,
    settings_router,
    transactions_router,
)

logger = logging.getLogger("fincontrol_api")
access_logger = logging.getLogger("fincontrol_api.access")

REQUEST_ID_HEADER = "X-Request-ID"


def _error_response(status_code: int, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": exc.message, "code": exc.code})


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    app = FastAPI(
        title="Financial Control API",
        version="0.1.0",
        description=(
            "Investment portfolio control with ARCA methodology "
            "and optional Diagrama do Cerrado"
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        access_logger.info(
            "%s %s %s",
            request.method,
            request.url.path,
            response.status_code,
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return response

    @app.exception_handler(NotFoundError)
    async def not_found_handler(_request: Request, exc: NotFoundError) -> JSONResponse:
        return _error_response(status.HTTP_404_NOT_FOUND, exc)

    @app.exception_handler(ValidationError)
    async def validation_error_handler(_request: Request, exc: ValidationError) -> JSONResponse:
        return _error_response(status.HTTP_400_BAD_REQUEST, exc)

    @app.exception_handler(ConflictError)
    async def conflict_error_handler(_request: Request, exc: ConflictError) -> JSONResponse:
        return _error_response(status.HTTP_409_CONFLICT, exc)

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

    api_prefix = "/api/v1"
    app.include_router(health_router, prefix=api_prefix)
    app.include_router(assets_router, prefix=api_prefix)
    app.include_router(transactions_router, prefix=api_prefix)
    app.include_router(earnings_router, prefix=api_prefix)
    app.include_router(portfolio_router, prefix=api_prefix)
    app.include_router(settings_router, prefix=api_prefix)
    app.include_router(market_router, prefix=api_prefix)

    return app


app = create_app()
