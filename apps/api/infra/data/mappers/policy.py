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
    ValuationPolicy,
)
from domain.shared.enums import (
    ArcaClass,
    IntraClassStrategy,
)
from infra.data.models.policy import InvestmentPolicyModel


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
    }


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
        version=model.version,
        created_at=model.created_at,
    )
