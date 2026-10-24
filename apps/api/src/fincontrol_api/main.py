"""FastAPI application factory, exception translation, and router registration."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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


def _error_response(status_code: int, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": exc.message, "code": exc.code})


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
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
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error", "code": "INTERNAL_ERROR"},
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
