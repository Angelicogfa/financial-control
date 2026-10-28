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
from domain.policy.services.policy import InvestmentPolicy, current_policy
from domain.shared.entities import AssetEntity
from domain.shared.enums import ArcaClass, AssetType
from domain.shared.unit_of_work import AbstractUnitOfWork
from domain.simulation.data import (
    CDI_KEY,
    IBOV_KEY,
    IFIX_KEY,
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
from domain.simulation.market import MarketHistory
from domain.simulation.robustness import rule_variants, with_band
from domain.tax.entities import TaxRuleBook
from domain.tax.services.rules import rule_book

# Stored with every run; the backtest is deterministic, the Monte Carlo layers (33.5+) use it.
DEFAULT_SEED = 20261028
POLICY_VERSIONS_LIMIT = 200
CASH_TICKER = "CAIXA-CDI"
STRATEGY_KEY = "strategy"
BENCHMARK_PREFIX = "benchmark:"


class Universe:
    REGISTERED = "REGISTERED"  # active market-traded assets (held or followed)
    REGISTERED_AND_CATALOG = "REGISTERED_AND_CATALOG"  # plus the most traded B3 instruments


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

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["start"] = self.start.isoformat()
        data["end"] = self.end.isoformat()
        data["benchmarks"] = list(self.benchmarks)
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
        params = BacktestParams.from_dict(run.params)
        with uow_factory() as uow:
            inputs = load_backtest_inputs(uow, params)
            digest = inputs.data_hash
            previous = uow.simulations.find_done(run.params_hash, digest, run.code_version)
            if previous is not None and previous.id is not None and previous.id != run.id:
                reused = previous.id
                stored = [
                    replace(r, run_id=run.id, id=None)  # type: ignore[arg-type]
                    for r in uow.simulations.results(previous.id)
                ]
        if reused is None:
            results = run_backtest_params(inputs, params, deadline=lambda: clock() > limit)
            stored = [to_stored_result(run.id, k, r) for k, r in results]  # type: ignore[arg-type]
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
