"""Unit tests for consolidation: FX effects, invalid ledgers, projections and the planner."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.market.entities import Quote
from domain.policy.services.allocation import ArcaTargets
from domain.portfolio.services.consolidation import (
    LEDGER_INVALID,
    ProjectionAssumptions,
    consolidate_portfolio,
    plan_contribution,
)
from domain.shared.entities import (
    AssetEntity,
    EarningEntity,
    FixedIncomeTermEntity,
    TransactionEntity,
)
from domain.shared.enums import (
    ArcaClass,
    AssetType,
    EarningKind,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    TransactionKind,
)

AS_OF = date(2025, 6, 30)


def _tx(asset_id: int, kind: TransactionKind, on: date, qty: str, price: str, fx: str = "1"):
    return TransactionEntity(
        asset_id=asset_id,
        kind=kind,
        trade_date=on,
        quantity=Decimal(qty),
        unit_price=Decimal(price),
        fx_rate=Decimal(fx),
    )


def _stock(asset_id: int, ticker: str, *txs: TransactionEntity, **kwargs) -> AssetEntity:
    return AssetEntity(
        id=asset_id,
        ticker=ticker,
        name=ticker,
        asset_type=kwargs.pop("asset_type", AssetType.STOCK_BR),
        transactions=txs,
        **kwargs,
    )


def test_invalid_ledger_is_reported_and_excluded_from_totals() -> None:
    good = _stock(1, "WEGE3", _tx(1, TransactionKind.BUY, date(2025, 1, 2), "10", "40"))
    broken = _stock(2, "PETR4", _tx(2, TransactionKind.SELL, date(2025, 1, 2), "5", "30"))

    report = consolidate_portfolio(
        [good, broken],
        ArcaTargets.default(),
        quotes={"WEGE3": Quote("WEGE3", 50.0), "PETR4": Quote("PETR4", 35.0)},
        as_of_date=AS_OF,
    )

    by_ticker = {p.ticker: p for p in report.positions}
    assert by_ticker["PETR4"].ledger_status == LEDGER_INVALID
    assert "Cannot sell" in (by_ticker["PETR4"].ledger_message or "")
    assert by_ticker["PETR4"].current_value_brl == 0.0
    assert report.total_current_value_brl == 500.0
    acoes = next(a for a in report.allocations if a.arca_class == ArcaClass.ACOES)
    assert acoes.current_value == 500.0


def test_usd_earnings_use_payment_fx_and_fx_pnl_is_split_from_price() -> None:
    asset = _stock(
        1,
        "AAPL",
        _tx(1, TransactionKind.BUY, date(2025, 1, 10), "10", "100", fx="5.0"),
        asset_type=AssetType.STOCK_INTL,
        earnings=(
            EarningEntity(
                asset_id=1,
                kind=EarningKind.DIVIDEND,
                payment_date=date(2025, 3, 1),
                gross_amount=Decimal("10"),
                fx_rate=Decimal("5.2"),
            ),
        ),
    )

    report = consolidate_portfolio(
        [asset],
        ArcaTargets.default(),
        quotes={"AAPL": Quote("AAPL", 110.0, currency="USD")},
        usd_brl_rate=6.0,
        as_of_date=AS_OF,
    )

    pos = report.positions[0]
    assert pos.received_earnings_brl == pytest.approx(52.0)
    # Cost 1000 USD bought at 5.0 and marked at 6.0: R$ 1000 of FX gain.
    assert pos.fx_pnl_brl == pytest.approx(1000.0)
    # Remaining unrealized gain is the price effect: 10 x 10 USD x 6.0.
    assert pos.unrealized_pnl_brl - pos.fx_pnl_brl == pytest.approx(600.0)
    assert report.total_fx_pnl_brl == pytest.approx(1000.0)


def test_projection_assumptions_drive_and_are_reported() -> None:
    asset = _stock(1, "WEGE3", _tx(1, TransactionKind.BUY, date(2025, 1, 2), "10", "40"))
    premises = ProjectionAssumptions(equity_capital_growth_rate=0.2)

    report = consolidate_portfolio(
        [asset],
        ArcaTargets.default(),
        quotes={"WEGE3": Quote("WEGE3", 50.0)},
        assumptions=premises,
        as_of_date=AS_OF,
    )

    assert report.positions[0].projected_12m_yield_brl == pytest.approx(100.0)
    assert report.projection_assumptions["equity_capital_growth_rate"] == 0.2


def test_fixed_income_partial_redemptions_do_not_invalidate_ledger() -> None:
    term = FixedIncomeTermEntity(
        instrument_kind=FixedIncomeInstrumentKind.CDB,
        indexer=FixedIncomeIndexer.PRE,
        contracted_rate=Decimal("0.10"),
        issue_date=date(2025, 1, 2),
    )
    cdb = AssetEntity(
        id=1,
        ticker="CDB-PRE",
        name="CDB",
        asset_type=AssetType.FIXED_INCOME,
        fixed_income_term=term,
        transactions=(
            _tx(1, TransactionKind.BUY, date(2025, 1, 2), "1", "1000"),
            _tx(1, TransactionKind.SELL, date(2025, 3, 3), "1", "200"),
            _tx(1, TransactionKind.SELL, date(2025, 4, 1), "1", "200"),
        ),
    )

    pos = consolidate_portfolio([cdb], ArcaTargets.default(), as_of_date=AS_OF).positions[0]

    assert pos.ledger_status == "VALID"
    assert 550.0 < pos.invested_value_brl < 650.0
    assert pos.realized_pnl_brl > 0.0


def test_budget_of_class_without_assets_goes_to_other_classes() -> None:
    stock = AssetEntity(
        id=1, ticker="CAIXA", name="Caixa", asset_type=AssetType.CASH, manual_price=Decimal("1")
    )
    report = consolidate_portfolio([stock], ArcaTargets.default(), as_of_date=AS_OF)

    plan = plan_contribution(report, ArcaTargets.default(), 1000.0)

    assert plan.executed_total_brl == pytest.approx(1000.0)
    assert plan.unallocated_cash_brl == 0.0


def test_emergency_reserve_is_valued_but_kept_out_of_arca() -> None:
    from domain.shared.enums import AssetPurpose

    stock = _stock(1, "WEGE3", _tx(1, TransactionKind.BUY, date(2025, 1, 2), "10", "40"))
    reserve = AssetEntity(
        id=2,
        ticker="RESERVA",
        name="Reserva de emergência",
        asset_type=AssetType.CASH,
        manual_price=Decimal("1"),
        purpose=AssetPurpose.EMERGENCY_RESERVE,
        transactions=(_tx(2, TransactionKind.BUY, date(2025, 1, 2), "20000", "1"),),
    )

    report = consolidate_portfolio(
        [stock, reserve],
        ArcaTargets.default(),
        quotes={"WEGE3": Quote("WEGE3", 50.0)},
        as_of_date=AS_OF,
    )

    assert report.total_current_value_brl == 20500.0
    assert report.value_by_purpose_brl == {
        "ARCA": 500.0,
        "EMERGENCY_RESERVE": 20000.0,
        "OTHER": 0.0,
    }
    caixa = next(a for a in report.allocations if a.arca_class == ArcaClass.CAIXA)
    acoes = next(a for a in report.allocations if a.arca_class == ArcaClass.ACOES)
    assert caixa.current_value == 0.0
    assert acoes.current_pct == 100.0
    reserve_pos = next(p for p in report.positions if p.ticker == "RESERVA")
    assert reserve_pos.class_target_weight_pct == 0.0

    plan = plan_contribution(report, ArcaTargets.default(), 1000.0)
    assert "RESERVA" not in {o.ticker for o in plan.orders}


def _single_class_plan(*assets: AssetEntity, prices: dict[str, float], **kwargs):
    """Everything goes to Ações (target 100%), so only the intra-class rules decide."""
    targets = ArcaTargets(
        {ArcaClass.ACOES: 100.0, ArcaClass.REAL_ESTATE: 0.0, ArcaClass.CAIXA: 0.0}
        | {ArcaClass.ATIVOS_INTERNACIONAIS: 0.0}
    )
    report = consolidate_portfolio(
        list(assets),
        targets,
        quotes={t: Quote(t, p) for t, p in prices.items()},
        as_of_date=AS_OF,
    )
    plan = plan_contribution(report, targets, 1000.0, **kwargs)
    return {o.ticker: o for o in plan.orders}


def test_order_reasons_explain_each_asset_of_the_class() -> None:
    from domain.shared.enums import ContributionOrderReason, IntraClassStrategy

    held = _stock(1, "WEGE3", _tx(1, TransactionKind.BUY, date(2025, 1, 2), "100", "40"))
    orders = _single_class_plan(
        held,
        _stock(2, "ITUB4"),
        _stock(3, "BIGG3"),
        prices={"WEGE3": 50.0, "ITUB4": 30.0, "BIGG3": 3000.0},
        strategy_override=IntraClassStrategy.EQUAL_WEIGHT,
    )

    # Above its 1/3 weight already; ITUB4 and BIGG3 split the R$ 1.000 by what they lack.
    assert orders["WEGE3"].reason == ContributionOrderReason.ABOVE_TARGET
    assert orders["WEGE3"].class_current_weight_pct == 100.0
    assert orders["BIGG3"].reason == ContributionOrderReason.PRICE_ABOVE_BUDGET
    assert orders["BIGG3"].allocated_amount_brl == pytest.approx(500.0)
    # ITUB4 buys its own share and then the leftovers BIGG3 could not spend.
    assert orders["ITUB4"].reason == ContributionOrderReason.BOUGHT
    assert orders["ITUB4"].executed_amount_brl == pytest.approx(990.0)
    assert orders["ITUB4"].leftover_amount_brl == pytest.approx(510.0)


def test_asset_bought_only_with_leftovers_is_marked() -> None:
    from domain.shared.enums import ContributionOrderReason, IntraClassStrategy

    held = _stock(1, "WEGE3", _tx(1, TransactionKind.BUY, date(2025, 1, 2), "100", "40"))
    orders = _single_class_plan(
        held,
        _stock(3, "BIGG3"),
        prices={"WEGE3": 50.0, "BIGG3": 3000.0},
        strategy_override=IntraClassStrategy.EQUAL_WEIGHT,
    )

    assert orders["BIGG3"].reason == ContributionOrderReason.PRICE_ABOVE_BUDGET
    assert orders["WEGE3"].reason == ContributionOrderReason.LEFTOVER_FILL
    assert orders["WEGE3"].leftover_amount_brl == orders["WEGE3"].executed_amount_brl == 1000.0


def test_asset_without_manual_weight_is_marked_zero_weight() -> None:
    from domain.shared.enums import ContributionOrderReason, IntraClassStrategy

    orders = _single_class_plan(
        _stock(1, "WEGE3", custom_class_weight=Decimal("0")),
        _stock(2, "ITUB4", custom_class_weight=Decimal("1")),
        prices={"WEGE3": 50.0, "ITUB4": 30.0},
        strategy_override=IntraClassStrategy.MANUAL_WEIGHT,
    )

    assert orders["WEGE3"].reason == ContributionOrderReason.ZERO_WEIGHT
    assert orders["ITUB4"].reason == ContributionOrderReason.BOUGHT


def test_class_rationale_names_the_first_level_rule() -> None:
    from domain.shared.enums import ContributionClassReason, IntraClassStrategy

    assets = [
        _stock(1, "WEGE3", _tx(1, TransactionKind.BUY, date(2025, 1, 2), "100", "40")),
        _stock(
            2,
            "HGLG11",
            _tx(2, TransactionKind.BUY, date(2025, 1, 2), "5", "150"),
            asset_type=AssetType.FII,
            arca_class=ArcaClass.REAL_ESTATE,
        ),
        AssetEntity(
            id=3,
            ticker="CAIXA",
            name="Caixa",
            asset_type=AssetType.CASH,
            arca_class=ArcaClass.CAIXA,
            manual_price=Decimal("1"),
            transactions=(_tx(3, TransactionKind.BUY, date(2025, 1, 2), "1000", "1"),),
        ),
    ]
    report = consolidate_portfolio(
        assets,
        ArcaTargets.default(),
        quotes={"WEGE3": Quote("WEGE3", 50.0), "HGLG11": Quote("HGLG11", 160.0)},
        bands=dict.fromkeys(ArcaClass, 5.0),
        as_of_date=AS_OF,
    )
    plan = plan_contribution(
        report,
        ArcaTargets.default(),
        1000.0,
        class_strategies=dict.fromkeys(ArcaClass, IntraClassStrategy.CERRADO),
    )
    by_class = {r.arca_class: r for r in plan.class_rationale}

    # R$ 6.800 + 1.000: the three classes below the band lack R$ 4.050, more than the aporte.
    assert by_class[ArcaClass.ACOES].reason == ContributionClassReason.BELOW_BAND_PRIORITY
    assert by_class[ArcaClass.ACOES].band_status == "ABOVE"
    assert by_class[ArcaClass.REAL_ESTATE].reason == ContributionClassReason.REFILL_BELOW_BAND
    assert by_class[ArcaClass.REAL_ESTATE].deficit_brl == pytest.approx(1150.0)
    assert by_class[ArcaClass.REAL_ESTATE].first_level_brl == pytest.approx(
        1000 * 1150 / 4050, 0.01
    )
    assert by_class[ArcaClass.CAIXA].reason == ContributionClassReason.REFILL_BELOW_BAND
    intl = by_class[ArcaClass.ATIVOS_INTERNACIONAIS]
    assert intl.reason == ContributionClassReason.NO_ELIGIBLE_ASSETS
    assert intl.eligible_assets == 0 and intl.received_brl == 0.0
    assert all(r.strategy == IntraClassStrategy.CERRADO for r in plan.class_rationale)
    assert not any(r.strategy_overridden for r in plan.class_rationale)
    assert sum(r.received_brl for r in plan.class_rationale) == pytest.approx(
        plan.executed_total_brl
    )


def test_class_rationale_inside_the_bands_follows_the_deficit() -> None:
    from domain.shared.enums import ContributionClassReason, IntraClassStrategy

    assets = [
        _stock(1, "WEGE3", _tx(1, TransactionKind.BUY, date(2025, 1, 2), "60", "40")),
        _stock(
            2,
            "AAPL",
            _tx(2, TransactionKind.BUY, date(2025, 1, 2), "10", "100"),
            asset_type=AssetType.STOCK_INTL,
            arca_class=ArcaClass.ATIVOS_INTERNACIONAIS,
        ),
    ]
    targets = ArcaTargets(
        {ArcaClass.ACOES: 50.0, ArcaClass.ATIVOS_INTERNACIONAIS: 50.0}
        | {ArcaClass.REAL_ESTATE: 0.0, ArcaClass.CAIXA: 0.0}
    )
    report = consolidate_portfolio(
        assets,
        targets,
        quotes={"WEGE3": Quote("WEGE3", 50.0), "AAPL": Quote("AAPL", 100.0)},
        usd_brl_rate=1.0,
        bands=dict.fromkeys(ArcaClass, 30.0),
        as_of_date=AS_OF,
    )
    plan = plan_contribution(
        report, targets, 1000.0, strategy_override=IntraClassStrategy.EQUAL_WEIGHT
    )
    by_class = {r.arca_class: r for r in plan.class_rationale}

    # Ações 3.000 x Internacional 1.000, both inside a 30-point band: only the deficit counts.
    intl = by_class[ArcaClass.ATIVOS_INTERNACIONAIS]
    assert intl.reason == ContributionClassReason.BELOW_TARGET
    assert intl.band_status == "WITHIN" and intl.first_level_brl == pytest.approx(1000.0)
    assert by_class[ArcaClass.ACOES].reason == ContributionClassReason.ABOVE_TARGET
    assert by_class[ArcaClass.REAL_ESTATE].reason == ContributionClassReason.ABOVE_TARGET
    assert all(r.strategy == IntraClassStrategy.EQUAL_WEIGHT for r in plan.class_rationale)
    assert all(r.strategy_overridden for r in plan.class_rationale)
