"""Response schemas of Acompanhar: alert rules and thesis notes (Phase 48.R6)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from domain.watch.entities import RuleMetric, RuleOperator


class AlertRuleDTO(BaseModel):
    id: int
    ticker: str
    metric: RuleMetric
    operator: RuleOperator
    threshold: float
    is_active: bool
    note: str | None = None
    description: str = Field(description="The rule in words, pt-BR")
    current_value: float | None = Field(default=None, description="Read now from the database")
    triggered: bool = Field(description="Active and holding now")
    triggered_at: datetime | None = Field(default=None, description="When the worker saw it fire")
    last_checked_at: datetime | None = None
    created_at: datetime | None = None


class AssetNoteDTO(BaseModel):
    id: int
    asset_id: int
    ticker: str | None = None
    written_on: date
    text: str
    review_at: date | None = None
    due: bool = Field(description="The review date arrived")
    created_at: datetime | None = None
    updated_at: datetime | None = None
