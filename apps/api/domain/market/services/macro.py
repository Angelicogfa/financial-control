"""Annual CDI and IPCA from the stored BCB series (Phase 39.4).

Same arithmetic the BCB provider applies to a live fetch, so a screen reading the database
gets the same rates the provider would give.
"""

from __future__ import annotations

from collections.abc import Sequence

from core.helpers.units import rate_fraction
from domain.shared.entities import MarketSeriesPoint


def annual_cdi_rate(points: Sequence[MarketSeriesPoint]) -> float | None:
    """The last daily CDI compounded over 252 business days; None without points."""
    if not points:
        return None
    last = max(points, key=lambda p: p.reference_date)
    return round((1.0 + rate_fraction(last.value, last.unit)) ** 252.0 - 1.0, 6)


def annual_ipca_rate(points: Sequence[MarketSeriesPoint]) -> float | None:
    """The last 12 monthly IPCA figures compounded (annualized when fewer); None without points."""
    if not points:
        return None
    last_12 = sorted(points, key=lambda p: p.reference_date)[-12:]
    factor = 1.0
    for point in last_12:
        factor *= 1.0 + rate_fraction(point.value, point.unit)
    if len(last_12) < 12:
        factor = factor ** (12.0 / len(last_12))
    return round(factor - 1.0, 6)
