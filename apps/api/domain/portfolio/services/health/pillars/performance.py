"""Performance pillar: consistency against the CDI, rolling Sharpe and information ratio."""

from __future__ import annotations

from domain.policy.services.policy import HealthPolicy
from domain.portfolio.services.analytics import (
    cagr,
    cumulative_return,
    sharpe_ratio,
)
from domain.portfolio.services.health.common import (
    _insufficient,
    _num,
    _pct,
)
from domain.portfolio.services.health.model import (
    MIN_CONSISTENCY_MONTHS,
    HealthCheck,
    HealthInputs,
    HealthStatus,
    HealthUnit,
    PerformanceDetail,
)
from domain.portfolio.services.risk_metrics import (
    ROLLING_WINDOW,
    ConfidenceInterval,
    bootstrap_intervals,
    consistency_against,
    information_ratio,
    omega_ratio,
    rolling_windows,
    tracking_error,
)


def _performance_pillar(
    inputs: HealthInputs, policy: HealthPolicy
) -> tuple[list[HealthCheck], PerformanceDetail]:
    returns = list(inputs.portfolio_returns)
    dates = list(inputs.portfolio_dates)
    n = len(returns)
    rf = inputs.annual_cdi_rate
    enough = n >= policy.min_observations
    checks: list[HealthCheck] = []

    bench = list(inputs.benchmark_returns)
    paired_bench = [b for b in bench if b is not None]
    te = tracking_error(returns, bench) if enough else None
    ir = information_ratio(returns, bench) if enough else None
    benchmark_return = cumulative_return(paired_bench) if paired_bench else None
    if ir is None:
        checks.append(
            _insufficient(
                "information_ratio",
                "Retorno × benchmark da política",
                f"São necessários {policy.min_observations} retornos diários da carteira e do "
                f"benchmark (há {n}).",
                observations=n,
                min_observations=policy.min_observations,
                unit=HealthUnit.RATIO,
            )
        )
    else:
        cum = cumulative_return(returns)
        checks.append(
            HealthCheck(
                key="information_ratio",
                title="Retorno × benchmark da política",
                status=HealthStatus.WARNING if ir < 0 else HealthStatus.OK,
                value=round(ir, 4),
                unit=HealthUnit.RATIO,
                warning_threshold=0.0,
                observations=n,
                min_observations=policy.min_observations,
                explanation=(
                    f"TWR de {_pct(cum)} contra {_pct(benchmark_return or 0.0)} do benchmark "
                    "da política (IBOV, IFIX, S&P 500 e CDI nos pesos-alvo ARCA). "
                    f"Tracking error {_pct(te or 0.0)} a.a., Information Ratio {_num(ir)}."
                ),
                action=(
                    "A carteira rende menos que a própria alocação-alvo em índices: compare "
                    "os ativos de cada quadrante com o índice do quadrante."
                    if ir < 0
                    else None
                ),
            )
        )

    consistency, months = consistency_against(dates, returns, list(inputs.cdi_returns))
    if consistency is None or months < MIN_CONSISTENCY_MONTHS:
        checks.append(
            _insufficient(
                "cdi_consistency",
                "Consistência contra o CDI",
                f"São necessários {MIN_CONSISTENCY_MONTHS} meses com CDI e carteira (há {months}).",
                observations=months,
                min_observations=MIN_CONSISTENCY_MONTHS,
            )
        )
    else:
        low = consistency < policy.min_cdi_consistency
        checks.append(
            HealthCheck(
                key="cdi_consistency",
                title="Consistência contra o CDI",
                status=HealthStatus.WARNING if low else HealthStatus.OK,
                value=round(consistency, 4),
                warning_threshold=policy.min_cdi_consistency,
                observations=months,
                min_observations=MIN_CONSISTENCY_MONTHS,
                explanation=(
                    f"A carteira superou o CDI em {_pct(consistency, 0)} de {months} meses."
                ),
                action=(
                    "Na maior parte dos meses o CDI rendeu mais: confirme se o risco assumido "
                    "está sendo pago no longo prazo."
                    if low
                    else None
                ),
            )
        )

    rolling = rolling_windows(dates, returns, annual_risk_free_rate=rf)
    if not rolling:
        checks.append(
            _insufficient(
                "rolling_sharpe",
                "Sharpe em 12 meses móveis",
                f"São necessários {ROLLING_WINDOW} retornos diários (há {n}).",
                observations=n,
                min_observations=ROLLING_WINDOW,
                unit=HealthUnit.RATIO,
            )
        )
    else:
        last = rolling[-1]
        checks.append(
            HealthCheck(
                key="rolling_sharpe",
                title="Sharpe em 12 meses móveis",
                status=HealthStatus.WARNING if last.sharpe < 0 else HealthStatus.OK,
                value=last.sharpe,
                unit=HealthUnit.RATIO,
                warning_threshold=0.0,
                observations=n,
                min_observations=ROLLING_WINDOW,
                explanation=(
                    f"Nos últimos 12 meses: retorno de {_pct(last.cumulative_return)} e Sharpe "
                    f"de {_num(last.sharpe)}."
                ),
                action=(
                    "O último ano rendeu abaixo do CDI considerando o risco: veja se é um "
                    "quadrante específico."
                    if last.sharpe < 0
                    else None
                ),
            )
        )

    sharpe = sharpe_ratio(returns, rf) if enough else None
    intervals = bootstrap_intervals(returns, annual_risk_free_rate=rf) if enough else None
    sharpe_ci: ConfidenceInterval | None = None
    cagr_ci: ConfidenceInterval | None = None
    if sharpe is None or intervals is None:
        checks.append(
            _insufficient(
                "sharpe_confidence",
                "Sharpe com intervalo de confiança",
                f"São necessários {policy.min_observations} retornos diários (há {n}).",
                observations=n,
                min_observations=policy.min_observations,
                unit=HealthUnit.RATIO,
            )
        )
    else:
        sharpe_ci, cagr_ci = intervals
        negative = sharpe_ci.high < 0
        checks.append(
            HealthCheck(
                key="sharpe_confidence",
                title="Sharpe com intervalo de confiança",
                status=HealthStatus.WARNING if negative else HealthStatus.OK,
                value=round(sharpe, 4),
                unit=HealthUnit.RATIO,
                observations=n,
                min_observations=policy.min_observations,
                explanation=(
                    f"Sharpe de {_num(sharpe)} (IC 95%: {_num(sharpe_ci.low)} a "
                    f"{_num(sharpe_ci.high)}); retorno anualizado entre {_pct(cagr_ci.low)} e "
                    f"{_pct(cagr_ci.high)}."
                    + (
                        " O intervalo inclui zero: ainda não dá para afirmar que o risco "
                        "foi remunerado."
                        if sharpe_ci.low <= 0 <= sharpe_ci.high
                        else ""
                    )
                ),
                action=(
                    "Mesmo no melhor cenário do intervalo a carteira rende abaixo do CDI."
                    if negative
                    else None
                ),
            )
        )

    cum = cumulative_return(returns) if n else None
    detail = PerformanceDetail(
        observations=n,
        cumulative_return=round(cum, 4) if cum is not None else None,
        cagr=round(cagr(cum, n), 4) if cum is not None and enough else None,
        benchmark_return=round(benchmark_return, 4) if benchmark_return is not None else None,
        tracking_error=round(te, 4) if te is not None else None,
        information_ratio=round(ir, 4) if ir is not None else None,
        omega=(
            round(o, 4)
            if enough and (o := omega_ratio(returns, list(inputs.cdi_returns))) is not None
            else None
        ),
        sharpe=round(sharpe, 4) if sharpe is not None else None,
        sharpe_interval=sharpe_ci,
        cagr_interval=cagr_ci,
        cdi_consistency=round(consistency, 4) if consistency is not None else None,
        months_compared=months,
        rolling=rolling,
        class_returns=dict(inputs.class_returns),
    )
    return checks, detail
