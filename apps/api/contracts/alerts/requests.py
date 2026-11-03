"""Pydantic request/response DTOs for the alerts module.

Scope: portfolio, valuation and data alerts.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AlertDTO(BaseModel):
    key: str
    kind: str
    severity: str
    title: str
    detail: str
    subject: str | None = None
    route: str | None = None


class AlertsResponseDTO(BaseModel):
    alerts: list[AlertDTO]
    dismissed: int
    generated_at: datetime


class AlertDismissRequest(BaseModel):
    """Hide an alert for `days` (default 7); `days=null` hides it while it persists."""

    key: str = Field(..., min_length=1, max_length=160)
    days: int | None = Field(default=7, ge=1, le=365)
