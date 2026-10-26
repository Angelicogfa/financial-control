"""Composition root: the only place that picks the infrastructure implementations
(SQLAlchemy Unit of Work, market data gateway, database probe) the modules receive."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends
from fincontrol_config import get_settings
from fincontrol_core.market.factory import build_market_gateway
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_persistence.core.health import check_database
from fincontrol_persistence.core.unit_of_work import SqlAlchemyUnitOfWork

from fincontrol_api.core.config import AppSettings
from fincontrol_api.core.deps import UoWFactory
from fincontrol_api.modules.system.use_cases import DatabaseProbe


def get_uow_factory() -> UoWFactory:
    """Return the Unit of Work factory."""
    return SqlAlchemyUnitOfWork


@lru_cache(maxsize=1)
def _singleton_gateway() -> CachedMarketGateway:
    return build_market_gateway(get_settings())


def get_market_gateway(
    _settings: AppSettings = Depends(get_settings),
) -> CachedMarketGateway:
    """Provide the configured CachedMarketGateway instance."""
    return _singleton_gateway()


def get_database_probe() -> DatabaseProbe:
    """Provide the database readiness probe."""
    return check_database
