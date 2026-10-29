"""Use cases (query/command handlers) for the simulation module (Phase 33)."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta

from controllers.shared.dependencies import UoWFactory
from controllers.simulation.requests import (
    BacktestRequest,
    CandidatesRequest,
    ProjectionRequest,
)
from controllers.simulation.responses import (
    CalibrationDTO,
    CandidateResultDTO,
    CandidatesDTO,
    CoverageReportDTO,
    CrisisDTO,
    DistributionDTO,
    ProjectionDTO,
    ProjectionScenarioDTO,
    RobustnessDTO,
    SeriesCoverageDTO,
    SeriesRefDTO,
    ShockDTO,
    SimulationResultDTO,
    SimulationRunDetailDTO,
    SimulationRunDTO,
    VariantDTO,
    VariantValidationDTO,
    WindowOutcomeDTO,
)
from core.errors import NotFoundError, ValidationError
from domain.policy.services.assumptions import ProjectionAssumptions
from domain.policy.services.policy import current_policy
from domain.portfolio.services.consolidation import ConsolidatedPortfolioReport
from domain.portfolio.services.service import PortfolioApplicationService
from domain.research.services.screener import ScreenerCriteria
from domain.research.services.use_cases import ResearchHandler
from domain.shared.enums import ArcaClass, AssetPurpose
from domain.shared.unit_of_work import AbstractUnitOfWork
from domain.simulation.candidate_runs import (
    CandidateOption,
    CandidatesParams,
    new_candidates_run,
    select_candidates,
)
from domain.simulation.candidates import (
    CANDIDATE_PREFIX,
    MAX_CANDIDATES,
    SUMMARY_KEY,
    CandidateSource,
)
from domain.simulation.data import (
    CDI_KEY,
    SIMULATION_HISTORY_START,
    coverage_report,
    simulation_universe,
)
from domain.simulation.engine import BacktestPoint
from domain.simulation.entities import SimulationKind, SimulationResult, SimulationRun
from domain.simulation.robustness import (
    HISTORICAL_CRISES,
    SYNTHETIC_SHOCKS,
    VARIANT_PREFIX,
    apply_shock,
    crisis_outcomes,
    distribution,
    holdout_start,
    points_from_stored,
    rule_variants,
    sample_warnings,
    variant_validation,
    window_outcome,
)
from domain.simulation.runs import (
    BENCHMARK_PREFIX,
    CALIBRATION_KEY,
    PROJECTION_PREFIX,
    STRATEGY_KEY,
    BacktestParams,
    ProjectionParams,
    Universe,
    income_yields,
    latest_calibration,
    new_backtest_run,
    new_projection_run,
    pending_calibration,
    queue_calibration,
)
from infra.providers.batch import fetch_market_data


def to_run_dto(run: SimulationRun) -> SimulationRunDTO:
    return SimulationRunDTO(**asdict(run))


def to_result_dto(result: SimulationResult) -> SimulationResultDTO:
    return SimulationResultDTO(
        key=result.key,
        label=result.label,
        summary=result.summary,  # type: ignore[arg-type]
        points=result.points,  # type: ignore[arg-type]
        unavailable=result.extra.get("unavailable", []),
        survivorship_bias=bool(result.extra.get("survivorship_bias", False)),
    )


class SimulationHandler:
    """Application handler for the portfolio simulation."""

    def __init__(
        self,
        uow_factory: UoWFactory,
        *,
        catalog_top: int = 50,
        portfolio_service: PortfolioApplicationService | None = None,
    ) -> None:
        self.uow_factory = uow_factory
        self.catalog_top = catalog_top
        # Reads today's portfolio and market rates for a projection's starting point.
        self.portfolio_service = portfolio_service

    def coverage(self, *, start: date | None = None, end: date | None = None) -> CoverageReportDTO:
        """Coverage of the stored series a simulation over the universe would read."""
        first = start or SIMULATION_HISTORY_START
        last = end or date.today()
        if first >= last:
            raise ValidationError("start must be before end", code="INVALID_PERIOD")
        with self.uow_factory() as uow:
            tickers = [a.ticker for a in simulation_universe(uow, self.catalog_top)]
            report = coverage_report(uow.market_series, tickers, start=first, end=last)
        return CoverageReportDTO(
            start=report.start,
            end=report.end,
            series=[SeriesCoverageDTO(**asdict(s), share=round(s.share, 4)) for s in report.series],
            missing=report.missing,
        )

    def submit_backtest(
        self, req: BacktestRequest, *, today: date | None = None
    ) -> SimulationRunDTO:
        """Queue a backtest (PENDING); the worker executes it and stores the results."""
        if req.start >= req.end:
            raise ValidationError("start must be before end", code="INVALID_PERIOD")
        if req.end > (today or date.today()):
            raise ValidationError("end cannot be in the future", code="INVALID_PERIOD")
        with_catalog = req.universe == Universe.REGISTERED_AND_CATALOG
        params = BacktestParams(
            start=req.start,
            end=req.end,
            monthly_contribution=req.monthly_contribution,
            initial_contribution=req.initial_contribution,
            correct_by_ipca=req.correct_by_ipca,
            fee_rate=req.fee_rate,
            rebalance=req.rebalance,
            universe=req.universe,
            catalog_top=(req.catalog_top if req.catalog_top is not None else self.catalog_top)
            if with_catalog
            else 0,
            policy_mode=req.policy_mode,
            benchmarks=tuple(dict.fromkeys(req.benchmarks)),
            variants=req.variants,
        )
        with self.uow_factory() as uow:
            run = uow.simulations.add(new_backtest_run(params, label=req.label))
            uow.commit()
        return to_run_dto(run)

    def submit_projection(self, req: ProjectionRequest) -> SimulationRunDTO:
        """Queue a forward projection from today's portfolio (starting point frozen now)."""
        with self.uow_factory() as uow:
            params = self._projection_params(uow, req, self._starting_point(uow, req))
            run = uow.simulations.add(new_projection_run(params, label=req.label))
            uow.commit()
        return to_run_dto(run)

    def submit_candidates(self, req: CandidatesRequest) -> SimulationRunDTO:
        """Queue a candidate run: options selected and filtered now, measured in the worker."""
        if self.portfolio_service is None:
            raise ValidationError(
                "candidates need the portfolio service (watchlist and screener)",
                code="PORTFOLIO_UNAVAILABLE",
            )
        research = ResearchHandler(self.uow_factory, self.portfolio_service)
        options = self._candidate_options(research, req)
        with self.uow_factory() as uow:
            report = self.portfolio_service.build_portfolio_report(uow)
            held = {p.ticker.upper() for p in report.positions if p.quantity > 0}
            counts: dict[str, int] = {}
            for p in report.positions:
                if p.quantity > 0 and p.purpose == AssetPurpose.ARCA:
                    counts[p.arca_class.value] = counts.get(p.arca_class.value, 0) + 1
            start = (
                self._starting_point(uow, req)
                if req.initial_by_class is not None
                else portfolio_start(report)
            )
            projection = self._projection_params(uow, req, start, require_money=False)
            chosen, excluded = select_candidates(
                options,
                held=held,
                include_ineligible=req.include_ineligible,
                include_suspicious=req.include_suspicious,
            )
            if not chosen:
                raise ValidationError(
                    "no candidate left after the filters (watchlist empty or all excluded)",
                    code="NO_CANDIDATES",
                )
            params = CandidatesParams(
                projection=projection,
                candidates=chosen,
                class_asset_counts=counts,
                weight_mode=req.weight_mode,
                fixed_weight=req.fixed_weight,
                rupture_stress=req.rupture_stress,
                excluded=excluded,
            )
            run = uow.simulations.add(new_candidates_run(params, label=req.label))
            uow.commit()
        return to_run_dto(run)

    def _candidate_options(
        self, research: ResearchHandler, req: CandidatesRequest
    ) -> list[CandidateOption]:
        service = self.portfolio_service
        assert service is not None
        options: list[CandidateOption] = []
        watchlist = research.watchlist()
        with self.uow_factory() as uow:
            assets = [
                a for a in (uow.assets.get_by_id(w.asset_id) for w in watchlist) if a is not None
            ]
        fundamentals = fetch_market_data(
            service.gateway,
            assets,
            include_quotes=False,
            max_workers=service.fetch_workers,
            timeout_seconds=service.fetch_timeout_seconds,
        ).fundamentals
        for item in watchlist:
            fund = fundamentals.get(item.ticker)
            options.append(
                CandidateOption(
                    ticker=item.ticker,
                    name=item.name,
                    arca_class=item.arca_class,
                    asset_type=item.asset_type,
                    source=CandidateSource.WATCHLIST,
                    eligible=item.eligible,
                    valuation_verdict=item.valuation_verdict,
                    dividend_yield=fund.dividend_yield if fund else None,
                    suspicious=bool(fund and fund.suspicious),
                )
            )
        if req.include_screener:
            found = research.screener(
                ScreenerCriteria(
                    min_volume_brl=req.screener_min_volume,
                    exclude_registered=True,
                    limit=MAX_CANDIDATES * 2,
                )
            )
            with self.uow_factory() as uow:
                catalog = {c.ticker: c for c in uow.catalog.list_all()}
            instruments = [catalog[r.ticker] for r in found.results if r.ticker in catalog]
            screened = service.catalog_fundamentals(instruments)
            for row in found.results:
                fund = screened.get(row.ticker)
                options.append(
                    CandidateOption(
                        ticker=row.ticker,
                        name=row.name,
                        arca_class=row.arca_class,
                        asset_type=row.asset_type,
                        source=CandidateSource.SCREENER,
                        eligible=None,
                        valuation_verdict=row.valuation_verdict,
                        dividend_yield=row.dividend_yield,
                        suspicious=bool(fund and fund.suspicious),
                        volume_brl=row.volume_brl,
                    )
                )
        return options

    def _projection_params(
        self,
        uow: AbstractUnitOfWork,
        req: ProjectionRequest,
        start: tuple[dict[ArcaClass, float], dict[ArcaClass, float]],
        *,
        require_money: bool = True,
    ) -> ProjectionParams:
        assumptions = current_policy(uow.policies).valuation.projections
        initial, earnings = start
        if require_money and sum(initial.values()) <= 0 and req.monthly_contribution <= 0:
            raise ValidationError(
                "nothing to project: no portfolio value and no contribution",
                code="EMPTY_PROJECTION",
            )
        yields = income_yields(initial, earnings, assumptions)
        yields.update({ArcaClass(k): v for k, v in (req.income_yield_by_class or {}).items()})
        cdi, ipca = self._rates(req, assumptions)
        return ProjectionParams(
            horizon_years=req.horizon_years,
            monthly_contribution=req.monthly_contribution,
            initial_by_class={c.value: round(v, 2) for c, v in initial.items()},
            income_yield_by_class={c.value: v for c, v in yields.items()},
            cdi_rate=cdi,
            ipca_rate=ipca,
            rate_shift=assumptions.scenario_rate_shift,
            contribution_real_growth=req.contribution_real_growth,
            wealth_goal=req.wealth_goal,
            income_goal=req.income_goal,
            rebalance=req.rebalance,
            paths=req.paths,
            mean_block_months=req.mean_block_months,
            fee_rate=req.fee_rate,
            sample_start=req.sample_start,
            generator=req.generator,
        )

    def _starting_point(
        self, uow: AbstractUnitOfWork, req: ProjectionRequest
    ) -> tuple[dict[ArcaClass, float], dict[ArcaClass, float]]:
        if req.initial_by_class is not None:
            return {ArcaClass(k): max(v, 0.0) for k, v in req.initial_by_class.items()}, {}
        if self.portfolio_service is None:
            raise ValidationError(
                "initial_by_class is required when the portfolio is not available",
                code="PORTFOLIO_UNAVAILABLE",
            )
        return portfolio_start(self.portfolio_service.build_portfolio_report(uow))

    def _rates(
        self, req: ProjectionRequest, assumptions: ProjectionAssumptions
    ) -> tuple[float, float]:
        cdi = req.cdi_rate if req.cdi_rate is not None else assumptions.projected_cdi_rate
        ipca = req.ipca_rate if req.ipca_rate is not None else assumptions.projected_ipca_rate
        if cdi is None or ipca is None:
            if self.portfolio_service is None:
                raise ValidationError(
                    "cdi_rate and ipca_rate are required without market rates",
                    code="RATES_UNAVAILABLE",
                )
            market_cdi, market_ipca = self.portfolio_service.gateway.get_macro_rates()
            cdi = market_cdi if cdi is None else cdi
            ipca = market_ipca if ipca is None else ipca
        return round(cdi, 6), round(ipca, 6)

    def get_run(self, run_id: int) -> SimulationRunDetailDTO:
        """Status and, for a backtest, its series (a projection's are in `projection`)."""
        with self.uow_factory() as uow:
            run = self._get(uow, run_id)
            results = uow.simulations.results(run_id)
        backtest = run.kind == SimulationKind.BACKTEST
        return SimulationRunDetailDTO(
            **to_run_dto(run).model_dump(),
            results=[to_result_dto(r) for r in results] if backtest else [],
        )

    def list_runs(
        self, limit: int = 20, kind: SimulationKind | None = None
    ) -> list[SimulationRunDTO]:
        with self.uow_factory() as uow:
            return [to_run_dto(r) for r in uow.simulations.list_recent(limit, kind)]

    def robustness(self, run_id: int) -> RobustnessDTO:
        """Crises, shocks and rule variants of a finished run (empty while it is not DONE)."""
        with self.uow_factory() as uow:
            run = self._get(uow, run_id, SimulationKind.BACKTEST)
            results = uow.simulations.results(run_id)
            trials_total = uow.simulations.count_results(VARIANT_PREFIX)
        return build_robustness(run, results, trials_total=trials_total)

    def submit_calibration(self) -> SimulationRunDTO:
        """Queue a calibration of the generators; one already waiting is returned instead."""
        with self.uow_factory() as uow:
            run = queue_calibration(uow)
            uow.commit()
        return to_run_dto(run)

    def calibration(self, run_id: int | None = None) -> CalibrationDTO:
        """A calibration by id, or the latest finished one (empty when there is none)."""
        with self.uow_factory() as uow:
            pending = pending_calibration(uow)
            if run_id is not None:
                run = self._get(uow, run_id, SimulationKind.CALIBRATION)
                rows = [r for r in uow.simulations.results(run_id) if r.key == CALIBRATION_KEY]
                found = (run, rows[0] if rows else None)
            else:
                latest = latest_calibration(uow)
                found = (latest[0], latest[1]) if latest else None
        pending_id = pending.id if pending is not None else None
        if found is None:
            return CalibrationDTO(pending_run_id=pending_id)
        run, result = found
        base = {
            "run_id": run.id,
            "status": run.status,
            "finished_at": run.finished_at,
            "error": run.error,
            "pending_run_id": pending_id if pending_id != run.id else None,
        }
        if result is None:
            return CalibrationDTO(**base)
        return CalibrationDTO(**base, **result.summary, origins=result.points)

    def candidates(self, run_id: int) -> CandidatesDTO:
        """Candidates to investigate of a finished run (empty while it is not DONE)."""
        with self.uow_factory() as uow:
            run = self._get(uow, run_id, SimulationKind.CANDIDATES)
            results = uow.simulations.results(run_id)
        return build_candidates(run, results)

    def projection(self, run_id: int) -> ProjectionDTO:
        """Percentiles, goals and premises of a projection (empty while it is not DONE)."""
        with self.uow_factory() as uow:
            run = self._get(uow, run_id, SimulationKind.PROJECTION)
            results = uow.simulations.results(run_id)
        return build_projection(run, results)

    @staticmethod
    def _get(
        uow: AbstractUnitOfWork, run_id: int, kind: SimulationKind | None = None
    ) -> SimulationRun:
        run = uow.simulations.get(run_id)
        if run is None:
            raise NotFoundError(f"Simulation run {run_id} not found")
        if kind is not None and run.kind != kind:
            raise ValidationError(
                f"simulation run {run_id} is a {run.kind.value}, not a {kind.value}",
                code="WRONG_SIMULATION_KIND",
            )
        return run


def portfolio_start(
    report: ConsolidatedPortfolioReport,
) -> tuple[dict[ArcaClass, float], dict[ArcaClass, float]]:
    """Today's value and trailing 12-month income by ARCA class."""
    values = {a.arca_class: max(a.current_value, 0.0) for a in report.allocations}
    earnings: dict[ArcaClass, float] = {}
    for p in report.positions:
        if p.purpose == AssetPurpose.ARCA:
            earnings[p.arca_class] = earnings.get(p.arca_class, 0.0) + p.earnings_12m_brl
    return values, earnings


def build_projection(run: SimulationRun, results: list[SimulationResult]) -> ProjectionDTO:
    rows = [r for r in results if r.key.startswith(PROJECTION_PREFIX)]
    extra = rows[0].extra if rows else {}
    return ProjectionDTO(
        run_id=run.id,  # type: ignore[arg-type]
        status=run.status,
        scenarios=[
            ProjectionScenarioDTO(key=r.key, points=r.points, **r.summary)  # type: ignore[arg-type]
            for r in rows
        ],
        sample_start=extra.get("sample_start"),
        sample_end=extra.get("sample_end"),
        sample_months=extra.get("sample_months", 0),
        classes=extra.get("classes", []),
        targets=extra.get("targets", {}),
        warnings=extra.get("warnings", []),
        calibration_run=extra.get("calibration_run"),
    )


def build_robustness(
    run: SimulationRun, results: list[SimulationResult], *, trials_total: int
) -> RobustnessDTO:
    series = [r for r in results if not r.key.startswith(VARIANT_PREFIX)]
    points = {r.key: points_from_stored(r.points) for r in results}
    strategy = points.get(STRATEGY_KEY, [])
    by_series = {r.key: crisis_outcomes(points[r.key]) for r in series}
    crises = [
        CrisisDTO(
            key=c.key,
            label=c.label,
            start=c.start,
            end=c.end,
            outcomes={k: WindowOutcomeDTO(**asdict(v[c.key])) for k, v in by_series.items()},
        )
        for c in HISTORICAL_CRISES
    ]
    last = strategy[-1] if strategy else None
    shocks = (
        [
            ShockDTO(**{**asdict(o), "by_class": {c.value: v for c, v in o.by_class.items()}})
            for o in (apply_shock(last.by_class, last.cash, s) for s in SYNTHETIC_SHOCKS)
        ]
        if last
        else []
    )

    split = holdout_start(strategy[-1].day) if strategy else None
    known = {v.key: v for v in rule_variants()}
    variants: list[VariantDTO] = []
    for r in results:
        spec = known.get(r.key)
        if spec is None:
            continue
        pts = points[r.key]
        variants.append(
            VariantDTO(
                key=r.key,
                label=r.label,
                band_pct=spec.band_pct,
                rebalance=spec.rebalance,
                summary=r.summary,  # type: ignore[arg-type]
                selection=WindowOutcomeDTO(
                    **asdict(window_outcome(pts, pts[0].day + timedelta(days=1), split))  # type: ignore[arg-type]
                )
                if pts and split
                else WindowOutcomeDTO(covered=False),
                holdout=WindowOutcomeDTO(**asdict(window_outcome(pts, split, pts[-1].day)))
                if pts and split
                else WindowOutcomeDTO(covered=False),
            )
        )

    def dist(values: list[float | None]) -> DistributionDTO:
        return DistributionDTO(**asdict(distribution(values)))

    return RobustnessDTO(
        run_id=run.id,  # type: ignore[arg-type]
        status=run.status,
        series=[SeriesRefDTO(key=r.key, label=r.label) for r in series],
        crises=crises,
        shocks=shocks,
        variants=variants,
        annual_twr_distribution=dist([v.summary.annual_twr for v in variants]),
        selection_distribution=dist([v.selection.return_rate for v in variants]),
        holdout_distribution=dist([v.holdout.return_rate for v in variants]),
        holdout_start=split,
        trials_in_run=len(variants),
        trials_total=trials_total,
        warnings=sample_warnings(strategy, crisis_outcomes(strategy)) if strategy else [],
        validation=_variant_validation(results, points, variants, trials_total, run.seed),
    )


def _variant_validation(
    results: list[SimulationResult],
    points: dict[str, list[BacktestPoint]],
    variants: list[VariantDTO],
    trials_total: int,
    seed: int,
) -> VariantValidationDTO | None:
    report = variant_validation(
        points,
        [v.key for v in variants],
        reference_key=STRATEGY_KEY,
        cdi_key=f"{BENCHMARK_PREFIX}{CDI_KEY}",
        trials_total=trials_total,
        seed=seed,
    )
    if report is None:
        return None
    labels = {r.key: r.label for r in results}
    months = 12**0.5
    return VariantValidationDTO(
        best=report.best,
        best_label=labels.get(report.best, report.best),
        best_sharpe_annual=report.best_sharpe_annual,
        expected_max_sharpe_annual=round(report.deflated.expected_max * months, 4),
        deflated_probability=report.deflated.probability,
        trials=report.deflated.trials,
        observations=report.deflated.observations,
        pbo=report.overfitting.pbo if report.overfitting else None,
        pbo_combinations=report.overfitting.combinations if report.overfitting else 0,
        gate_probability=report.gate.probability if report.gate else None,
        passed=report.passed,
        verdict=report.verdict.replace(report.best, labels.get(report.best, report.best)),
        notes=report.notes,
    )


def build_candidates(run: SimulationRun, results: list[SimulationResult]) -> CandidatesDTO:
    summary = next((r.summary for r in results if r.key == SUMMARY_KEY), None)
    rows = [r for r in results if r.key.startswith(CANDIDATE_PREFIX)]
    if summary is None:
        return CandidatesDTO(run_id=run.id, status=run.status)  # type: ignore[arg-type]
    return CandidatesDTO(
        run_id=run.id,  # type: ignore[arg-type]
        status=run.status,
        horizon_months=summary.get("horizon_months", 0),
        paths=summary.get("paths", 0),
        base=summary.get("base"),
        candidates=[
            CandidateResultDTO(
                **r.summary["spec"], fit=r.summary["fit"], effect=r.summary["effect"]
            )
            for r in rows
        ],
        excluded=summary.get("excluded", []),
        tau_annual=summary.get("tau_annual", {}),
        tested=summary.get("tested", 0),
        evaluated=summary.get("evaluated", 0),
        weight_mode=summary.get("weight_mode", "NEXT_CONTRIBUTION"),
        rupture_loss=summary.get("rupture_loss", 0.55),
        sample_start=summary.get("sample_start"),
        sample_end=summary.get("sample_end"),
        calibration_run=summary.get("calibration_run"),
        warnings=summary.get("warnings", []),
    )
