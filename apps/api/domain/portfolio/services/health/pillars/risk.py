"""Risk pillar: volatility, current drawdown and historical stress."""

from __future__ import annotations

from collections.abc import Sequence

from domain.policy.services.policy import HealthPolicy
from domain.portfolio.services.analytics import (
    annualized_volatility,
    conditional_var,
    historical_var,
)
from domain.portfolio.services.health.common import (
    _insufficient,
    _max_status,
    _pct,
)
from domain.portfolio.services.health.model import (
    MIN_DRAWDOWN_OBSERVATIONS,
    HealthCheck,
    HealthInputs,
    Holding,
    RiskDetail,
)
from domain.portfolio.services.risk_metrics import (
    STRESS_WINDOW,
    StressResult,
    drawdown_state,
    historical_stress,
    ulcer_index,
    weighted_returns,
)


def _risk_pillar(
    inputs: HealthInputs, holdings: Sequence[Holding], policy: HealthPolicy
) -> tuple[list[HealthCheck], RiskDetail]:
    returns = list(inputs.portfolio_returns)
    n = len(returns)
    checks: list[HealthCheck] = []

    vol = annualized_volatility(returns) if n >= policy.min_observations else None
    if vol is None:
        checks.append(
            _insufficient(
                "volatility",
                "Volatilidade anualizada",
                f"São necessários {policy.min_observations} retornos diários da carteira (há {n}).",
                observations=n,
                min_observations=policy.min_observations,
            )
        )
    else:
        checks.append(
            HealthCheck(
                key="volatility",
                title="Volatilidade anualizada",
                status=_max_status(
                    vol, policy.max_volatility_warning, policy.max_volatility_critical
                ),
                value=round(vol, 4),
                warning_threshold=policy.max_volatility_warning,
                critical_threshold=policy.max_volatility_critical,
                observations=n,
                min_observations=policy.min_observations,
                explanation=f"A carteira oscila {_pct(vol)} ao ano.",
                action=(
                    "A oscilação está acima do perfil da política: aumente o peso do quadrante "
                    "Caixa ou revise os limites na Estratégia."
                    if vol > policy.max_volatility_warning
                    else None
                ),
            )
        )

    state = drawdown_state(inputs.portfolio_dates, returns)
    if n < MIN_DRAWDOWN_OBSERVATIONS:
        checks.append(
            _insufficient(
                "current_drawdown",
                "Queda desde o pico",
                f"São necessários {MIN_DRAWDOWN_OBSERVATIONS} retornos diários (há {n}).",
                observations=n,
                min_observations=MIN_DRAWDOWN_OBSERVATIONS,
            )
        )
    else:
        depth = -state.current
        checks.append(
            HealthCheck(
                key="current_drawdown",
                title="Queda desde o pico",
                status=_max_status(
                    depth, policy.max_drawdown_warning, policy.max_drawdown_critical
                ),
                value=round(depth, 4),
                warning_threshold=policy.max_drawdown_warning,
                critical_threshold=policy.max_drawdown_critical,
                observations=n,
                min_observations=MIN_DRAWDOWN_OBSERVATIONS,
                explanation=(
                    "A carteira está no pico."
                    if depth <= 0
                    else (
                        f"A carteira está {_pct(depth)} abaixo do pico"
                        + (f" de {state.peak_date.strftime('%d/%m/%Y')}" if state.peak_date else "")
                        + f", há {state.periods} pregões."
                    )
                ),
                action=(
                    "Confira se a queda vem de poucos ativos (veja a contribuição ao risco) "
                    "antes de mudar a estratégia."
                    if depth > policy.max_drawdown_warning
                    else None
                ),
            )
        )

    values = {h.ticker: h.value_brl for h in holdings if h.ticker in inputs.asset_returns}
    total = sum(values.values())
    stress: StressResult | None = None
    if total > 0:
        weights = {t: v / total for t, v in values.items()}
        replay = weighted_returns(weights, inputs.asset_returns)
        stress = historical_stress(list(inputs.asset_dates), replay, window=STRESS_WINDOW)
    if stress is None:
        checks.append(
            _insufficient(
                "historical_stress",
                "Estresse histórico com os pesos atuais",
                "Falta histórico de preço dos ativos para simular os pesos atuais.",
                min_observations=STRESS_WINDOW,
            )
        )
    else:
        loss = max(0.0, -stress.worst_window_return)
        window = (
            f" entre {stress.window_start.strftime('%d/%m/%Y')} e "
            f"{stress.window_end.strftime('%d/%m/%Y')}"
            if stress.window_start and stress.window_end
            else ""
        )
        checks.append(
            HealthCheck(
                key="historical_stress",
                title="Estresse histórico com os pesos atuais",
                status=_max_status(
                    loss, policy.max_stress_loss_warning, policy.max_stress_loss_critical
                ),
                value=round(loss, 4),
                warning_threshold=policy.max_stress_loss_warning,
                critical_threshold=policy.max_stress_loss_critical,
                observations=stress.observations,
                min_observations=STRESS_WINDOW,
                explanation=(
                    f"Com os pesos de hoje, o pior mês do histórico{window} teria custado "
                    f"{_pct(loss)}; a maior queda acumulada seria {_pct(-stress.max_drawdown)}."
                ),
                action=(
                    "Avalie se aguentaria essa perda sem vender; se não, aumente o Caixa."
                    if loss > policy.max_stress_loss_warning
                    else None
                ),
            )
        )

    detail = RiskDetail(
        observations=n,
        volatility=round(vol, 4) if vol is not None else None,
        current_drawdown=round(state.current, 4) if n else None,
        drawdown_periods=state.periods if n else None,
        peak_date=state.peak_date,
        ulcer_index=round(ulcer_index(returns), 4) if n else None,
        var_95=round(historical_var(returns), 4) if n >= policy.min_observations else None,
        cvar_95=round(conditional_var(returns), 4) if n >= policy.min_observations else None,
        stress=stress,
    )
    return checks, detail
