"""InvestmentPolicy aggregate: ARCA targets and bands, eligibility and valuation premises.

Every engine (allocation, contribution, lifecycle, valuation, projections) receives the
policy explicitly; no business premise is hard-coded (ADR 0005, finding I-11). Policies are
immutable and versioned: changing a rule creates a new version.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import TYPE_CHECKING

from fincontrol_core.arca.allocation import ArcaTargets, InvalidTargetsError
from fincontrol_core.domain.enums import ArcaClass, IntraClassStrategy
from fincontrol_core.errors import ValidationError
from fincontrol_core.portfolio.consolidation import ProjectionAssumptions

if TYPE_CHECKING:
    from fincontrol_core.ports.repositories import AbstractPolicyRepository

MAX_BAND_PCT = 50.0


@dataclass(frozen=True)
class ClassPolicy:
    """Target weight, tolerance band (percentage points) and intra-class strategy."""

    target_pct: float
    band_pct: float = 5.0
    intra_class_strategy: IntraClassStrategy = IntraClassStrategy.CERRADO

    def __post_init__(self) -> None:
        if not 0.0 <= self.target_pct <= 100.0:
            raise InvalidTargetsError("target_pct must be between 0 and 100")
        if not 0.0 <= self.band_pct <= MAX_BAND_PCT:
            raise ValidationError(
                f"band_pct must be between 0 and {MAX_BAND_PCT:.0f} percentage points",
                code="INVALID_BAND",
            )


@dataclass(frozen=True)
class ArcaPolicy:
    """Macro-allocation rules for the four ARCA classes."""

    classes: Mapping[ArcaClass, ClassPolicy]

    def __post_init__(self) -> None:
        # Validates presence of every class and the 100% sum.
        ArcaTargets({c: p.target_pct for c, p in self.classes.items()})

    @classmethod
    def default(cls) -> ArcaPolicy:
        return cls(dict.fromkeys(ArcaClass, ClassPolicy(target_pct=25.0)))

    @property
    def targets(self) -> ArcaTargets:
        return ArcaTargets({c: p.target_pct for c, p in self.classes.items()})

    @property
    def strategies(self) -> dict[ArcaClass, IntraClassStrategy]:
        return {c: p.intra_class_strategy for c, p in self.classes.items()}

    @property
    def bands(self) -> dict[ArcaClass, float]:
        return {c: p.band_pct for c, p in self.classes.items()}


@dataclass(frozen=True)
class EligibilityPolicy:
    """When an asset is fit to receive contributions (fundamentalist lens).

    - `require_evaluation=False` keeps the checklist optional: assets never evaluated are
      eligible (ADR 0002); evaluated assets must meet the score and coverage below.
    - `min_score` is the minimum checklist score (yes = +1, no = -1).
    - `min_coverage_pct` is the minimum share of answered questions (0-100).
    """

    require_evaluation: bool = False
    min_score: int = 1
    min_coverage_pct: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_coverage_pct <= 100.0:
            raise ValidationError("min_coverage_pct must be between 0 and 100")


@dataclass(frozen=True)
class ValuationPolicy:
    """Valuation premises (Bazin, Graham) and 12-month projection assumptions."""

    bazin_required_yield: float = 0.06
    graham_multiplier: float = 22.5
    projections: ProjectionAssumptions = field(default_factory=ProjectionAssumptions)

    def __post_init__(self) -> None:
        if not 0.0 < self.bazin_required_yield < 1.0:
            raise ValidationError("bazin_required_yield must be an annual fraction (0.06 = 6%)")
        if self.graham_multiplier <= 0:
            raise ValidationError("graham_multiplier must be positive")


@dataclass(frozen=True)
class InvestmentPolicy:
    """Complete, versioned set of rules applied by every operational context."""

    arca: ArcaPolicy = field(default_factory=ArcaPolicy.default)
    eligibility: EligibilityPolicy = field(default_factory=EligibilityPolicy)
    valuation: ValuationPolicy = field(default_factory=ValuationPolicy)
    version: int | None = None
    created_at: datetime | None = None

    def with_arca(self, arca: ArcaPolicy) -> InvestmentPolicy:
        """A new (unsaved) policy changing only the ARCA rules."""
        return replace(self, arca=arca, version=None, created_at=None)


def current_policy(policies: AbstractPolicyRepository) -> InvestmentPolicy:
    """The latest stored policy, or the defaults when none was ever saved."""
    return policies.get_current() or InvestmentPolicy()
