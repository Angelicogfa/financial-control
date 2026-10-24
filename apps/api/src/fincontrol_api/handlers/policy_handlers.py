"""Investment policy commands and queries (item 10.1, ADR 0005).

`/settings/arca-targets` is kept as a thin facade: editing targets there creates a new
policy version that keeps the current bands, eligibility and valuation rules.
"""

from __future__ import annotations

from collections.abc import Callable

from fincontrol_core.domain.enums import ArcaClass
from fincontrol_core.policy import (
    ArcaPolicy,
    ClassPolicy,
    EligibilityPolicy,
    InvestmentPolicy,
    ValuationPolicy,
    current_policy,
)
from fincontrol_core.portfolio.consolidation import ProjectionAssumptions
from fincontrol_core.ports.unit_of_work import AbstractUnitOfWork

from fincontrol_api.schemas import (
    ArcaTargetItemDTO,
    ArcaTargetsUpdateRequest,
    ClassPolicyDTO,
    EligibilityPolicyDTO,
    PolicyDTO,
    PolicyUpdateRequest,
    ProjectionAssumptionsDTO,
    ValuationPolicyDTO,
)

UoWFactory = Callable[[], AbstractUnitOfWork]


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
        eligibility=EligibilityPolicyDTO(
            require_evaluation=policy.eligibility.require_evaluation,
            min_score=policy.eligibility.min_score,
            min_coverage_pct=policy.eligibility.min_coverage_pct,
        ),
        valuation=ValuationPolicyDTO(
            bazin_required_yield=policy.valuation.bazin_required_yield,
            graham_multiplier=policy.valuation.graham_multiplier,
            projections=ProjectionAssumptionsDTO(**policy.valuation.projections.as_dict()),
        ),
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
        policy = InvestmentPolicy(
            arca=_arca_policy(req.arca),
            eligibility=EligibilityPolicy(
                require_evaluation=req.eligibility.require_evaluation,
                min_score=req.eligibility.min_score,
                min_coverage_pct=req.eligibility.min_coverage_pct,
            ),
            valuation=ValuationPolicy(
                bazin_required_yield=req.valuation.bazin_required_yield,
                graham_multiplier=req.valuation.graham_multiplier,
                projections=ProjectionAssumptions(**req.valuation.projections.model_dump()),
            ),
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
