"""Pydantic response DTOs for the contributions module.

Scope: saved contribution plans and their confirmation.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from controllers.contributions.requests import ExecutionDTO
from controllers.portfolio.responses import ContributionPlanResponseDTO
from domain.shared.enums import (
    ContributionPlanStatus,
    IntraClassStrategy,
)


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
