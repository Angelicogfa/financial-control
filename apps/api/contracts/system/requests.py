"""Pydantic request/response DTOs for the system module.

Scope: health and readiness probes.
"""

from __future__ import annotations

from pydantic import BaseModel


class ReadinessCheckDTO(BaseModel):
    ok: bool
    detail: str


class ReadinessDTO(BaseModel):
    """Readiness of the API: `ready`, `degraded` (cache down) or `not_ready`."""

    status: str
    checks: dict[str, ReadinessCheckDTO]
