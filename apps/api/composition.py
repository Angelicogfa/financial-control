"""Composition root: the only place that picks the infrastructure implementations
(SQLAlchemy Unit of Work, market data gateway, database probe) the modules receive."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from controllers.shared.dependencies import UoWFactory
from core.settings import AppSettings, get_settings
from domain.system.services.use_cases import DatabaseProbe
from infra.data.health import check_database
from infra.data.unit_of_work import SqlAlchemyUnitOfWork
from infra.providers.factory import build_market_gateway
from infra.providers.gateway import CachedMarketGateway


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
