"""The diagnosis: runs every pillar and orders the report worst first."""

from __future__ import annotations

import math
from dataclasses import replace

from domain.policy.services.policy import HealthPolicy
from domain.portfolio.services.health.common import (
    _pillar,
    issuer_of,
    worst,
)
from domain.portfolio.services.health.model import (
    _PILLAR_ORDER,
    _SEVERITY,
    BracketLot,
    HealthCheck,
    HealthInputs,
    HealthPillar,
    HealthReport,
    HealthStatus,
    HealthUnit,
    Holding,
    PillarResult,
)
from domain.portfolio.services.health.pillars.concentration import (
    _concentration_pillar,
)
from domain.portfolio.services.health.pillars.diversification import (
    _diversification_pillar,
)
from domain.portfolio.services.health.pillars.liquidity import (
    _liquidity_pillar,
)
from domain.portfolio.services.health.pillars.performance import (
    _performance_pillar,
)
from domain.portfolio.services.health.pillars.policy import (
    _policy_pillar,
)
from domain.portfolio.services.health.pillars.quality import (
    _quality_pillar,
)
from domain.portfolio.services.health.pillars.risk import (
    _risk_pillar,
)

# Checks computed from each series: they carry the note of what was dropped from it.
ASSET_SERIES_CHECKS = frozenset(
    {"diversification_ratio", "risk_contribution", "correlated_pairs", "historical_stress"}
)
PORTFOLIO_SERIES_CHECKS = frozenset(
    {
        "volatility",
        "current_drawdown",
        "information_ratio",
        "cdi_consistency",
        "rolling_sharpe",
        "sharpe_confidence",
    }
)


def _mark_suspicious(checks: list[HealthCheck], inputs: HealthInputs) -> list[HealthCheck]:
    asset_note = (
        "Dados descartados antes do cálculo: " + "; ".join(inputs.asset_data_notes) + "."
        if inputs.asset_data_notes
        else None
    )
    portfolio_note = (
        "Dias com retorno impossível da carteira (aporte ou dado errado) ficaram de fora: "
        + ", ".join(inputs.portfolio_data_notes)
        + "."
        if inputs.portfolio_data_notes
        else None
    )
    out = []
    for check in checks:
        note = (
            asset_note
            if check.key in ASSET_SERIES_CHECKS
            else portfolio_note
            if check.key in PORTFOLIO_SERIES_CHECKS
            else None
        )
        out.append(replace(check, suspicious=note) if note else check)
    return out


def diagnose(inputs: HealthInputs, policy: HealthPolicy) -> HealthReport:
    """Run every pillar and order them worst first."""
    holdings = [h for h in inputs.holdings if h.value_brl > 0 and math.isfinite(h.value_brl)]
    total = sum(h.value_brl for h in holdings)

    policy_checks = _policy_pillar(inputs, holdings, total)
    concentration_checks, breakdowns, institutions = _concentration_pillar(holdings, total, policy)
    diversification_checks, diversification = _diversification_pillar(inputs, holdings, policy)
    risk_checks, risk = _risk_pillar(inputs, holdings, policy)
    performance_checks, performance = _performance_pillar(inputs, policy)
    quality_checks, quality = _quality_pillar(holdings, total, policy)
    liquidity_checks, liquidity = _liquidity_pillar(inputs, holdings, total, policy)

    diversification_checks = _mark_suspicious(diversification_checks, inputs)
    risk_checks = _mark_suspicious(risk_checks, inputs)
    performance_checks = _mark_suspicious(performance_checks, inputs)

    pillars = [
        _pillar(HealthPillar.POLICY, policy_checks),
        _pillar(HealthPillar.CONCENTRATION, concentration_checks),
        _pillar(HealthPillar.DIVERSIFICATION, diversification_checks),
        _pillar(HealthPillar.RISK, risk_checks),
        _pillar(HealthPillar.PERFORMANCE, performance_checks),
        _pillar(HealthPillar.QUALITY, quality_checks),
        _pillar(HealthPillar.LIQUIDITY, liquidity_checks),
    ]
    pillars.sort(key=lambda p: (_SEVERITY[p.status], _PILLAR_ORDER[p.pillar]))
    return HealthReport(
        as_of_date=inputs.as_of,
        status=worst([p.status for p in pillars]),
        total_value_brl=round(total, 2),
        pillars=pillars,
        concentration=breakdowns,
        institutions=institutions,
        diversification=diversification,
        risk=risk,
        performance=performance,
        quality=quality,
        liquidity=liquidity,
    )


__all__ = [
    "BracketLot",
    "HealthCheck",
    "HealthInputs",
    "HealthPillar",
    "HealthReport",
    "HealthStatus",
    "HealthUnit",
    "Holding",
    "PillarResult",
    "diagnose",
    "issuer_of",
    "worst",
]
