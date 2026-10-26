"""HTTP controllers (routers) of the policy module; they only delegate to use cases.

Scope: versioned investment policy and ARCA targets.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from fincontrol_api.modules.policy.dependencies import get_policy_handler
from fincontrol_api.modules.policy.schemas import (
    ArcaTargetItemDTO,
    ArcaTargetsUpdateRequest,
    PolicyDTO,
    PolicyUpdateRequest,
)
from fincontrol_api.modules.policy.use_cases import PolicyHandler

settings_router = APIRouter(prefix="/settings", tags=["Settings"])


policy_router = APIRouter(prefix="/policy", tags=["Investment Policy"])


@settings_router.get("/arca-targets", response_model=list[ArcaTargetItemDTO])
def get_arca_targets(
    handler: PolicyHandler = Depends(get_policy_handler),
) -> list[ArcaTargetItemDTO]:
    return handler.get_arca_targets()


@settings_router.put("/arca-targets", response_model=list[ArcaTargetItemDTO])
def update_arca_targets(
    payload: ArcaTargetsUpdateRequest,
    handler: PolicyHandler = Depends(get_policy_handler),
) -> list[ArcaTargetItemDTO]:
    return handler.update_arca_targets(payload)


@policy_router.get("", response_model=PolicyDTO)
def get_policy(handler: PolicyHandler = Depends(get_policy_handler)) -> PolicyDTO:
    return handler.get_current()


@policy_router.put("", response_model=PolicyDTO)
def update_policy(
    payload: PolicyUpdateRequest,
    handler: PolicyHandler = Depends(get_policy_handler),
) -> PolicyDTO:
    return handler.update(payload)


@policy_router.get("/versions", response_model=list[PolicyDTO])
def list_policy_versions(
    limit: int = Query(default=20, ge=1, le=200),
    handler: PolicyHandler = Depends(get_policy_handler),
) -> list[PolicyDTO]:
    return handler.list_versions(limit)
