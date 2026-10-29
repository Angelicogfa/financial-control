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


class QuoteStatusDTO(BaseModel):
    """How old the stored quotes are (Phase 38): screens read them, the worker refreshes them."""

    holdings: int = Field(description="Assets with trades priced from the market.")
    stored: int = Field(description="How many of them have a stored quote.")
    oldest_at: datetime | None = Field(
        default=None, description="Fetch time of the oldest stored quote among the holdings."
    )
    newest_at: datetime | None = Field(
        default=None, description="Fetch time of the newest stored quote among the holdings."
    )
    stale: int = Field(description="Holdings whose quote is missing or older than `stale_minutes`.")
    stale_minutes: int


class QuoteDayDTO(BaseModel):
    """The last stored quote of a ticker on a day (audit trail, Phase 39.1)."""

    day: date
    price: float
    currency: str
    provider: str | None = None
    freshness: str
    fetched_at: datetime


class WorkerRequestErrorDTO(BaseModel):
    """Detailed log entry for a failed upstream request made during a background worker job."""

    id: int
    job_run_id: int | None = None
    job_name: str
    provider: str
    operation: str
    target: str
    request_url: str
    status_code: int | None = None
    error_type: str
    error_detail: str
    occurred_at: datetime
    resolved_at: datetime | None = None


class WorkerErrorsResponseDTO(BaseModel):
    """Worker request error log and unresolved notification count."""

    unresolved_count: int
    errors: list[WorkerRequestErrorDTO]
