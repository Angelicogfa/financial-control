"""FastAPI application factory: wires core infrastructure and the module routers."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fincontrol_config import get_settings
from fincontrol_config.logging import configure_logging

from fincontrol_api.core.http_errors import install_error_handlers
from fincontrol_api.core.middleware import install_middleware
from fincontrol_api.modules.accounts.router import accounts_router
from fincontrol_api.modules.alerts.router import alerts_router
from fincontrol_api.modules.assets.router import assets_router
from fincontrol_api.modules.auth.dependencies import require_user
from fincontrol_api.modules.auth.router import auth_router
from fincontrol_api.modules.contributions.router import contributions_router
from fincontrol_api.modules.ledger.router import (
    earnings_router,
    events_router,
    imports_router,
    transactions_router,
)
from fincontrol_api.modules.market.router import market_router
from fincontrol_api.modules.policy.router import policy_router, settings_router
from fincontrol_api.modules.portfolio.router import portfolio_router
from fincontrol_api.modules.research.router import research_router
from fincontrol_api.modules.system.router import health_router

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
)


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
    )
    install_middleware(app, settings)
    install_error_handlers(app)

    for router in PUBLIC_ROUTERS:
        app.include_router(router, prefix=API_PREFIX)
    protected = [Depends(require_user)]
    for router in PROTECTED_ROUTERS:
        app.include_router(router, prefix=API_PREFIX, dependencies=protected)
    return app


app = create_app()
