"""Domain entity to DTO serializers for the portfolio module.

Scope: consolidated portfolio, ARCA allocation, snapshots and analytics.
"""

from __future__ import annotations

from dataclasses import asdict

from controllers.portfolio.responses import (
    AssetContributionOrderDTO,
    BenchmarkComparisonDTO,
    ClassAllocationDTO,
    ContributionPlanResponseDTO,
    EarningsAgendaDTO,
    FixedIncomeValuationDTO,
    PortfolioHealthDTO,
    PortfolioReportResponseDTO,
    RiskReturnSummaryDTO,
    TreasuryMarketDTO,
    ValuedPositionDTO,
)
from controllers.shared.serializers import to_cerrado_dto
from domain.portfolio.services.analytics import RiskReturnSummary
from domain.portfolio.services.consolidation import (
    ConsolidatedPortfolioReport,
    ContributionPlan,
    ValuedAssetPosition,
)
from domain.portfolio.services.earnings_agenda import EarningsAgenda
from domain.portfolio.services.health import HealthReport
from domain.portfolio.services.mark_to_market import TreasuryMarketValuation


def to_valued_position_dto(pos: ValuedAssetPosition) -> ValuedPositionDTO:
    fi_dto = (
        FixedIncomeValuationDTO(**asdict(pos.fixed_income_details))
        if pos.fixed_income_details is not None
        else None
    )
    return ValuedPositionDTO(
        asset_id=pos.asset_id,
        ticker=pos.ticker,
        name=pos.name,
        asset_type=pos.asset_type,
        arca_class=pos.arca_class,
        currency=pos.currency,
        quantity=pos.quantity,
        average_price=pos.average_price,
        current_unit_price=pos.current_unit_price,
        fx_rate=pos.fx_rate,
        price_freshness=pos.price_freshness,
        invested_value_brl=pos.invested_value_brl,
        gross_current_value_brl=pos.gross_current_value_brl,
        estimated_tax_brl=pos.estimated_tax_brl,
        current_value_brl=pos.current_value_brl,
        unrealized_pnl_brl=pos.unrealized_pnl_brl,
        unrealized_pnl_pct=pos.unrealized_pnl_pct,
        realized_pnl_brl=pos.realized_pnl_brl,
        received_earnings_brl=pos.received_earnings_brl,
        earnings_12m_brl=pos.earnings_12m_brl,
        yield_on_cost_pct=pos.yield_on_cost_pct,
        estimated_yield_to_date_brl=pos.estimated_yield_to_date_brl,
        estimated_yield_to_date_pct=pos.estimated_yield_to_date_pct,
        estimated_yield_basis=pos.estimated_yield_basis,
        projected_12m_yield_brl=pos.projected_12m_yield_brl,
        consolidated_pnl_brl=pos.consolidated_pnl_brl,
        consolidated_return_pct=pos.consolidated_return_pct,
        cerrado_evaluation=to_cerrado_dto(pos.cerrado_evaluation),
        class_target_weight_pct=pos.class_target_weight_pct,
        class_current_weight_pct=pos.class_current_weight_pct,
        fixed_income_details=fi_dto,
        fx_pnl_brl=pos.fx_pnl_brl,
        custom_class_weight=pos.custom_class_weight,
        ledger_status=pos.ledger_status,
        ledger_message=pos.ledger_message,
        purpose=pos.purpose,
        lifecycle_status=pos.lifecycle_status,
        eligible=pos.eligible,
    )


def to_portfolio_report_dto(report: ConsolidatedPortfolioReport) -> PortfolioReportResponseDTO:
    return PortfolioReportResponseDTO(
        as_of_date=report.as_of_date,
        total_invested_brl=report.total_invested_brl,
        total_gross_value_brl=report.total_gross_value_brl,
        total_estimated_tax_brl=report.total_estimated_tax_brl,
        total_current_value_brl=report.total_current_value_brl,
        total_unrealized_pnl_brl=report.total_unrealized_pnl_brl,
        total_unrealized_pnl_pct=report.total_unrealized_pnl_pct,
        total_realized_pnl_brl=report.total_realized_pnl_brl,
        total_received_earnings_brl=report.total_received_earnings_brl,
        total_earnings_12m_brl=report.total_earnings_12m_brl,
        portfolio_yield_on_cost_pct=report.portfolio_yield_on_cost_pct,
        total_estimated_yield_to_date_brl=report.total_estimated_yield_to_date_brl,
        total_projected_12m_yield_brl=report.total_projected_12m_yield_brl,
        total_projected_12m_value_brl=report.total_projected_12m_value_brl,
        total_consolidated_pnl_brl=report.total_consolidated_pnl_brl,
        total_consolidated_return_pct=report.total_consolidated_return_pct,
        allocations=[ClassAllocationDTO(**asdict(a)) for a in report.allocations],
        positions=[to_valued_position_dto(p) for p in report.positions],
        earnings_by_month=dict(report.earnings_by_month),
        total_fx_pnl_brl=report.total_fx_pnl_brl,
        projection_assumptions=dict(report.projection_assumptions),
        value_by_purpose_brl=dict(report.value_by_purpose_brl),
    )


def to_contribution_plan_dto(plan: ContributionPlan) -> ContributionPlanResponseDTO:
    return ContributionPlanResponseDTO(
        contribution_amount_brl=plan.contribution_amount_brl,
        executed_total_brl=plan.executed_total_brl,
        unallocated_cash_brl=plan.unallocated_cash_brl,
        by_class_allocated_brl=dict(plan.by_class_allocated_brl),
        orders=[
            AssetContributionOrderDTO(
                asset_id=o.asset_id,
                ticker=o.ticker,
                name=o.name,
                asset_type=o.asset_type,
                arca_class=o.arca_class,
                cerrado_score=o.cerrado_score,
                cerrado_recommendation=o.cerrado_recommendation.value,
                intra_class_target_weight_pct=o.intra_class_target_weight_pct,
                allocated_amount_brl=o.allocated_amount_brl,
                unit_price_brl=o.unit_price_brl,
                recommended_quantity=o.recommended_quantity,
                executed_amount_brl=o.executed_amount_brl,
                projected_value_brl=o.projected_value_brl,
            )
            for o in plan.orders
        ],
        projected_allocations=[ClassAllocationDTO(**asdict(a)) for a in plan.projected_allocations],
    )


def to_risk_summary_dto(summary: RiskReturnSummary) -> RiskReturnSummaryDTO:
    return RiskReturnSummaryDTO(
        observations=summary.observations,
        cumulative_return=summary.cumulative_return,
        cagr=summary.cagr,
        real_return_vs_ipca=summary.real_return_vs_ipca,
        annualized_volatility=summary.annualized_volatility,
        sharpe_ratio=summary.sharpe_ratio,
        sortino_ratio=summary.sortino_ratio,
        max_drawdown=summary.max_drawdown,
        calmar_ratio=summary.calmar_ratio,
        var_95_historical=summary.var_95_historical,
        var_95_parametric=summary.var_95_parametric,
        cvar_95=summary.cvar_95,
        benchmarks=[BenchmarkComparisonDTO(**asdict(b)) for b in summary.benchmarks],
        drawdown_curve=list(summary.drawdown_curve),
    )


def to_portfolio_health_dto(report: HealthReport) -> PortfolioHealthDTO:
    return PortfolioHealthDTO.model_validate(asdict(report))


def to_treasury_market_dto(valuation: TreasuryMarketValuation) -> TreasuryMarketDTO:
    return TreasuryMarketDTO.model_validate(asdict(valuation))


def to_earnings_agenda_dto(agenda: EarningsAgenda) -> EarningsAgendaDTO:
    return EarningsAgendaDTO.model_validate(asdict(agenda))
