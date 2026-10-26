"""Pydantic request/response DTOs for the contributions module.

Scope: saved contribution plans and their confirmation.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from controllers.portfolio.responses import ContributionPlanResponseDTO
from domain.shared.enums import (
    ContributionPlanStatus,
    IntraClassStrategy,
)


class ExecutionDTO(BaseModel):
    """What was bought for one asset of the plan, in the asset currency with its `fx_rate`.

    For a foreign asset sent with `fx_rate=1`, price and fees are read as BRL (as the plan
    shows them) and converted at the day's USD/BRL rate.
    """

    asset_id: int
    quantity: Decimal = Field(..., gt=Decimal("0"))
    unit_price: Decimal = Field(..., ge=Decimal("0"))
    fees: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    fx_rate: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))


class ContributionConfirmRequest(BaseModel):
    """Confirm a draft: without `executions`, the suggested quantities and prices are used."""

    trade_date: date
    account_id: int | None = None
    executions: list[ExecutionDTO] | None = None


class SavedContributionPlanDTO(BaseModel):
    id: int
    status: ContributionPlanStatus
    created_at: datetime | None = None
    confirmed_at: datetime | None = None
    discarded_at: datetime | None = None
    strategy_override: IntraClassStrategy | None = None
    policy_version: int | None = None
    account_id: int | None = None
    transaction_ids: list[int] = Field(default_factory=list)
    plan: ContributionPlanResponseDTO
