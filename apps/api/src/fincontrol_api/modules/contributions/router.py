"""HTTP controllers (routers) of the contributions module; they only delegate to use cases.

Scope: saved contribution plans and their confirmation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from fincontrol_core.domain.enums import ContributionPlanStatus

from fincontrol_api.modules.contributions.dependencies import get_contribution_handler
from fincontrol_api.modules.contributions.schemas import (
    ContributionConfirmRequest,
    SavedContributionPlanDTO,
)
from fincontrol_api.modules.contributions.use_cases import ContributionHandler
from fincontrol_api.modules.portfolio.schemas import ContributionSimulationRequest

contributions_router = APIRouter(prefix="/contributions", tags=["Contributions"])


@contributions_router.post(
    "", response_model=SavedContributionPlanDTO, status_code=status.HTTP_201_CREATED
)
def create_contribution_plan(
    payload: ContributionSimulationRequest,
    handler: ContributionHandler = Depends(get_contribution_handler),
) -> SavedContributionPlanDTO:
    return handler.create_draft(payload)


@contributions_router.get("", response_model=list[SavedContributionPlanDTO])
def list_contribution_plans(
    plan_status: ContributionPlanStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    handler: ContributionHandler = Depends(get_contribution_handler),
) -> list[SavedContributionPlanDTO]:
    return handler.list_recent(status=plan_status, limit=limit)


@contributions_router.get("/{plan_id}", response_model=SavedContributionPlanDTO)
def get_contribution_plan(
    plan_id: int,
    handler: ContributionHandler = Depends(get_contribution_handler),
) -> SavedContributionPlanDTO:
    return handler.get(plan_id)


@contributions_router.post("/{plan_id}/confirm", response_model=SavedContributionPlanDTO)
def confirm_contribution_plan(
    plan_id: int,
    payload: ContributionConfirmRequest,
    handler: ContributionHandler = Depends(get_contribution_handler),
) -> SavedContributionPlanDTO:
    return handler.confirm(plan_id, payload)


@contributions_router.post("/{plan_id}/discard", response_model=SavedContributionPlanDTO)
def discard_contribution_plan(
    plan_id: int,
    handler: ContributionHandler = Depends(get_contribution_handler),
) -> SavedContributionPlanDTO:
    return handler.discard(plan_id)
