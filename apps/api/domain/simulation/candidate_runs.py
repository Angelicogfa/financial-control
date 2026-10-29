"""Stored candidate runs (Phase 33.7): request-time selection, inputs and execution.

The API selects the candidates when the run is requested, with the same filters as the real
contribution (eligibility, no suspicious data, valuation verdict, liquidity), and freezes
them with the starting point and the rates. The worker reads only the database: the
long histories (33.1), the policy and the latest calibration weights (33.6).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import numpy as np

from domain.policy.services.assumptions import ProjectionAssumptions
from domain.policy.services.policy import InvestmentPolicy, current_policy
from domain.shared.enums import ArcaClass, AssetType
from domain.shared.unit_of_work import AbstractUnitOfWork
from domain.simulation.candidates import (
    CANDIDATE_PREFIX,
    MAX_CANDIDATES,
    RANK_RESAMPLES,
    RISK_MONTHS,
    RUPTURE_ANNUAL,
    RUPTURE_LOSS,
    RUPTURE_STRESS_LOSS,
    SUMMARY_KEY,
    CandidateEffect,
    CandidateSource,
    CandidateSpec,
    FactorFit,
    blend,
    candidate_excess,
    class_tau,
    cvar,
    diversification_ratio,
    fit_asset,
    max_drawdowns,
    p_improvement,
    ranking_stability,
    rupture_zone,
    shrink,
    static_returns,
)
from domain.simulation.data import (
    SIMULATION_HISTORY_START,
    build_market_history,
    simulation_universe,
)
from domain.simulation.engine import ENGINE_VERSION, SimulationTimeout
from domain.simulation.entities import SimulationKind, SimulationResult, SimulationRun
from domain.simulation.generators import draw_mixture, sample_posterior
from domain.simulation.market import MarketHistory
from domain.simulation.runs import (
    DEFAULT_SEED,
    ProjectionParams,
    _digest,
    _series_fingerprint,
    mixture_weights,
    projection_config,
    required_classes,
)
from domain.simulation.scenarios import (
    CASH_INDEX,
    CLASS_ORDER,
    ClassSample,
    annual_to_monthly,
    cash_annual_net,
    class_sample,
    project,
)
from domain.tax.services.comparator import default_scenarios

USD_TYPES = frozenset({AssetType.STOCK_INTL, AssetType.ETF_INTL, AssetType.REIT})


class WeightMode:
    NEXT_CONTRIBUTION = "NEXT_CONTRIBUTION"  # an equal share of its class with the candidate
    FIXED = "FIXED"  # a fixed weight of the whole portfolio


@dataclass(frozen=True)
class CandidatesParams:
    projection: ProjectionParams
    candidates: list[CandidateSpec]
    class_asset_counts: dict[str, int] = field(default_factory=dict)
    weight_mode: str = WeightMode.NEXT_CONTRIBUTION
    fixed_weight: float = 0.05
    rupture_stress: bool = False
    excluded: list[dict[str, str]] = field(default_factory=list)  # filtered at request time

    def to_dict(self) -> dict[str, Any]:
        return {
            "projection": self.projection.to_dict(),
            "candidates": [c.to_dict() for c in self.candidates],
            "class_asset_counts": dict(self.class_asset_counts),
            "weight_mode": self.weight_mode,
            "fixed_weight": self.fixed_weight,
            "rupture_stress": self.rupture_stress,
            "excluded": list(self.excluded),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CandidatesParams:
        return cls(
            projection=ProjectionParams.from_dict(data["projection"]),
            candidates=[CandidateSpec.from_dict(c) for c in data.get("candidates", [])],
            class_asset_counts={k: int(v) for k, v in data.get("class_asset_counts", {}).items()},
            weight_mode=data.get("weight_mode", WeightMode.NEXT_CONTRIBUTION),
            fixed_weight=float(data.get("fixed_weight", 0.05)),
            rupture_stress=bool(data.get("rupture_stress", False)),
            excluded=list(data.get("excluded", [])),
        )


def new_candidates_run(
    params: CandidatesParams, *, label: str | None = None, seed: int = DEFAULT_SEED
) -> SimulationRun:
    return SimulationRun(
        kind=SimulationKind.CANDIDATES,
        params=params.to_dict(),
        params_hash=_digest({"kind": "CANDIDATES", **params.to_dict()}),
        code_version=ENGINE_VERSION,
        seed=seed,
        label=label,
    )


# --- request-time selection ----------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateOption:
    """An asset offered by the watchlist or the screener, with what the filters need."""

    ticker: str
    name: str
    arca_class: ArcaClass
    asset_type: AssetType
    source: str
    eligible: bool | None
    valuation_verdict: str | None
    dividend_yield: float | None
    suspicious: bool
    volume_brl: float | None = None


def select_candidates(
    options: Sequence[CandidateOption],
    *,
    held: set[str],
    include_ineligible: bool = False,
    include_suspicious: bool = False,
    limit: int = MAX_CANDIDATES,
) -> tuple[list[CandidateSpec], list[dict[str, str]]]:
    """The real contribution's filters, watchlist first, then the screener by volume."""
    chosen: list[CandidateSpec] = []
    excluded: list[dict[str, str]] = []
    seen: set[str] = set()
    ordered = sorted(
        options,
        key=lambda o: (o.source != CandidateSource.WATCHLIST, -(o.volume_brl or 0.0), o.ticker),
    )
    for option in ordered:
        ticker = option.ticker.upper()
        if ticker in seen or ticker in held:
            continue
        seen.add(ticker)
        if option.suspicious and not include_suspicious:
            excluded.append({"ticker": ticker, "reason": "Dado suspeito nos indicadores"})
            continue
        if option.eligible is False and not include_ineligible:
            excluded.append({"ticker": ticker, "reason": "Fora dos critérios de elegibilidade"})
            continue
        if len(chosen) >= limit:
            excluded.append({"ticker": ticker, "reason": f"Além do teto de {limit} candidatos"})
            continue
        chosen.append(
            CandidateSpec(
                ticker=ticker,
                name=option.name,
                arca_class=option.arca_class,
                asset_type=option.asset_type,
                source=option.source,
                eligible=option.eligible,
                valuation_verdict=option.valuation_verdict,
                dividend_yield=option.dividend_yield,
                suspicious=option.suspicious,
                zone=rupture_zone(option.asset_type),
            )
        )
    return chosen, excluded


# --- inputs and execution ------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidatesInputs:
    sample: ClassSample
    history: MarketHistory
    policy: InvestmentPolicy
    universe: dict[str, ArcaClass]  # assets with history used to estimate τ by class
    weights: dict[str, float]
    calibration_run: int | None = None
    data_hash: str = ""


def load_candidates_inputs(
    uow: AbstractUnitOfWork, params: CandidatesParams, *, today: date | None = None
) -> CandidatesInputs:
    policy = current_policy(uow.policies)
    registered = [a for a in simulation_universe(uow, 0) if a.arca_class is not None]
    universe = {a.ticker.upper(): a.arca_class for a in registered}  # type: ignore[misc]
    tickers = sorted({*universe, *(c.ticker for c in params.candidates)})
    currencies = {a.ticker.upper(): (a.currency or "BRL") for a in registered}
    currencies.update({c.ticker: "USD" for c in params.candidates if c.asset_type in USD_TYPES})
    history = build_market_history(
        uow.market_series,
        tickers,
        start=params.projection.sample_start or SIMULATION_HISTORY_START,
        end=today or date.today(),
        currency_by_ticker=currencies,
    )
    required = [
        *required_classes(params.projection, policy),
        *(c.arca_class for c in params.candidates),
    ]
    sample = class_sample(
        history,
        [c for c in CLASS_ORDER if c in set(required)],
        start=params.projection.sample_start,
    )
    weights, calibration_run, _ = mixture_weights(uow, params.projection.generator, sample)
    return CandidatesInputs(
        sample=sample,
        history=history,
        policy=policy,
        universe=universe,
        weights=weights,
        calibration_run=calibration_run,
        data_hash=_digest(
            {
                "series": _series_fingerprint(history),
                "policy": repr(policy),
                "weights": weights,
                "calibration": calibration_run,
            }
        ),
    )


def _annual(monthly: float) -> float:
    return round(float((1.0 + monthly) ** 12 - 1.0), 6)


@dataclass(frozen=True)
class CandidateOutcome:
    spec: CandidateSpec
    fit: FactorFit
    effect: CandidateEffect


def run_candidates(
    inputs: CandidatesInputs,
    params: CandidatesParams,
    *,
    seed: int,
    deadline: Callable[[], bool] | None = None,
) -> tuple[dict[str, Any], list[CandidateOutcome]]:
    """Base projection, one projection per candidate on the same paths, and the effects."""
    sample = inputs.sample
    proj = params.projection
    config = projection_config(proj, inputs.policy)
    scenario = next(
        s
        for s in default_scenarios(
            proj.cdi_rate,
            proj.ipca_rate,
            ProjectionAssumptions(scenario_rate_shift=proj.rate_shift),
        )
        if s.name == "BASE"
    )
    posterior = sample_posterior(sample)
    excess, labels = draw_mixture(
        sample,
        inputs.weights,
        config.paths,
        config.horizon_months,
        mean_block=config.mean_block_months,
        seed=seed,
        posterior=posterior,
    )
    base = project(
        sample,
        scenario,
        config,
        seed=seed,
        excess=excess,
        labels=labels,
        posterior=posterior,
        keep_paths=True,
    )

    # Factor fits: every asset with history estimates τ of its class; candidates are shrunk.
    fits: dict[str, FactorFit] = {}
    for ticker, cls in {
        **inputs.universe,
        **{c.ticker: c.arca_class for c in params.candidates},
    }.items():
        if cls in sample.classes and cls != ArcaClass.CAIXA:
            fit = fit_asset(ticker, cls, inputs.history, sample)
            if fit is not None:
                fits[ticker] = fit
    taus = {
        cls: class_tau([f for f in fits.values() if f.arca_class == cls])
        for cls in {f.arca_class for f in fits.values()}
    }

    initial = np.array([max(config.initial_by_class.get(c, 0.0), 0.0) for c in CLASS_ORDER])
    targets = np.array([config.targets.get(c, 0.0) for c in CLASS_ORDER])
    weights = initial / initial.sum() if initial.sum() > 0 else targets
    cdi_m = annual_to_monthly(scenario.annual_cdi_rate)
    cash_m = (1.0 + cash_annual_net(scenario, config)) ** (1.0 / 12.0) - 1.0
    totals = (1.0 + excess) * (1.0 + cdi_m) - 1.0
    totals[:, :, CASH_INDEX] = cash_m
    base_monthly = static_returns(excess, weights, cdi_m, cash_m)
    base_12m = np.prod(1.0 + base_monthly[:, :RISK_MONTHS], axis=1) - 1.0
    base_cvar = cvar(base_12m)
    base_dd = float(np.median(max_drawdowns(base_monthly)))
    active = weights > 0
    base_dr = (
        diversification_ratio(totals[:, :, active], weights[active]) if active.sum() > 1 else 1.0
    )
    base_goal = float(base.goal_hits.mean()) if base.goal_hits is not None else None

    loss = RUPTURE_STRESS_LOSS if params.rupture_stress else RUPTURE_LOSS
    outcomes: list[CandidateOutcome] = []
    diffs: list[np.ndarray] = []
    excluded = list(params.excluded)
    for i, spec in enumerate(params.candidates):
        if deadline is not None and deadline():
            raise SimulationTimeout(f"candidates stopped at {spec.ticker}")
        raw = fits.get(spec.ticker)
        if spec.arca_class not in sample.classes or spec.arca_class == ArcaClass.CAIXA:
            excluded.append({"ticker": spec.ticker, "reason": "Classe sem série de referência"})
            continue
        if raw is None:
            excluded.append(
                {"ticker": spec.ticker, "reason": "Menos de 36 meses de histórico guardado"}
            )
            continue
        fit = shrink(raw, taus.get(spec.arca_class, 0.0))
        k = CLASS_ORDER.index(spec.arca_class)
        rng = np.random.default_rng([seed, 1000 + i])
        cand = candidate_excess(
            fit,
            excess[:, :, k],
            rupture_annual=RUPTURE_ANNUAL.get(spec.zone, RUPTURE_ANNUAL["NO_DATA"]),
            rupture_loss=loss,
            mean_block=config.mean_block_months,
            rng=rng,
        )
        class_weight = float(weights[k]) if weights[k] > 0 else float(targets[k])
        if params.weight_mode == WeightMode.FIXED and class_weight > 0:
            share = min(params.fixed_weight / class_weight, 1.0)
        else:
            # Held assets of the class: a class with none gives the candidate all of it.
            count = params.class_asset_counts.get(spec.arca_class.value, 0)
            share = 1.0 / (max(count, 0) + 1)
        with_c = project(
            sample,
            scenario,
            config,
            seed=seed,
            excess=blend(excess, k, cand, share),
            labels=labels,
            posterior=posterior,
            keep_paths=True,
        )
        diff = with_c.final_net_paths - base.final_net_paths  # type: ignore[operator]
        diffs.append(diff)
        p, low, high = p_improvement(diff)

        cand_total = (1.0 + cand) * (1.0 + cdi_m) - 1.0
        with_weights = weights.copy()
        with_weights[k] = class_weight * (1.0 - share)
        with_monthly = totals @ with_weights + class_weight * share * cand_total
        with_12m = np.prod(1.0 + with_monthly[:, :RISK_MONTHS], axis=1) - 1.0
        components = np.concatenate([totals, cand_total[:, :, None]], axis=2)
        comp_weights = np.append(with_weights, class_weight * share)
        mask = comp_weights > 0
        dy_class = config.income_yield.get(spec.arca_class, 0.0)
        dy_cand = spec.dividend_yield if spec.dividend_yield is not None else dy_class
        outcomes.append(
            CandidateOutcome(
                spec=spec,
                fit=fit,
                effect=CandidateEffect(
                    ticker=spec.ticker,
                    share_in_class=round(share, 4),
                    weight=round(class_weight * share, 4),
                    delta_final_wealth=round(float(np.median(diff)), 2),
                    p_improve=p,
                    p_improve_low=low,
                    p_improve_high=high,
                    delta_goal_probability=round(float(with_c.goal_hits.mean()) - base_goal, 4)
                    if base_goal is not None and with_c.goal_hits is not None
                    else None,
                    delta_cvar_12m=round(cvar(with_12m) - base_cvar, 4),
                    delta_drawdown=round(
                        float(np.median(max_drawdowns(with_monthly))) - base_dd, 4
                    ),
                    delta_diversification=round(
                        diversification_ratio(components[:, :, mask], comp_weights[mask]) - base_dr,
                        4,
                    ),
                    delta_income_yield=round(class_weight * share * (dy_cand - dy_class), 6),
                ),
            )
        )

    if diffs:
        stability = ranking_stability(
            np.vstack(diffs), resamples=RANK_RESAMPLES, rng=np.random.default_rng([seed, 7])
        )
        order = np.argsort([-o.effect.delta_final_wealth for o in outcomes])
        ranks = np.empty(len(outcomes), dtype=int)
        ranks[order] = np.arange(1, len(outcomes) + 1)
        outcomes = [
            CandidateOutcome(
                o.spec,
                o.fit,
                CandidateEffect(
                    **{
                        **asdict(o.effect),
                        "top_k_share": round(float(stability[j]), 4),
                        "rank": int(ranks[j]),
                    }
                ),
            )
            for j, o in enumerate(outcomes)
        ]
        outcomes.sort(key=lambda o: o.effect.rank)

    summary = {
        "scenario": {
            "annual_cdi_rate": scenario.annual_cdi_rate,
            "annual_ipca_rate": scenario.annual_ipca_rate,
        },
        "horizon_months": config.horizon_months,
        "paths": config.paths,
        "base": {
            "final_net_wealth_p50": base.final_net_wealth.p50,
            "cvar_12m": round(base_cvar, 4),
            "drawdown_median": round(base_dd, 4),
            "diversification": round(base_dr, 4),
            "goal_probability": round(base_goal, 4) if base_goal is not None else None,
        },
        "tau_annual": {c.value: _annual(t) for c, t in taus.items()},
        "tested": len(params.candidates),
        "evaluated": len(outcomes),
        "excluded": excluded,
        "weight_mode": params.weight_mode,
        "rupture_loss": loss,
        "sample_start": sample.months[0].isoformat(),
        "sample_end": sample.months[-1].isoformat(),
        "calibration_run": inputs.calibration_run,
        "warnings": candidate_warnings(params, outcomes),
    }
    return summary, outcomes


def candidate_warnings(params: CandidatesParams, outcomes: Sequence[CandidateOutcome]) -> list[str]:
    out = [
        "Candidatos para investigar, não recomendação de compra: a probabilidade de melhora "
        "vale dado o modelo e os dados até hoje.",
        f"{len(params.candidates)} candidato(s) comparados nesta rodada (teto {MAX_CANDIDATES}): "
        "com muitos candidatos, o melhor tende a ser o mais sortudo do histórico.",
    ]
    if any(o.spec.source == CandidateSource.SCREENER for o in outcomes):
        out.append(
            "Candidatos do screener só existem porque sobreviveram até hoje: o evento de "
            "ruptura cobre parte desse viés."
        )
    if any(o.fit.shrinkage > 0.8 for o in outcomes):
        out.append(
            "Em vários candidatos o histórico é curto ou ruidoso demais e o α foi quase todo "
            "encolhido para zero: a diferença deles vem do β e da diversificação, não do passado."
        )
    return out


def to_stored_candidates(
    run_id: int, summary: dict[str, Any], outcomes: Sequence[CandidateOutcome]
) -> list[SimulationResult]:
    rows = [SimulationResult(run_id=run_id, key=SUMMARY_KEY, label="Resumo", summary=summary)]
    for o in outcomes:
        f = o.fit
        rows.append(
            SimulationResult(
                run_id=run_id,
                key=f"{CANDIDATE_PREFIX}{o.spec.ticker}",
                label=o.spec.name,
                summary={
                    "spec": o.spec.to_dict(),
                    "fit": {
                        "months": f.months,
                        "alpha_annual": _annual(f.alpha),
                        "alpha_post_annual": _annual(f.alpha_post),
                        "alpha_post_sd_annual": round(f.alpha_post_sd * 12**0.5, 6),
                        "beta": round(f.beta, 4),
                        "beta_post": round(f.beta_post, 4),
                        "beta_post_sd": round(f.beta_post_sd, 4),
                        "shrinkage": f.shrinkage,
                        "residual_vol_annual": round(
                            float(np.std(f.residuals, ddof=1) * 12**0.5), 6
                        ),
                    },
                    "effect": asdict(o.effect),
                },
            )
        )
    return rows
