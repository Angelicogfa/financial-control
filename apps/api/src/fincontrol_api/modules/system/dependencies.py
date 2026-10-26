"""FastAPI dependency providers for the system module.

Scope: health and readiness probes.
"""

from __future__ import annotations

from fastapi import Depends
from fincontrol_core.market.gateway import CachedMarketGateway

from fincontrol_api.composition import get_database_probe, get_market_gateway
from fincontrol_api.modules.system.use_cases import DatabaseProbe, SystemHandler


def get_system_handler(
    gateway: CachedMarketGateway = Depends(get_market_gateway),
    database_probe: DatabaseProbe = Depends(get_database_probe),
) -> SystemHandler:
    """Provide the SystemHandler instance."""
    return SystemHandler(gateway=gateway, database_probe=database_probe)
