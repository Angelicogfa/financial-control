"""Formatting, status and grouping helpers shared by the health pillars."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence

from domain.portfolio.services.diversification import (
    Concentration,
    concentration,
)
from domain.portfolio.services.health.model import (
    _SEVERITY,
    PILLAR_TITLES,
    ConcentrationBreakdown,
    HealthCheck,
    HealthPillar,
    HealthStatus,
    HealthUnit,
    Holding,
    PillarResult,
)
from domain.shared.enums import AssetType

# --- formatting (user-facing texts are pt-BR) ---------------------------------------------


def _pct(value: float, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%".replace(".", ",")


def _num(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _brl(value: float) -> str:
    text = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {text}"


# --- status helpers -------------------------------------------------------------------------


def _max_status(value: float, warning: float, critical: float) -> HealthStatus:
    if value > critical:
        return HealthStatus.CRITICAL
    if value > warning:
        return HealthStatus.WARNING
    return HealthStatus.OK


def _min_status(value: float, warning: float, critical: float) -> HealthStatus:
    if value < critical:
        return HealthStatus.CRITICAL
    if value < warning:
        return HealthStatus.WARNING
    return HealthStatus.OK


def worst(statuses: Sequence[HealthStatus]) -> HealthStatus:
    """Worst evaluated state; INSUFFICIENT_DATA only when nothing could be evaluated."""
    evaluated = [s for s in statuses if s != HealthStatus.INSUFFICIENT_DATA]
    if not evaluated:
        return HealthStatus.INSUFFICIENT_DATA
    return min(evaluated, key=lambda s: _SEVERITY[s])


def _insufficient(
    key: str,
    title: str,
    explanation: str,
    *,
    observations: int | None = None,
    min_observations: int | None = None,
    unit: HealthUnit = HealthUnit.FRACTION,
) -> HealthCheck:
    return HealthCheck(
        key=key,
        title=title,
        status=HealthStatus.INSUFFICIENT_DATA,
        explanation=explanation,
        unit=unit,
        observations=observations,
        min_observations=min_observations,
    )


def _pillar(pillar: HealthPillar, checks: list[HealthCheck]) -> PillarResult:
    return PillarResult(
        pillar=pillar,
        title=PILLAR_TITLES[pillar],
        status=worst([c.status for c in checks]),
        checks=checks,
    )


# --- grouping -------------------------------------------------------------------------------

_B3_ROOT = re.compile(r"^([A-Z]{4})\d{1,2}F?$")


def issuer_of(holding: Holding) -> str:
    """Issuer used for concentration: the bond issuer or the B3 ticker root (PETR3/PETR4)."""
    if holding.issuer:
        return holding.issuer.strip().upper()
    if holding.asset_type == AssetType.TREASURY:
        return "TESOURO NACIONAL"
    match = _B3_ROOT.match(holding.ticker)
    return match.group(1) if match else holding.ticker


def _sum_by(holdings: Sequence[Holding], key: Callable[[Holding], str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for h in holdings:
        label = key(h)
        out[label] = out.get(label, 0.0) + h.value_brl
    return out


def _breakdown(dimension: str, values: Mapping[str, float]) -> ConcentrationBreakdown | None:
    conc: Concentration | None = concentration(values)
    if conc is None:
        return None
    return ConcentrationBreakdown(
        dimension=dimension,
        hhi=conc.hhi,
        effective_count=conc.effective_count,
        weights={k: round(v, 4) for k, v in conc.weights.items()},
    )
