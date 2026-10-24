"""Application service coordinating portfolio consolidation, contributions, and analytics."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fincontrol_core.analytics import (
    RiskReturnSummary,
    align_to_base,
    analyze_return_series,
    build_base100_curve,
    correlation_matrix,
    dated_simple_returns,
    dated_time_weighted_returns,
)
from fincontrol_core.cerrado.scoring import (
    CerradoEvaluation,
    evaluate,
    evaluation_record,
    history_for_assets,
    record_if_changed,
)
from fincontrol_core.domain.entities import AssetEntity
from fincontrol_core.domain.enums import (
    AssetLifecycle,
    AssetType,
    IntraClassStrategy,
)
from fincontrol_core.fundamentals.history import HistoricalMetrics
from fincontrol_core.market.batch import fetch_market_data
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_core.policy import InvestmentPolicy, current_policy
from fincontrol_core.policy.lifecycle import asset_lifecycle
from fincontrol_core.portfolio.consolidation import (
    ConsolidatedPortfolioReport,
    ContributionPlan,
    ValuedAssetPosition,
    consolidate_portfolio,
    plan_contribution,
)
from fincontrol_core.portfolio.curves import earliest_fixed_income_start, load_rate_curves
from fincontrol_core.portfolio.fixed_income import RateCurves
from fincontrol_core.ports.unit_of_work import AbstractUnitOfWork
from fincontrol_core.valuation import summarize_valuation


def _restrict_to_account(assets: list[AssetEntity], account_id: int) -> list[AssetEntity]:
    restricted = []
    for asset in assets:
        transactions = tuple(t for t in asset.transactions if t.account_id == account_id)
        earnings = tuple(e for e in asset.earnings if e.account_id == account_id)
        if transactions or earnings:
            restricted.append(replace(asset, transactions=transactions, earnings=earnings))
    return restricted


ANALYTICS_OK = "OK"
ANALYTICS_INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
MIN_PORTFOLIO_RETURNS = 2
BENCHMARK_SYMBOLS = ("IBOV", "IFIX", "SP500")


class PortfolioApplicationService:
    """Stateless application service operating on an AbstractUnitOfWork and MarketGateway."""

    def __init__(
        self,
        gateway: CachedMarketGateway,
        *,
        fetch_workers: int = 8,
        fetch_timeout_seconds: float = 20.0,
    ) -> None:
        self.gateway = gateway
        self.fetch_workers = fetch_workers
        self.fetch_timeout_seconds = fetch_timeout_seconds

    def load_policy(self, uow: AbstractUnitOfWork) -> InvestmentPolicy:
        """Current investment policy (defaults when none was saved)."""
        return current_policy(uow.policies)

    def checklist_histories(
        self, uow: AbstractUnitOfWork, assets: list[AssetEntity]
    ) -> dict[str, HistoricalMetrics]:
        """Multi-year statement metrics feeding the historical checklist questions."""
        snapshots = uow.fundamentals.list_for_many([a.ticker for a in assets])
        return history_for_assets(assets, snapshots)

    def evaluate_checklist(self, uow: AbstractUnitOfWork, asset: AssetEntity) -> CerradoEvaluation:
        """Checklist of one asset with its current fundamentals and statement history."""
        fund = self.gateway.get_fundamentals(asset.ticker, asset_type=asset.asset_type)
        return evaluate(
            asset.profile,
            asset.cerrado_answers,
            fund,
            use_cerrado=asset.use_cerrado,
            history=self.checklist_histories(uow, [asset]).get(asset.ticker),
        )

    def record_checklist(
        self, uow: AbstractUnitOfWork, asset: AssetEntity, evaluation: CerradoEvaluation
    ) -> bool:
        """Store the evaluation when its outcome changed since the last record."""
        if asset.id is None:
            return False
        return record_if_changed(
            uow.checklists, evaluation_record(asset.id, evaluation, datetime.now(UTC))
        )

    def asset_lifecycles(
        self, uow: AbstractUnitOfWork, assets: list[AssetEntity]
    ) -> dict[int, tuple[AssetLifecycle, bool]]:
        """Lifecycle status and eligibility of each asset under the current policy."""
        policy = self.load_policy(uow).eligibility
        fundamentals = fetch_market_data(
            self.gateway,
            assets,
            include_quotes=False,
            max_workers=self.fetch_workers,
            timeout_seconds=self.fetch_timeout_seconds,
        ).fundamentals
        histories = self.checklist_histories(uow, assets)
        result: dict[int, tuple[AssetLifecycle, bool]] = {}
        for asset in assets:
            evaluation = evaluate(
                asset.profile,
                asset.cerrado_answers,
                fundamentals.get(asset.ticker),
                use_cerrado=asset.use_cerrado,
                history=histories.get(asset.ticker),
            )
            result[asset.id or 0] = asset_lifecycle(asset, evaluation, policy)
        return result

    def ledger_curves(
        self, uow: AbstractUnitOfWork, asset: AssetEntity, as_of: date
    ) -> RateCurves | None:
        """Rate curves needed to validate a fixed income ledger (None for market assets)."""
        if asset.fixed_income_term is None:
            return None
        annual_cdi, annual_ipca = self.gateway.get_macro_rates()
        return load_rate_curves(
            uow.market_series,
            date_from=earliest_fixed_income_start([asset]),
            date_to=as_of,
            annual_cdi_rate=annual_cdi,
            annual_ipca_rate=annual_ipca,
        )

    def build_portfolio_report(
        self,
        uow: AbstractUnitOfWork,
        *,
        as_of_date: date | None = None,
        date_from: date | None = None,
        account_id: int | None = None,
    ) -> ConsolidatedPortfolioReport:
        """Fetch active assets, quotes, fundamentals, FX, and BCB curves to consolidate.

        With `account_id`, only the trades and earnings of that account are consolidated.
        """
        ref_date = as_of_date or date.today()
        assets = uow.assets.list_all(active_only=True)
        if account_id is not None:
            assets = _restrict_to_account(assets, account_id)
        policy = self.load_policy(uow)

        market = fetch_market_data(
            self.gateway,
            assets,
            max_workers=self.fetch_workers,
            timeout_seconds=self.fetch_timeout_seconds,
        )
        quotes, fundamentals = market.quotes, market.fundamentals

        usd_brl = self.gateway.get_usd_brl_rate()
        annual_cdi, annual_ipca = self.gateway.get_macro_rates()

        curves = load_rate_curves(
            uow.market_series,
            date_from=earliest_fixed_income_start(assets),
            date_to=ref_date,
            annual_cdi_rate=annual_cdi,
            annual_ipca_rate=annual_ipca,
        )

        return consolidate_portfolio(
            assets=assets,
            targets=policy.arca.targets,
            quotes=quotes,
            fundamentals_by_ticker=fundamentals,
            history_by_ticker=self.checklist_histories(uow, assets),
            intra_strategies=policy.arca.strategies,
            bands=policy.arca.bands,
            eligibility=policy.eligibility,
            usd_brl_rate=usd_brl,
            curves=curves,
            assumptions=policy.valuation.projections,
            as_of_date=ref_date,
            date_from=date_from,
        )

    def simulate_contribution(
        self,
        uow: AbstractUnitOfWork,
        *,
        amount_brl: float,
        strategy_override: IntraClassStrategy | None = None,
    ) -> ContributionPlan:
        """Build a 2-level contribution plan from the current consolidated portfolio."""
        report = self.build_portfolio_report(uow)
        return plan_contribution(
            report=report,
            targets=self.load_policy(uow).arca.targets,
            amount_brl=amount_brl,
            strategy_override=strategy_override,
        )

    def analyze_single_asset(self, uow: AbstractUnitOfWork, asset: AssetEntity) -> dict[str, Any]:
        """Produce deep fundamental, valuation, Cerrado, and risk/return analysis for an asset."""
        report = self.build_portfolio_report(uow)
        pos: ValuedAssetPosition | None = next(
            (p for p in report.positions if p.asset_id == asset.id), None
        )

        fund = self.gateway.get_fundamentals(asset.ticker, asset_type=asset.asset_type)
        cerrado_eval = self.evaluate_checklist(uow, asset)

        current_price = (
            pos.current_unit_price
            if pos
            else (float(asset.manual_price) if asset.manual_price is not None else None)
        )
        valuation_policy = self.load_policy(uow).valuation
        valuation_summary = summarize_valuation(
            current_price,
            fund,
            bazin_required_yield=valuation_policy.bazin_required_yield,
            graham_multiplier=valuation_policy.graham_multiplier,
        )

        history = self.gateway.get_history(
            asset.ticker, range_period="1y", asset_type=asset.asset_type
        )
        asset_dates, asset_rets = dated_simple_returns(
            [p.date for p in history], [p.close for p in history]
        )

        annual_cdi, annual_ipca = self.gateway.get_macro_rates()
        benchmark_symbol = (
            "IFIX"
            if asset.asset_type == AssetType.FII
            else (
                "SP500"
                if asset.asset_type in (AssetType.STOCK_INTL, AssetType.ETF_INTL, AssetType.REIT)
                else "IBOV"
            )
        )
        bench_pts = (
            uow.market_series.list_series(
                benchmark_symbol, date_from=history[0].date, date_to=history[-1].date
            )
            if history
            else []
        )
        bench_dates, bench_rets = dated_simple_returns(
            [p.reference_date for p in bench_pts], [p.value for p in bench_pts]
        )

        risk_summary: RiskReturnSummary = analyze_return_series(
            asset_rets,
            benchmark_returns_map={benchmark_symbol: bench_rets} if bench_rets else {},
            benchmark_dates_map={benchmark_symbol: bench_dates},
            dates=asset_dates,
            annual_cdi_rate=annual_cdi,
            annual_ipca_rate=annual_ipca,
        )

        return {
            "position": pos,
            "fundamentals": fund.to_dict() if fund else None,
            "valuation": asdict(valuation_summary),
            "cerrado": cerrado_eval,
            "risk_return": risk_summary,
            "price_history": [p.to_dict() for p in history],
        }

    def build_portfolio_analytics(
        self,
        uow: AbstractUnitOfWork,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, Any]:
        """Compute portfolio TWR, risk metrics, correlation matrix, and Base-100 curves.

        Only the user's own snapshots feed the PORTFOLIO series. Without enough history the
        result carries status INSUFFICIENT_HISTORY and no portfolio curve (finding C-03).
        """
        end = date_to or date.today()
        start = date_from or (end - timedelta(days=365))

        snapshots = sorted(
            uow.snapshots.list_range(date_from=start, date_to=end),
            key=lambda s: s.snapshot_date,
        )
        port_dates, port_returns = dated_time_weighted_returns(snapshots)
        has_history = len(port_returns) >= MIN_PORTFOLIO_RETURNS
        if not has_history:
            port_dates, port_returns = [], []

        curves: dict[str, list[dict[str, Any]]] = {}
        if has_history:
            first_index = next(
                i for i, s in enumerate(snapshots) if s.snapshot_date == port_dates[0]
            )
            curves["PORTFOLIO"] = build_base100_curve(
                [snapshots[first_index - 1].snapshot_date, *port_dates], port_returns
            )

        bench_returns: dict[str, list[float]] = {}
        bench_dates: dict[str, list[date]] = {}
        for sym in BENCHMARK_SYMBOLS:
            pts = uow.market_series.list_series(sym, date_from=start, date_to=end)
            if len(pts) < 2:
                continue
            level_dates = [p.reference_date for p in pts]
            bench_dates[sym], bench_returns[sym] = dated_simple_returns(
                level_dates, [p.value for p in pts]
            )
            curves[sym] = build_base100_curve(level_dates, bench_returns[sym])

        annual_cdi, annual_ipca = self.gateway.get_macro_rates()
        summary = analyze_return_series(
            port_returns,
            benchmark_returns_map=bench_returns if has_history else {},
            benchmark_dates_map=bench_dates,
            dates=port_dates,
            annual_cdi_rate=annual_cdi,
            annual_ipca_rate=annual_ipca,
        )

        return {
            "status": ANALYTICS_OK if has_history else ANALYTICS_INSUFFICIENT_HISTORY,
            "available_points": len(snapshots),
            "summary": summary,
            "correlation_matrix": _aligned_correlation_matrix(
                port_dates, port_returns, bench_dates, bench_returns
            ),
            "curves": curves,
        }


def _aligned_correlation_matrix(
    port_dates: list[date],
    port_returns: list[float],
    bench_dates: dict[str, list[date]],
    bench_returns: dict[str, list[float]],
) -> dict[str, dict[str, float]]:
    """Correlations with every series re-expressed over the same base periods."""
    if port_returns:
        base_name, base_dates, base_returns = "PORTFOLIO", port_dates, port_returns
    elif bench_returns:
        base_name = next(iter(bench_returns))
        base_dates, base_returns = bench_dates[base_name], bench_returns[base_name]
    else:
        return {}
    series: dict[str, list[float | None]] = {base_name: list(base_returns)}
    for sym, rets in bench_returns.items():
        if sym != base_name:
            series[sym] = align_to_base(base_dates, bench_dates[sym], rets)
    return correlation_matrix(series)
