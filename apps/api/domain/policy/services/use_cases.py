"""Use cases (command/query handlers) for the policy module.

Scope: versioned investment policy and ARCA targets.
"""

from __future__ import annotations

from dataclasses import asdict

from controllers.policy.requests import (
    ArcaTargetItemDTO,
    ArcaTargetsUpdateRequest,
    ClassPolicyDTO,
    EligibilityPolicyDTO,
    HealthPolicyDTO,
    PolicyUpdateRequest,
    ProjectionAssumptionsDTO,
    RecommendationPolicyDTO,
    ValuationPolicyDTO,
)
from controllers.policy.responses import PolicyDTO
from controllers.shared.dependencies import UoWFactory
from domain.policy.services.assumptions import ProjectionAssumptions
from domain.policy.services.policy import (
    ArcaPolicy,
    ClassPolicy,
    EligibilityPolicy,
    HealthPolicy,
    InvestmentPolicy,
    RecommendationPolicy,
    ValuationPolicy,
    current_policy,
)
from domain.shared.enums import ArcaClass


def to_policy_dto(policy: InvestmentPolicy) -> PolicyDTO:
    return PolicyDTO(
        version=policy.version,
        created_at=policy.created_at,
        arca=[
            ClassPolicyDTO(
                arca_class=c,
                target_pct=p.target_pct,
                band_pct=p.band_pct,
                intra_class_strategy=p.intra_class_strategy,
            )
            for c, p in policy.arca.classes.items()
        ],
        eligibility=EligibilityPolicyDTO(**asdict(policy.eligibility)),
        valuation=ValuationPolicyDTO(
            **policy.valuation.as_dict(),
            projections=ProjectionAssumptionsDTO(**policy.valuation.projections.as_dict()),
        ),
        health=HealthPolicyDTO(**policy.health.as_dict()),
        recommendation=RecommendationPolicyDTO(
            objectives=dict(policy.recommendation.objectives),  # type: ignore[arg-type]
            matrices={
                o: [list(row) for row in m] for o, m in policy.recommendation.matrices.items()
            },
            score_scale_annual=policy.recommendation.score_scale_annual,
            risk_aversion=policy.recommendation.risk_aversion,
            k_min=policy.recommendation.k_min,
            k_max=policy.recommendation.k_max,
            sector_cap=policy.recommendation.sector_cap,
            group_cap=policy.recommendation.group_cap,
            max_per_sector=policy.recommendation.max_per_sector,
            sector_margin_sd=policy.recommendation.sector_margin_sd,
            min_lot_brl=policy.recommendation.min_lot_brl,
        ),
    )


def _recommendation_policy(dto: RecommendationPolicyDTO) -> RecommendationPolicy:
    return RecommendationPolicy(
        objectives=dict(dto.objectives),
        matrices={o: tuple(tuple(row) for row in m) for o, m in dto.matrices.items()},
        score_scale_annual=dto.score_scale_annual,
        risk_aversion=dto.risk_aversion,
        k_min=dto.k_min,
        k_max=dto.k_max,
        sector_cap=dto.sector_cap,
        group_cap=dto.group_cap,
        max_per_sector=dto.max_per_sector,
        sector_margin_sd=dto.sector_margin_sd,
        min_lot_brl=dto.min_lot_brl,
    )


def _arca_policy(items: list[ClassPolicyDTO]) -> ArcaPolicy:
    return ArcaPolicy(
        {
            item.arca_class: ClassPolicy(
                target_pct=item.target_pct,
                band_pct=item.band_pct,
                intra_class_strategy=item.intra_class_strategy,
            )
            for item in items
        }
    )


class PolicyHandler:
    """Application handler for the versioned investment policy."""

    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def get_current(self) -> PolicyDTO:
        with self.uow_factory() as uow:
            return to_policy_dto(current_policy(uow.policies))

    def list_versions(self, limit: int = 20) -> list[PolicyDTO]:
        with self.uow_factory() as uow:
            return [to_policy_dto(p) for p in uow.policies.list_versions(limit)]

    def update(self, req: PolicyUpdateRequest) -> PolicyDTO:
        recommendation = (
            _recommendation_policy(req.recommendation) if req.recommendation is not None else None
        )
        with self.uow_factory() as uow:
            kept = current_policy(uow.policies).recommendation
        policy = InvestmentPolicy(
            arca=_arca_policy(req.arca),
            eligibility=EligibilityPolicy(**req.eligibility.model_dump()),
            valuation=ValuationPolicy(
                **req.valuation.model_dump(exclude={"projections"}),
                projections=ProjectionAssumptions(**req.valuation.projections.model_dump()),
            ),
            health=HealthPolicy(**req.health.model_dump()),
            recommendation=recommendation or kept,
        )
        with self.uow_factory() as uow:
            saved = uow.policies.add(policy)
            uow.commit()
            return to_policy_dto(saved)

    def get_arca_targets(self) -> list[ArcaTargetItemDTO]:
        with self.uow_factory() as uow:
            arca = current_policy(uow.policies).arca
        return [
            ArcaTargetItemDTO(
                arca_class=c,
                target_pct=arca.classes[c].target_pct,
                intra_class_strategy=arca.classes[c].intra_class_strategy,
            )
            for c in ArcaClass
        ]

    def update_arca_targets(self, req: ArcaTargetsUpdateRequest) -> list[ArcaTargetItemDTO]:
        requested = {item.arca_class: item for item in req.targets}
        with self.uow_factory() as uow:
            current = current_policy(uow.policies)
            bands = current.arca.bands
            arca = ArcaPolicy(
                {
                    c: ClassPolicy(
                        target_pct=item.target_pct,
                        band_pct=bands.get(c, 5.0),
                        intra_class_strategy=item.intra_class_strategy,
                    )
                    for c, item in requested.items()
                }
            )
            uow.policies.add(current.with_arca(arca))
            uow.commit()
        return [
            ArcaTargetItemDTO(
                arca_class=c,
                target_pct=arca.classes[c].target_pct,
                intra_class_strategy=arca.classes[c].intra_class_strategy,
            )
            for c in ArcaClass
        ]
