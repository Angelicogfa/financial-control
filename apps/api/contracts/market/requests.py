"""Pydantic request/response DTOs for the market module.

Scope: market data jobs and series freshness.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from domain.shared.enums import (
    SeriesUnit,
)


class JobRunDTO(BaseModel):
    """Latest execution of a background job."""

    job_name: str
    status: str
    attempts: int
    started_at: datetime
    finished_at: datetime | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class SeriesStatusDTO(BaseModel):
    """Freshness diagnostics of a persisted market or macro series."""

    symbol: str
    unit: SeriesUnit | None = None
    points: int
    first_date: date | None = None
    last_date: date | None = None
    stale: bool
    missing_business_days: int
