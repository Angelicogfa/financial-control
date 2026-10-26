"""FastAPI dependency providers for the market module.

Scope: market data jobs and series freshness.
"""

from __future__ import annotations

from fastapi import Depends

from fincontrol_api.composition import get_uow_factory
from fincontrol_api.core.deps import UoWFactory
from fincontrol_api.modules.market.use_cases import MarketDataHandler


def get_market_data_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> MarketDataHandler:
    """Provide the MarketDataHandler instance."""
    return MarketDataHandler(uow_factory=uow_factory)
