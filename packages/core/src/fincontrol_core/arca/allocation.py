"""ARCA macro-allocation targets, deviations, and contribution distribution without selling."""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from dataclasses import dataclass

from fincontrol_core.domain.enums import ARCA_LABELS, ArcaClass
from fincontrol_core.errors import ValidationError

_TOLERANCE = 0.01

BAND_WITHIN = "WITHIN"
BAND_BELOW = "BELOW"
BAND_ABOVE = "ABOVE"


class InvalidTargetsError(ValidationError):
    """Raised when ARCA target weights do not sum to 100% or contain negative values."""

    code = "INVALID_ARCA_TARGETS"


@dataclass(frozen=True)
class ArcaTargets:
    """Target percentages (0-100) per ARCA class. Default: 25% each."""

    weights: Mapping[ArcaClass, float]

    def __post_init__(self) -> None:
        missing = set(ArcaClass) - set(self.weights)
        if missing:
            raise InvalidTargetsError(f"Missing ARCA target classes: {sorted(missing)}")
        if any(v < 0 for v in self.weights.values()):
            raise InvalidTargetsError("Target weights cannot be negative")
        total = sum(self.weights.values())
        if abs(total - 100.0) > _TOLERANCE:
            raise InvalidTargetsError(f"ARCA target weights must sum to 100% (got {total:.2f}%)")

    @classmethod
    def default(cls) -> ArcaTargets:
        return cls({c: 25.0 for c in ArcaClass})

    def fraction(self, arca_class: ArcaClass) -> float:
        return self.weights[arca_class] / 100.0

    def as_fractions(self) -> dict[ArcaClass, float]:
        return {c: self.fraction(c) for c in ArcaClass}


@dataclass(frozen=True)
class ClassAllocation:
    """Current vs target allocation state for a single ARCA macro-class."""

    arca_class: ArcaClass
    label: str
    invested_value: float
    current_value: float
    current_pct: float
    target_pct: float
    deviation_pct: float
    gap_value: float
    consolidated_pnl: float = 0.0
    band_pct: float = 0.0
    band_status: str = BAND_WITHIN


def band_status(current_pct: float, target_pct: float, band_pct: float, total: float) -> str:
    """WITHIN when |current - target| <= band (percentage points), else BELOW / ABOVE."""
    if total <= 0:
        return BAND_WITHIN
    deviation = current_pct - target_pct
    if deviation < -band_pct - _TOLERANCE:
        return BAND_BELOW
    if deviation > band_pct + _TOLERANCE:
        return BAND_ABOVE
    return BAND_WITHIN


def compute_allocation(
    values_by_class: Mapping[ArcaClass, float],
    targets: ArcaTargets,
    *,
    bands: Mapping[ArcaClass, float] | None = None,
    invested_by_class: Mapping[ArcaClass, float] | None = None,
    consolidated_pnl_by_class: Mapping[ArcaClass, float] | None = None,
) -> list[ClassAllocation]:
    """Current %, target %, deviation, R$ gap and tolerance-band status per ARCA class."""
    total = sum(max(values_by_class.get(c, 0.0), 0.0) for c in ArcaClass)
    result: list[ClassAllocation] = []
    for c in ArcaClass:
        value = max(values_by_class.get(c, 0.0), 0.0)
        invested = max((invested_by_class or {}).get(c, 0.0), 0.0)
        cons_pnl = (consolidated_pnl_by_class or {}).get(c, 0.0)
        current_pct = (value / total * 100.0) if total > 0 else 0.0
        target_pct = targets.weights[c]
        band = (bands or {}).get(c, 0.0)
        result.append(
            ClassAllocation(
                arca_class=c,
                label=ARCA_LABELS[c],
                invested_value=round(invested, 2),
                current_value=round(value, 2),
                current_pct=round(current_pct, 4),
                target_pct=round(target_pct, 4),
                deviation_pct=round(current_pct - target_pct, 4),
                gap_value=round(total * target_pct / 100.0 - value, 2),
                consolidated_pnl=round(cons_pnl, 2),
                band_pct=round(band, 4),
                band_status=band_status(current_pct, target_pct, band, total),
            )
        )
    return result


def distribute_with_bands(
    current: Mapping[ArcaClass, float],
    targets: ArcaTargets,
    below_band: set[ArcaClass],
    amount: float,
) -> dict[ArcaClass, float]:
    """Level-1 contribution that first refills classes below their band (finding A-01).

    Classes below the band receive money up to their target before anything else; whatever
    remains is split by `distribute_by_targets` across all classes.
    """
    if amount < 0:
        raise ValidationError("Contribution amount cannot be negative")
    result = dict.fromkeys(ArcaClass, 0.0)
    if not below_band:
        return distribute_by_targets(current, targets.as_fractions(), amount)

    total_after = sum(max(current.get(c, 0.0), 0.0) for c in ArcaClass) + amount
    deficits = {
        c: max(targets.fraction(c) * total_after - max(current.get(c, 0.0), 0.0), 0.0)
        for c in below_band
    }
    needed = sum(deficits.values())
    if needed >= amount and needed > 0:
        for c, deficit in deficits.items():
            result[c] = amount * deficit / needed
        return result

    for c, deficit in deficits.items():
        result[c] = deficit
    refilled = {c: current.get(c, 0.0) + result[c] for c in ArcaClass}
    for c, extra in distribute_by_targets(
        refilled, targets.as_fractions(), amount - needed
    ).items():
        result[c] += extra
    return result


def distribute_by_targets[K: Hashable](
    current: Mapping[K, float],
    target_weights: Mapping[K, float],
    amount: float,
) -> dict[K, float]:
    """Distribute a new cash contribution prioritizing items furthest below target (no selling)."""
    if amount < 0:
        raise ValidationError("Contribution amount cannot be negative")
    keys = list(target_weights)
    result: dict[K, float] = {k: 0.0 for k in keys}
    if amount == 0 or not keys:
        return result

    weight_sum = sum(max(w, 0.0) for w in target_weights.values())
    if weight_sum <= 0:
        return result
    weights = {k: max(target_weights[k], 0.0) / weight_sum for k in keys}

    current_total = sum(max(current.get(k, 0.0), 0.0) for k in keys)
    new_total = current_total + amount
    deficits = {k: max(weights[k] * new_total - max(current.get(k, 0.0), 0.0), 0.0) for k in keys}
    deficit_sum = sum(deficits.values())

    if deficit_sum <= 0:
        return {k: amount * weights[k] for k in keys}
    if deficit_sum <= amount:
        remainder = amount - deficit_sum
        return {k: deficits[k] + remainder * weights[k] for k in keys}
    return {k: amount * deficits[k] / deficit_sum for k in keys}
