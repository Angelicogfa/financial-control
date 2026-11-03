"""Quality pillar: accounting scores, checklist quality and freshness, suspicious data."""

from __future__ import annotations

from collections.abc import Sequence

from domain.policy.services.policy import HealthPolicy
from domain.portfolio.services.health.common import (
    _insufficient,
    _min_status,
    _num,
    _pct,
)
from domain.portfolio.services.health.model import (
    LOW_F_SCORE,
    Z_DISTRESS,
    HealthCheck,
    HealthStatus,
    HealthUnit,
    Holding,
    HoldingQuality,
)
from domain.shared.text import plural


def _quality_pillar(
    holdings: Sequence[Holding], total: float, policy: HealthPolicy
) -> tuple[list[HealthCheck], list[HoldingQuality]]:
    checks: list[HealthCheck] = []
    rows = [
        HoldingQuality(
            ticker=h.ticker,
            weight=round(h.value_brl / total, 4) if total > 0 else 0.0,
            checklist_ratio=h.checklist_ratio,
            stale=h.checklist_stale,
            f_score=h.f_score,
            z_score=h.z_score,
        )
        for h in holdings
        if h.checklist_ratio is not None or h.f_score is not None or h.z_score is not None
    ]
    rows.sort(key=lambda r: -r.weight)

    scored = [h for h in holdings if h.checklist_ratio is not None and h.value_brl > 0]
    scored_value = sum(h.value_brl for h in scored)
    if scored_value <= 0:
        checks.append(
            _insufficient(
                "checklist_quality",
                "Nota média ponderada do checklist",
                "Nenhum ativo com peso tem checklist respondido.",
                unit=HealthUnit.RATIO,
            )
        )
    else:
        quality = sum((h.checklist_ratio or 0.0) * h.value_brl for h in scored) / scored_value
        coverage = scored_value / total if total > 0 else 0.0
        checks.append(
            HealthCheck(
                key="checklist_quality",
                title="Nota média ponderada do checklist",
                status=_min_status(
                    quality,
                    policy.min_checklist_quality_warning,
                    policy.min_checklist_quality_critical,
                ),
                value=round(quality, 4),
                unit=HealthUnit.RATIO,
                warning_threshold=policy.min_checklist_quality_warning,
                critical_threshold=policy.min_checklist_quality_critical,
                explanation=(
                    f"Nota média de {_num(quality)} (de -1 a 1: saldo de sim e não sobre as "
                    f"perguntas aplicáveis), cobrindo {_pct(coverage)} da carteira."
                ),
                action=(
                    "Os ativos de maior peso têm teses fracas: revise o checklist deles antes "
                    "do próximo aporte."
                    if quality < policy.min_checklist_quality_warning
                    else None
                ),
            )
        )

    answered = [h for h in scored if h.checklist_age_days is not None]
    if not answered:
        checks.append(
            HealthCheck(
                key="stale_checklist",
                title="Peso com checklist vencido",
                status=HealthStatus.OK,
                value=0.0,
                warning_threshold=policy.max_stale_checklist_weight,
                explanation="Nenhum ativo com peso tem respostas manuais no checklist.",
            )
        )
    else:
        stale = [h for h in answered if h.checklist_stale]
        weight = sum(h.value_brl for h in stale) / total if total > 0 else 0.0
        too_much = weight > policy.max_stale_checklist_weight
        checks.append(
            HealthCheck(
                key="stale_checklist",
                title="Peso com checklist vencido",
                status=HealthStatus.WARNING if too_much else HealthStatus.OK,
                value=round(weight, 4),
                warning_threshold=policy.max_stale_checklist_weight,
                explanation=(
                    f"{plural(len(stale), 'ativo', 'ativos')}"
                    f" com respostas manuais vencidas (prazo de validade da "
                    f"elegibilidade ou demonstrativo anual mais novo) somam {_pct(weight)} da "
                    "carteira" + (f": {', '.join(h.ticker for h in stale)}." if stale else ".")
                ),
                action=(
                    "Revise as respostas manuais desses ativos com o último demonstrativo."
                    if stale
                    else None
                ),
            )
        )

    suspicious = [h for h in holdings if h.suspicious_data]
    suspicious_weight = sum(h.value_brl for h in suspicious) / total if total > 0 else 0.0
    checks.append(
        HealthCheck(
            key="suspicious_data",
            title="Peso com dado suspeito",
            status=HealthStatus.WARNING if suspicious else HealthStatus.OK,
            value=round(suspicious_weight, 4),
            explanation=(
                f"{plural(len(suspicious), 'ativo', 'ativos')}"
                f" com indicadores fora da faixa plausível ou "
                f"divergentes entre fontes somam {_pct(suspicious_weight)} da carteira: "
                f"{', '.join(h.ticker for h in suspicious)}."
                if suspicious
                else "Nenhum ativo com peso tem indicador marcado como suspeito."
            ),
            action=(
                "Confira os indicadores desses ativos antes de usar o valuation e o checklist."
                if suspicious
                else None
            ),
        )
    )

    with_scores = [h for h in holdings if h.f_score is not None or h.z_score is not None]
    if not with_scores:
        checks.append(
            _insufficient(
                "accounting_scores",
                "Piotroski F-score e Altman Z''-score",
                "Os demonstrativos armazenados não trazem as linhas necessárias (ativo total, "
                "fluxo de caixa operacional, ativo e passivo circulantes, lucros retidos, EBIT).",
                unit=HealthUnit.COUNT,
            )
        )
    else:
        weak = [
            h
            for h in with_scores
            if (h.f_score is not None and h.f_score <= LOW_F_SCORE)
            or (h.z_score is not None and h.z_score < Z_DISTRESS)
        ]
        weight = sum(h.value_brl for h in weak) / total if total > 0 else 0.0
        checks.append(
            HealthCheck(
                key="accounting_scores",
                title="Piotroski F-score e Altman Z''-score",
                status=HealthStatus.WARNING if weak else HealthStatus.OK,
                value=round(weight, 4),
                explanation=(
                    f"{plural(len(weak), 'ativo', 'ativos')}"
                    f" com F-score até {LOW_F_SCORE} ou Z''-score abaixo de "
                    f"{_num(Z_DISTRESS, 1)} somam {_pct(weight)} da carteira: "
                    f"{', '.join(h.ticker for h in weak)}."
                    if weak
                    else f"{plural(len(with_scores), 'ativo avaliado', 'ativos avaliados')}"
                    f" sem sinal de fragilidade contábil."
                ),
                action=(
                    "Confira o endividamento e a geração de caixa dessas empresas."
                    if weak
                    else None
                ),
            )
        )
    return checks, rows
