"""Unit tests for Phase 2 pure domain engines (in-memory, zero DB/network)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fincontrol_core.arca.allocation import (
    ArcaTargets,
    InvalidTargetsError,
    compute_allocation,
    distribute_by_targets,
)
from fincontrol_core.cerrado.questions import questions_for
from fincontrol_core.cerrado.scoring import (
    Recommendation,
    evaluate,
    resolve_intra_class_weights,
    target_weights_from_scores,
)
from fincontrol_core.domain.entities import (
    AssetEntity,
    EarningEntity,
    FixedIncomeTermEntity,
    TransactionEntity,
)
from fincontrol_core.domain.enums import (
    ArcaClass,
    AssetType,
    EarningKind,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    IntraClassStrategy,
    TransactionKind,
)
from fincontrol_core.market.models import Fundamentals, Quote
from fincontrol_core.portfolio.consolidation import (
    consolidate_portfolio,
    plan_contribution,
)
from fincontrol_core.portfolio.fixed_income import (
    RateCurves,
    count_business_days,
    regressive_iof_rate,
    regressive_ir_rate,
    value_fixed_income_position,
)
from fincontrol_core.portfolio.positions import (
    InsufficientQuantityError,
    build_position,
    quantity_on,
)
from fincontrol_core.valuation import (
    bazin_ceiling_price,
    graham_fair_value,
    margin_of_safety,
    summarize_valuation,
)


# ---------------------------------------------------------------------------
# 1. Position Engine Tests
# ---------------------------------------------------------------------------
def test_build_position_weighted_average_and_partial_sell() -> None:
    txs = [
        TransactionEntity(
            asset_id=1,
            kind=TransactionKind.BUY,
            trade_date=date(2025, 1, 10),
            quantity=Decimal("100"),
            unit_price=Decimal("20.00"),
            fees=Decimal("0"),
        ),
        TransactionEntity(
            asset_id=1,
            kind=TransactionKind.BUY,
            trade_date=date(2025, 2, 10),
            quantity=Decimal("100"),
            unit_price=Decimal("30.00"),
            fees=Decimal("0"),
        ),
        TransactionEntity(
            asset_id=1,
            kind=TransactionKind.SELL,
            trade_date=date(2025, 3, 10),
            quantity=Decimal("50"),
            unit_price=Decimal("35.00"),
            fees=Decimal("5.00"),
        ),
    ]
    pos = build_position(txs)
    assert pos.quantity == Decimal("150")
    assert pos.average_price == Decimal("25.00")
    assert pos.total_cost == Decimal("3750.00")
    # Realized PnL: (35*50 - 5) - (25*50) = 1745 - 1250 = 495
    assert pos.realized_pnl == Decimal("495.00")
    assert quantity_on(txs, 1, date(2025, 2, 15)) == Decimal("200")


def test_build_position_rejects_short_sell() -> None:
    txs = [
        TransactionEntity(
            asset_id=1,
            kind=TransactionKind.SELL,
            trade_date=date(2025, 1, 10),
            quantity=Decimal("10"),
            unit_price=Decimal("20.00"),
        )
    ]
    with pytest.raises(InsufficientQuantityError):
        build_position(txs)


# ---------------------------------------------------------------------------
# 2. Fixed Income Engine Tests
# ---------------------------------------------------------------------------
def test_regressive_taxes_and_business_days() -> None:
    assert regressive_iof_rate(1) == 0.96
    assert regressive_iof_rate(15) == 0.50
    assert regressive_iof_rate(30) == 0.0
    assert regressive_ir_rate(90) == 0.225
    assert regressive_ir_rate(200) == 0.200
    assert regressive_ir_rate(400) == 0.175
    assert regressive_ir_rate(800) == 0.150
    # Monday 2025-01-06 to Monday 2025-01-13 = 5 business days
    assert count_business_days(date(2025, 1, 6), date(2025, 1, 13)) == 5


def test_value_fixed_income_cdi_and_tax_exempt_lci() -> None:
    txs = [
        TransactionEntity(
            asset_id=10,
            kind=TransactionKind.BUY,
            trade_date=date(2024, 1, 2),
            quantity=Decimal("1"),
            unit_price=Decimal("10000.00"),
        )
    ]
    cdb_term = FixedIncomeTermEntity(
        instrument_kind=FixedIncomeInstrumentKind.CDB,
        indexer=FixedIncomeIndexer.CDI,
        contracted_rate=Decimal("1.10"),
        issue_date=date(2024, 1, 2),
        tax_exempt=False,
    )
    val_cdb = value_fixed_income_position(
        transactions=txs,
        term=cdb_term,
        as_of_date=date(2025, 1, 2),
        curves=RateCurves(annual_cdi_rate=0.1125),
    )
    assert val_cdb.gross_value > 11000.0
    assert val_cdb.income_tax > 0.0
    assert val_cdb.net_value < val_cdb.gross_value
    assert val_cdb.projected_12m_net_yield > 0.0

    lci_term = FixedIncomeTermEntity(
        instrument_kind=FixedIncomeInstrumentKind.LCI,
        indexer=FixedIncomeIndexer.CDI,
        contracted_rate=Decimal("0.95"),
        issue_date=date(2024, 1, 2),
        tax_exempt=True,
    )
    val_lci = value_fixed_income_position(
        transactions=txs,
        term=lci_term,
        as_of_date=date(2025, 1, 2),
        curves=RateCurves(annual_cdi_rate=0.1125),
    )
    assert val_lci.income_tax == 0.0
    assert val_lci.net_value == val_lci.gross_value


# ---------------------------------------------------------------------------
# 3. ARCA Allocation & Rebalancing Tests
# ---------------------------------------------------------------------------
def test_arca_targets_validation_and_rebalancing() -> None:
    targets = ArcaTargets.default()
    with pytest.raises(InvalidTargetsError):
        ArcaTargets({ArcaClass.ACOES: 50.0})

    current = {
        ArcaClass.ACOES: 3000.0,
        ArcaClass.REAL_ESTATE: 2500.0,
        ArcaClass.CAIXA: 2500.0,
        ArcaClass.ATIVOS_INTERNACIONAIS: 1000.0,
    }
    plan = distribute_by_targets(current, targets.as_fractions(), 1000.0)
    # Total after = 10000 -> ideal is 2500 per class.
    # Only ATIVOS_INTERNACIONAIS has a deficit (1500), so all 1000 goes to it!
    assert plan[ArcaClass.ATIVOS_INTERNACIONAIS] == 1000.0
    assert plan[ArcaClass.ACOES] == 0.0

    rows = compute_allocation(current, targets)
    assert len(rows) == 4


# ---------------------------------------------------------------------------
# 4. Optional Diagrama do Cerrado & Intra-Class Weight Strategies
# ---------------------------------------------------------------------------
def test_cerrado_scoring_and_optional_intra_class_strategies() -> None:
    questions = questions_for(AssetType.STOCK_BR)
    assert len(questions) == 12

    fundamentals = Fundamentals(
        symbol="WEGE3",
        return_on_equity=0.28,
        profit_margin=0.18,
        net_debt_to_ebitda=0.20,
        revenue_growth=0.15,
        dividend_yield=0.02,
        price_to_earnings=25.0,
        price_to_book=7.0,
        avg_daily_volume=150_000_000.0,
    )
    eval_on = evaluate(
        asset_type=AssetType.STOCK_BR,
        manual_answers={"governance": True, "perennial_sector": True},
        fundamentals=fundamentals,
        use_cerrado=True,
    )
    assert eval_on.score > 0
    assert eval_on.recommendation == Recommendation.APTO

    eval_off = evaluate(
        asset_type=AssetType.STOCK_BR,
        manual_answers={"governance": True},
        fundamentals=fundamentals,
        use_cerrado=False,
    )
    assert eval_off.recommendation == Recommendation.DESATIVADO

    weights_from_scores = target_weights_from_scores({"WEGE3": eval_on.score})
    assert weights_from_scores["WEGE3"] == 1.0

    # Strategy 1: EQUAL_WEIGHT (Cerrado ignored)
    w_equal = resolve_intra_class_weights(
        IntraClassStrategy.EQUAL_WEIGHT,
        ["WEGE3", "ITUB4"],
        cerrado_scores={"WEGE3": 8, "ITUB4": 4},
    )
    assert w_equal["WEGE3"] == 0.5
    assert w_equal["ITUB4"] == 0.5

    # Strategy 2: MANUAL_WEIGHT
    w_manual = resolve_intra_class_weights(
        IntraClassStrategy.MANUAL_WEIGHT,
        ["WEGE3", "ITUB4"],
        manual_weights={"WEGE3": 60.0, "ITUB4": 40.0},
    )
    assert w_manual["WEGE3"] == 0.6
    assert w_manual["ITUB4"] == 0.4

    # Strategy 3: CERRADO
    w_cerrado = resolve_intra_class_weights(
        IntraClassStrategy.CERRADO,
        ["WEGE3", "ITUB4"],
        cerrado_scores={"WEGE3": 8, "ITUB4": 4},
        cerrado_enabled={"WEGE3": True, "ITUB4": True},
    )
    assert w_cerrado["WEGE3"] > w_cerrado["ITUB4"]


# ---------------------------------------------------------------------------
# 5. Valuation Models (Graham & Bazin)
# ---------------------------------------------------------------------------
def test_graham_and_bazin_valuation() -> None:
    fair = graham_fair_value(eps=5.00, bvps=25.00)
    assert fair is not None
    assert round(fair, 2) == 53.03

    ceiling = bazin_ceiling_price(dividends_per_share=3.00, required_yield=0.06)
    assert ceiling == 50.00

    mos = margin_of_safety(fair_value=50.00, price=40.00)
    assert mos == 0.20

    summary = summarize_valuation(
        price=28.00,
        f=Fundamentals(
            symbol="BBAS3",
            earnings_per_share=6.00,
            book_value_per_share=30.00,
            dividends_per_share_ttm=2.60,
            price_to_earnings=4.67,
        ),
    )
    assert summary.graham_fair_value is not None
    assert summary.bazin_ceiling_price is not None


# ---------------------------------------------------------------------------
# 6. Portfolio Consolidation & Two-Level Contribution Planner
# ---------------------------------------------------------------------------
def test_consolidate_portfolio_and_contribution_planner() -> None:
    assets = [
        AssetEntity(
            id=1,
            ticker="WEGE3",
            name="WEG S.A.",
            asset_type=AssetType.STOCK_BR,
            arca_class=ArcaClass.ACOES,
            cerrado_answers={"roe": True, "governance": True, "profitable": True},
            transactions=(
                TransactionEntity(
                    asset_id=1,
                    kind=TransactionKind.BUY,
                    trade_date=date(2024, 6, 1),
                    quantity=Decimal("100"),
                    unit_price=Decimal("40.00"),
                ),
            ),
            earnings=(
                EarningEntity(
                    asset_id=1,
                    kind=EarningKind.DIVIDEND,
                    payment_date=date(2024, 9, 15),
                    gross_amount=Decimal("120.00"),
                ),
            ),
        ),
        AssetEntity(
            id=2,
            ticker="HGLG11",
            name="CSHG Logística",
            asset_type=AssetType.FII,
            arca_class=ArcaClass.REAL_ESTATE,
            cerrado_answers={"dy": True, "pvp": True, "multi_property": True},
            transactions=(
                TransactionEntity(
                    asset_id=2,
                    kind=TransactionKind.BUY,
                    trade_date=date(2024, 6, 1),
                    quantity=Decimal("25"),
                    unit_price=Decimal("160.00"),
                ),
            ),
            earnings=(
                EarningEntity(
                    asset_id=2,
                    kind=EarningKind.FII_YIELD,
                    payment_date=date(2024, 10, 15),
                    gross_amount=Decimal("320.00"),
                ),
            ),
        ),
        AssetEntity(
            id=3,
            ticker="CDB-110",
            name="CDB Liquidez Diária 110% CDI",
            asset_type=AssetType.FIXED_INCOME,
            arca_class=ArcaClass.CAIXA,
            fixed_income_term=FixedIncomeTermEntity(
                instrument_kind=FixedIncomeInstrumentKind.CDB,
                indexer=FixedIncomeIndexer.CDI,
                contracted_rate=Decimal("1.10"),
                issue_date=date(2024, 6, 1),
            ),
            transactions=(
                TransactionEntity(
                    asset_id=3,
                    kind=TransactionKind.BUY,
                    trade_date=date(2024, 6, 1),
                    quantity=Decimal("1"),
                    unit_price=Decimal("4000.00"),
                ),
            ),
        ),
        AssetEntity(
            id=4,
            ticker="IVV",
            name="iShares Core S&P 500 ETF",
            asset_type=AssetType.ETF_INTL,
            arca_class=ArcaClass.ATIVOS_INTERNACIONAIS,
            currency="USD",
            cerrado_answers={"global_leader": True, "low_fee": True},
            transactions=(
                TransactionEntity(
                    asset_id=4,
                    kind=TransactionKind.BUY,
                    trade_date=date(2024, 6, 1),
                    quantity=Decimal("2"),
                    unit_price=Decimal("500.00"),
                    fx_rate=Decimal("5.00"),
                ),
            ),
        ),
    ]
    quotes = {
        "WEGE3": Quote(symbol="WEGE3", price=50.00, currency="BRL"),
        "HGLG11": Quote(symbol="HGLG11", price=162.00, currency="BRL"),
        "IVV": Quote(symbol="IVV", price=550.00, currency="USD"),
    }
    fundamentals = {
        "WEGE3": Fundamentals(symbol="WEGE3", dividend_yield=0.025),
        "HGLG11": Fundamentals(symbol="HGLG11", dividend_yield=0.09),
        "IVV": Fundamentals(symbol="IVV", dividend_yield=0.015),
    }

    report = consolidate_portfolio(
        assets=assets,
        targets=ArcaTargets.default(),
        quotes=quotes,
        fundamentals_by_ticker=fundamentals,
        usd_brl_rate=5.20,
        as_of_date=date(2025, 1, 2),
    )

    assert len(report.positions) == 4
    assert report.total_invested_brl == 17200.00
    assert report.total_current_value_brl > report.total_invested_brl
    assert report.total_received_earnings_brl == 440.00
    assert report.total_consolidated_pnl_brl > 0.0
    assert report.total_projected_12m_yield_brl > 0.0

    # Test Contribution Planner both with Cerrado ON and OFF (EQUAL_WEIGHT)
    plan_with_cerrado = plan_contribution(
        report=report,
        targets=ArcaTargets.default(),
        amount_brl=2000.00,
        strategy_override=IntraClassStrategy.CERRADO,
    )
    assert len(plan_with_cerrado.orders) > 0

    plan_without_cerrado = plan_contribution(
        report=report,
        targets=ArcaTargets.default(),
        amount_brl=2000.00,
        strategy_override=IntraClassStrategy.EQUAL_WEIGHT,
    )
    assert len(plan_without_cerrado.orders) > 0
