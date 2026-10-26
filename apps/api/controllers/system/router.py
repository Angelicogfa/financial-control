"""HTTP controllers (routers) of the system module; they only delegate to use cases.

Scope: health and readiness probes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from controllers.system.dependencies import get_system_handler
from controllers.system.responses import ReadinessDTO
from domain.system.services.use_cases import SystemHandler

health_router = APIRouter(tags=["Health"])


@health_router.get("/health")
def get_health() -> dict[str, str]:
    """Liveness check: the process is up (no dependency is touched)."""
    return {"status": "ok", "service": "fincontrol-api"}


@health_router.get("/ready", response_model=ReadinessDTO)
def get_ready(
    response: Response,
    handler: SystemHandler = Depends(get_system_handler),
) -> ReadinessDTO:
    """Readiness check: database reachable and migrated (503 otherwise), cache status."""
    result = handler.readiness()
    if result.status == "not_ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
