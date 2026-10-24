"""Unit tests for consolidation: FX effects, invalid ledgers, projections and the planner."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fincontrol_core.arca.allocation import ArcaTargets
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
    TransactionKind,
)
from fincontrol_core.market.models import Quote
from fincontrol_core.portfolio.consolidation import (
    LEDGER_INVALID,
    ProjectionAssumptions,
    consolidate_portfolio,
    plan_contribution,
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
