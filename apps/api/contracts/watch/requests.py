"""Request schemas of Acompanhar: alert rules and thesis notes (Phase 48.R6)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from domain.watch.entities import RuleMetric, RuleOperator


class AlertRuleCreateRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=32)
    metric: RuleMetric
    operator: RuleOperator
    threshold: Decimal = Field(..., ge=0, description="Dividend yield as a fraction (0.08 = 8%)")
    note: str | None = Field(default=None, max_length=500)


class AlertRuleUpdateRequest(BaseModel):
    threshold: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None
    note: str | None = Field(default=None, max_length=500)


class AssetNoteRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    review_at: date | None = None
    written_on: date | None = Field(default=None, description="Today when omitted (create only)")
