"""Application service coordinating portfolio consolidation, contributions, and analytics."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from typing import Any

from fincontrol_core.analytics import (
    RiskReturnSummary,
    analyze_return_series,
    build_base100_curve,
    correlation_matrix,
    simple_returns,
    time_weighted_return,
)
from fincontrol_core.arca.allocation import ArcaTargets
from fincontrol_core.cerrado.scoring import CerradoEvaluation, evaluate
from fincontrol_core.domain.entities import ArcaTargetEntity, AssetEntity
from fincontrol_core.domain.enums import (
    ArcaClass,
    AssetType,
    IntraClassStrategy,
    Market,
)
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_core.market.models import Fundamentals, Quote
from fincontrol_core.portfolio.consolidation import (
    ConsolidatedPortfolioReport,
    ContributionPlan,
    ProjectionAssumptions,
    ValuedAssetPosition,
    consolidate_portfolio,
    plan_contribution,
)
from fincontrol_core.portfolio.curves import earliest_fixed_income_start, load_rate_curves
from fincontrol_core.ports.unit_of_work import AbstractUnitOfWork
from fincontrol_core.valuation import summarize_valuation


class PortfolioApplicationService:
    """Stateless application service operating on an AbstractUnitOfWork and MarketGateway."""

    def __init__(
        self,
        gateway: CachedMarketGateway,
        assumptions: ProjectionAssumptions | None = None,
    ) -> None:
        self.gateway = gateway
        self.assumptions = assumptions or ProjectionAssumptions()

    def load_arca_targets(
        self, uow: AbstractUnitOfWork
    ) -> tuple[ArcaTargets, dict[ArcaClass, IntraClassStrategy]]:
        """Load persisted ARCA target weights and intra-class strategies (or defaults)."""
        rows: list[ArcaTargetEntity] = uow.arca_targets.get_all()
        if not rows or len(rows) < len(ArcaClass):
            return ArcaTargets.default(), {c: IntraClassStrategy.CERRADO for c in ArcaClass}
        weights = {r.arca_class: float(r.target_pct) for r in rows}
        strategies = {r.arca_class: r.intra_class_strategy for r in rows}
        return ArcaTargets(weights), strategies

    def build_portfolio_report(
        self,
        uow: AbstractUnitOfWork,
        *,
        as_of_date: date | None = None,
        date_from: date | None = None,
    ) -> ConsolidatedPortfolioReport:
        """Fetch active assets, quotes, fundamentals, FX, and BCB curves to consolidate."""
        ref_date = as_of_date or date.today()
        assets = uow.assets.list_all(active_only=True)
        targets, intra_strategies = self.load_arca_targets(uow)

        quotes: dict[str, Quote] = {}
        fundamentals: dict[str, Fundamentals] = {}

        for asset in assets:
            if asset.market in (Market.MANUAL, Market.FIXED_INCOME_CURVE):
                continue
            q = self.gateway.get_quote(asset.ticker, asset_type=asset.asset_type)
            if q is not None:
                quotes[asset.ticker] = q
            fund = self.gateway.get_fundamentals(asset.ticker, asset_type=asset.asset_type)
            if fund is not None:
                fundamentals[asset.ticker] = fund

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
            targets=targets,
            quotes=quotes,
            fundamentals_by_ticker=fundamentals,
            intra_strategies=intra_strategies,
            usd_brl_rate=usd_brl,
            curves=curves,
            assumptions=self.assumptions,
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
        targets, _ = self.load_arca_targets(uow)
        return plan_contribution(
            report=report,
            targets=targets,
            amount_brl=amount_brl,
            strategy_override=strategy_override,
        )

    def analyze_single_asset(
        self, uow: AbstractUnitOfWork, asset: AssetEntity
    ) -> dict[str, Any]:
        """Produce deep fundamental, valuation, Cerrado, and risk/return analysis for an asset."""
        report = self.build_portfolio_report(uow)
        pos: ValuedAssetPosition | None = next(
            (p for p in report.positions if p.asset_id == asset.id), None
        )

        fund = self.gateway.get_fundamentals(asset.ticker, asset_type=asset.asset_type)
        cerrado_eval: CerradoEvaluation = evaluate(
            asset.asset_type,
            asset.cerrado_answers,
            fund,
            use_cerrado=asset.use_cerrado,
        )

        current_price = pos.current_unit_price if pos else (
            float(asset.manual_price) if asset.manual_price is not None else None
        )
        valuation_summary = summarize_valuation(current_price, fund)

        history = self.gateway.get_history(
            asset.ticker, range_period="1y", asset_type=asset.asset_type
        )
        prices = [p.close for p in history]
        asset_rets = simple_returns(prices)

        annual_cdi, annual_ipca = self.gateway.get_macro_rates()
        benchmark_symbol = "IFIX" if asset.asset_type == AssetType.FII else (
            "SP500"
            if asset.asset_type in (AssetType.STOCK_INTL, AssetType.ETF_INTL, AssetType.REIT)
            else "IBOV"
        )
        bench_pts = uow.market_series.list_series(benchmark_symbol)
        bench_rets = simple_returns([p.value for p in bench_pts])
        bench_map = {benchmark_symbol: bench_rets} if bench_rets else {}

        risk_summary: RiskReturnSummary = analyze_return_series(
            asset_rets,
            benchmark_returns_map=bench_map,
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
        """Compute portfolio TWR, risk metrics, correlation matrix, and Base-100 curves."""
        end = date_to or date.today()
        start = date_from or (end - timedelta(days=365))

        snapshots = uow.snapshots.list_range(date_from=start, date_to=end)
        port_returns = time_weighted_return(snapshots)
        dates = [s.snapshot_date for s in snapshots]

        # If fewer than 2 snapshots exist, synthesize a series from asset histories or report
        if len(port_returns) < 2:
            ibov_pts = uow.market_series.list_series("IBOV", date_from=start, date_to=end)
            if len(ibov_pts) >= 2:
                port_returns = simple_returns([p.value for p in ibov_pts])
                dates = [p.reference_date for p in ibov_pts]

        bench_returns_map: dict[str, list[float]] = {}
        curves: dict[str, list[dict[str, Any]]] = {}

        if dates and port_returns:
            curves["PORTFOLIO"] = build_base100_curve(dates, port_returns)

        for sym in ("IBOV", "IFIX", "SP500"):
            pts = uow.market_series.list_series(sym, date_from=start, date_to=end)
            if len(pts) >= 2:
                b_rets = simple_returns([p.value for p in pts])
                bench_returns_map[sym] = b_rets
                curves[sym] = build_base100_curve([p.reference_date for p in pts], b_rets)

        annual_cdi, annual_ipca = self.gateway.get_macro_rates()
        summary = analyze_return_series(
            port_returns,
            benchmark_returns_map=bench_returns_map,
            annual_cdi_rate=annual_cdi,
            annual_ipca_rate=annual_ipca,
        )

        corr_inputs: dict[str, list[float]] = {}
        if port_returns:
            corr_inputs["PORTFOLIO"] = port_returns
        for sym, b_rets in bench_returns_map.items():
            if b_rets:
                corr_inputs[sym] = b_rets
        corr_mat = correlation_matrix(corr_inputs) if corr_inputs else {}

        return {
            "summary": summary,
            "correlation_matrix": corr_mat,
            "curves": curves,
        }
