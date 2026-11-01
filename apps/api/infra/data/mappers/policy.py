"""ORM model <-> domain entity mappers: versioned investment policy."""

from __future__ import annotations

from dataclasses import asdict, fields

from domain.policy.services.assumptions import ProjectionAssumptions
from domain.policy.services.policy import (
    ArcaPolicy,
    ClassPolicy,
    EligibilityPolicy,
    HealthPolicy,
    InvestmentPolicy,
    RecommendationPolicy,
    ValuationPolicy,
)
from domain.shared.enums import (
    ArcaClass,
    IntraClassStrategy,
)
from infra.data.models.policy import InvestmentPolicyModel

CONSTRUCTION_FIELDS = (
    "risk_aversion",
    "k_min",
    "k_max",
    "sector_cap",
    "group_cap",
    "max_per_sector",
    "sector_margin_sd",
    "min_lot_brl",
    "use_cerrado",
)


def policy_payload(policy: InvestmentPolicy) -> dict[str, dict]:
    """JSON-serializable sections of a policy for storage."""
    return {
        "arca": {
            c.value: {
                "target_pct": p.target_pct,
                "band_pct": p.band_pct,
                "intra_class_strategy": p.intra_class_strategy.value,
            }
            for c, p in policy.arca.classes.items()
        },
        "eligibility": asdict(policy.eligibility),
        "valuation": {
            **policy.valuation.as_dict(),
            "projections": policy.valuation.projections.as_dict(),
        },
        "health": policy.health.as_dict(),
        "recommendation": {
            "objectives": {c.value: o for c, o in policy.recommendation.objectives.items()},
            "matrices": {
                o: [list(row) for row in m] for o, m in policy.recommendation.matrices.items()
            },
            "score_scale_annual": policy.recommendation.score_scale_annual,
            **{name: getattr(policy.recommendation, name) for name in CONSTRUCTION_FIELDS},
        },
    }


def _recommendation_policy(raw: dict | None) -> RecommendationPolicy:
    """Versions saved before Phase 45.3 have no recommendation premises and take the defaults."""
    if not raw:
        return RecommendationPolicy()
    return RecommendationPolicy(
        objectives={ArcaClass(c): o for c, o in raw.get("objectives", {}).items()},
        matrices={o: tuple(tuple(row) for row in m) for o, m in raw["matrices"].items()},
        score_scale_annual=float(raw.get("score_scale_annual", 0.06)),
        **{name: raw[name] for name in CONSTRUCTION_FIELDS if name in raw},
    )


def _health_policy(raw: dict | None) -> HealthPolicy:
    """Versions saved before Phase 29 have no health limits and take the defaults."""
    known = {f.name for f in fields(HealthPolicy)}
    return HealthPolicy(**{k: v for k, v in (raw or {}).items() if k in known})


def to_investment_policy(model: InvestmentPolicyModel) -> InvestmentPolicy:
    valuation = dict(model.valuation)
    projections = ProjectionAssumptions(**valuation.pop("projections", {}))
    return InvestmentPolicy(
        arca=ArcaPolicy(
            {
                ArcaClass(c): ClassPolicy(
                    target_pct=float(p["target_pct"]),
                    band_pct=float(p.get("band_pct", 5.0)),
                    intra_class_strategy=IntraClassStrategy(p["intra_class_strategy"]),
                )
                for c, p in model.arca.items()
            }
        ),
        eligibility=EligibilityPolicy(**model.eligibility),
        valuation=ValuationPolicy(projections=projections, **valuation),
        health=_health_policy(model.health),
        recommendation=_recommendation_policy(model.recommendation),
        version=model.version,
        created_at=model.created_at,
    )
