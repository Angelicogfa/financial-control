"""FastAPI application factory: wires core infrastructure and the module routers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from starlette.routing import Route

from controllers.accounts.router import accounts_router
from controllers.agentic.router import agentic_router
from controllers.alerts.router import alerts_router
from controllers.assets.router import assets_router
from controllers.auth.dependencies import require_user
from controllers.auth.router import auth_router
from controllers.contributions.router import contributions_router
from controllers.ledger.router import (
    earnings_router,
    events_router,
    imports_router,
    transactions_router,
)
from controllers.market.router import market_router
from controllers.policy.router import policy_router, settings_router
from controllers.portfolio.router import portfolio_router
from controllers.research.router import research_router
from controllers.simulation.router import simulation_router
from controllers.system.router import health_router
from controllers.tax.router import tax_router
from core.http_errors import install_error_handlers
from core.logging import configure_logging
from core.middleware import install_middleware
from core.settings import get_settings
from infra.mcp import mcp_port

API_PREFIX = "/api/v1"

# Public routers first, then the ones behind the session; the order is the OpenAPI order.
PUBLIC_ROUTERS = (health_router, auth_router)
PROTECTED_ROUTERS = (
    assets_router,
    transactions_router,
    earnings_router,
    portfolio_router,
    settings_router,
    market_router,
    policy_router,
    accounts_router,
    research_router,
    contributions_router,
    events_router,
    imports_router,
    alerts_router,
    agentic_router,
    tax_router,
    simulation_router,
)


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    async with mcp_port.running():
        yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    app = FastAPI(
        title="Financial Control API",
        version="0.1.0",
        description=(
            "Investment portfolio control with ARCA methodology and optional Diagrama do Cerrado"
        ),
        lifespan=_lifespan,
    )
    install_middleware(app, settings)
    install_error_handlers(app)

    for router in PUBLIC_ROUTERS:
        app.include_router(router, prefix=API_PREFIX)
    protected = [Depends(require_user)]
    for router in PROTECTED_ROUTERS:
        app.include_router(router, prefix=API_PREFIX, dependencies=protected)
    app.router.routes.append(
        Route(f"{API_PREFIX}/mcp", endpoint=mcp_port, methods=["GET", "POST", "DELETE"])
    )
    return app


app = create_app()
