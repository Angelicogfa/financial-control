"""Pydantic response DTOs for the policy module.

Scope: versioned investment policy and ARCA targets.
"""

from __future__ import annotations

from datetime import datetime

from controllers.policy.requests import (
    ArcaTargetItemDTO,
    ArcaTargetsUpdateRequest,
    ClassPolicyDTO,
    EligibilityPolicyDTO,
    HealthPolicyDTO,
    PolicyUpdateRequest,
    ProjectionAssumptionsDTO,
    ValuationPolicyDTO,
)


class PolicyDTO(PolicyUpdateRequest):
    version: int | None = None
    created_at: datetime | None = None


__all__ = [
    "ArcaTargetItemDTO",
    "ArcaTargetsUpdateRequest",
    "ClassPolicyDTO",
    "EligibilityPolicyDTO",
    "HealthPolicyDTO",
    "PolicyDTO",
    "PolicyUpdateRequest",
    "ProjectionAssumptionsDTO",
    "ValuationPolicyDTO",
]
