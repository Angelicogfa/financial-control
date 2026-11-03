"""Policy pillar: classes inside their ARCA bands and the weight of ineligible assets."""

from __future__ import annotations

from collections.abc import Sequence

from domain.policy.services.allocation import BAND_ABOVE, BAND_WITHIN
from domain.portfolio.services.health.common import (
    _insufficient,
    _num,
    _pct,
)
from domain.portfolio.services.health.model import (
    HealthCheck,
    HealthInputs,
    HealthStatus,
    Holding,
)
from domain.shared.enums import ARCA_LABELS, AssetPurpose
from domain.shared.text import plural


def _policy_pillar(
    inputs: HealthInputs, holdings: Sequence[Holding], total: float
) -> list[HealthCheck]:
    checks: list[HealthCheck] = []
    if total <= 0 or not inputs.allocations:
        checks.append(
            _insufficient(
                "band_adherence", "Quadrantes dentro da banda", "A carteira ainda não tem valor."
            )
        )
    else:
        outside = [a for a in inputs.allocations if a.band_status != BAND_WITHIN]
        deepest = max((abs(a.deviation_pct) for a in inputs.allocations), default=0.0)
        if not outside:
            checks.append(
                HealthCheck(
                    key="band_adherence",
                    title="Quadrantes dentro da banda",
                    status=HealthStatus.OK,
                    value=deepest / 100.0,
                    explanation="Todos os quadrantes ARCA estão dentro da banda de tolerância.",
                )
            )
        else:
            critical = any(abs(a.deviation_pct) > 2 * a.band_pct for a in outside)
            parts = []
            for a in sorted(outside, key=lambda x: -abs(x.deviation_pct)):
                side = "acima" if a.band_status == BAND_ABOVE else "abaixo"
                days = inputs.class_out_of_band_days.get(a.arca_class)
                since = f", há {days} dias" if days else ""
                parts.append(
                    f"{ARCA_LABELS[a.arca_class]} {_num(abs(a.deviation_pct), 1)} p.p. {side} "
                    f"(banda {_num(a.band_pct, 1)} p.p.{since})"
                )
            checks.append(
                HealthCheck(
                    key="band_adherence",
                    title="Quadrantes dentro da banda",
                    status=HealthStatus.CRITICAL if critical else HealthStatus.WARNING,
                    value=deepest / 100.0,
                    explanation=f"{plural(len(parts), 'quadrante', 'quadrantes')} fora da banda:",
                    items=parts,
                    action=(
                        "Direcione os próximos aportes para os quadrantes abaixo da banda "
                        "(o simulador de aporte já os prioriza). Um desvio maior que o dobro "
                        "da banda pede rebalanceamento."
                    ),
                )
            )

    arca = [h for h in holdings if h.purpose == AssetPurpose.ARCA]
    ineligible = [h for h in arca if not h.eligible]
    weight = sum(h.value_brl for h in ineligible) / total if total > 0 else 0.0
    checks.append(
        HealthCheck(
            key="ineligible_weight",
            title="Ativos fora da elegibilidade com peso",
            status=HealthStatus.WARNING if ineligible else HealthStatus.OK,
            value=round(weight, 4),
            explanation=(
                f"{plural(len(ineligible), 'ativo', 'ativos')} fora dos critérios de "
                f"elegibilidade {'soma' if len(ineligible) == 1 else 'somam'} "
                f"{_pct(weight)} da carteira: {', '.join(h.ticker for h in ineligible)}."
                if ineligible
                else "Todos os ativos com peso atendem aos critérios de elegibilidade."
            ),
            action=(
                "Revise o checklist desses ativos ou planeje a saída; eles não recebem aportes."
                if ineligible
                else None
            ),
        )
    )
    return checks
