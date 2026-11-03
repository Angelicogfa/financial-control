"""Concentration pillar: largest asset and sector, effective number of assets, FGC exposure."""

from __future__ import annotations

from collections.abc import Sequence

from domain.policy.services.policy import HealthPolicy
from domain.portfolio.services.diversification import (
    concentration,
    top_weight,
)
from domain.portfolio.services.health.common import (
    _breakdown,
    _brl,
    _insufficient,
    _max_status,
    _min_status,
    _num,
    _pct,
    _sum_by,
    issuer_of,
)
from domain.portfolio.services.health.model import (
    DIVERSIFIED_TYPES,
    SOVEREIGN_TYPES,
    UNKNOWN_SECTOR,
    VARIABLE_INCOME_TYPES,
    ConcentrationBreakdown,
    HealthCheck,
    HealthStatus,
    HealthUnit,
    Holding,
    InstitutionExposure,
)


def _concentration_pillar(
    holdings: Sequence[Holding], total: float, policy: HealthPolicy
) -> tuple[list[HealthCheck], list[ConcentrationBreakdown], list[InstitutionExposure]]:
    checks: list[HealthCheck] = []
    breakdowns: list[ConcentrationBreakdown] = []
    if total <= 0:
        return (
            [_insufficient("largest_asset", "Maior ativo", "A carteira ainda não tem valor.")],
            breakdowns,
            [],
        )

    private = [h for h in holdings if h.asset_type not in SOVEREIGN_TYPES]
    weights = {h.ticker: h.value_brl / total for h in private}
    if weights:
        largest_ticker, largest = max(weights.items(), key=lambda kv: kv[1])
        checks.append(
            HealthCheck(
                key="largest_asset",
                title="Maior ativo",
                status=_max_status(
                    largest, policy.max_asset_weight_warning, policy.max_asset_weight_critical
                ),
                value=round(largest, 4),
                warning_threshold=policy.max_asset_weight_warning,
                critical_threshold=policy.max_asset_weight_critical,
                explanation=(
                    f"{largest_ticker} representa {_pct(largest)} da carteira "
                    "(Tesouro e caixa não entram nesta conta)."
                ),
                action=(
                    f"Pare de aportar em {largest_ticker} até o peso voltar ao limite."
                    if largest > policy.max_asset_weight_warning
                    else None
                ),
            )
        )
        top5 = top_weight(weights, 5)
        checks.append(
            HealthCheck(
                key="top5_assets",
                title="Cinco maiores ativos",
                status=_max_status(
                    top5, policy.max_top5_weight_warning, policy.max_top5_weight_critical
                ),
                value=round(top5, 4),
                warning_threshold=policy.max_top5_weight_warning,
                critical_threshold=policy.max_top5_weight_critical,
                explanation=f"Os cinco maiores ativos somam {_pct(top5)} da carteira.",
                action=(
                    "Distribua os próximos aportes entre mais ativos do quadrante."
                    if top5 > policy.max_top5_weight_warning
                    else None
                ),
            )
        )
        effective = concentration({h.ticker: h.value_brl for h in private})
        if effective is not None:
            checks.append(
                HealthCheck(
                    key="effective_assets",
                    title="Número efetivo de ativos",
                    status=_min_status(
                        effective.effective_count,
                        policy.min_effective_assets_warning,
                        policy.min_effective_assets_critical,
                    ),
                    value=effective.effective_count,
                    unit=HealthUnit.COUNT,
                    warning_threshold=policy.min_effective_assets_warning,
                    critical_threshold=policy.min_effective_assets_critical,
                    explanation=(
                        f"{len(private)} ativos equivalem a {_num(effective.effective_count, 1)} "
                        f"ativos de mesmo peso (HHI {_num(effective.hhi, 3)})."
                    ),
                    action=(
                        "Aumente o número de ativos ou reduza a diferença de pesos entre eles."
                        if effective.effective_count < policy.min_effective_assets_warning
                        else None
                    ),
                )
            )

    variable = [
        h
        for h in holdings
        if h.asset_type in VARIABLE_INCOME_TYPES and h.asset_type not in DIVERSIFIED_TYPES
    ]
    variable_total = sum(h.value_brl for h in variable)
    if variable_total > 0:
        by_sector = _sum_by(variable, lambda h: h.sector or UNKNOWN_SECTOR)
        known = {k: v / variable_total for k, v in by_sector.items() if k != UNKNOWN_SECTOR}
        if known:
            sector, sector_weight = max(known.items(), key=lambda kv: kv[1])
            unknown = by_sector.get(UNKNOWN_SECTOR, 0.0) / variable_total
            note = f" {_pct(unknown)} da renda variável não tem setor informado." if unknown else ""
            checks.append(
                HealthCheck(
                    key="largest_sector",
                    title="Maior setor da renda variável",
                    status=_max_status(
                        sector_weight,
                        policy.max_sector_weight_warning,
                        policy.max_sector_weight_critical,
                    ),
                    value=round(sector_weight, 4),
                    warning_threshold=policy.max_sector_weight_warning,
                    critical_threshold=policy.max_sector_weight_critical,
                    explanation=(
                        f"{sector} concentra {_pct(sector_weight)} da renda variável.{note}"
                    ),
                    action=(
                        f"Busque ativos de outros setores antes de aportar de novo em {sector}."
                        if sector_weight > policy.max_sector_weight_warning
                        else None
                    ),
                )
            )
        else:
            checks.append(
                _insufficient(
                    "largest_sector",
                    "Maior setor da renda variável",
                    "Os provedores não informaram o setor de nenhum ativo de renda variável.",
                )
            )
        sector_breakdown = _breakdown("SECTOR", by_sector)
        if sector_breakdown:
            breakdowns.append(sector_breakdown)

    institutions: list[InstitutionExposure] = []
    covered = [h for h in holdings if h.fgc_covered]
    if covered:
        by_issuer = _sum_by(covered, lambda h: (h.issuer or "").strip().upper())
        unknown_value = by_issuer.pop("", 0.0)
        for issuer, value in sorted(by_issuer.items(), key=lambda kv: -kv[1]):
            institutions.append(
                InstitutionExposure(
                    issuer=issuer,
                    value_brl=round(value, 2),
                    limit_brl=policy.fgc_limit_brl,
                    usage=round(value / policy.fgc_limit_brl, 4),
                )
            )
        top = institutions[0] if institutions else None
        usage = top.usage if top else 0.0
        if usage > 1.0:
            status = HealthStatus.CRITICAL
        elif usage > policy.fgc_warning_ratio or unknown_value > 0:
            status = HealthStatus.WARNING
        else:
            status = HealthStatus.OK
        above = [i for i in institutions if i.usage > 1.0]
        explanation = (
            f"Maior exposição: {top.issuer} com {_brl(top.value_brl)} ({_pct(usage, 0)} do "
            f"limite de {_brl(policy.fgc_limit_brl)} do FGC)."
            if top
            else "Os títulos cobertos pelo FGC não têm emissor informado."
        )
        if unknown_value > 0 and top:
            explanation += f" {_brl(unknown_value)} em títulos sem emissor informado."
        checks.append(
            HealthCheck(
                key="fgc_exposure",
                title="Exposição por instituição (FGC)",
                status=status,
                value=round(usage, 4),
                warning_threshold=policy.fgc_warning_ratio,
                critical_threshold=1.0,
                explanation=explanation,
                action=(
                    "O excedente de "
                    + ", ".join(f"{i.issuer} ({_brl(i.value_brl - i.limit_brl)})" for i in above)
                    + " não tem garantia: distribua entre outras instituições."
                    if above
                    else (
                        "Informe o emissor dos títulos para conferir o limite do FGC."
                        if unknown_value > 0
                        else None
                    )
                ),
            )
        )

    for dimension, values in (
        ("ASSET", _sum_by(holdings, lambda h: h.ticker)),
        ("ISSUER", _sum_by(holdings, issuer_of)),
        ("CLASS", _sum_by(holdings, lambda h: h.arca_class.value)),
    ):
        breakdown = _breakdown(dimension, values)
        if breakdown:
            breakdowns.append(breakdown)
    order = {"ASSET": 0, "SECTOR": 1, "ISSUER": 2, "CLASS": 3}
    breakdowns.sort(key=lambda b: order[b.dimension])
    return checks, breakdowns, institutions
