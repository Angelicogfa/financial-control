"""FastAPI dependency providers for the market module.

Scope: market data jobs and series freshness.
"""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from controllers.shared.dependencies import UoWFactory
from domain.market.services.use_cases import MarketDataHandler


def get_market_data_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> MarketDataHandler:
    """Provide the MarketDataHandler instance."""
    return MarketDataHandler(uow_factory=uow_factory)
