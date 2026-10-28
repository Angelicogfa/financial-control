"""Forward projection of the portfolio (Phase 33.5, layer B; design section 4).

- Generator: stationary block bootstrap (Politis & Romano, 1994) over the joint monthly
  returns of the ARCA class proxies (IBOV for Ações, IFIX for Real Estate, S&P 500 in BRL for
  Internacional). Blocks keep the cross-class correlation and the volatility persistence.
- Rates: the bootstrap samples each class's return *in excess of that month's CDI* and adds
  the CDI of the rate scenario, so the historical premium is kept while the rate level comes
  from the policy premises (base, low and high scenarios), never from the past.
- Flow: monthly contribution kept constant in real terms (plus an optional real growth),
  allocated to the classes furthest below target; optional rebalancing back to target when a
  class leaves its band, with income tax on the gain sold; fees on every trade.
- Outputs, in today's money (deflated by the scenario IPCA): percentiles of wealth and of
  monthly passive income, probability of each goal (with its Monte Carlo error), drawdown of
  the strategy and time until the income goal.

The class proxies are total-return series: dividends are already inside the returns, so the
passive income is a reading of the distributed share (value x yield), never extra cash.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date

import numpy as np

from domain.shared.enums import ArcaClass
from domain.simulation.bayes import NiwPosterior, credible_interval
from domain.simulation.data import CDI_KEY, IBOV_KEY, IFIX_KEY, SP500_BRL_KEY
from domain.simulation.engine import SimulationTimeout
from domain.simulation.market import MarketHistory, month_ends
from domain.tax.services.comparator import RateScenario

CLASS_ORDER: tuple[ArcaClass, ...] = (
    ArcaClass.ACOES,
    ArcaClass.REAL_ESTATE,
    ArcaClass.ATIVOS_INTERNACIONAIS,
    ArcaClass.CAIXA,
)
CASH_INDEX = CLASS_ORDER.index(ArcaClass.CAIXA)
CLASS_PROXY: dict[ArcaClass, str] = {
    ArcaClass.ACOES: IBOV_KEY,
    ArcaClass.REAL_ESTATE: IFIX_KEY,
    ArcaClass.ATIVOS_INTERNACIONAIS: SP500_BRL_KEY,
    ArcaClass.CAIXA: CDI_KEY,
}
PERCENTILES: tuple[int, ...] = (5, 25, 50, 75, 95)
# Fewer monthly returns than this cannot feed a bootstrap; fewer than the second only warn.
MIN_SAMPLE_MONTHS = 24
SHORT_SAMPLE_MONTHS = 60
# Income tax on the gain of a sale, by class (stocks without the monthly exemption, FIIs 20%).
DEFAULT_SALE_TAX: dict[ArcaClass, float] = {
    ArcaClass.ACOES: 0.15,
    ArcaClass.REAL_ESTATE: 0.20,
    ArcaClass.ATIVOS_INTERNACIONAIS: 0.15,
    ArcaClass.CAIXA: 0.0,
}
SCENARIO_LABELS: dict[str, str] = {
    "LOW": "Juros em queda",
    "BASE": "Juros na premissa",
    "HIGH": "Juros em alta",
}


class InsufficientHistory(ValueError):
    """The stored series cannot support the projection (missing or too short)."""


@dataclass(frozen=True)
class ClassSample:
    """Joint monthly history of the classes: returns in excess of the CDI and the CDI."""

    months: tuple[date, ...]  # month end of each return
    excess: np.ndarray  # (T, K): (1 + r_class) / (1 + r_cdi) - 1; the Caixa column is zero
    cdi: np.ndarray  # (T,)
    classes: tuple[ArcaClass, ...]  # classes whose proxy was required
    limited_by: str = ""  # the series whose first date starts the common window

    @property
    def size(self) -> int:
        return len(self.months)


def _monthly_returns(history: MarketHistory, key: str, ends: Sequence[date]) -> np.ndarray:
    series = history.series[key]
    levels = np.array([series.last_on_or_before(d) for d in ends], dtype=float)
    return levels[1:] / levels[:-1] - 1.0


def class_sample(
    history: MarketHistory,
    required: Sequence[ArcaClass],
    *,
    start: date | None = None,
) -> ClassSample:
    """The common window of the required proxies (and the CDI), from month end to month end."""
    keys = [CDI_KEY] + [CLASS_PROXY[c] for c in required if c != ArcaClass.CAIXA]
    missing = [k for k in keys if k not in history.series or not history.series[k].dates]
    if missing:
        raise InsufficientHistory(
            "Sem série histórica para " + ", ".join(missing) + "; rode a carga de histórico."
        )
    limited_by = max(keys, key=lambda k: history.series[k].dates[0])
    first = history.series[limited_by].dates[0]
    last = min(history.series[k].dates[-1] for k in keys)
    if start is not None and start > first:
        first, limited_by = start, ""
    ends = month_ends(first, last)
    if len(ends) - 1 < MIN_SAMPLE_MONTHS:
        raise InsufficientHistory(
            f"Histórico comum de {max(len(ends) - 1, 0)} meses; são precisos ao menos "
            f"{MIN_SAMPLE_MONTHS}."
        )
    cdi = _monthly_returns(history, CDI_KEY, ends)
    excess = np.zeros((len(cdi), len(CLASS_ORDER)))
    for k, cls in enumerate(CLASS_ORDER):
        if cls != ArcaClass.CAIXA and cls in required:
            excess[:, k] = (1.0 + _monthly_returns(history, CLASS_PROXY[cls], ends)) / (
                1.0 + cdi
            ) - 1.0
    return ClassSample(
        months=tuple(ends[1:]),
        excess=excess,
        cdi=cdi,
        classes=tuple(c for c in CLASS_ORDER if c in required),
        limited_by=limited_by,
    )


def stationary_bootstrap_indices(
    n: int, horizon: int, paths: int, mean_block: float, rng: np.random.Generator
) -> np.ndarray:
    """(paths, horizon) indices into a sample of size n (Politis & Romano, 1994).

    Each step starts a new block at a random month with probability 1 / mean_block, otherwise
    takes the month after the previous one (wrapping around), so block lengths are geometric.
    """
    p = 0.0 if mean_block == float("inf") else 1.0 / mean_block
    idx = np.empty((paths, horizon), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, paths)
    if horizon > 1:
        restart = rng.random((paths, horizon)) < p
        jumps = rng.integers(0, n, (paths, horizon))
        for t in range(1, horizon):
            idx[:, t] = np.where(restart[:, t], jumps[:, t], (idx[:, t - 1] + 1) % n)
    return idx


def annual_to_monthly(rate: float) -> float:
    return (1.0 + rate) ** (1.0 / 12.0) - 1.0


@dataclass(frozen=True)
class ProjectionConfig:
    """Rules of one projection; amounts are in today's money (BRL)."""

    horizon_months: int
    monthly_contribution: float
    initial_by_class: Mapping[ArcaClass, float]
    targets: Mapping[ArcaClass, float]  # fractions summing to 1
    bands: Mapping[ArcaClass, float] = field(default_factory=dict)  # fractions (5 p.p. = 0.05)
    # Annual share of the value distributed as income (dividends, FII yield) by class.
    income_yield: Mapping[ArcaClass, float] = field(default_factory=dict)
    contribution_real_growth: float = 0.0  # annual
    cash_cdi_multiplier: float = 1.0
    cash_income_tax_rate: float = 0.175
    sale_tax: Mapping[ArcaClass, float] = field(default_factory=lambda: dict(DEFAULT_SALE_TAX))
    fee_rate: float = 0.0003
    rebalance: bool = False
    wealth_goal: float | None = None
    income_goal: float | None = None  # monthly
    paths: int = 5000
    mean_block_months: float = 12.0


@dataclass(frozen=True)
class Percentiles:
    p5: float
    p25: float
    p50: float
    p75: float
    p95: float


def percentiles(values: np.ndarray) -> Percentiles:
    q = np.percentile(values, PERCENTILES)
    return Percentiles(*(round(float(v), 2) for v in q))


@dataclass(frozen=True)
class Chance:
    """A probability with its 90% credibility interval (design 6.3).

    The interval is the Beta(k + 1, n - k + 1) posterior of the share of favourable paths,
    widened to cover the share of each generator of the mixture (their disagreement). The
    parameter uncertainty is already inside the paths of the Bayesian generators.
    """

    probability: float
    standard_error: float  # Monte Carlo only
    low: float
    high: float
    by_generator: dict[str, float] = field(default_factory=dict)


# Generators with fewer paths than this give a share too noisy to widen the interval.
MIN_GENERATOR_PATHS = 100


def chance(hits: np.ndarray, labels: np.ndarray | None = None) -> Chance:
    n = hits.size
    k = float(hits.sum())
    p = k / n
    low, high = credible_interval(k, n)
    shares: dict[str, float] = {}
    if labels is not None:
        for g in dict.fromkeys(labels.tolist()):
            mask = labels == g
            if mask.sum() >= MIN_GENERATOR_PATHS:
                shares[g] = round(float(hits[mask].mean()), 4)
    if len(shares) > 1:
        low, high = min(low, *shares.values()), max(high, *shares.values())
    return Chance(
        probability=round(p, 4),
        standard_error=round(float(np.sqrt(p * (1.0 - p) / n)), 4),
        low=round(low, 4),
        high=round(high, 4),
        by_generator=shares,
    )


@dataclass(frozen=True)
class GoalOutcome:
    """Share of the paths that reach a goal, with its credibility interval."""

    target: float
    probability: float
    standard_error: float
    # Months until the goal among the paths that reach it (None when none does).
    months: Percentiles | None = None
    low: float = 0.0
    high: float = 1.0
    by_generator: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class EventOutcome:
    """A probability of the strategy itself (design 6.3: loss in 12 months, beating the CDI)."""

    key: str
    label: str
    probability: float
    standard_error: float
    low: float
    high: float
    by_generator: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class GeneratorShare:
    key: str
    label: str
    weight: float
    paths: int


@dataclass(frozen=True)
class ProjectionPoint:
    month: int
    contributed: float  # cumulative, today's money
    wealth: Percentiles
    income: Percentiles  # monthly


@dataclass(frozen=True)
class ClassPremise:
    """What the sample says about a class and what the scenario turns it into."""

    arca_class: ArcaClass
    proxy: str
    excess_annual: float  # geometric mean of the monthly excess over the CDI, annualized
    volatility: float  # annualized standard deviation of the monthly excess
    expected_annual: float  # nominal: (1 + scenario CDI) x (1 + excess) - 1
    income_yield: float
    # Bayesian layer: the decision 8 target and the posterior premium (geometric, a year).
    prior_excess_annual: float | None = None
    posterior_excess_annual: float | None = None


@dataclass(frozen=True)
class ProjectionResult:
    scenario: RateScenario
    label: str
    paths: int
    horizon_months: int
    points: list[ProjectionPoint]
    final_wealth: Percentiles
    final_net_wealth: Percentiles  # after the income tax of selling everything at the end
    final_income: Percentiles
    max_drawdown: Percentiles  # of the strategy itself (contributions removed)
    contributed: float
    wealth_goal: GoalOutcome | None
    income_goal: GoalOutcome | None
    premises: list[ClassPremise]
    fees: float  # median, today's money
    taxes: float  # median, today's money
    events: list[EventOutcome] = field(default_factory=list)
    generators: list[GeneratorShare] = field(default_factory=list)
    prior_months: float | None = None  # weight of the prior in equivalent months of data


def _goal(
    reached_at: np.ndarray, hit_final: np.ndarray, target: float, labels: np.ndarray | None
) -> GoalOutcome:
    reached = reached_at[reached_at >= 0]
    c = chance(hit_final, labels)
    return GoalOutcome(
        target=target,
        probability=c.probability,
        standard_error=c.standard_error,
        months=percentiles(reached) if reached.size else None,
        low=c.low,
        high=c.high,
        by_generator=c.by_generator,
    )


def _allocate(values: np.ndarray, amount: np.ndarray, targets: np.ndarray) -> np.ndarray:
    """Split `amount` (per path) over the classes in proportion to their gap to target."""
    total = values.sum(axis=1) + amount
    gap = np.maximum(targets[None, :] * total[:, None] - values, 0.0)
    gap_sum = gap.sum(axis=1)
    share = np.where(
        gap_sum[:, None] > 0, gap / np.where(gap_sum > 0, gap_sum, 1.0)[:, None], targets[None, :]
    )
    return share * amount[:, None]


def premises(
    sample: ClassSample,
    scenario: RateScenario,
    config: ProjectionConfig,
    posterior: NiwPosterior | None = None,
) -> list[ClassPremise]:
    cash_net = cash_annual_net(scenario, config)
    out: list[ClassPremise] = []
    for k, cls in enumerate(CLASS_ORDER):
        if cls == ArcaClass.CAIXA:
            expected, excess, vol = cash_net, 0.0, 0.0
        elif cls in sample.classes:
            column = sample.excess[:, k]
            excess = float(np.prod(1.0 + column) ** (12.0 / column.size) - 1.0)
            vol = float(np.std(column, ddof=1) * np.sqrt(12.0))
            expected = (1.0 + scenario.annual_cdi_rate) * (1.0 + excess) - 1.0
        else:
            continue
        prior = post = None
        if posterior is not None and cls in posterior.classes:
            j = posterior.classes.index(cls)
            prior = round(float(np.expm1(12.0 * posterior.prior_mean[j])), 6)
            post = round(float(np.expm1(12.0 * posterior.mean[j])), 6)
        out.append(
            ClassPremise(
                arca_class=cls,
                proxy=CLASS_PROXY[cls],
                excess_annual=round(excess, 6),
                volatility=round(vol, 6),
                expected_annual=round(expected, 6),
                income_yield=round(
                    cash_real_yield(scenario, config)
                    if cls == ArcaClass.CAIXA
                    else config.income_yield.get(cls, 0.0),
                    6,
                ),
                prior_excess_annual=prior,
                posterior_excess_annual=post,
            )
        )
    return out


def cash_annual_net(scenario: RateScenario, config: ProjectionConfig) -> float:
    """Caixa yields the scenario CDI x multiplier, net of the fixed income tax."""
    monthly = annual_to_monthly(scenario.annual_cdi_rate) * config.cash_cdi_multiplier
    return (1.0 + monthly * (1.0 - config.cash_income_tax_rate)) ** 12 - 1.0


def cash_real_yield(scenario: RateScenario, config: ProjectionConfig) -> float:
    """Income Caixa can pay forever: only the yield above inflation (never negative)."""
    real = (1.0 + cash_annual_net(scenario, config)) / (1.0 + scenario.annual_ipca_rate) - 1.0
    return max(real, 0.0)


def project(
    sample: ClassSample,
    scenario: RateScenario,
    config: ProjectionConfig,
    *,
    seed: int,
    deadline: Callable[[], bool] | None = None,
    excess: np.ndarray | None = None,
    labels: np.ndarray | None = None,
    posterior: NiwPosterior | None = None,
    generators: Sequence[GeneratorShare] = (),
) -> ProjectionResult:
    """Simulate `config.paths` futures of the portfolio under one rate scenario.

    `excess` (paths, horizon, K) are the drawn monthly excess returns over the CDI and
    `labels` the generator of each path; without them, the plain block bootstrap is used.
    """
    paths, horizon = config.paths, config.horizon_months
    targets = np.array([config.targets.get(c, 0.0) for c in CLASS_ORDER])
    bands = np.array([config.bands.get(c, 0.0) for c in CLASS_ORDER])
    sale_tax = np.array([config.sale_tax.get(c, 0.0) for c in CLASS_ORDER])

    cdi_m = annual_to_monthly(scenario.annual_cdi_rate)
    ipca_m = annual_to_monthly(scenario.annual_ipca_rate)
    growth_m = annual_to_monthly(config.contribution_real_growth)
    cash_m = cdi_m * config.cash_cdi_multiplier * (1.0 - config.cash_income_tax_rate)
    income_yield = np.array(
        [
            cash_real_yield(scenario, config)
            if c == ArcaClass.CAIXA
            else config.income_yield.get(c, 0.0)
            for c in CLASS_ORDER
        ]
    )
    monthly_income_yield = income_yield / 12.0

    if excess is None:
        rng = np.random.default_rng(seed)
        idx = stationary_bootstrap_indices(
            sample.size, horizon, paths, config.mean_block_months, rng
        )
        excess = sample.excess[idx]
        labels = np.full(paths, "BOOTSTRAP")
    if excess.shape[:2] != (paths, horizon):
        raise ValueError(f"excess paths {excess.shape[:2]} do not match {(paths, horizon)}")

    values = np.tile(
        np.array([max(config.initial_by_class.get(c, 0.0), 0.0) for c in CLASS_ORDER]),
        (paths, 1),
    )
    basis = values.copy()
    strategy = np.ones(paths)
    peak = np.ones(paths)
    drawdown = np.zeros(paths)
    fees = np.zeros(paths)
    taxes = np.zeros(paths)
    deflator = 1.0
    contribution = config.monthly_contribution
    contributed = float(values[0].sum())
    strategy_12m: np.ndarray | None = None

    wealth = np.empty((paths, horizon + 1))
    net = np.empty((paths, horizon + 1))
    income = np.empty((paths, horizon + 1))

    def record(t: int) -> None:
        gains = np.maximum(values - basis, 0.0) @ sale_tax
        total = values.sum(axis=1)
        wealth[:, t] = total / deflator
        net[:, t] = (total - gains) / deflator
        income[:, t] = (values @ monthly_income_yield) / deflator

    record(0)
    yearly = [(0, contributed)]
    for t in range(1, horizon + 1):
        if deadline is not None and deadline():
            raise SimulationTimeout(f"projection stopped at month {t}")
        returns = (1.0 + excess[:, t - 1]) * (1.0 + cdi_m) - 1.0
        returns[:, CASH_INDEX] = cash_m
        before = values.sum(axis=1)
        values = values * (1.0 + returns)
        after = values.sum(axis=1)
        strategy *= np.where(before > 0, after / np.where(before > 0, before, 1.0), 1.0)
        peak = np.maximum(peak, strategy)
        drawdown = np.minimum(drawdown, strategy / peak - 1.0)
        if t == 12:
            strategy_12m = strategy.copy()

        deflator *= 1.0 + ipca_m
        contribution *= 1.0 + growth_m
        amount = contribution * deflator
        contributed += contribution
        if amount > 0:
            bought = _allocate(values, np.full(paths, amount * (1.0 - config.fee_rate)), targets)
            values += bought
            basis += bought
            fees += amount * config.fee_rate / deflator

        if config.rebalance:
            total = values.sum(axis=1)
            weights = values / np.where(total > 0, total, 1.0)[:, None]
            above = weights > targets[None, :] + bands[None, :] + 1e-12
            sell = np.where(above, values - targets[None, :] * total[:, None], 0.0)
            if sell.any():
                held = np.where(values > 0, values, 1.0)
                gain_share = np.clip(1.0 - basis / held, 0.0, 1.0)
                tax = sell * gain_share * sale_tax[None, :]
                basis -= sell * basis / held
                values -= sell
                proceeds = (sell - tax).sum(axis=1)
                fee = (sell.sum(axis=1) + proceeds) * config.fee_rate
                bought = _allocate(values, np.maximum(proceeds - fee, 0.0), targets)
                values += bought
                basis += bought
                taxes += tax.sum(axis=1) / deflator
                fees += fee / deflator
        record(t)
        if t % 12 == 0 or t == horizon:
            yearly.append((t, contributed))

    points = [
        ProjectionPoint(
            month=t,
            contributed=round(c, 2),
            wealth=percentiles(wealth[:, t]),
            income=percentiles(income[:, t]),
        )
        for t, c in yearly
    ]

    def first_hit(series: np.ndarray, target: float) -> tuple[np.ndarray, np.ndarray]:
        hit = series >= target
        reached = np.where(hit.any(axis=1), hit.argmax(axis=1), -1)
        return reached, series[:, -1] >= target

    wealth_goal = income_goal = None
    if config.wealth_goal:
        wealth_goal = _goal(*first_hit(net, config.wealth_goal), config.wealth_goal, labels)
    if config.income_goal:
        income_goal = _goal(*first_hit(income, config.income_goal), config.income_goal, labels)

    events: list[EventOutcome] = []
    if strategy_12m is not None:
        events.append(
            EventOutcome(
                key="LOSS_10_12M",
                label="Perder mais de 10% nos primeiros 12 meses",
                **asdict(chance(strategy_12m < 0.90, labels)),
            )
        )
    events.append(
        EventOutcome(
            key="BEAT_CDI",
            label="Render mais que o CDI no horizonte",
            **asdict(chance(strategy > (1.0 + cdi_m) ** horizon, labels)),
        )
    )

    return ProjectionResult(
        scenario=scenario,
        label=SCENARIO_LABELS.get(scenario.name, scenario.name),
        paths=paths,
        horizon_months=horizon,
        points=points,
        final_wealth=percentiles(wealth[:, -1]),
        final_net_wealth=percentiles(net[:, -1]),
        final_income=percentiles(income[:, -1]),
        max_drawdown=Percentiles(
            *(round(float(v), 4) for v in np.percentile(drawdown, PERCENTILES))
        ),
        contributed=round(contributed, 2),
        wealth_goal=wealth_goal,
        income_goal=income_goal,
        premises=premises(sample, scenario, config, posterior),
        fees=round(float(np.median(fees)), 2),
        taxes=round(float(np.median(taxes)), 2),
        events=events,
        generators=list(generators),
        prior_months=posterior.prior_months if posterior is not None else None,
    )


def projection_warnings(sample: ClassSample, config: ProjectionConfig) -> list[str]:
    """What the sample and the premises cannot support (risks R4, R9 and R18)."""
    warnings = [
        "Simulação, não recomendação: as faixas repetem os prêmios do período amostrado sobre "
        "os juros do cenário; o futuro pode ter prêmios menores e crises mais longas.",
    ]
    months = sample.size
    if months < SHORT_SAMPLE_MONTHS:
        warnings.append(
            f"Amostra curta: {months} meses de histórico comum (menos de {SHORT_SAMPLE_MONTHS}). "
            "As faixas ficam estreitas demais e a probabilidade de meta é só indicativa."
        )
    if sample.limited_by and sample.limited_by != CDI_KEY:
        warnings.append(
            f"A janela comum começa em {sample.months[0]:%m/%Y} porque a série {sample.limited_by} "
            "começa ali; as outras classes têm histórico mais longo que fica de fora."
        )
    if config.horizon_months > months:
        warnings.append(
            f"O horizonte ({config.horizon_months} meses) é maior que a amostra ({months}): "
            "os mesmos meses se repetem em blocos ao longo de cada trajetória."
        )
    return warnings
