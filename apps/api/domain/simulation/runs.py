"""Stored simulation runs (Phase 33.3): parameters, inputs from the database and execution.

A run is requested by the API (PENDING) and executed by the worker. The inputs it reads (price
series, IPCA, assets with their checklist history, policy versions and tax rules) are hashed
into `data_hash`; together with the parameters hash and `ENGINE_VERSION` it identifies the
result, so a run over unchanged data reuses the stored result of an earlier one.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, date, datetime
from typing import Any

from domain.assets.services.etf_exposure import suggest_arca_class
from domain.policy.services.assumptions import ProjectionAssumptions
from domain.policy.services.policy import InvestmentPolicy, current_policy
from domain.shared.entities import AssetEntity
from domain.shared.enums import ArcaClass, AssetType
from domain.shared.unit_of_work import AbstractUnitOfWork
from domain.simulation.calibration import (
    MIN_TRAIN_MONTHS,
    PATHS_PER_ORIGIN,
    STACKED,
    CalibrationResult,
    calibrate,
)
from domain.simulation.data import (
    CDI_KEY,
    IBOV_KEY,
    IFIX_KEY,
    SIMULATION_HISTORY_START,
    SP500_BRL_KEY,
    build_market_history,
    simulation_universe,
)
from domain.simulation.engine import (
    ENGINE_VERSION,
    BacktestConfig,
    BacktestResult,
    SimulatedAsset,
    SimulationTimeout,
    run_backtest,
    run_benchmark,
)
from domain.simulation.entities import (
    SimulationKind,
    SimulationResult,
    SimulationRun,
    SimulationStatus,
)
from domain.simulation.generators import (
    EQUAL_WEIGHTS,
    GENERATOR_LABELS,
    Generator,
    draw_mixture,
    sample_posterior,
)
from domain.simulation.market import MarketHistory
from domain.simulation.robustness import rule_variants, with_band
from domain.simulation.scenarios import (
    CLASS_ORDER,
    ClassSample,
    GeneratorShare,
    ProjectionConfig,
    ProjectionResult,
    class_sample,
    project,
    projection_warnings,
)
from domain.tax.entities import TaxRuleBook
from domain.tax.services.comparator import default_scenarios
from domain.tax.services.rules import rule_book

# Stored with every run; the backtest is deterministic, the Monte Carlo layers (33.5+) use it.
DEFAULT_SEED = 20261028
POLICY_VERSIONS_LIMIT = 200
CASH_TICKER = "CAIXA-CDI"
STRATEGY_KEY = "strategy"
BENCHMARK_PREFIX = "benchmark:"
PROJECTION_PREFIX = "projection:"
CALIBRATION_KEY = "calibration"
CALIBRATION_LOOKUP = 20
# Income yield of a class without a position to measure it (annual share of the value).
DEFAULT_INCOME_YIELD: dict[ArcaClass, float] = {
    ArcaClass.ACOES: 0.05,
    ArcaClass.ATIVOS_INTERNACIONAIS: 0.015,
}
MAX_INCOME_YIELD = 0.30


class Universe:
    REGISTERED = "REGISTERED"  # active market-traded assets (held or followed)
    REGISTERED_AND_CATALOG = "REGISTERED_AND_CATALOG"  # plus the most traded B3 instruments


class AnswersMode:
    DATED = "DATED"  # each checklist answer counts from the date it was given
    TODAY = "TODAY"  # today's answers on every date (labelled: uses later information)


class PolicyMode:
    CURRENT = "CURRENT"  # today's rules over the whole history (decision 5)
    AS_OF = "AS_OF"  # the version in force on each date


BENCHMARK_LABELS: dict[str, str] = {
    CDI_KEY: "CDI",
    IBOV_KEY: "Ibovespa",
    IFIX_KEY: "IFIX",
    SP500_BRL_KEY: "S&P 500 (R$)",
}


@dataclass(frozen=True)
class BacktestParams:
    """What a backtest run was asked to do; stored as JSON in `simulation_runs.params`."""

    start: date
    end: date
    monthly_contribution: float
    initial_contribution: float = 0.0
    correct_by_ipca: bool = False
    fee_rate: float = 0.0003
    rebalance: bool = False
    universe: str = Universe.REGISTERED
    catalog_top: int = 0
    policy_mode: str = PolicyMode.CURRENT
    benchmarks: tuple[str, ...] = (CDI_KEY, IBOV_KEY)
    # Also run the rule variants (bands x rebalancing) for the Robustness view (33.4).
    variants: bool = False
    answers_mode: str = AnswersMode.DATED

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["start"] = self.start.isoformat()
        data["end"] = self.end.isoformat()
        data["benchmarks"] = list(self.benchmarks)
        if self.answers_mode == AnswersMode.DATED:
            data.pop("answers_mode")  # older runs keep their hash
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BacktestParams:
        return cls(
            start=date.fromisoformat(data["start"]),
            end=date.fromisoformat(data["end"]),
            monthly_contribution=float(data["monthly_contribution"]),
            initial_contribution=float(data.get("initial_contribution", 0.0)),
            correct_by_ipca=bool(data.get("correct_by_ipca", False)),
            fee_rate=float(data.get("fee_rate", 0.0003)),
            rebalance=bool(data.get("rebalance", False)),
            universe=data.get("universe", Universe.REGISTERED),
            catalog_top=int(data.get("catalog_top", 0)),
            policy_mode=data.get("policy_mode", PolicyMode.CURRENT),
            benchmarks=tuple(data.get("benchmarks", (CDI_KEY, IBOV_KEY))),
            variants=bool(data.get("variants", False)),
            answers_mode=data.get("answers_mode", AnswersMode.DATED),
        )

    def config(self) -> BacktestConfig:
        return BacktestConfig(
            start=self.start,
            end=self.end,
            monthly_contribution=self.monthly_contribution,
            initial_contribution=self.initial_contribution,
            correct_by_ipca=self.correct_by_ipca,
            fee_rate=self.fee_rate,
            cash_symbol=CDI_KEY,
            rebalance=self.rebalance,
            answers_today=self.answers_mode == AnswersMode.TODAY,
        )


def _digest(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def params_hash(params: BacktestParams) -> str:
    return _digest(params.to_dict())


def new_backtest_run(
    params: BacktestParams, *, label: str | None = None, seed: int = DEFAULT_SEED
) -> SimulationRun:
    return SimulationRun(
        kind=SimulationKind.BACKTEST,
        params=params.to_dict(),
        params_hash=params_hash(params),
        code_version=ENGINE_VERSION,
        seed=seed,
        label=label,
    )


@dataclass(frozen=True)
class BacktestInputs:
    """Everything a backtest reads from the database, already in domain form."""

    assets: list[SimulatedAsset]
    history: MarketHistory
    policy: InvestmentPolicy
    policy_versions: list[InvestmentPolicy] = field(default_factory=list)
    tax_rules: TaxRuleBook | None = None
    data_hash: str = ""


def cash_asset() -> SimulatedAsset:
    """The CAIXA class follows the CDI: fixed income bonds have no long market series."""
    return SimulatedAsset(
        ticker=CASH_TICKER,
        name="Caixa (CDI)",
        asset_type=AssetType.CASH,
        arca_class=ArcaClass.CAIXA,
        price_symbol=CDI_KEY,
        use_cerrado=False,
    )


def to_simulated_asset(uow: AbstractUnitOfWork, asset: AssetEntity) -> SimulatedAsset:
    from_catalog = asset.id is None
    answers = () if from_catalog else tuple(uow.checklists.answer_history(asset.id))  # type: ignore[arg-type]
    return SimulatedAsset(
        ticker=asset.ticker.upper(),
        name=asset.name,
        asset_type=asset.asset_type,
        arca_class=asset.arca_class
        or suggest_arca_class(asset.ticker, asset.asset_type).arca_class,
        answers=answers,
        use_cerrado=asset.use_cerrado,
        checklist_profile=asset.checklist_profile,
        from_catalog=from_catalog,
    )


def _series_fingerprint(history: MarketHistory) -> list[list[Any]]:
    return [
        [
            key,
            len(s.dates),
            s.dates[0].isoformat() if s.dates else None,
            s.dates[-1].isoformat() if s.dates else None,
            round(sum(s.prices), 6),
            round(s.prices[-1], 8) if s.prices else None,
        ]
        for key, s in sorted(history.series.items())
    ]


def data_hash(
    history: MarketHistory,
    assets: Sequence[SimulatedAsset],
    policy: InvestmentPolicy,
    policy_versions: Sequence[InvestmentPolicy],
    tax_rules: Sequence[Any],
) -> str:
    """Hash of every input read from the database (changes when any of them changes)."""
    return _digest(
        {
            "series": _series_fingerprint(history),
            "ipca": sorted(
                [f"{y}-{m:02d}", round(v, 10)] for (y, m), v in history.ipca_monthly.items()
            ),
            "assets": [
                [
                    a.ticker,
                    a.asset_type.value,
                    a.arca_class.value,
                    a.use_cerrado,
                    a.checklist_profile.value if a.checklist_profile else None,
                    a.from_catalog,
                    [[x.question_id, str(x.value), str(x.answered_at)] for x in a.answers],
                ]
                for a in assets
            ],
            "policy": repr(policy),
            "policy_versions": [repr(p) for p in policy_versions],
            "tax_rules": [repr(r) for r in tax_rules],
        }
    )


def load_backtest_inputs(uow: AbstractUnitOfWork, params: BacktestParams) -> BacktestInputs:
    top = params.catalog_top if params.universe == Universe.REGISTERED_AND_CATALOG else 0
    universe = simulation_universe(uow, top)
    assets = [to_simulated_asset(uow, a) for a in universe] + [cash_asset()]
    currencies = {a.ticker.upper(): (a.currency or "BRL") for a in universe}
    history = build_market_history(
        uow.market_series,
        [a.ticker for a in universe],
        start=params.start,
        end=params.end,
        currency_by_ticker=currencies,
    )
    policy = current_policy(uow.policies)
    versions = (
        uow.policies.list_versions(POLICY_VERSIONS_LIMIT)
        if params.policy_mode == PolicyMode.AS_OF
        else []
    )
    stored_rules = uow.tax_rules.list_all()
    return BacktestInputs(
        assets=assets,
        history=history,
        policy=policy,
        policy_versions=versions,
        tax_rules=rule_book(stored_rules),
        data_hash=data_hash(history, assets, policy, versions, stored_rules),
    )


def run_backtest_params(
    inputs: BacktestInputs,
    params: BacktestParams,
    *,
    deadline: Callable[[], bool] | None = None,
) -> list[tuple[str, BacktestResult]]:
    """The strategy and each requested benchmark, fed with the same contributions."""
    config = params.config()
    out = [
        (
            STRATEGY_KEY,
            run_backtest(
                inputs.assets,
                inputs.history,
                inputs.policy,
                config,
                policy_versions=inputs.policy_versions,
                tax_rules=inputs.tax_rules,
                deadline=deadline,
            ),
        )
    ]
    for key in params.benchmarks:
        if key not in inputs.history.series:
            continue
        out.append(
            (
                f"{BENCHMARK_PREFIX}{key}",
                run_benchmark(
                    key,
                    inputs.history,
                    config,
                    label=BENCHMARK_LABELS.get(key, key),
                    deadline=deadline,
                ),
            )
        )
    if params.variants:
        for variant in rule_variants():
            out.append(
                (
                    variant.key,
                    run_backtest(
                        inputs.assets,
                        inputs.history,
                        with_band(inputs.policy, variant.band_pct),
                        replace(config, rebalance=variant.rebalance),
                        label=variant.label,
                        policy_versions=[
                            with_band(p, variant.band_pct) for p in inputs.policy_versions
                        ],
                        tax_rules=inputs.tax_rules,
                        deadline=deadline,
                    ),
                )
            )
    return out


def to_stored_result(run_id: int, key: str, result: BacktestResult) -> SimulationResult:
    return SimulationResult(
        run_id=run_id,
        key=key,
        label=result.label,
        summary=asdict(result.summary),
        points=[
            {
                "day": p.day.isoformat(),
                "contribution": p.contribution,
                "contributed": p.contributed,
                "market_value": p.market_value,
                "cash": p.cash,
                "fees": p.fees,
                "taxes": p.taxes,
                "by_class": {c.value: v for c, v in p.by_class.items()},
            }
            for p in result.points
        ],
        extra={"unavailable": result.unavailable, "survivorship_bias": result.survivorship_bias},
    )


@dataclass(frozen=True)
class ProjectionParams:
    """What a projection run was asked to do; the starting point and the rates are frozen here.

    The API resolves today's portfolio (value and income yield by class) and the CDI/IPCA
    premises when the run is requested, so the worker never calls a provider (risk R14) and
    the parameters hash changes whenever the starting point does.
    """

    horizon_years: int
    monthly_contribution: float  # today's money, kept constant in real terms
    initial_by_class: dict[str, float]
    income_yield_by_class: dict[str, float]
    cdi_rate: float
    ipca_rate: float
    rate_shift: float = 0.02
    contribution_real_growth: float = 0.0
    wealth_goal: float | None = None
    income_goal: float | None = None
    rebalance: bool = False
    paths: int = 5000
    mean_block_months: float = 12.0
    fee_rate: float = 0.0003
    sample_start: date | None = None
    # STACKED mixes the generators with the latest calibration's weights; a generator name
    # (BOOTSTRAP, BAYESIAN_BOOTSTRAP, BAYESIAN_NORMAL) uses that one alone (Phase 33.6).
    generator: str = STACKED

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["sample_start"] = self.sample_start.isoformat() if self.sample_start else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectionParams:
        start = data.get("sample_start")
        return cls(
            horizon_years=int(data["horizon_years"]),
            monthly_contribution=float(data["monthly_contribution"]),
            initial_by_class={k: float(v) for k, v in data["initial_by_class"].items()},
            income_yield_by_class={
                k: float(v) for k, v in data.get("income_yield_by_class", {}).items()
            },
            cdi_rate=float(data["cdi_rate"]),
            ipca_rate=float(data["ipca_rate"]),
            rate_shift=float(data.get("rate_shift", 0.02)),
            contribution_real_growth=float(data.get("contribution_real_growth", 0.0)),
            wealth_goal=data.get("wealth_goal"),
            income_goal=data.get("income_goal"),
            rebalance=bool(data.get("rebalance", False)),
            paths=int(data.get("paths", 5000)),
            mean_block_months=float(data.get("mean_block_months", 12.0)),
            fee_rate=float(data.get("fee_rate", 0.0003)),
            sample_start=date.fromisoformat(start) if start else None,
            generator=data.get("generator", STACKED),
        )

    def class_values(self, data: dict[str, float]) -> dict[ArcaClass, float]:
        return {ArcaClass(k): v for k, v in data.items()}


def new_projection_run(
    params: ProjectionParams, *, label: str | None = None, seed: int = DEFAULT_SEED
) -> SimulationRun:
    return SimulationRun(
        kind=SimulationKind.PROJECTION,
        params=params.to_dict(),
        params_hash=_digest(params.to_dict()),
        code_version=ENGINE_VERSION,
        seed=seed,
        label=label,
    )


def income_yields(
    values: dict[ArcaClass, float],
    earnings_12m: dict[ArcaClass, float],
    assumptions: ProjectionAssumptions,
) -> dict[ArcaClass, float]:
    """Trailing 12-month income over value by class; the premise when there is no position."""
    defaults = {
        **DEFAULT_INCOME_YIELD,
        ArcaClass.REAL_ESTATE: assumptions.real_estate_default_yield_rate,
    }
    out: dict[ArcaClass, float] = {}
    for cls in CLASS_ORDER:
        if cls == ArcaClass.CAIXA:
            continue  # the cash income follows the scenario CDI
        value, income = values.get(cls, 0.0), earnings_12m.get(cls, 0.0)
        measured = income / value if value > 0 and income > 0 else None
        chosen = measured if measured is not None else defaults[cls]
        out[cls] = round(min(chosen, MAX_INCOME_YIELD), 6)
    return out


@dataclass(frozen=True)
class ProjectionInputs:
    sample: ClassSample
    policy: InvestmentPolicy
    data_hash: str = ""
    # Generator mixture and where its weights came from.
    weights: dict[str, float] = field(default_factory=lambda: {Generator.BOOTSTRAP.value: 1.0})
    calibration_run: int | None = None
    generator_note: str | None = None


def latest_calibration(
    uow: AbstractUnitOfWork,
) -> tuple[SimulationRun, SimulationResult] | None:
    """The newest finished calibration and its stored result."""
    for run in uow.simulations.list_recent(CALIBRATION_LOOKUP, SimulationKind.CALIBRATION):
        if run.status == SimulationStatus.DONE and run.id is not None:
            rows = [r for r in uow.simulations.results(run.id) if r.key == CALIBRATION_KEY]
            if rows:
                return run, rows[0]
    return None


def mixture_weights(
    uow: AbstractUnitOfWork, generator: str, sample: ClassSample
) -> tuple[dict[str, float], int | None, str | None]:
    """Generator weights of a projection: the calibration's, when it fits the same classes."""
    if generator != STACKED:
        return {Generator(generator).value: 1.0}, None, None
    found = latest_calibration(uow)
    if found is None:
        return (
            dict(EQUAL_WEIGHTS),
            None,
            (
                "Ainda não há calibração: os três geradores entram com pesos iguais. Rode a "
                "calibração na aba Confiança."
            ),
        )
    run, result = found
    classes = set(result.summary.get("classes", []))
    if classes != {c.value for c in sample.classes}:
        return (
            dict(EQUAL_WEIGHTS),
            run.id,
            (
                "A última calibração foi feita com outras classes (a política mudou?): os três "
                "geradores entram com pesos iguais até a próxima calibração."
            ),
        )
    weights = {k: float(v) for k, v in result.summary.get("weights", {}).items()}
    return weights, run.id, None


def required_classes(params: ProjectionParams, policy: InvestmentPolicy) -> list[ArcaClass]:
    """Classes the projection can hold: a target above zero or money already there."""
    initial = params.class_values(params.initial_by_class)
    return [
        c for c in CLASS_ORDER if policy.arca.classes[c].target_pct > 0 or initial.get(c, 0.0) > 0
    ]


def load_projection_inputs(
    uow: AbstractUnitOfWork, params: ProjectionParams, *, today: date | None = None
) -> ProjectionInputs:
    policy = current_policy(uow.policies)
    history = build_market_history(
        uow.market_series,
        [],
        start=params.sample_start or SIMULATION_HISTORY_START,
        end=today or date.today(),
    )
    sample = class_sample(history, required_classes(params, policy), start=params.sample_start)
    weights, calibration_run, note = mixture_weights(uow, params.generator, sample)
    return ProjectionInputs(
        sample=sample,
        policy=policy,
        data_hash=_digest(
            {
                "series": _series_fingerprint(history),
                "policy": repr(policy),
                "sample": sample.size,
                "weights": weights,
                "calibration": calibration_run,
            }
        ),
        weights=weights,
        calibration_run=calibration_run,
        generator_note=note,
    )


def projection_config(params: ProjectionParams, policy: InvestmentPolicy) -> ProjectionConfig:
    premises = policy.valuation.projections
    return ProjectionConfig(
        horizon_months=params.horizon_years * 12,
        monthly_contribution=params.monthly_contribution,
        initial_by_class=params.class_values(params.initial_by_class),
        targets={c: p.target_pct / 100.0 for c, p in policy.arca.classes.items()},
        bands={c: p.band_pct / 100.0 for c, p in policy.arca.classes.items()},
        income_yield=params.class_values(params.income_yield_by_class),
        contribution_real_growth=params.contribution_real_growth,
        cash_cdi_multiplier=premises.cash_cdi_multiplier,
        cash_income_tax_rate=premises.cash_income_tax_rate,
        fee_rate=params.fee_rate,
        rebalance=params.rebalance,
        wealth_goal=params.wealth_goal,
        income_goal=params.income_goal,
        paths=params.paths,
        mean_block_months=params.mean_block_months,
    )


def run_projection_params(
    inputs: ProjectionInputs,
    params: ProjectionParams,
    *,
    seed: int,
    deadline: Callable[[], bool] | None = None,
) -> list[ProjectionResult]:
    """One projection per rate scenario, all from the same draws (common random numbers).

    The paths of the generator mixture are drawn once and reused in every scenario, so the
    differences between scenarios come from the rates alone, not from sampling noise.
    """
    config = projection_config(params, inputs.policy)
    scenarios = default_scenarios(
        params.cdi_rate,
        params.ipca_rate,
        ProjectionAssumptions(scenario_rate_shift=params.rate_shift),
    )
    posterior = sample_posterior(inputs.sample)
    excess, labels = draw_mixture(
        inputs.sample,
        inputs.weights,
        config.paths,
        config.horizon_months,
        mean_block=config.mean_block_months,
        seed=seed,
        posterior=posterior,
    )
    counts = {g: int((labels == g).sum()) for g in inputs.weights}
    shares = [
        GeneratorShare(key=g, label=GENERATOR_LABELS.get(g, g), weight=round(w, 4), paths=counts[g])
        for g, w in inputs.weights.items()
        if counts[g] > 0
    ]
    return [
        project(
            inputs.sample,
            s,
            config,
            seed=seed,
            deadline=deadline,
            excess=excess,
            labels=labels,
            posterior=posterior,
            generators=shares,
        )
        for s in scenarios
    ]


def to_stored_projection(
    run_id: int, result: ProjectionResult, inputs: ProjectionInputs, params: ProjectionParams
) -> SimulationResult:
    sample = inputs.sample
    summary = asdict(result)
    points = summary.pop("points")
    summary.pop("final_net_paths", None)
    summary.pop("goal_hits", None)
    summary["scenario"] = {
        "name": result.scenario.name,
        "annual_cdi_rate": result.scenario.annual_cdi_rate,
        "annual_ipca_rate": result.scenario.annual_ipca_rate,
    }
    summary["premises"] = [{**p, "arca_class": p["arca_class"].value} for p in summary["premises"]]
    return SimulationResult(
        run_id=run_id,
        key=f"{PROJECTION_PREFIX}{result.scenario.name}",
        label=result.label,
        summary=summary,
        points=points,
        extra={
            "sample_start": sample.months[0].isoformat(),
            "sample_end": sample.months[-1].isoformat(),
            "sample_months": sample.size,
            "classes": [c.value for c in sample.classes],
            "targets": {c.value: p.target_pct for c, p in inputs.policy.arca.classes.items()},
            "warnings": projection_warnings(sample, projection_config(params, inputs.policy))
            + bayes_warnings(result, inputs),
            "calibration_run": inputs.calibration_run,
        },
    )


def bayes_warnings(result: ProjectionResult, inputs: ProjectionInputs) -> list[str]:
    """Where the weights came from and when the prior outweighs the data (risk R15)."""
    out = [inputs.generator_note] if inputs.generator_note else []
    if result.prior_months is not None and result.prior_months > inputs.sample.size:
        out.append(
            f"O prior pesa mais que os dados: equivale a {result.prior_months:.0f} meses contra "
            f"{inputs.sample.size} de histórico, e puxa os prêmios para o alvo conservador "
            "(CDI + 3% em ações, CDI + 2% em FIIs)."
        )
    return out


@dataclass(frozen=True)
class CalibrationParams:
    """A weekly (or requested) calibration of the generators over the stored history."""

    mean_block_months: float = 12.0
    paths_per_origin: int = PATHS_PER_ORIGIN
    min_train_months: int = MIN_TRAIN_MONTHS

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalibrationParams:
        return cls(
            mean_block_months=float(data.get("mean_block_months", 12.0)),
            paths_per_origin=int(data.get("paths_per_origin", PATHS_PER_ORIGIN)),
            min_train_months=int(data.get("min_train_months", MIN_TRAIN_MONTHS)),
        )


def new_calibration_run(
    params: CalibrationParams | None = None, *, seed: int = DEFAULT_SEED
) -> SimulationRun:
    params = params or CalibrationParams()
    return SimulationRun(
        kind=SimulationKind.CALIBRATION,
        params=params.to_dict(),
        params_hash=_digest({"kind": "CALIBRATION", **params.to_dict()}),
        code_version=ENGINE_VERSION,
        seed=seed,
        label="Calibração dos geradores",
    )


def pending_calibration(uow: AbstractUnitOfWork) -> SimulationRun | None:
    """A calibration still queued or running."""
    for run in uow.simulations.list_recent(CALIBRATION_LOOKUP, SimulationKind.CALIBRATION):
        if run.status in (SimulationStatus.PENDING, SimulationStatus.RUNNING):
            return run
    return None


def queue_calibration(uow: AbstractUnitOfWork) -> SimulationRun:
    """Queue a calibration (no commit); one already waiting is returned instead."""
    waiting = pending_calibration(uow)
    return waiting if waiting is not None else uow.simulations.add(new_calibration_run())


@dataclass(frozen=True)
class CalibrationInputs:
    sample: ClassSample
    targets: dict[ArcaClass, float]
    data_hash: str = ""


def load_calibration_inputs(
    uow: AbstractUnitOfWork, *, today: date | None = None
) -> CalibrationInputs:
    """The common history of the classes with a target, and those targets (model portfolio)."""
    policy = current_policy(uow.policies)
    targets = {c: p.target_pct / 100.0 for c, p in policy.arca.classes.items()}
    history = build_market_history(
        uow.market_series, [], start=SIMULATION_HISTORY_START, end=today or date.today()
    )
    sample = class_sample(history, [c for c in CLASS_ORDER if targets.get(c, 0.0) > 0])
    return CalibrationInputs(
        sample=sample,
        targets=targets,
        data_hash=_digest(
            {
                "series": _series_fingerprint(history),
                "targets": {c.value: v for c, v in targets.items()},
            }
        ),
    )


def to_stored_calibration(run_id: int, result: CalibrationResult) -> SimulationResult:
    summary = asdict(result)
    origins = summary.pop("origins")
    summary["classes"] = [c.value for c in result.classes]
    summary["targets"] = {c.value: v for c, v in result.targets.items()}
    summary["first_origin"] = result.first_origin.isoformat()
    summary["last_origin"] = result.last_origin.isoformat()
    for g in summary["generators"]:
        g["status"] = g["status"].value
    return SimulationResult(
        run_id=run_id,
        key=CALIBRATION_KEY,
        label="Calibração dos geradores",
        summary=summary,
        points=[{**o, "origin": o["origin"].isoformat()} for o in origins],
    )


Compute = Callable[[Callable[[], bool]], list[SimulationResult]]


def prepare_run(uow: AbstractUnitOfWork, run: SimulationRun) -> tuple[str, Compute]:
    """Read the run's inputs and return their hash and the computation (by kind)."""
    run_id: int = run.id  # type: ignore[assignment]
    if run.kind == SimulationKind.LAB:
        from domain.simulation.ml.lab import run_lab
        from domain.simulation.ml.runs import prior_trials, to_stored_lab

        lab_inputs = load_calibration_inputs(uow)
        trials = prior_trials(uow)
        min_train = int(run.params.get("min_train_months", 60))
        return lab_inputs.data_hash, lambda deadline: to_stored_lab(
            run_id,
            run_lab(
                lab_inputs.sample,
                lab_inputs.targets,
                prior_trials=trials,
                seed=run.seed,
                min_train=min_train,
                deadline=deadline,
            ),
        )
    if run.kind == SimulationKind.CANDIDATES:
        # Imported here: candidate_runs builds on this module's projection helpers.
        from domain.simulation.candidate_runs import (
            CandidatesParams,
            load_candidates_inputs,
            run_candidates,
            to_stored_candidates,
        )

        cand_params = CandidatesParams.from_dict(run.params)
        cand_inputs = load_candidates_inputs(uow, cand_params)
        return cand_inputs.data_hash, lambda deadline: to_stored_candidates(
            run_id, *run_candidates(cand_inputs, cand_params, seed=run.seed, deadline=deadline)
        )
    if run.kind == SimulationKind.CALIBRATION:
        calibration = CalibrationParams.from_dict(run.params)
        c_inputs = load_calibration_inputs(uow)
        return c_inputs.data_hash, lambda deadline: [
            to_stored_calibration(
                run_id,
                calibrate(
                    c_inputs.sample,
                    c_inputs.targets,
                    seed=run.seed,
                    mean_block=calibration.mean_block_months,
                    paths=calibration.paths_per_origin,
                    min_train=calibration.min_train_months,
                    deadline=deadline,
                ),
            )
        ]
    if run.kind == SimulationKind.PROJECTION:
        projection = ProjectionParams.from_dict(run.params)
        p_inputs = load_projection_inputs(uow, projection)
        return p_inputs.data_hash, lambda deadline: [
            to_stored_projection(run_id, r, p_inputs, projection)
            for r in run_projection_params(p_inputs, projection, seed=run.seed, deadline=deadline)
        ]
    backtest = BacktestParams.from_dict(run.params)
    b_inputs = load_backtest_inputs(uow, backtest)
    return b_inputs.data_hash, lambda deadline: [
        to_stored_result(run_id, k, r)
        for k, r in run_backtest_params(b_inputs, backtest, deadline=deadline)
    ]


def _now() -> datetime:
    return datetime.now(UTC)


def execute_next_run(
    uow_factory: Callable[[], AbstractUnitOfWork],
    *,
    timeout_seconds: float,
    clock: Callable[[], float] = time.monotonic,
) -> SimulationRun | None:
    """Run the oldest PENDING simulation; returns it in its final state (None when idle).

    Never raises for a failing run: the error is stored and the status is FAILED or TIMEOUT.
    """
    with uow_factory() as uow:
        run = uow.simulations.next_pending()
        if run is None:
            return None
        run = uow.simulations.update(
            replace(run, status=SimulationStatus.RUNNING, started_at=_now())
        )
        uow.commit()

    limit = clock() + timeout_seconds
    status, error, digest, reused = SimulationStatus.DONE, None, None, None
    stored: list[SimulationResult] = []
    try:
        with uow_factory() as uow:
            digest, compute = prepare_run(uow, run)
            previous = uow.simulations.find_done(run.params_hash, digest, run.code_version)
            if previous is not None and previous.id is not None and previous.id != run.id:
                reused = previous.id
                stored = [
                    replace(r, run_id=run.id, id=None)  # type: ignore[arg-type]
                    for r in uow.simulations.results(previous.id)
                ]
        if reused is None:
            stored = compute(lambda: clock() > limit)
    except SimulationTimeout:
        status, error = SimulationStatus.TIMEOUT, f"time limit of {timeout_seconds:.0f}s reached"
    except Exception as exc:  # noqa: BLE001 - stored on the run, the worker keeps going
        status, error = SimulationStatus.FAILED, f"{type(exc).__name__}: {exc}"

    with uow_factory() as uow:
        if status == SimulationStatus.DONE:
            uow.simulations.save_results(run.id, stored)  # type: ignore[arg-type]
        final = uow.simulations.update(
            replace(
                run,
                status=status,
                error=error,
                data_hash=digest,
                reused_from=reused,
                finished_at=_now(),
            )
        )
        uow.commit()
    return final
