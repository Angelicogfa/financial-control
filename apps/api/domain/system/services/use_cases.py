"""Use cases (command/query handlers) for the system module.

Scope: health and readiness probes.
"""

from __future__ import annotations

from collections.abc import Callable

from controllers.system.responses import ReadinessCheckDTO, ReadinessDTO
from infra.data.health import DatabaseStatus
from infra.providers.gateway import CachedMarketGateway

DatabaseProbe = Callable[[], DatabaseStatus]


class SystemHandler:
    """Reports whether the API can serve traffic: database reachable and migrated, cache up."""

    def __init__(self, gateway: CachedMarketGateway, database_probe: DatabaseProbe) -> None:
        self.gateway = gateway
        self.database_probe = database_probe

    def readiness(self) -> ReadinessDTO:
        db = self.database_probe()
        cache_ok = self.gateway.cache.ping()
        checks = {
            "database": ReadinessCheckDTO(ok=db.reachable, detail=db.error or "reachable"),
            "migrations": ReadinessCheckDTO(
                ok=db.migrated,
                detail=f"current={db.current_revision} head={db.head_revision}",
            ),
            "cache": ReadinessCheckDTO(ok=cache_ok, detail=self.gateway.cache.backend_name),
        }
        if not (db.reachable and db.migrated):
            status = "not_ready"
        elif not cache_ok:
            status = "degraded"
        else:
            status = "ready"
        return ReadinessDTO(status=status, checks=checks)
