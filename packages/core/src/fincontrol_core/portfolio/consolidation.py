"""Portfolio valuation, yield estimation, P/L consolidation, and 2-level contribution planner.

Currency conventions (finding C-02): cost and realized P/L are converted with the FX of each
trade, earnings with the FX of each payment, and open positions with the current FX. The
difference between the current-FX cost and the historical-FX cost is reported as `fx_pnl_brl`.

An asset whose ledger cannot be valued (oversell) is reported with `ledger_status=INVALID`
and excluded from totals and allocations instead of failing the whole report (finding I-04).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from fincontrol_core.arca.allocation import (
    BAND_BELOW,
    ArcaTargets,
    ClassAllocation,
    compute_allocation,
    distribute_by_targets,
    distribute_with_bands,
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
    AssetLifecycle,
    AssetPurpose,
    AssetType,
    IntraClassStrategy,
    TransactionKind,
)
from fincontrol_core.errors import ValidationError
from fincontrol_core.fundamentals.history import HistoricalMetrics
from fincontrol_core.market.models import Fundamentals, Quote, QuoteFreshness
from fincontrol_core.policy.assumptions import ProjectionAssumptions
from fincontrol_core.policy.lifecycle import (
    CONTRIBUTION_STATUSES,
    has_position,
    is_eligible,
    lifecycle_status,
)
from fincontrol_core.policy.models import EligibilityPolicy
from fincontrol_core.portfolio.fixed_income import (
    FixedIncomeValuation,
    RateCurves,
    value_fixed_income_position,
)
from fincontrol_core.portfolio.positions import InsufficientQuantityError, build_position

LEDGER_VALID = "VALID"
LEDGER_INVALID = "INVALID"

FIXED_INCOME_TYPES = frozenset({AssetType.FIXED_INCOME, AssetType.TREASURY})


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
    fx_pnl_brl: float = 0.0
    custom_class_weight: float | None = None
    ledger_status: str = LEDGER_VALID
    ledger_message: str | None = None
    purpose: AssetPurpose = AssetPurpose.ARCA
    lifecycle_status: AssetLifecycle = AssetLifecycle.HELD
    eligible: bool = True


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
    total_fx_pnl_brl: float = 0.0
    projection_assumptions: dict[str, float] = field(default_factory=dict)
    value_by_purpose_brl: dict[str, float] = field(default_factory=dict)


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


@dataclass
class _Valuation:
    """Intermediate per-asset numbers before intra-class weights are known."""

    asset: AssetEntity
    qty: float = 0.0
    avg_price: float = 0.0
    unit_price: float = 0.0
    fx: float = 1.0
    freshness: QuoteFreshness = QuoteFreshness.FALLBACK
    invested_brl: float = 0.0
    gross_brl: float = 0.0
    tax_brl: float = 0.0
    current_brl: float = 0.0
    realized_brl: float = 0.0
    fx_pnl_brl: float = 0.0
    fi_val: FixedIncomeValuation | None = None
    ledger_message: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.ledger_message is None


def _sum_earnings(
    earnings: Iterable[EarningEntity],
    *,
    as_of_date: date,
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
        net_val = float(e.net_amount or (e.gross_amount - e.withholding_tax)) * float(e.fx_rate)
        total_net += net_val
        if e.payment_date >= trailing_12m_cutoff:
            earnings_12m += net_val
        month_key = e.payment_date.strftime("%Y-%m")
        by_month[month_key] = round(by_month.get(month_key, 0.0) + net_val, 2)

    return round(total_net, 2), round(earnings_12m, 2), by_month


def _pct(value: float, base: float) -> float:
    return round(value / base * 100.0, 4) if base > 0 else 0.0


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
    assumptions: ProjectionAssumptions,
) -> tuple[float, float, str, float]:
    """Compute estimated yield to date and 12m projection tailored to the specific AssetType."""
    atype = asset.asset_type

    if atype in FIXED_INCOME_TYPES and fi_valuation is not None:
        basis = (
            f"Fixed Income Curve ({asset.fixed_income_term.indexer.value})"
            if asset.fixed_income_term
            else "Fixed Income"
        )
        est_brl = fi_valuation.net_yield + received_earnings_brl
        return (
            round(est_brl, 2),
            _pct(est_brl, invested_brl),
            basis,
            round(fi_valuation.projected_12m_net_yield, 2),
        )

    est_brl = unrealized_brl + received_earnings_brl
    est_pct = _pct(est_brl, invested_brl)

    if atype == AssetType.CASH:
        proj_12m = (
            current_net_brl
            * annual_cdi_rate
            * assumptions.cash_cdi_multiplier
            * (1.0 - assumptions.cash_income_tax_rate)
        )
        return round(est_brl, 2), est_pct, "Cash / Daily Liquidity (CDI)", round(proj_12m, 2)

    dy = fundamentals.dividend_yield if fundamentals and fundamentals.dividend_yield else 0.0
    expected_div_12m = max(earnings_12m_brl, current_net_brl * dy)

    if atype in (AssetType.FII, AssetType.REIT):
        proj_12m = (
            expected_div_12m
            if expected_div_12m > 0
            else current_net_brl * assumptions.real_estate_default_yield_rate
        )
        return (
            round(est_brl, 2),
            est_pct,
            "Quota Appreciation + Tax-Exempt Real Estate Distributions",
            round(proj_12m, 2),
        )

    if atype in (AssetType.STOCK_BR, AssetType.STOCK_INTL, AssetType.BDR):
        proj_12m = expected_div_12m + current_net_brl * assumptions.equity_capital_growth_rate
        return (
            round(est_brl, 2),
            est_pct,
            "Price Appreciation + Dividends/JCP + Yield on Cost",
            round(proj_12m, 2),
        )

    # ETF_BR, ETF_INTL, CRYPTO
    proj_12m = current_net_brl * assumptions.fund_capital_growth_rate
    return (
        round(est_brl, 2),
        est_pct,
        "Market Price Appreciation (BRL Adjusted)",
        round(proj_12m, 2),
    )


def _value_fixed_income(v: _Valuation, ref_date: date, curves: RateCurves) -> None:
    asset = v.asset
    assert asset.fixed_income_term is not None
    v.fi_val = value_fixed_income_position(
        asset.transactions, asset.fixed_income_term, ref_date, curves=curves
    )
    open_qty = sum(
        float(t.quantity) if t.kind == TransactionKind.BUY else -float(t.quantity)
        for t in asset.transactions
        if t.trade_date <= ref_date
    )
    v.qty = max(open_qty, 0.0) if v.fi_val.invested_principal > 0 else 0.0
    v.invested_brl = v.fi_val.invested_principal
    v.avg_price = v.invested_brl / v.qty if v.qty > 0 else v.invested_brl
    v.gross_brl = v.fi_val.gross_value
    v.tax_brl = round(v.fi_val.iof_tax + v.fi_val.income_tax, 2)
    v.current_brl = v.fi_val.net_value
    v.realized_brl = v.fi_val.realized_pnl
    v.unit_price = v.current_brl / v.qty if v.qty > 0 else v.current_brl
    v.freshness = QuoteFreshness.CURVE


def _value_market_asset(
    v: _Valuation, ref_date: date, quote: Quote | None, usd_brl_rate: float
) -> None:
    asset = v.asset
    pos = build_position(asset.transactions, up_to_date=ref_date)
    v.fx = usd_brl_rate if (asset.currency or "BRL").upper() == "USD" else 1.0
    v.qty = float(pos.quantity)
    v.avg_price = float(pos.average_price)
    v.invested_brl = round(float(pos.total_cost_brl), 2)
    v.realized_brl = round(float(pos.realized_pnl_brl), 2)

    if quote is not None:
        v.unit_price, v.freshness = float(quote.price), quote.freshness
    elif asset.manual_price is not None:
        v.unit_price, v.freshness = float(asset.manual_price), QuoteFreshness.MANUAL
    else:
        v.unit_price, v.freshness = v.avg_price, QuoteFreshness.FALLBACK

    v.gross_brl = round(v.qty * v.unit_price * v.fx, 2)
    v.current_brl = v.gross_brl
    v.fx_pnl_brl = round(float(pos.total_cost) * v.fx - float(pos.total_cost_brl), 2)


def consolidate_portfolio(
    assets: Iterable[AssetEntity],
    targets: ArcaTargets,
    *,
    quotes: Mapping[str, Quote] | None = None,
    fundamentals_by_ticker: Mapping[str, Fundamentals] | None = None,
    history_by_ticker: Mapping[str, HistoricalMetrics] | None = None,
    intra_strategies: Mapping[ArcaClass, IntraClassStrategy] | None = None,
    bands: Mapping[ArcaClass, float] | None = None,
    eligibility: EligibilityPolicy | None = None,
    usd_brl_rate: float = 5.0,
    curves: RateCurves | None = None,
    assumptions: ProjectionAssumptions | None = None,
    as_of_date: date | None = None,
    date_from: date | None = None,
) -> ConsolidatedPortfolioReport:
    """Consolidate all assets, positions, fixed income curves, earnings, and ARCA allocations."""
    ref_date = as_of_date or date.today()
    rate_curves = curves or RateCurves()
    premises = assumptions or ProjectionAssumptions()
    eligibility_policy = eligibility or EligibilityPolicy()
    quotes_map = quotes or {}
    fund_map = fundamentals_by_ticker or {}
    history_map = history_by_ticker or {}
    strategy_map = intra_strategies or {}

    valuations: list[_Valuation] = []
    for asset in assets:
        if not asset.is_active:
            continue
        v = _Valuation(asset=asset)
        try:
            if asset.asset_type in FIXED_INCOME_TYPES and asset.fixed_income_term is not None:
                _value_fixed_income(v, ref_date, rate_curves)
            else:
                _value_market_asset(v, ref_date, quotes_map.get(asset.ticker), usd_brl_rate)
        except InsufficientQuantityError as err:
            v = _Valuation(asset=asset, ledger_message=str(err))
        valuations.append(v)

    combined_earnings_by_month: dict[str, float] = {}
    rows: list[dict[str, Any]] = []
    for v in valuations:
        asset = v.asset
        fund = fund_map.get(asset.ticker)
        cerrado_eval = evaluate(
            asset.profile,
            asset.cerrado_answers,
            fund,
            use_cerrado=asset.use_cerrado,
            history=history_map.get(asset.ticker),
        )
        received_brl, earnings_12m_brl, monthly = (
            _sum_earnings(asset.earnings, as_of_date=ref_date, date_from=date_from)
            if v.is_valid
            else (0.0, 0.0, {})
        )
        for m_key, m_val in monthly.items():
            combined_earnings_by_month[m_key] = round(
                combined_earnings_by_month.get(m_key, 0.0) + m_val, 2
            )

        unrealized_brl = round(v.current_brl - v.invested_brl, 2)
        est_brl, est_pct, est_basis, proj_12m = (
            _estimate_yield_and_projection_by_type(
                asset,
                invested_brl=v.invested_brl,
                current_net_brl=v.current_brl,
                unrealized_brl=unrealized_brl,
                received_earnings_brl=received_brl,
                earnings_12m_brl=earnings_12m_brl,
                fundamentals=fund,
                fi_valuation=v.fi_val,
                annual_cdi_rate=rate_curves.annual_cdi_rate,
                assumptions=premises,
            )
            if v.is_valid
            else (0.0, 0.0, "Invalid ledger", 0.0)
        )
        consolidated = round(unrealized_brl + v.realized_brl + received_brl, 2)
        eligible = is_eligible(cerrado_eval, eligibility_policy, asset.purpose)
        holds = (
            v.invested_brl > 0 or v.qty > 0
            if v.is_valid
            else has_position(asset.transactions, fixed_income=asset.fixed_income_term is not None)
        )
        status = lifecycle_status(
            is_active=asset.is_active, holds_position=holds, eligible=eligible
        )
        if not v.is_valid and status == AssetLifecycle.HELD:
            status = AssetLifecycle.REVIEW
        rows.append(
            {
                "eligible": eligible,
                "lifecycle": status,
                "v": v,
                "cerrado": cerrado_eval,
                "received": received_brl,
                "earnings_12m": earnings_12m_brl,
                "unrealized": unrealized_brl,
                "est_brl": est_brl,
                "est_pct": est_pct,
                "est_basis": est_basis,
                "proj_12m": proj_12m,
                "consolidated": consolidated,
            }
        )

    positions: list[ValuedAssetPosition] = []
    values_by_class: dict[ArcaClass, float] = dict.fromkeys(ArcaClass, 0.0)
    invested_by_class: dict[ArcaClass, float] = dict.fromkeys(ArcaClass, 0.0)
    cons_pnl_by_class: dict[ArcaClass, float] = dict.fromkeys(ArcaClass, 0.0)

    for row in rows:
        if row["v"].asset.purpose != AssetPurpose.ARCA:
            positions.append(_to_position(row, 0.0, 0.0))

    for arca_class in ArcaClass:
        class_rows = [
            r
            for r in rows
            if r["v"].asset.arca_class == arca_class and r["v"].asset.purpose == AssetPurpose.ARCA
        ]
        if not class_rows:
            continue
        valid_rows = [r for r in class_rows if r["v"].is_valid]
        class_total = sum(r["v"].current_brl for r in valid_rows)
        values_by_class[arca_class] = round(class_total, 2)
        invested_by_class[arca_class] = round(sum(r["v"].invested_brl for r in valid_rows), 2)
        cons_pnl_by_class[arca_class] = round(sum(r["consolidated"] for r in valid_rows), 2)

        target_weights = resolve_intra_class_weights(
            strategy_map.get(arca_class, IntraClassStrategy.CERRADO),
            [r["v"].asset.ticker for r in valid_rows],
            cerrado_scores={r["v"].asset.ticker: r["cerrado"].score for r in valid_rows},
            cerrado_enabled={r["v"].asset.ticker: r["v"].asset.use_cerrado for r in valid_rows},
            manual_weights={r["v"].asset.ticker: _custom_weight(r["v"].asset) for r in valid_rows},
        )
        for r in class_rows:
            positions.append(
                _to_position(r, class_total, target_weights.get(r["v"].asset.ticker, 0.0))
            )

    allocations = compute_allocation(
        values_by_class,
        targets,
        bands=bands,
        invested_by_class=invested_by_class,
        consolidated_pnl_by_class=cons_pnl_by_class,
    )

    valid = [p for p in positions if p.ledger_status == LEDGER_VALID]
    total_invested = round(sum(p.invested_value_brl for p in valid), 2)
    total_current = round(sum(p.current_value_brl for p in valid), 2)
    total_unrealized = round(total_current - total_invested, 2)
    total_realized = round(sum(p.realized_pnl_brl for p in valid), 2)
    total_earnings = round(sum(p.received_earnings_brl for p in valid), 2)
    total_earnings_12m = round(sum(p.earnings_12m_brl for p in valid), 2)
    total_proj_12m = round(sum(p.projected_12m_yield_brl for p in valid), 2)
    total_consolidated = round(total_unrealized + total_realized + total_earnings, 2)

    return ConsolidatedPortfolioReport(
        as_of_date=ref_date,
        total_invested_brl=total_invested,
        total_gross_value_brl=round(sum(p.gross_current_value_brl for p in valid), 2),
        total_estimated_tax_brl=round(sum(p.estimated_tax_brl for p in valid), 2),
        total_current_value_brl=total_current,
        total_unrealized_pnl_brl=total_unrealized,
        total_unrealized_pnl_pct=_pct(total_unrealized, total_invested),
        total_realized_pnl_brl=total_realized,
        total_received_earnings_brl=total_earnings,
        total_earnings_12m_brl=total_earnings_12m,
        portfolio_yield_on_cost_pct=_pct(total_earnings_12m, total_invested),
        total_estimated_yield_to_date_brl=round(
            sum(p.estimated_yield_to_date_brl for p in valid), 2
        ),
        total_projected_12m_yield_brl=total_proj_12m,
        total_projected_12m_value_brl=round(total_current + total_proj_12m, 2),
        total_consolidated_pnl_brl=total_consolidated,
        total_consolidated_return_pct=_pct(total_consolidated, total_invested),
        allocations=allocations,
        positions=positions,
        earnings_by_month=dict(sorted(combined_earnings_by_month.items())),
        total_fx_pnl_brl=round(sum(p.fx_pnl_brl for p in valid), 2),
        value_by_purpose_brl={
            purpose.value: round(sum(p.current_value_brl for p in valid if p.purpose == purpose), 2)
            for purpose in AssetPurpose
        },
        projection_assumptions=premises.as_dict(),
    )


def _custom_weight(asset: AssetEntity) -> float | None:
    return float(asset.custom_class_weight) if asset.custom_class_weight is not None else None


def _to_position(
    row: dict[str, Any], class_total: float, target_weight: float
) -> ValuedAssetPosition:
    v: _Valuation = row["v"]
    a = v.asset
    return ValuedAssetPosition(
        asset_id=a.id or 0,
        ticker=a.ticker,
        name=a.name,
        asset_type=a.asset_type,
        arca_class=a.arca_class or ArcaClass.ACOES,
        currency=a.currency or "BRL",
        quantity=round(v.qty, 8),
        average_price=round(v.avg_price, 4),
        current_unit_price=round(v.unit_price, 4),
        fx_rate=round(v.fx, 4),
        price_freshness=v.freshness,
        invested_value_brl=v.invested_brl,
        gross_current_value_brl=v.gross_brl,
        estimated_tax_brl=v.tax_brl,
        current_value_brl=v.current_brl,
        unrealized_pnl_brl=row["unrealized"],
        unrealized_pnl_pct=_pct(row["unrealized"], v.invested_brl),
        realized_pnl_brl=v.realized_brl,
        received_earnings_brl=row["received"],
        earnings_12m_brl=row["earnings_12m"],
        yield_on_cost_pct=_pct(row["earnings_12m"], v.invested_brl),
        estimated_yield_to_date_brl=row["est_brl"],
        estimated_yield_to_date_pct=row["est_pct"],
        estimated_yield_basis=row["est_basis"],
        projected_12m_yield_brl=row["proj_12m"],
        consolidated_pnl_brl=row["consolidated"],
        consolidated_return_pct=_pct(row["consolidated"], v.invested_brl),
        cerrado_evaluation=row["cerrado"],
        class_target_weight_pct=round(target_weight * 100.0, 4),
        class_current_weight_pct=(_pct(v.current_brl, class_total) if v.is_valid else 0.0),
        fixed_income_details=v.fi_val,
        fx_pnl_brl=v.fx_pnl_brl,
        custom_class_weight=_custom_weight(a),
        ledger_status=LEDGER_VALID if v.is_valid else LEDGER_INVALID,
        ledger_message=v.ledger_message,
        purpose=a.purpose,
        lifecycle_status=row["lifecycle"],
        eligible=row["eligible"],
    )


@dataclass
class _DraftOrder:
    pos: ValuedAssetPosition
    weight: float
    budget: float
    unit_brl: float
    qty: float = 0.0
    executed: float = 0.0

    @property
    def is_integer(self) -> bool:
        return self.pos.asset_type in INTEGER_QUANTITY_TYPES

    @property
    def can_buy(self) -> bool:
        return self.unit_brl > 0 and self.weight > 0


def _class_weights(
    class_positions: list[ValuedAssetPosition], strategy_override: IntraClassStrategy | None
) -> dict[str, float]:
    if strategy_override is not None:
        return resolve_intra_class_weights(
            strategy_override,
            [p.ticker for p in class_positions],
            cerrado_scores={p.ticker: p.cerrado_evaluation.score for p in class_positions},
            cerrado_enabled={p.ticker: p.cerrado_evaluation.use_cerrado for p in class_positions},
            manual_weights={p.ticker: p.custom_class_weight for p in class_positions},
        )
    weights = {p.ticker: max(p.class_target_weight_pct / 100.0, 0.0) for p in class_positions}
    if sum(weights.values()) <= 0:
        return {p.ticker: 1.0 / len(class_positions) for p in class_positions}
    return weights


def _fill(order: _DraftOrder, amount: float) -> float:
    """Spend up to `amount` on `order`; return what was actually spent."""
    if not order.can_buy or amount <= 0:
        return 0.0
    if order.is_integer:
        units = math.floor(amount / order.unit_brl + 1e-9)
        spent = units * order.unit_brl
        order.qty += units
    else:
        spent = amount
        order.qty += amount / order.unit_brl
    order.executed += spent
    return spent


def _redistribute_leftover(
    drafts: dict[ArcaClass, list[_DraftOrder]],
    projected: dict[ArcaClass, float],
    targets: ArcaTargets,
    leftover: float,
) -> float:
    """Spend rounding leftovers on the classes furthest below target (finding A-04)."""
    while leftover > 0.005:
        total_after = sum(projected.values()) + leftover
        ranked = sorted(
            (c for c in ArcaClass if targets.fraction(c) > 0 and drafts.get(c)),
            key=lambda c: projected[c] - targets.fraction(c) * total_after,
        )
        progressed = False
        for arca_class in ranked:
            candidates = sorted(
                (o for o in drafts[arca_class] if o.can_buy),
                key=lambda o: (o.is_integer, -o.weight, o.unit_brl),
            )
            for order in candidates:
                if order.is_integer and order.unit_brl > leftover:
                    continue
                spent = _fill(order, order.unit_brl if order.is_integer else leftover)
                if spent > 0:
                    leftover -= spent
                    projected[arca_class] += spent
                    progressed = True
                    break
            if progressed:
                break
        if not progressed:
            break
    return leftover


def plan_contribution(
    report: ConsolidatedPortfolioReport,
    targets: ArcaTargets,
    amount_brl: float,
    *,
    strategy_override: IntraClassStrategy | None = None,
) -> ContributionPlan:
    """Build a 2-level contribution plan (Level 1: ARCA classes; Level 2: intra-class assets)."""
    if amount_brl < 0:
        raise ValidationError("Contribution amount cannot be negative")

    current_by_class = {a.arca_class: a.current_value for a in report.allocations}
    below_band = {a.arca_class for a in report.allocations if a.band_status == BAND_BELOW}
    class_alloc_brl = distribute_with_bands(current_by_class, targets, below_band, amount_brl)
    bands = {a.arca_class: a.band_pct for a in report.allocations}

    drafts: dict[ArcaClass, list[_DraftOrder]] = {}
    projected = dict(current_by_class)
    leftover = 0.0
    for arca_class in ArcaClass:
        class_budget = class_alloc_brl.get(arca_class, 0.0)
        class_positions = [
            p
            for p in report.positions
            if p.arca_class == arca_class
            and p.ledger_status == LEDGER_VALID
            and p.purpose == AssetPurpose.ARCA
            and p.lifecycle_status in CONTRIBUTION_STATUSES
        ]
        if class_budget <= 0 or not class_positions:
            leftover += max(class_budget, 0.0)
            continue

        weights = _class_weights(class_positions, strategy_override)
        budgets = distribute_by_targets(
            {p.ticker: p.current_value_brl for p in class_positions}, weights, class_budget
        )
        drafts[arca_class] = [
            _DraftOrder(
                pos=p,
                weight=weights.get(p.ticker, 0.0),
                budget=budgets.get(p.ticker, 0.0),
                unit_brl=max(p.current_unit_price * p.fx_rate, 0.0),
            )
            for p in class_positions
        ]
        for order in drafts[arca_class]:
            spent = _fill(order, order.budget)
            leftover += order.budget - spent
            projected[arca_class] = projected.get(arca_class, 0.0) + spent

    leftover = _redistribute_leftover(drafts, projected, targets, leftover)

    orders = [
        AssetContributionOrder(
            asset_id=o.pos.asset_id,
            ticker=o.pos.ticker,
            name=o.pos.name,
            asset_type=o.pos.asset_type,
            arca_class=o.pos.arca_class,
            cerrado_score=o.pos.cerrado_evaluation.score,
            cerrado_recommendation=o.pos.cerrado_evaluation.recommendation,
            intra_class_target_weight_pct=round(o.weight * 100.0, 2),
            allocated_amount_brl=round(o.budget, 2),
            unit_price_brl=round(o.unit_brl, 2),
            recommended_quantity=o.qty if o.is_integer else round(o.qty, 6),
            executed_amount_brl=round(o.executed, 2),
            projected_value_brl=round(o.pos.current_value_brl + o.executed, 2),
        )
        for arca_class in ArcaClass
        for o in drafts.get(arca_class, [])
    ]
    executed_total = round(sum(o.executed_amount_brl for o in orders), 2)
    return ContributionPlan(
        contribution_amount_brl=round(amount_brl, 2),
        executed_total_brl=executed_total,
        unallocated_cash_brl=round(max(amount_brl - executed_total, 0.0), 2),
        by_class_allocated_brl={k: round(v, 2) for k, v in class_alloc_brl.items()},
        orders=orders,
        projected_allocations=compute_allocation(
            {c: round(v, 2) for c, v in projected.items()}, targets, bands=bands
        ),
    )
