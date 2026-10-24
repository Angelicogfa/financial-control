"""Pure DTO serialization helpers converting Domain Entities and Reports into API DTOs."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fincontrol_core.analytics import RiskReturnSummary
from fincontrol_core.cerrado.scoring import CerradoEvaluation
from fincontrol_core.domain.entities import (
    AssetEntity,
    EarningEntity,
    TransactionEntity,
)
from fincontrol_core.domain.enums import ArcaClass
from fincontrol_core.domain.pagination import PageMeta
from fincontrol_core.portfolio.consolidation import (
    ConsolidatedPortfolioReport,
    ContributionPlan,
    ValuedAssetPosition,
)

from fincontrol_api.schemas import (
    AssetContributionOrderDTO,
    AssetResponseDTO,
    BenchmarkComparisonDTO,
    CerradoEvaluationDTO,
    ClassAllocationDTO,
    ContributionPlanResponseDTO,
    EarningResponseDTO,
    EvaluatedAnswerDTO,
    FixedIncomeTermPayload,
    FixedIncomeValuationDTO,
    PageMetaDTO,
    PortfolioReportResponseDTO,
    RiskReturnSummaryDTO,
    TransactionResponseDTO,
    ValuedPositionDTO,
)


def to_page_meta_dto(meta: PageMeta) -> PageMetaDTO:
    return PageMetaDTO(
        page=meta.page,
        page_size=meta.page_size,
        total_items=meta.total_items,
        total_pages=meta.total_pages,
        has_next=meta.has_next,
        has_prev=meta.has_prev,
        sort_by=meta.sort_by,
        sort_order=meta.sort_order,
    )


def to_asset_dto(entity: AssetEntity) -> AssetResponseDTO:
    term_dto = None
    if entity.fixed_income_term is not None:
        t = entity.fixed_income_term
        term_dto = FixedIncomeTermPayload(
            instrument_kind=t.instrument_kind,
            indexer=t.indexer,
            contracted_rate=t.contracted_rate,
            issue_date=t.issue_date,
            maturity_date=t.maturity_date,
            tax_exempt=t.tax_exempt,
            liquidity=t.liquidity,
            issuer=t.issuer,
        )
    return AssetResponseDTO(
        id=entity.id or 0,
        ticker=entity.ticker,
        name=entity.name,
        asset_type=entity.asset_type,
        arca_class=entity.arca_class or ArcaClass.ACOES,
        currency=entity.currency or "BRL",
        manual_price=entity.manual_price,
        custom_class_weight=entity.custom_class_weight,
        use_cerrado=entity.use_cerrado,
        cerrado_answers=dict(entity.cerrado_answers),
        is_active=entity.is_active,
        notes=entity.notes,
        purpose=entity.purpose,
        fixed_income_term=term_dto,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def to_transaction_dto(
    entity: TransactionEntity, ticker: str | None = None
) -> TransactionResponseDTO:
    qty = float(entity.quantity)
    price = float(entity.unit_price)
    fees = float(entity.fees)
    fx = float(entity.fx_rate)
    total_brl = round((qty * price + fees) * fx, 2)
    return TransactionResponseDTO(
        id=entity.id or 0,
        asset_id=entity.asset_id,
        ticker=ticker,
        kind=entity.kind,
        trade_date=entity.trade_date,
        quantity=qty,
        unit_price=price,
        fees=fees,
        fx_rate=fx,
        total_brl=total_brl,
        notes=entity.notes,
        account_id=entity.account_id,
        created_at=entity.created_at,
    )


def to_earning_dto(entity: EarningEntity, ticker: str | None = None) -> EarningResponseDTO:
    gross = float(entity.gross_amount)
    tax = float(entity.withholding_tax)
    net = float(entity.net_amount) if entity.net_amount is not None else (gross - tax)
    fx = float(entity.fx_rate)
    return EarningResponseDTO(
        id=entity.id or 0,
        asset_id=entity.asset_id,
        ticker=ticker,
        kind=entity.kind,
        payment_date=entity.payment_date,
        ex_date=entity.ex_date,
        gross_amount=gross,
        withholding_tax=tax,
        net_amount=net,
        fx_rate=fx,
        net_amount_brl=round(net * fx, 2),
        notes=entity.notes,
        account_id=entity.account_id,
        created_at=entity.created_at,
    )


def to_cerrado_dto(eval_obj: CerradoEvaluation) -> CerradoEvaluationDTO:
    return CerradoEvaluationDTO(
        asset_type=eval_obj.asset_type,
        use_cerrado=eval_obj.use_cerrado,
        score=eval_obj.score,
        max_score=eval_obj.max_score,
        answered=eval_obj.answered,
        pending=eval_obj.pending,
        recommendation=eval_obj.recommendation.value,
        answers=[
            EvaluatedAnswerDTO(
                question_id=a.question_id,
                text=a.text,
                category=a.category,
                hint=a.hint,
                answer=a.answer,
                source=a.source.value,
                automatable=a.automatable,
            )
            for a in eval_obj.answers
        ],
    )


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


def to_asset_analysis_dto(asset: AssetEntity, raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset": to_asset_dto(asset),
        "position": (
            to_valued_position_dto(raw["position"]) if raw["position"] is not None else None
        ),
        "fundamentals": raw["fundamentals"],
        "valuation": raw["valuation"],
        "cerrado": to_cerrado_dto(raw["cerrado"]),
        "risk_return": to_risk_summary_dto(raw["risk_return"]),
        "price_history": raw["price_history"],
    }
