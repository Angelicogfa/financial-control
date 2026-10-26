"""FastAPI dependency providers for the system module.

Scope: health and readiness probes.
"""

from __future__ import annotations

from fastapi import Depends

from composition import get_database_probe, get_market_gateway
from domain.system.services.use_cases import DatabaseProbe, SystemHandler
from infra.providers.gateway import CachedMarketGateway


def get_system_handler(
    gateway: CachedMarketGateway = Depends(get_market_gateway),
    database_probe: DatabaseProbe = Depends(get_database_probe),
) -> SystemHandler:
    """Provide the SystemHandler instance."""
    return SystemHandler(gateway=gateway, database_probe=database_probe)
