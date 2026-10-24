"""FastAPI application factory, exception translation, and router registration."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fincontrol_core.arca.allocation import InvalidTargetsError
from fincontrol_core.portfolio.positions import InsufficientQuantityError

from fincontrol_api.config import get_settings
from fincontrol_api.controllers import (
    assets_router,
    earnings_router,
    health_router,
    portfolio_router,
    settings_router,
    transactions_router,
)


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

    @app.exception_handler(LookupError)
    async def lookup_error_handler(_request: Request, exc: LookupError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )

    @app.exception_handler(InsufficientQuantityError)
    async def short_sell_error_handler(
        _request: Request, exc: InsufficientQuantityError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(exc), "code": "INSUFFICIENT_QUANTITY"},
        )

    @app.exception_handler(InvalidTargetsError)
    async def invalid_targets_error_handler(
        _request: Request, exc: InvalidTargetsError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(exc), "code": "INVALID_ARCA_TARGETS"},
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(exc)},
        )

    api_prefix = "/api/v1"
    app.include_router(health_router, prefix=api_prefix)
    app.include_router(assets_router, prefix=api_prefix)
    app.include_router(transactions_router, prefix=api_prefix)
    app.include_router(earnings_router, prefix=api_prefix)
    app.include_router(portfolio_router, prefix=api_prefix)
    app.include_router(settings_router, prefix=api_prefix)

    return app


app = create_app()
