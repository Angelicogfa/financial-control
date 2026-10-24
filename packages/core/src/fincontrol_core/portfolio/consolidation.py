"""Portfolio valuation, yield estimation, P/L consolidation, and 2-level contribution planner."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from fincontrol_core.arca.allocation import (
    ArcaTargets,
    ClassAllocation,
    compute_allocation,
    distribute_by_targets,
)
from fincontrol_core.cerrado.scoring import (
    CerradoEvaluation,
    Recommendation,
    evaluate,
    resolve_intra_class_weights,
)
from fincontrol_core.domain.entities import AssetEntity, EarningEntity
from fincontrol_core.domain.enums import (
    INTEGER_QUANTITY_TYPES,
    ArcaClass,
    AssetType,
    IntraClassStrategy,
)
from fincontrol_core.market.models import Fundamentals, Quote, QuoteFreshness
from fincontrol_core.portfolio.fixed_income import (
    FixedIncomeValuation,
    value_fixed_income_position,
)
from fincontrol_core.portfolio.positions import PositionState, build_position


@dataclass(frozen=True)
class ValuedAssetPosition:
    """Comprehensive valuation, yield estimation, and consolidated P/L for a single asset."""

    asset_id: int
    ticker: str
    name: str
    asset_type: AssetType
    arca_class: ArcaClass
    currency: str
    quantity: float
    average_price: float
    current_unit_price: float
    fx_rate: float
    price_freshness: QuoteFreshness
    invested_value_brl: float
    gross_current_value_brl: float
    estimated_tax_brl: float
    current_value_brl: float
    unrealized_pnl_brl: float
    unrealized_pnl_pct: float
    realized_pnl_brl: float
    received_earnings_brl: float
    earnings_12m_brl: float
    yield_on_cost_pct: float
    estimated_yield_to_date_brl: float
    estimated_yield_to_date_pct: float
    estimated_yield_basis: str
    projected_12m_yield_brl: float
    consolidated_pnl_brl: float
    consolidated_return_pct: float
    cerrado_evaluation: CerradoEvaluation
    class_target_weight_pct: float = 0.0
    class_current_weight_pct: float = 0.0
    fixed_income_details: FixedIncomeValuation | None = None


@dataclass(frozen=True)
class ConsolidatedPortfolioReport:
    """Complete portfolio consolidation across assets, ARCA classes, earnings, and projections."""

    as_of_date: date
    total_invested_brl: float
    total_gross_value_brl: float
    total_estimated_tax_brl: float
    total_current_value_brl: float
    total_unrealized_pnl_brl: float
    total_unrealized_pnl_pct: float
    total_realized_pnl_brl: float
    total_received_earnings_brl: float
    total_earnings_12m_brl: float
    portfolio_yield_on_cost_pct: float
    total_estimated_yield_to_date_brl: float
    total_projected_12m_yield_brl: float
    total_projected_12m_value_brl: float
    total_consolidated_pnl_brl: float
    total_consolidated_return_pct: float
    allocations: list[ClassAllocation]
    positions: list[ValuedAssetPosition]
    earnings_by_month: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class AssetContributionOrder:
    """Suggested purchase order for a single asset inside an ARCA class."""

    asset_id: int
    ticker: str
    name: str
    asset_type: AssetType
    arca_class: ArcaClass
    cerrado_score: int
    cerrado_recommendation: Recommendation
    intra_class_target_weight_pct: float
    allocated_amount_brl: float
    unit_price_brl: float
    recommended_quantity: float
    executed_amount_brl: float
    projected_value_brl: float


@dataclass(frozen=True)
class ContributionPlan:
    """Two-level contribution plan (ARCA classes -> assets inside each class)."""

    contribution_amount_brl: float
    executed_total_brl: float
    unallocated_cash_brl: float
    by_class_allocated_brl: dict[ArcaClass, float]
    orders: list[AssetContributionOrder]
    projected_allocations: list[ClassAllocation]


def _sum_earnings(
    earnings: Iterable[EarningEntity],
    *,
    as_of_date: date,
    fx_rate: float,
    date_from: date | None = None,
) -> tuple[float, float, dict[str, float]]:
    total_net = 0.0
    trailing_12m_cutoff = as_of_date - timedelta(days=365)
    earnings_12m = 0.0
    by_month: dict[str, float] = {}

    for e in earnings:
        if e.payment_date > as_of_date:
            continue
        if date_from is not None and e.payment_date < date_from:
            continue
        net_val = float(e.net_amount or (e.gross_amount - e.withholding_tax)) * fx_rate
        total_net += net_val
        if e.payment_date >= trailing_12m_cutoff:
            earnings_12m += net_val
        month_key = e.payment_date.strftime("%Y-%m")
        by_month[month_key] = round(by_month.get(month_key, 0.0) + net_val, 2)

    return round(total_net, 2), round(earnings_12m, 2), by_month


def _estimate_yield_and_projection_by_type(
    asset: AssetEntity,
    *,
    invested_brl: float,
    current_net_brl: float,
    unrealized_brl: float,
    received_earnings_brl: float,
    earnings_12m_brl: float,
    fundamentals: Fundamentals | None,
    fi_valuation: FixedIncomeValuation | None,
    annual_cdi_rate: float,
) -> tuple[float, float, str, float]:
    """Compute estimated yield to date and 12m projection tailored to the specific AssetType."""
    atype = asset.asset_type

    if atype in (AssetType.FIXED_INCOME, AssetType.TREASURY) and fi_valuation is not None:
        basis = (
            f"Fixed Income Curve ({asset.fixed_income_term.indexer.value})"
            if asset.fixed_income_term
            else "Fixed Income"
        )
        est_brl = fi_valuation.net_yield + received_earnings_brl
        est_pct = (est_brl / invested_brl * 100.0) if invested_brl > 0 else 0.0
        return (
            round(est_brl, 2),
            round(est_pct, 4),
            basis,
            round(fi_valuation.projected_12m_net_yield, 2),
        )

    if atype == AssetType.CASH:
        est_brl = unrealized_brl + received_earnings_brl
        est_pct = (est_brl / invested_brl * 100.0) if invested_brl > 0 else 0.0
        proj_12m = current_net_brl * annual_cdi_rate * 0.825
        return (
            round(est_brl, 2),
            round(est_pct, 4),
            "Cash / Daily Liquidity (CDI)",
            round(proj_12m, 2),
        )

    dy = fundamentals.dividend_yield if fundamentals and fundamentals.dividend_yield else 0.0
    expected_div_12m = max(earnings_12m_brl, current_net_brl * dy)

    if atype in (AssetType.FII, AssetType.REIT):
        est_brl = unrealized_brl + received_earnings_brl
        est_pct = (est_brl / invested_brl * 100.0) if invested_brl > 0 else 0.0
        proj_12m = expected_div_12m if expected_div_12m > 0 else current_net_brl * 0.085
        return (
            round(est_brl, 2),
            round(est_pct, 4),
            "Quota Appreciation + Tax-Exempt Real Estate Distributions",
            round(proj_12m, 2),
        )

    if atype in (AssetType.STOCK_BR, AssetType.STOCK_INTL, AssetType.BDR):
        est_brl = unrealized_brl + received_earnings_brl
        est_pct = (est_brl / invested_brl * 100.0) if invested_brl > 0 else 0.0
        cap_growth = current_net_brl * 0.08
        proj_12m = expected_div_12m + cap_growth
        return (
            round(est_brl, 2),
            round(est_pct, 4),
            "Price Appreciation + Dividends/JCP + Yield on Cost",
            round(proj_12m, 2),
        )

    # ETF_BR, ETF_INTL, CRYPTO
    est_brl = unrealized_brl + received_earnings_brl
    est_pct = (est_brl / invested_brl * 100.0) if invested_brl > 0 else 0.0
    proj_12m = current_net_brl * 0.10
    return (
        round(est_brl, 2),
        round(est_pct, 4),
        "Market Price Appreciation (BRL Adjusted)",
        round(proj_12m, 2),
    )


def consolidate_portfolio(
    assets: Iterable[AssetEntity],
    targets: ArcaTargets,
    *,
    quotes: Mapping[str, Quote] | None = None,
    fundamentals_by_ticker: Mapping[str, Fundamentals] | None = None,
    intra_strategies: Mapping[ArcaClass, IntraClassStrategy] | None = None,
    usd_brl_rate: float = 5.0,
    annual_cdi_rate: float = 0.1075,
    annual_ipca_rate: float = 0.045,
    daily_cdi_series: Mapping[date, float] | None = None,
    as_of_date: date | None = None,
    date_from: date | None = None,
) -> ConsolidatedPortfolioReport:
    """Consolidate all assets, positions, fixed income curves, earnings, and ARCA allocations."""
    ref_date = as_of_date or date.today()
    quotes_map = quotes or {}
    fund_map = fundamentals_by_ticker or {}
    strategy_map = intra_strategies or {}

    raw_positions: list[dict[str, Any]] = []
    combined_earnings_by_month: dict[str, float] = {}

    for asset in assets:
        if not asset.is_active:
            continue

        pos_state: PositionState = build_position(asset.transactions, up_to_date=ref_date)
        fx = usd_brl_rate if (asset.currency or "BRL").upper() == "USD" else 1.0
        fund = fund_map.get(asset.ticker)
        cerrado_eval = evaluate(
            asset.asset_type,
            asset.cerrado_answers,
            fund,
            use_cerrado=asset.use_cerrado,
        )

        received_earnings_brl, earnings_12m_brl, asset_monthly = _sum_earnings(
            asset.earnings,
            as_of_date=ref_date,
            fx_rate=fx,
            date_from=date_from,
        )
        for m_key, m_val in asset_monthly.items():
            combined_earnings_by_month[m_key] = round(
                combined_earnings_by_month.get(m_key, 0.0) + m_val, 2
            )

        qty = float(pos_state.quantity)
        avg_price = float(pos_state.average_price)
        invested_brl = round(float(pos_state.total_cost) * fx, 2)
        realized_brl = round(float(pos_state.realized_pnl) * fx, 2)

        fi_val: FixedIncomeValuation | None = None
        if (
            asset.asset_type in (AssetType.FIXED_INCOME, AssetType.TREASURY)
            and asset.fixed_income_term is not None
        ):
            fi_val = value_fixed_income_position(
                asset.transactions,
                asset.fixed_income_term,
                ref_date,
                annual_cdi_rate=annual_cdi_rate,
                annual_ipca_rate=annual_ipca_rate,
                daily_cdi_series=daily_cdi_series,
            )
            invested_brl = fi_val.invested_principal
            gross_brl = fi_val.gross_value
            tax_brl = round(fi_val.iof_tax + fi_val.income_tax, 2)
            current_brl = fi_val.net_value
            unit_price = (current_brl / qty) if qty > 0 else avg_price
            freshness = QuoteFreshness.CURVE
        else:
            quote = quotes_map.get(asset.ticker)
            if quote is not None:
                unit_price = float(quote.price)
                freshness = quote.freshness
            elif asset.manual_price is not None:
                unit_price = float(asset.manual_price)
                freshness = QuoteFreshness.MANUAL
            else:
                unit_price = avg_price
                freshness = QuoteFreshness.FALLBACK

            gross_brl = round(qty * unit_price * fx, 2)
            tax_brl = 0.0
            current_brl = gross_brl

        unrealized_brl = round(current_brl - invested_brl, 2)
        unrealized_pct = (
            round(unrealized_brl / invested_brl * 100.0, 4) if invested_brl > 0 else 0.0
        )
        yoc_pct = (
            round(earnings_12m_brl / invested_brl * 100.0, 4) if invested_brl > 0 else 0.0
        )

        est_yield_brl, est_yield_pct, est_basis, proj_12m_brl = (
            _estimate_yield_and_projection_by_type(
                asset,
                invested_brl=invested_brl,
                current_net_brl=current_brl,
                unrealized_brl=unrealized_brl,
                received_earnings_brl=received_earnings_brl,
                earnings_12m_brl=earnings_12m_brl,
                fundamentals=fund,
                fi_valuation=fi_val,
                annual_cdi_rate=annual_cdi_rate,
            )
        )

        consolidated_pnl_brl = round(unrealized_brl + realized_brl + received_earnings_brl, 2)
        denom = invested_brl if invested_brl > 0 else 0.0
        consolidated_return_pct = (
            round(consolidated_pnl_brl / denom * 100.0, 4) if denom > 0 else 0.0
        )

        raw_positions.append(
            {
                "asset": asset,
                "qty": qty,
                "avg_price": avg_price,
                "unit_price": unit_price,
                "fx": fx,
                "freshness": freshness,
                "invested_brl": invested_brl,
                "gross_brl": gross_brl,
                "tax_brl": tax_brl,
                "current_brl": current_brl,
                "unrealized_brl": unrealized_brl,
                "unrealized_pct": unrealized_pct,
                "realized_brl": realized_brl,
                "received_earnings_brl": received_earnings_brl,
                "earnings_12m_brl": earnings_12m_brl,
                "yoc_pct": yoc_pct,
                "est_yield_brl": est_yield_brl,
                "est_yield_pct": est_yield_pct,
                "est_basis": est_basis,
                "proj_12m_brl": proj_12m_brl,
                "consolidated_pnl_brl": consolidated_pnl_brl,
                "consolidated_return_pct": consolidated_return_pct,
                "cerrado_eval": cerrado_eval,
                "fi_val": fi_val,
            }
        )

    # Resolve intra-class target weights and current weights per ARCA class
    valued_positions: list[ValuedAssetPosition] = []
    values_by_class: dict[ArcaClass, float] = {c: 0.0 for c in ArcaClass}
    invested_by_class: dict[ArcaClass, float] = {c: 0.0 for c in ArcaClass}
    cons_pnl_by_class: dict[ArcaClass, float] = {c: 0.0 for c in ArcaClass}

    for arca_class in ArcaClass:
        class_items = [
            item for item in raw_positions if item["asset"].arca_class == arca_class
        ]
        if not class_items:
            continue
        class_total_val = sum(item["current_brl"] for item in class_items)
        values_by_class[arca_class] = round(class_total_val, 2)
        invested_by_class[arca_class] = round(
            sum(item["invested_brl"] for item in class_items), 2
        )
        cons_pnl_by_class[arca_class] = round(
            sum(item["consolidated_pnl_brl"] for item in class_items), 2
        )

        strategy = strategy_map.get(arca_class, IntraClassStrategy.CERRADO)
        keys = [item["asset"].ticker for item in class_items]
        scores = {item["asset"].ticker: item["cerrado_eval"].score for item in class_items}
        enabled = {item["asset"].ticker: item["asset"].use_cerrado for item in class_items}
        manuals = {
            item["asset"].ticker: (
                float(item["asset"].custom_class_weight)
                if item["asset"].custom_class_weight is not None
                else None
            )
            for item in class_items
        }
        target_weights = resolve_intra_class_weights(
            strategy,
            keys,
            cerrado_scores=scores,
            cerrado_enabled=enabled,
            manual_weights=manuals,
        )

        for item in class_items:
            a: AssetEntity = item["asset"]
            cur_w_pct = (
                round(item["current_brl"] / class_total_val * 100.0, 4)
                if class_total_val > 0
                else 0.0
            )
            tgt_w_pct = round(target_weights.get(a.ticker, 0.0) * 100.0, 4)
            valued_positions.append(
                ValuedAssetPosition(
                    asset_id=a.id or 0,
                    ticker=a.ticker,
                    name=a.name,
                    asset_type=a.asset_type,
                    arca_class=a.arca_class or ArcaClass.ACOES,
                    currency=a.currency or "BRL",
                    quantity=round(item["qty"], 8),
                    average_price=round(item["avg_price"], 4),
                    current_unit_price=round(item["unit_price"], 4),
                    fx_rate=round(item["fx"], 4),
                    price_freshness=item["freshness"],
                    invested_value_brl=item["invested_brl"],
                    gross_current_value_brl=item["gross_brl"],
                    estimated_tax_brl=item["tax_brl"],
                    current_value_brl=item["current_brl"],
                    unrealized_pnl_brl=item["unrealized_brl"],
                    unrealized_pnl_pct=item["unrealized_pct"],
                    realized_pnl_brl=item["realized_brl"],
                    received_earnings_brl=item["received_earnings_brl"],
                    earnings_12m_brl=item["earnings_12m_brl"],
                    yield_on_cost_pct=item["yoc_pct"],
                    estimated_yield_to_date_brl=item["est_yield_brl"],
                    estimated_yield_to_date_pct=item["est_yield_pct"],
                    estimated_yield_basis=item["est_basis"],
                    projected_12m_yield_brl=item["proj_12m_brl"],
                    consolidated_pnl_brl=item["consolidated_pnl_brl"],
                    consolidated_return_pct=item["consolidated_return_pct"],
                    cerrado_evaluation=item["cerrado_eval"],
                    class_target_weight_pct=tgt_w_pct,
                    class_current_weight_pct=cur_w_pct,
                    fixed_income_details=item["fi_val"],
                )
            )

    allocations = compute_allocation(
        values_by_class,
        targets,
        invested_by_class=invested_by_class,
        consolidated_pnl_by_class=cons_pnl_by_class,
    )

    total_invested = round(sum(p.invested_value_brl for p in valued_positions), 2)
    total_gross = round(sum(p.gross_current_value_brl for p in valued_positions), 2)
    total_tax = round(sum(p.estimated_tax_brl for p in valued_positions), 2)
    total_current = round(sum(p.current_value_brl for p in valued_positions), 2)
    total_unrealized = round(total_current - total_invested, 2)
    total_unrealized_pct = (
        round(total_unrealized / total_invested * 100.0, 4) if total_invested > 0 else 0.0
    )
    total_realized = round(sum(p.realized_pnl_brl for p in valued_positions), 2)
    total_earnings = round(sum(p.received_earnings_brl for p in valued_positions), 2)
    total_earnings_12m = round(sum(p.earnings_12m_brl for p in valued_positions), 2)
    portfolio_yoc = (
        round(total_earnings_12m / total_invested * 100.0, 4) if total_invested > 0 else 0.0
    )
    total_est_yield = round(sum(p.estimated_yield_to_date_brl for p in valued_positions), 2)
    total_proj_12m = round(sum(p.projected_12m_yield_brl for p in valued_positions), 2)
    total_consolidated = round(total_unrealized + total_realized + total_earnings, 2)
    total_consolidated_pct = (
        round(total_consolidated / total_invested * 100.0, 4) if total_invested > 0 else 0.0
    )

    return ConsolidatedPortfolioReport(
        as_of_date=ref_date,
        total_invested_brl=total_invested,
        total_gross_value_brl=total_gross,
        total_estimated_tax_brl=total_tax,
        total_current_value_brl=total_current,
        total_unrealized_pnl_brl=total_unrealized,
        total_unrealized_pnl_pct=total_unrealized_pct,
        total_realized_pnl_brl=total_realized,
        total_received_earnings_brl=total_earnings,
        total_earnings_12m_brl=total_earnings_12m,
        portfolio_yield_on_cost_pct=portfolio_yoc,
        total_estimated_yield_to_date_brl=total_est_yield,
        total_projected_12m_yield_brl=total_proj_12m,
        total_projected_12m_value_brl=round(total_current + total_proj_12m, 2),
        total_consolidated_pnl_brl=total_consolidated,
        total_consolidated_return_pct=total_consolidated_pct,
        allocations=allocations,
        positions=valued_positions,
        earnings_by_month=dict(sorted(combined_earnings_by_month.items())),
    )


def plan_contribution(
    report: ConsolidatedPortfolioReport,
    targets: ArcaTargets,
    amount_brl: float,
    *,
    strategy_override: IntraClassStrategy | None = None,
) -> ContributionPlan:
    """Build a 2-level contribution plan (Level 1: ARCA classes; Level 2: intra-class assets)."""
    if amount_brl < 0:
        raise ValueError("Contribution amount cannot be negative")

    current_by_class = {a.arca_class: a.current_value for a in report.allocations}
    class_alloc_brl = distribute_by_targets(
        current_by_class,
        targets.as_fractions(),
        amount_brl,
    )

    orders: list[AssetContributionOrder] = []
    projected_by_class = dict(current_by_class)
    executed_total = 0.0

    for arca_class in ArcaClass:
        class_budget = class_alloc_brl.get(arca_class, 0.0)
        if class_budget <= 0:
            continue

        class_positions = [p for p in report.positions if p.arca_class == arca_class]
        if not class_positions:
            continue

        if strategy_override is not None:
            weights_map = resolve_intra_class_weights(
                strategy_override,
                [p.ticker for p in class_positions],
                cerrado_scores={p.ticker: p.cerrado_evaluation.score for p in class_positions},
                cerrado_enabled={
                    p.ticker: p.cerrado_evaluation.use_cerrado for p in class_positions
                },
                manual_weights={
                    p.ticker: p.class_target_weight_pct for p in class_positions
                },
            )
        else:
            weights_map = {
                p.ticker: max(p.class_target_weight_pct / 100.0, 0.0) for p in class_positions
            }
            if sum(weights_map.values()) <= 0:
                weights_map = {p.ticker: 1.0 / len(class_positions) for p in class_positions}

        current_asset_values = {p.ticker: p.current_value_brl for p in class_positions}
        asset_budgets = distribute_by_targets(current_asset_values, weights_map, class_budget)

        class_leftover = 0.0
        temp_orders: list[dict[str, Any]] = []

        for pos in class_positions:
            raw_budget = asset_budgets.get(pos.ticker, 0.0)
            unit_brl = max(pos.current_unit_price * pos.fx_rate, 0.0)
            if unit_brl <= 0 or raw_budget <= 0:
                qty = 0.0
                exec_brl = 0.0
            elif pos.asset_type in INTEGER_QUANTITY_TYPES:
                qty = float(math.floor(raw_budget / unit_brl))
                exec_brl = qty * unit_brl
                class_leftover += raw_budget - exec_brl
            else:
                qty = round(raw_budget / unit_brl, 6)
                exec_brl = round(raw_budget, 2)

            temp_orders.append(
                {
                    "pos": pos,
                    "weight_pct": round(weights_map.get(pos.ticker, 0.0) * 100.0, 2),
                    "raw_budget": round(raw_budget, 2),
                    "unit_brl": round(unit_brl, 2),
                    "qty": qty,
                    "exec_brl": exec_brl,
                }
            )

        # Redistribute integer rounding leftover to highest-weight integer assets that fit
        integer_candidates = sorted(
            [
                o
                for o in temp_orders
                if o["pos"].asset_type in INTEGER_QUANTITY_TYPES
                and o["unit_brl"] > 0
                and o["weight_pct"] > 0
            ],
            key=lambda o: (-o["weight_pct"], o["unit_brl"]),
        )
        made_progress = True
        while made_progress and class_leftover > 0:
            made_progress = False
            for cand in integer_candidates:
                if class_leftover >= cand["unit_brl"]:
                    cand["qty"] += 1.0
                    cand["exec_brl"] += cand["unit_brl"]
                    class_leftover -= cand["unit_brl"]
                    made_progress = True

        for o in temp_orders:
            pos = o["pos"]
            exec_brl = round(o["exec_brl"], 2)
            executed_total += exec_brl
            projected_by_class[arca_class] = round(
                projected_by_class.get(arca_class, 0.0) + exec_brl, 2
            )
            orders.append(
                AssetContributionOrder(
                    asset_id=pos.asset_id,
                    ticker=pos.ticker,
                    name=pos.name,
                    asset_type=pos.asset_type,
                    arca_class=pos.arca_class,
                    cerrado_score=pos.cerrado_evaluation.score,
                    cerrado_recommendation=pos.cerrado_evaluation.recommendation,
                    intra_class_target_weight_pct=o["weight_pct"],
                    allocated_amount_brl=o["raw_budget"],
                    unit_price_brl=o["unit_brl"],
                    recommended_quantity=o["qty"],
                    executed_amount_brl=exec_brl,
                    projected_value_brl=round(pos.current_value_brl + exec_brl, 2),
                )
            )

    projected_allocations = compute_allocation(projected_by_class, targets)
    return ContributionPlan(
        contribution_amount_brl=round(amount_brl, 2),
        executed_total_brl=round(executed_total, 2),
        unallocated_cash_brl=round(max(amount_brl - executed_total, 0.0), 2),
        by_class_allocated_brl={k: round(v, 2) for k, v in class_alloc_brl.items()},
        orders=orders,
        projected_allocations=projected_allocations,
    )
