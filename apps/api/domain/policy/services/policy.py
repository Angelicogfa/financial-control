"""InvestmentPolicy aggregate: ARCA targets and bands, eligibility and valuation premises.

Every engine (allocation, contribution, lifecycle, valuation, projections) receives the
policy explicitly; no business premise is hard-coded (ADR 0005, finding I-11). Policies are
immutable and versioned: changing a rule creates a new version.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace
from datetime import datetime
from typing import TYPE_CHECKING

from core.errors import ValidationError
from domain.policy.services.allocation import ArcaTargets, InvalidTargetsError
from domain.policy.services.assumptions import ProjectionAssumptions
from domain.shared.enums import ArcaClass, IntraClassStrategy

if TYPE_CHECKING:
    from domain.shared.repositories import AbstractPolicyRepository

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
    # Phase 25: a manual answer expires after `answer_validity_months` or when a newer
    # annual statement arrives. Expired answers flag the asset for review
    # (`review_on_expired_answers`) and, with `drop_expired_answers`, leave the score.
    answer_validity_months: int = 12
    review_on_expired_answers: bool = True
    drop_expired_answers: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_coverage_pct <= 100.0:
            raise ValidationError("min_coverage_pct must be between 0 and 100")
        if not 1 <= self.answer_validity_months <= 120:
            raise ValidationError("answer_validity_months must be between 1 and 120")


@dataclass(frozen=True)
class ValuationPolicy:
    """Valuation premises by instrument type (item 11.5) and 12-month projection assumptions.

    Rates and margins are fractions (ADR 0006); multiples are plain ratios.
    `reference_real_yield` is the inflation-linked bond (NTN-B) real yield FIIs compete with.
    """

    bazin_required_yield: float = 0.06
    graham_multiplier: float = 22.5
    max_price_to_earnings: float = 15.0
    max_ev_to_ebitda: float = 10.0
    max_price_to_book_bank: float = 2.0
    bank_cost_of_equity: float = 0.14
    max_price_to_book_fii: float = 1.05
    reference_real_yield: float = 0.06
    min_fii_spread: float = 0.02
    min_margin_of_safety: float = 0.15
    # Tesouro Direto (Phase 26): weight the quadrant by the redemption price instead of
    # the curve, and the thresholds of the early-sale opportunity.
    treasury_mark_to_market: bool = True
    early_sale_min_excess_rate: float = 0.01
    early_sale_min_reinvest_spread: float = 0.005
    projections: ProjectionAssumptions = field(default_factory=ProjectionAssumptions)

    def __post_init__(self) -> None:
        if not 0.0 < self.bazin_required_yield < 1.0:
            raise ValidationError("bazin_required_yield must be an annual fraction (0.06 = 6%)")
        for name in (
            "graham_multiplier",
            "max_price_to_earnings",
            "max_ev_to_ebitda",
            "max_price_to_book_bank",
            "max_price_to_book_fii",
        ):
            if getattr(self, name) <= 0:
                raise ValidationError(f"{name} must be positive")
        if not 0.0 < self.bank_cost_of_equity < 1.0:
            raise ValidationError("bank_cost_of_equity must be an annual fraction")
        for name in (
            "reference_real_yield",
            "min_fii_spread",
            "min_margin_of_safety",
            "early_sale_min_excess_rate",
            "early_sale_min_reinvest_spread",
        ):
            if not -1.0 < getattr(self, name) < 1.0:
                raise ValidationError(f"{name} must be a fraction (0.06 = 6%)")

    def as_dict(self) -> dict[str, float | bool]:
        """Scalar premises (projections excluded)."""
        return {f.name: getattr(self, f.name) for f in fields(self) if f.name != "projections"}


@dataclass(frozen=True)
class HealthPolicy:
    """Limits of the portfolio health diagnosis (Phase 29); fractions follow ADR 0006.

    Each `*_warning` / `*_critical` pair marks where a check turns "atenção" and "crítico".
    For maximum limits the warning must not exceed the critical value; for minimums it must
    not be below it. `monthly_expenses_brl=None` leaves the reserve check without data.
    """

    max_asset_weight_warning: float = 0.15
    max_asset_weight_critical: float = 0.25
    max_top5_weight_warning: float = 0.60
    max_top5_weight_critical: float = 0.80
    max_sector_weight_warning: float = 0.30
    max_sector_weight_critical: float = 0.45
    min_effective_assets_warning: float = 8.0
    min_effective_assets_critical: float = 4.0
    fgc_limit_brl: float = 250_000.0
    fgc_warning_ratio: float = 0.90
    min_diversification_ratio_warning: float = 1.20
    min_diversification_ratio_critical: float = 1.05
    high_correlation: float = 0.80
    max_asset_risk_share: float = 0.25
    max_volatility_warning: float = 0.15
    max_volatility_critical: float = 0.25
    max_drawdown_warning: float = 0.10
    max_drawdown_critical: float = 0.20
    max_stress_loss_warning: float = 0.10
    max_stress_loss_critical: float = 0.20
    min_cdi_consistency: float = 0.50
    min_checklist_quality_warning: float = 0.50
    min_checklist_quality_critical: float = 0.0
    max_stale_checklist_weight: float = 0.20
    monthly_expenses_brl: float | None = None
    min_reserve_months_warning: float = 6.0
    min_reserve_months_critical: float = 3.0
    min_liquid_weight: float = 0.20
    bracket_window_days: int = 30
    min_observations: int = 60

    _MAX_PAIRS = (
        "asset_weight",
        "top5_weight",
        "sector_weight",
        "volatility",
        "drawdown",
        "stress_loss",
    )
    _MIN_PAIRS = (
        "effective_assets",
        "diversification_ratio",
        "checklist_quality",
        "reserve_months",
    )

    def __post_init__(self) -> None:
        for name in self._MAX_PAIRS:
            warning = getattr(self, f"max_{name}_warning")
            critical = getattr(self, f"max_{name}_critical")
            if not 0.0 <= warning <= critical:
                raise ValidationError(
                    f"max_{name}: warning must be between 0 and the critical limit",
                    code="INVALID_HEALTH_LIMIT",
                )
        for name in self._MIN_PAIRS:
            warning = getattr(self, f"min_{name}_warning")
            critical = getattr(self, f"min_{name}_critical")
            if warning < critical:
                raise ValidationError(
                    f"min_{name}: warning must not be below the critical limit",
                    code="INVALID_HEALTH_LIMIT",
                )
        for name in (
            "fgc_warning_ratio",
            "high_correlation",
            "max_asset_risk_share",
            "min_cdi_consistency",
            "max_stale_checklist_weight",
            "min_liquid_weight",
        ):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValidationError(
                    f"{name} must be a fraction between 0 and 1", code="INVALID_HEALTH_LIMIT"
                )
        if self.fgc_limit_brl <= 0:
            raise ValidationError("fgc_limit_brl must be positive", code="INVALID_HEALTH_LIMIT")
        if self.monthly_expenses_brl is not None and self.monthly_expenses_brl <= 0:
            raise ValidationError(
                "monthly_expenses_brl must be positive", code="INVALID_HEALTH_LIMIT"
            )
        for name in ("bracket_window_days", "min_observations"):
            if getattr(self, name) < 1:
                raise ValidationError(f"{name} must be at least 1", code="INVALID_HEALTH_LIMIT")

    def as_dict(self) -> dict[str, float | int | None]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass(frozen=True)
class InvestmentPolicy:
    """Complete, versioned set of rules applied by every operational context."""

    arca: ArcaPolicy = field(default_factory=ArcaPolicy.default)
    eligibility: EligibilityPolicy = field(default_factory=EligibilityPolicy)
    valuation: ValuationPolicy = field(default_factory=ValuationPolicy)
    health: HealthPolicy = field(default_factory=HealthPolicy)
    version: int | None = None
    created_at: datetime | None = None

    def with_arca(self, arca: ArcaPolicy) -> InvestmentPolicy:
        """A new (unsaved) policy changing only the ARCA rules."""
        return replace(self, arca=arca, version=None, created_at=None)


def current_policy(policies: AbstractPolicyRepository) -> InvestmentPolicy:
    """The latest stored policy, or the defaults when none was ever saved."""
    return policies.get_current() or InvestmentPolicy()
