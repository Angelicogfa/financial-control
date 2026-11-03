"""Diversification pillar: correlated pairs, diversification ratio and risk contribution."""

from __future__ import annotations

from collections.abc import Sequence

from domain.policy.services.policy import HealthPolicy
from domain.portfolio.services.diversification import (
    decompose_risk,
    estimate_covariance,
    sample_correlations,
)
from domain.portfolio.services.health.common import (
    _insufficient,
    _min_status,
    _num,
    _pct,
)
from domain.portfolio.services.health.model import (
    CorrelatedPair,
    DiversificationDetail,
    HealthCheck,
    HealthInputs,
    HealthStatus,
    HealthUnit,
    Holding,
    RiskShare,
)
from domain.portfolio.services.risk_metrics import (
    ROLLING_WINDOW,
)
from domain.shared.enums import ARCA_LABELS, ArcaClass


def _diversification_pillar(
    inputs: HealthInputs, holdings: Sequence[Holding], policy: HealthPolicy
) -> tuple[list[HealthCheck], DiversificationDetail]:
    values = {h.ticker: h.value_brl for h in holdings if h.value_brl > 0}
    series = {t: list(s)[-ROLLING_WINDOW:] for t, s in inputs.asset_returns.items() if t in values}
    estimate = estimate_covariance(series, min_observations=policy.min_observations)
    titles = (
        ("diversification_ratio", "Índice de diversificação (Choueifaty)"),
        ("risk_contribution", "Contribuição ao risco"),
        ("correlated_pairs", "Pares muito correlacionados"),
    )
    if estimate is None or len(estimate.names) < 2:
        known = max((sum(v is not None for v in s) for s in series.values()), default=0)
        explanation = (
            f"São necessários ao menos dois ativos com {policy.min_observations} retornos "
            "diários de histórico de preço."
        )
        return (
            [
                _insufficient(
                    key,
                    title,
                    explanation,
                    observations=known,
                    min_observations=policy.min_observations,
                    unit=HealthUnit.RATIO
                    if key == "diversification_ratio"
                    else HealthUnit.FRACTION,
                )
                for key, title in titles
            ],
            DiversificationDetail(excluded=sorted(values)),
        )

    decomposition = decompose_risk(estimate, values)
    by_class: dict[ArcaClass, tuple[float, float]] = {}
    class_of = {h.ticker: h.arca_class for h in holdings}
    for name in estimate.names:
        w, r = by_class.get(class_of[name], (0.0, 0.0))
        by_class[class_of[name]] = (
            w + decomposition.weights.get(name, 0.0),
            r + decomposition.risk_shares.get(name, 0.0),
        )
    risky = [n for i, n in enumerate(estimate.names) if estimate.volatilities[i] > 0]
    correlations = sample_correlations(series, risky)
    high = sorted(
        (
            CorrelatedPair(a, b, c)
            for (a, b), c in correlations.items()
            if c >= policy.high_correlation
        ),
        key=lambda p: -p.correlation,
    )
    detail = DiversificationDetail(
        observations=estimate.observations,
        shrinkage=estimate.shrinkage,
        volatility=decomposition.volatility,
        diversification_ratio=decomposition.diversification_ratio,
        by_asset=sorted(
            (
                RiskShare(
                    n, decomposition.weights.get(n, 0.0), decomposition.risk_shares.get(n, 0.0)
                )
                for n in estimate.names
            ),
            key=lambda s: -s.risk_share,
        ),
        by_class=sorted(
            (RiskShare(c.value, round(w, 4), round(r, 4)) for c, (w, r) in by_class.items()),
            key=lambda s: -s.risk_share,
        ),
        correlated_pairs=high,
        excluded=sorted(set(values) - set(estimate.names)),
    )

    checks: list[HealthCheck] = []
    ratio = decomposition.diversification_ratio
    if ratio is None:
        checks.append(
            _insufficient(
                titles[0][0], titles[0][1], "Os ativos com histórico não oscilaram no período."
            )
        )
    else:
        checks.append(
            HealthCheck(
                key="diversification_ratio",
                title=titles[0][1],
                status=_min_status(
                    ratio,
                    policy.min_diversification_ratio_warning,
                    policy.min_diversification_ratio_critical,
                ),
                value=ratio,
                unit=HealthUnit.RATIO,
                warning_threshold=policy.min_diversification_ratio_warning,
                critical_threshold=policy.min_diversification_ratio_critical,
                observations=estimate.observations,
                min_observations=policy.min_observations,
                explanation=(
                    f"A volatilidade média ponderada dos ativos é {_num(ratio)} vezes a "
                    f"volatilidade da carteira ({_pct(decomposition.volatility)} a.a.). "
                    "Quanto maior, mais as oscilações se compensam (1 = sem diversificação)."
                ),
                action=(
                    "Inclua ativos de comportamento diferente (outros quadrantes, setores ou "
                    "moedas) em vez de mais ativos parecidos."
                    if ratio < policy.min_diversification_ratio_warning
                    else None
                ),
            )
        )

    top = detail.by_asset[0] if detail.by_asset else None
    if top is None or decomposition.volatility <= 0:
        checks.append(
            _insufficient(titles[1][0], titles[1][1], "A carteira não oscilou no período.")
        )
    else:
        heavy = top.risk_share > policy.max_asset_risk_share
        class_items = [
            f"{ARCA_LABELS[ArcaClass(s.label)]}: {_pct(s.weight, 0)} do peso e "
            f"{_pct(s.risk_share, 0)} do risco"
            for s in detail.by_class
        ]
        checks.append(
            HealthCheck(
                key="risk_contribution",
                title=titles[1][1],
                status=HealthStatus.WARNING if heavy else HealthStatus.OK,
                value=top.risk_share,
                warning_threshold=policy.max_asset_risk_share,
                observations=estimate.observations,
                explanation=(
                    f"{top.label} responde por {_pct(top.risk_share)} do risco com "
                    f"{_pct(top.weight)} do peso. Por quadrante:"
                ),
                items=class_items,
                action=(
                    f"Reduza o peso de {top.label} ou aporte em ativos que oscilem menos."
                    if heavy
                    else None
                ),
            )
        )

    checks.append(
        HealthCheck(
            key="correlated_pairs",
            title=titles[2][1],
            status=HealthStatus.WARNING if high else HealthStatus.OK,
            value=float(len(high)),
            unit=HealthUnit.COUNT,
            warning_threshold=policy.high_correlation,
            observations=estimate.observations,
            explanation=(
                f"{len(high)} par(es) com correlação acima de {_num(policy.high_correlation)}:"
                if high
                else f"Nenhum par com correlação acima de {_num(policy.high_correlation)}."
            ),
            items=[f"{p.first} × {p.second} ({_num(p.correlation)})" for p in high[:5]],
            action=(
                "Ativos muito correlacionados se comportam como um só: avalie manter apenas o "
                "de melhor nota no checklist."
                if high
                else None
            ),
        )
    )
    return checks, detail
