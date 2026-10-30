"""Application service for the portfolio module.

Scope: consolidated portfolio, ARCA allocation, snapshots and analytics.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

from domain.assets.services.cerrado import (
    AnswerFreshness,
    CerradoEvaluation,
    answer_freshness,
    evaluate,
    evaluation_record,
    history_for_assets,
    record_if_changed,
)
from domain.assets.services.history import HistoricalMetrics, historical_metrics
from domain.assets.services.questions import STATEMENT_PROFILES
from domain.assets.services.ratings import rate_indicators
from domain.assets.services.valuation import AssetValuation, value_asset
from domain.market.entities import Fundamentals
from domain.market.services.price_chart import PriceChart, price_chart
from domain.market.services.treasury_prices import (
    RATE_SUFFIX,
    asset_price_symbol,
    bond_family,
    price_symbol,
)
from domain.policy.services.allocation import BAND_BELOW
from domain.policy.services.lifecycle import asset_lifecycle
from domain.policy.services.policy import InvestmentPolicy, current_policy
from domain.portfolio.services.analytics import (
    RiskReturnSummary,
    accumulate_daily_rate_curve,
    align_to_base,
    analyze_return_series,
    build_base100_curve,
    correlation_matrix,
    dated_simple_returns,
    dated_time_weighted_returns,
)
from domain.portfolio.services.consolidation import (
    ConsolidatedPortfolioReport,
    ContributionPlan,
    ValuedAssetPosition,
    consolidate_portfolio,
    plan_contribution,
)
from domain.portfolio.services.curves import earliest_fixed_income_start, load_rate_curves
from domain.portfolio.services.earnings_agenda import EarningsAgenda, build_agenda
from domain.portfolio.services.fixed_income import RateCurves
from domain.portfolio.services.health import HealthInputs, HealthReport, diagnose
from domain.portfolio.services.health_inputs import (
    asset_return_grid,
    bracket_lots,
    build_holdings,
    cdi_returns,
    clean_histories,
    drop_impossible_periods,
    policy_benchmark,
)
from domain.portfolio.services.mark_to_market import (
    EarlySaleRules,
    MarketQuoteTD,
    TreasuryMarketValuation,
    evaluate_mark_to_market,
    quantity_lots,
)
from domain.portfolio.services.risk_metrics import class_time_weighted_returns, days_out_of_band
from domain.shared.entities import AssetEntity, CatalogInstrument
from domain.shared.enums import (
    ArcaClass,
    AssetLifecycle,
    AssetType,
    IntraClassStrategy,
)
from domain.shared.unit_of_work import AbstractUnitOfWork
from domain.tax.entities import TaxRuleBook
from domain.tax.services.rules import rule_book
from domain.tax.services.status import asset_tax_status
from infra.providers.gateway import CachedMarketGateway
from infra.providers.stored import (
    stored_distributions,
    stored_fundamentals,
    stored_histories,
    stored_history,
    stored_macro_rates,
    stored_market_data,
    stored_usd_brl,
)


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


AGENDA_TYPES = frozenset({AssetType.STOCK_BR, AssetType.BDR, AssetType.FII})


HEALTH_PORTFOLIO_YEARS = 3
HEALTH_HISTORY_RANGE = "2y"
HEALTH_HISTORY_DAYS = 730


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

    def evaluate_with(
        self,
        asset: AssetEntity,
        fundamentals: Fundamentals | None,
        history: HistoricalMetrics | None,
        freshness: AnswerFreshness | None = None,
    ) -> CerradoEvaluation:
        """Checklist of an asset with data already loaded by the caller."""
        return evaluate(
            asset.profile,
            asset.cerrado_answers,
            fundamentals,
            use_cerrado=asset.use_cerrado,
            history=history,
            freshness=freshness,
        )

    def checklist_freshness(
        self, uow: AbstractUnitOfWork, assets: list[AssetEntity], as_of: date | None = None
    ) -> dict[str, AnswerFreshness]:
        """Validity rules of the manual answers of each asset (policy + newest statement)."""
        policy = self.load_policy(uow).eligibility
        snapshots = uow.fundamentals.list_for_many([a.ticker for a in assets])
        day = as_of or date.today()
        return {
            a.ticker: answer_freshness(policy, day, snapshots.get(a.ticker, [])) for a in assets
        }

    def checklist_histories(
        self, uow: AbstractUnitOfWork, assets: list[AssetEntity]
    ) -> dict[str, HistoricalMetrics]:
        """Multi-year statement metrics feeding the historical checklist questions."""
        snapshots = uow.fundamentals.list_for_many([a.ticker for a in assets])
        return history_for_assets(assets, snapshots)

    def evaluate_checklist(self, uow: AbstractUnitOfWork, asset: AssetEntity) -> CerradoEvaluation:
        """Checklist of one asset with its current fundamentals and statement history."""
        fund = stored_fundamentals(uow, self.gateway, asset)
        return evaluate(
            asset.profile,
            asset.cerrado_answers,
            fund,
            use_cerrado=asset.use_cerrado,
            history=self.checklist_histories(uow, [asset]).get(asset.ticker),
            freshness=self.checklist_freshness(uow, [asset]).get(asset.ticker),
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
        fundamentals = stored_market_data(
            uow,
            self.gateway,
            assets,
            include_quotes=False,
            max_workers=self.fetch_workers,
            timeout_seconds=self.fetch_timeout_seconds,
        ).fundamentals
        histories = self.checklist_histories(uow, assets)
        freshness = self.checklist_freshness(uow, assets)
        result: dict[int, tuple[AssetLifecycle, bool]] = {}
        for asset in assets:
            evaluation = evaluate(
                asset.profile,
                asset.cerrado_answers,
                fundamentals.get(asset.ticker),
                use_cerrado=asset.use_cerrado,
                history=histories.get(asset.ticker),
                freshness=freshness.get(asset.ticker),
            )
            result[asset.id or 0] = asset_lifecycle(asset, evaluation, policy)
        return result

    def tax_rules(self, uow: AbstractUnitOfWork) -> TaxRuleBook:
        """Registered tax rules (the built-in registry completes missing regimes)."""
        return rule_book(uow.tax_rules.list_all())

    def ledger_curves(
        self, uow: AbstractUnitOfWork, asset: AssetEntity, as_of: date
    ) -> RateCurves | None:
        """Rate curves needed to validate a fixed income ledger (None for market assets)."""
        if asset.fixed_income_term is None:
            return None
        annual_cdi, annual_ipca = stored_macro_rates(uow, self.gateway)
        return load_rate_curves(
            uow.market_series,
            date_from=earliest_fixed_income_start([asset]),
            date_to=as_of,
            annual_cdi_rate=annual_cdi,
            annual_ipca_rate=annual_ipca,
        )

    def treasury_quote(
        self, uow: AbstractUnitOfWork, asset: AssetEntity, as_of: date
    ) -> tuple[MarketQuoteTD | None, list[tuple[date, float]]]:
        """Latest redemption price up to `as_of` and the stored price history of a bond.

        Without a stored series, today's daily catalog is used (when it is about `as_of`).
        """
        symbol = asset_price_symbol(asset)
        if symbol is None:
            return None, []
        points = uow.market_series.list_series(symbol, date_to=as_of)
        history = [(p.reference_date, p.value) for p in points]
        if points:
            last = points[-1]
            rates = uow.market_series.list_series(
                f"{symbol}:{RATE_SUFFIX}", date_from=last.reference_date, date_to=as_of
            )
            rate = rates[-1].value if rates else None
            return MarketQuoteTD(last.value, last.reference_date, rate), history
        for bond in uow.treasury_catalog.list_all():
            if price_symbol(bond_family(bond.bond_type), bond.maturity_date) != symbol:
                continue
            if bond.sell_price and bond.base_date and bond.base_date <= as_of:
                return MarketQuoteTD(bond.sell_price, bond.base_date, bond.sell_rate), history
        return None, history

    def treasury_market_prices(
        self, uow: AbstractUnitOfWork, assets: list[AssetEntity], as_of: date
    ) -> dict[str, float]:
        """Redemption price of each Treasury asset on `as_of` (assets without one are left out)."""
        prices: dict[str, float] = {}
        for asset in assets:
            if asset.asset_type != AssetType.TREASURY:
                continue
            quote, _ = self.treasury_quote(uow, asset, as_of)
            if quote is not None:
                prices[asset.ticker] = quote.price
        return prices

    def treasury_market(
        self,
        uow: AbstractUnitOfWork,
        *,
        as_of_date: date | None = None,
        asset_id: int | None = None,
        with_history: bool = False,
    ) -> list[TreasuryMarketValuation]:
        """Curve versus market of the open Treasury positions, with the early-sale signals."""
        as_of = as_of_date or date.today()
        assets = [
            a
            for a in uow.assets.list_all(active_only=True)
            if a.asset_type == AssetType.TREASURY
            and a.fixed_income_term is not None
            and (asset_id is None or a.id == asset_id)
            and sum(q.quantity for q in quantity_lots(a.transactions, as_of)) > 0
        ]
        if not assets:
            return []
        policy = self.load_policy(uow).valuation
        annual_cdi, annual_ipca = stored_macro_rates(uow, self.gateway)
        curves = load_rate_curves(
            uow.market_series,
            date_from=earliest_fixed_income_start(assets),
            date_to=as_of,
            annual_cdi_rate=annual_cdi,
            annual_ipca_rate=annual_ipca,
        )
        rules = self.tax_rules(uow)
        reference = (
            policy.projections.projected_cdi_rate
            if policy.projections.projected_cdi_rate is not None
            else annual_cdi
        )
        thresholds = EarlySaleRules(
            min_excess_rate=policy.early_sale_min_excess_rate,
            min_reinvest_spread=policy.early_sale_min_reinvest_spread,
        )
        results: list[TreasuryMarketValuation] = []
        for asset in assets:
            quote, history = self.treasury_quote(uow, asset, as_of)
            results.append(
                evaluate_mark_to_market(
                    asset,
                    as_of,
                    quote=quote,
                    curves=curves,
                    rules=rules,
                    reference_rate=reference,
                    early_sale=thresholds,
                    price_history=history if with_history else (),
                )
            )
        return results

    def earnings_agenda(
        self, uow: AbstractUnitOfWork, *, as_of_date: date | None = None
    ) -> EarningsAgenda:
        """Declared distributions of the held and followed B3 stocks, BDRs and FIIs."""
        as_of = as_of_date or date.today()
        assets = [a for a in uow.assets.list_all(active_only=True) if a.asset_type in AGENDA_TYPES]
        declared = stored_distributions(
            uow,
            self.gateway,
            assets,
            max_workers=self.fetch_workers,
            timeout_seconds=self.fetch_timeout_seconds,
        )
        return build_agenda(
            assets,
            {ticker: d.cash for ticker, d in declared.items()},
            as_of=as_of,
            rules=self.tax_rules(uow),
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

        market = stored_market_data(
            uow,
            self.gateway,
            assets,
            max_workers=self.fetch_workers,
            timeout_seconds=self.fetch_timeout_seconds,
        )
        quotes, fundamentals = market.quotes, market.fundamentals

        usd_brl = stored_usd_brl(uow, self.gateway)
        annual_cdi, annual_ipca = stored_macro_rates(uow, self.gateway)

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
            tax_rules=self.tax_rules(uow),
            treasury_market_prices=(
                self.treasury_market_prices(uow, assets, ref_date)
                if policy.valuation.treasury_mark_to_market
                else None
            ),
            statement_seen_at={
                ticker: f.statement_seen_at
                for ticker, f in self.checklist_freshness(uow, assets, ref_date).items()
            },
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
        arca = self.load_policy(uow).arca
        return plan_contribution(
            report=report,
            targets=arca.targets,
            amount_brl=amount_brl,
            strategy_override=strategy_override,
            class_strategies=arca.strategies,
        )

    def analyze_single_asset(self, uow: AbstractUnitOfWork, asset: AssetEntity) -> dict[str, Any]:
        """Produce deep fundamental, valuation, Cerrado, and risk/return analysis for an asset."""
        report = self.build_portfolio_report(uow)
        pos: ValuedAssetPosition | None = next(
            (p for p in report.positions if p.asset_id == asset.id), None
        )

        fund = stored_fundamentals(uow, self.gateway, asset)
        snapshots = uow.fundamentals.list_for(asset.ticker)
        metrics = historical_metrics(snapshots) if snapshots else None
        checklist = evaluate(
            asset.profile,
            asset.cerrado_answers,
            fund,
            use_cerrado=asset.use_cerrado,
            history=metrics if asset.profile in STATEMENT_PROFILES else None,
            freshness=answer_freshness(self.load_policy(uow).eligibility, date.today(), snapshots),
        )

        current_price = (
            pos.current_unit_price
            if pos
            else (float(asset.manual_price) if asset.manual_price is not None else None)
        )
        valuation = value_asset(
            asset.profile,
            current_price,
            fund,
            self.load_policy(uow).valuation,
            statements=snapshots,
        )

        history = stored_history(uow, self.gateway, asset, "1y")
        asset_dates, asset_rets = dated_simple_returns(
            [p.date for p in history], [p.close for p in history]
        )

        annual_cdi, annual_ipca = stored_macro_rates(uow, self.gateway)
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
            "fundamental_history": snapshots,
            "historical_metrics": metrics,
            "valuation": valuation,
            "checklist": checklist,
            "checklist_history": uow.checklists.evaluation_history(asset.id or 0),
            "answer_history": uow.checklists.answer_history(asset.id or 0),
            "risk_return": risk_summary,
            "benchmark": benchmark_symbol,
            "price_history": [p.to_dict() for p in history],
            "indicator_ratings": rate_indicators(
                asset.profile, fund, metrics, self.load_policy(uow).valuation
            ),
        }

    def price_chart(
        self, uow: AbstractUnitOfWork, asset: AssetEntity, range_period: str
    ) -> PriceChart:
        """Closes of one period for the asset chart (stored history), cleaned and thinned."""
        history = stored_history(uow, self.gateway, asset, range_period)
        return price_chart(range_period, history)

    def catalog_fundamentals(
        self, uow: AbstractUnitOfWork, instruments: list[CatalogInstrument]
    ) -> dict[str, Fundamentals]:
        """Indicators of catalog instruments from the database; the missing ones are saved."""
        probes = [
            AssetEntity(ticker=i.ticker, name=i.name, asset_type=i.asset_type)
            for i in instruments
            if i.asset_type is not None
        ]
        return stored_market_data(
            uow,
            self.gateway,
            probes,
            include_quotes=False,
            max_workers=self.fetch_workers,
            timeout_seconds=self.fetch_timeout_seconds,
            persist=True,
        ).fundamentals

    def classes_below_band(self, uow: AbstractUnitOfWork) -> frozenset[ArcaClass]:
        """ARCA classes whose weight is below the tolerance band (contribution priority)."""
        report = self.build_portfolio_report(uow)
        return frozenset(a.arca_class for a in report.allocations if a.band_status == BAND_BELOW)

    def value(
        self,
        uow: AbstractUnitOfWork,
        asset: AssetEntity,
        price: float | None,
        fundamentals: Fundamentals | None,
    ) -> AssetValuation:
        snapshots = uow.fundamentals.list_for(asset.ticker)
        return value_asset(
            asset.profile,
            price,
            fundamentals,
            self.load_policy(uow).valuation,
            statements=snapshots,
        )

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
        port_dates, port_returns = dated_time_weighted_returns(snapshots, purchases_at_start=True)
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

        cdi = uow.market_series.list_series("CDI", date_from=start, date_to=end)
        if len(cdi) >= 2:
            curves["CDI"] = accumulate_daily_rate_curve(
                [p.reference_date for p in cdi], [p.value for p in cdi]
            )

        annual_cdi, annual_ipca = stored_macro_rates(uow, self.gateway)
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

    def build_portfolio_health(
        self, uow: AbstractUnitOfWork, *, as_of_date: date | None = None
    ) -> HealthReport:
        """Seven-pillar health diagnosis of the consolidated portfolio (Phase 29)."""
        as_of = as_of_date or date.today()
        policy = self.load_policy(uow)
        report = self.build_portfolio_report(uow, as_of_date=as_of)
        assets = {a.id: a for a in uow.assets.list_all(active_only=True) if a.id is not None}
        held = [assets[p.asset_id] for p in report.positions if p.asset_id in assets]

        fundamentals = stored_market_data(
            uow,
            self.gateway,
            held,
            include_quotes=False,
            max_workers=self.fetch_workers,
            timeout_seconds=self.fetch_timeout_seconds,
        ).fundamentals
        statements = uow.fundamentals.list_for_many([a.ticker for a in held])
        holdings = build_holdings(
            report.positions,
            assets,
            as_of=as_of,
            fundamentals=fundamentals,
            statements=statements,
        )

        history_start = as_of - timedelta(days=HEALTH_HISTORY_DAYS)
        histories, asset_notes = clean_histories(
            stored_histories(
                uow,
                self.gateway,
                [assets[p.asset_id] for p in report.positions if p.asset_id in assets],
                range_period=HEALTH_HISTORY_RANGE,
                max_workers=self.fetch_workers,
                timeout_seconds=self.fetch_timeout_seconds,
            )
        )
        portfolio_start = as_of - timedelta(days=365 * HEALTH_PORTFOLIO_YEARS)
        cdi = cdi_returns(
            uow.market_series.list_series(
                "CDI", date_from=min(history_start, portfolio_start), date_to=as_of
            )
        )
        asset_dates, asset_returns = asset_return_grid(
            holdings, histories, cdi, date_from=history_start
        )

        snapshots = sorted(
            uow.snapshots.list_range(date_from=portfolio_start, date_to=as_of),
            key=lambda s: s.snapshot_date,
        )
        port_dates, port_returns, portfolio_notes = drop_impossible_periods(
            *dated_time_weighted_returns(snapshots, purchases_at_start=True)
        )
        index_returns = {
            sym: _dated_levels(
                uow.market_series.list_series(sym, date_from=portfolio_start, date_to=as_of)
            )
            for sym in BENCHMARK_SYMBOLS
        }
        index_returns["CDI"] = cdi
        targets = {c: p.target_pct for c, p in policy.arca.classes.items()}

        annual_cdi, annual_ipca = stored_macro_rates(uow, self.gateway)
        fixed_income = [a for a in held if a.fixed_income_term is not None]
        tax_statuses = []
        if fixed_income:
            curves = load_rate_curves(
                uow.market_series,
                date_from=earliest_fixed_income_start(fixed_income),
                date_to=as_of,
                annual_cdi_rate=annual_cdi,
                annual_ipca_rate=annual_ipca,
            )
            rules = self.tax_rules(uow)
            tax_statuses = [
                asset_tax_status(a, as_of, curves=curves, rules=rules) for a in fixed_income
            ]

        inputs = HealthInputs(
            as_of=as_of,
            holdings=holdings,
            allocations=report.allocations,
            earnings_12m_brl=report.total_earnings_12m_brl,
            portfolio_dates=port_dates,
            portfolio_returns=port_returns,
            benchmark_returns=policy_benchmark(port_dates, targets, index_returns),
            cdi_returns=align_to_base(port_dates, cdi[0], cdi[1]) if port_dates else [],
            asset_dates=asset_dates,
            asset_returns=asset_returns,
            asset_data_notes=asset_notes,
            portfolio_data_notes=portfolio_notes,
            class_returns={
                ArcaClass(k): v
                for k, v in class_time_weighted_returns(snapshots).items()
                if k in {c.value for c in ArcaClass}
            },
            class_out_of_band_days={
                ArcaClass(k): v
                for k, v in days_out_of_band(
                    snapshots, {c.value: b for c, b in policy.arca.bands.items()}, as_of
                ).items()
            },
            bracket_lots=bracket_lots(tax_statuses),
            annual_cdi_rate=annual_cdi,
        )
        return diagnose(inputs, policy.health)


def _dated_levels(points: list[Any]) -> tuple[list[date], list[float]]:
    return dated_simple_returns([p.reference_date for p in points], [p.value for p in points])


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
