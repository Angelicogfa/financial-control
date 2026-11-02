"""Liquidity pillar: emergency reserve, liquid and exempt weight, passive income, tax brackets."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from domain.policy.services.policy import HealthPolicy
from domain.portfolio.services.health.common import (
    _brl,
    _insufficient,
    _min_status,
    _num,
    _pct,
)
from domain.portfolio.services.health.model import (
    HealthCheck,
    HealthInputs,
    HealthStatus,
    HealthUnit,
    Holding,
    LiquidityDetail,
    Maturity,
)
from domain.shared.enums import AssetPurpose, AssetType
from domain.shared.text import plural


def _liquidity_pillar(
    inputs: HealthInputs, holdings: Sequence[Holding], total: float, policy: HealthPolicy
) -> tuple[list[HealthCheck], LiquidityDetail]:
    checks: list[HealthCheck] = []
    reserve = sum(h.value_brl for h in holdings if h.purpose == AssetPurpose.EMERGENCY_RESERVE)
    months: float | None = None
    if policy.monthly_expenses_brl is None:
        checks.append(
            _insufficient(
                "emergency_reserve",
                "Reserva de emergência",
                f"Reserva atual de {_brl(reserve)}. Informe o custo de vida mensal na "
                "Estratégia para medir quantos meses ela cobre.",
                unit=HealthUnit.MONTHS,
            )
        )
    else:
        months = reserve / policy.monthly_expenses_brl
        checks.append(
            HealthCheck(
                key="emergency_reserve",
                title="Reserva de emergência",
                status=_min_status(
                    months, policy.min_reserve_months_warning, policy.min_reserve_months_critical
                ),
                value=round(months, 2),
                unit=HealthUnit.MONTHS,
                warning_threshold=policy.min_reserve_months_warning,
                critical_threshold=policy.min_reserve_months_critical,
                explanation=(
                    f"A reserva de {_brl(reserve)} cobre {_num(months, 1)} meses de um custo "
                    f"mensal de {_brl(policy.monthly_expenses_brl)}."
                ),
                action=(
                    "Complete a reserva antes de aportar nos quadrantes de risco."
                    if months < policy.min_reserve_months_warning
                    else None
                ),
            )
        )

    liquid_weight = sum(h.value_brl for h in holdings if h.liquid_d2) / total if total > 0 else None
    if liquid_weight is None:
        checks.append(
            _insufficient("liquid_weight", "Liquidez em até D+2", "A carteira ainda não tem valor.")
        )
    else:
        low = liquid_weight < policy.min_liquid_weight
        checks.append(
            HealthCheck(
                key="liquid_weight",
                title="Liquidez em até D+2",
                status=HealthStatus.WARNING if low else HealthStatus.OK,
                value=round(liquid_weight, 4),
                warning_threshold=policy.min_liquid_weight,
                explanation=f"{_pct(liquid_weight)} da carteira pode virar dinheiro em até D+2.",
                action=(
                    "Prefira títulos com liquidez diária nos próximos aportes do Caixa."
                    if low
                    else None
                ),
            )
        )

    horizon = inputs.as_of + timedelta(days=365)
    maturities = sorted(
        (
            Maturity(h.ticker, h.maturity_date, round(h.value_brl, 2))
            for h in holdings
            if h.maturity_date is not None and inputs.as_of <= h.maturity_date <= horizon
        ),
        key=lambda m: m.maturity_date,
    )
    maturing = sum(m.value_brl for m in maturities)
    checks.append(
        HealthCheck(
            key="maturities_12m",
            title="Vencimentos em 12 meses",
            status=HealthStatus.OK,
            value=round(maturing, 2),
            unit=HealthUnit.BRL,
            explanation=(
                f"{plural(len(maturities), 'título vence', 'títulos vencem')}"
                f" em 12 meses, somando {_brl(maturing)}"
                + (
                    f"; o primeiro é {maturities[0].ticker} em "
                    f"{maturities[0].maturity_date.strftime('%d/%m/%Y')}."
                    if maturities
                    else "."
                )
            ),
            action=(
                "Planeje onde reinvestir esses valores para não deixá-los parados."
                if maturities
                else None
            ),
        )
    )

    income = inputs.earnings_12m_brl
    checks.append(
        HealthCheck(
            key="passive_income",
            title="Renda passiva em 12 meses",
            status=HealthStatus.OK,
            value=round(income, 2),
            unit=HealthUnit.BRL,
            explanation=(
                f"{_brl(income)} recebidos em proventos nos últimos 12 meses "
                f"({_brl(income / 12)} por mês"
                + (f", {_pct(income / total)} da carteira)." if total > 0 else ").")
            ),
        )
    )

    fixed = [h for h in holdings if h.asset_type in (AssetType.FIXED_INCOME, AssetType.TREASURY)]
    fixed_total = sum(h.value_brl for h in fixed)
    exempt_weight = (
        sum(h.value_brl for h in fixed if h.tax_exempt) / fixed_total if fixed_total > 0 else None
    )
    checks.append(
        HealthCheck(
            key="exempt_weight",
            title="Renda fixa isenta de IR",
            status=HealthStatus.OK,
            value=round(exempt_weight, 4) if exempt_weight is not None else None,
            explanation=(
                f"{_pct(exempt_weight)} da renda fixa é isenta de IR (LCI, LCA, CRI, CRA e "
                "debêntures incentivadas)."
                if exempt_weight is not None
                else "A carteira não tem renda fixa."
            ),
        )
    )

    window = [
        lot for lot in inputs.bracket_lots if lot.days_to_next_bracket <= policy.bracket_window_days
    ]
    window.sort(key=lambda lot: lot.days_to_next_bracket)
    saving = sum(lot.tax_saving_by_waiting for lot in window)
    checks.append(
        HealthCheck(
            key="tax_brackets",
            title="Lotes perto de mudar de faixa de IR",
            status=HealthStatus.WARNING if window else HealthStatus.OK,
            value=float(len(window)),
            unit=HealthUnit.COUNT,
            warning_threshold=float(policy.bracket_window_days),
            explanation=(
                f"{plural(len(window), 'lote muda', 'lotes mudam')}"
                f" de faixa em até {policy.bracket_window_days} dias; "
                f"esperar economiza {_brl(saving)} de IR. O próximo é {window[0].ticker} em "
                f"{window[0].next_bracket_date.strftime('%d/%m/%Y')} "
                f"({_pct(window[0].current_rate)} → {_pct(window[0].next_rate)})."
                if window
                else f"Nenhum lote muda de faixa nos próximos {policy.bracket_window_days} dias."
            ),
            action=(
                "Se precisar resgatar, prefira outros títulos ou espere a data da nova faixa."
                if window
                else None
            ),
        )
    )
    detail = LiquidityDetail(
        reserve_brl=round(reserve, 2),
        reserve_months=round(months, 2) if months is not None else None,
        liquid_weight=round(liquid_weight, 4) if liquid_weight is not None else None,
        maturities_12m=maturities,
        passive_income_12m_brl=round(income, 2),
        exempt_weight=round(exempt_weight, 4) if exempt_weight is not None else None,
        bracket_lots=window,
    )
    return checks, detail
