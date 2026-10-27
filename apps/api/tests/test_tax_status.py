"""Unit tests for the per-lot tax status (item 24.2)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from domain.portfolio.services.fixed_income import RateCurves, value_fixed_income_position
from domain.shared.entities import AssetEntity, FixedIncomeTermEntity, TransactionEntity
from domain.shared.enums import (
    AssetType,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    TransactionKind,
)
from domain.tax.entities import TaxRegime
from domain.tax.services.status import asset_tax_status

START = date(2026, 1, 2)
CURVES = RateCurves(annual_cdi_rate=0.14, annual_ipca_rate=0.045)


def _buy(day: date, amount: str, tx_id: int = 1) -> TransactionEntity:
    return TransactionEntity(
        asset_id=1,
        kind=TransactionKind.BUY,
        trade_date=day,
        quantity=Decimal("1"),
        unit_price=Decimal(amount),
        id=tx_id,
    )


def _fixed_income(
    *,
    tax_exempt: bool = False,
    maturity: date | None = None,
    transactions: tuple[TransactionEntity, ...] = (),
) -> AssetEntity:
    term = FixedIncomeTermEntity(
        instrument_kind=FixedIncomeInstrumentKind.LCA
        if tax_exempt
        else FixedIncomeInstrumentKind.CDB,
        indexer=FixedIncomeIndexer.CDI,
        contracted_rate=Decimal("1.10"),
        issue_date=START,
        maturity_date=maturity,
        tax_exempt=tax_exempt,
    )
    return AssetEntity(
        id=1,
        ticker="CDB-X",
        name="CDB X",
        asset_type=AssetType.FIXED_INCOME,
        fixed_income_term=term,
        transactions=transactions or (_buy(START, "10000"),),
    )


def test_lot_at_day_180_shows_the_drop_on_day_181() -> None:
    asset = _fixed_income()
    status = asset_tax_status(asset, START + timedelta(days=180), curves=CURVES)

    lot = status.lots[0]
    assert status.is_fixed_income
    assert lot.holding_days == 180
    assert lot.income_tax_rate == 0.225
    assert lot.next_bracket_date == START + timedelta(days=181)
    assert lot.days_to_next_bracket == 1
    assert lot.next_income_tax_rate == 0.2
    assert lot.iof_due == 0.0
    assert lot.iof_free_date is None
    # Waiting one day saves 2.5 points of IR on the whole gain.
    assert lot.tax_saving_by_waiting == pytest.approx(lot.gross_yield * 0.025, rel=0.02)
    assert lot.net_gain_by_waiting is not None and lot.net_gain_by_waiting > 0
    assert status.next_bracket_date == lot.next_bracket_date
    assert status.tax_saving_by_waiting == lot.tax_saving_by_waiting


def test_lot_on_day_181_moves_to_the_20_percent_bracket() -> None:
    status = asset_tax_status(_fixed_income(), START + timedelta(days=181), curves=CURVES)
    lot = status.lots[0]
    assert lot.income_tax_rate == 0.2
    assert lot.next_bracket_date == START + timedelta(days=361)
    assert lot.next_income_tax_rate == 0.175


@pytest.mark.parametrize(
    ("days", "rate", "next_rate"),
    [(360, 0.2, 0.175), (361, 0.175, 0.15), (720, 0.175, 0.15), (721, 0.15, None)],
)
def test_bracket_boundaries(days: int, rate: float, next_rate: float | None) -> None:
    status = asset_tax_status(_fixed_income(), START + timedelta(days=days), curves=CURVES)
    lot = status.lots[0]
    assert lot.income_tax_rate == rate
    assert lot.next_income_tax_rate == next_rate
    if next_rate is None:
        assert lot.next_bracket_date is None
        assert lot.tax_saving_by_waiting is None


def test_iof_still_due_until_day_30() -> None:
    day29 = asset_tax_status(_fixed_income(), START + timedelta(days=29), curves=CURVES).lots[0]
    assert day29.iof_rate == pytest.approx(0.03, abs=1e-4)
    assert day29.iof_due > 0
    assert day29.iof_free_date == START + timedelta(days=30)

    day30 = asset_tax_status(_fixed_income(), START + timedelta(days=30), curves=CURVES).lots[0]
    assert day30.iof_due == 0.0
    assert day30.iof_rate == 0.0
    assert day30.iof_free_date is None


def test_status_matches_the_fixed_income_engine() -> None:
    asset = _fixed_income(transactions=(_buy(START, "10000"), _buy(date(2026, 6, 1), "5000", 2)))
    as_of = date(2026, 10, 27)
    status = asset_tax_status(asset, as_of, curves=CURVES)
    assert asset.fixed_income_term is not None
    valuation = value_fixed_income_position(
        asset.transactions, asset.fixed_income_term, as_of, curves=CURVES
    )
    assert len(status.lots) == 2
    assert status.gross_value == pytest.approx(valuation.gross_value, abs=0.02)
    assert status.income_tax_due == pytest.approx(valuation.income_tax, abs=0.02)
    assert status.iof_due == pytest.approx(valuation.iof_tax, abs=0.02)
    assert status.net_value == pytest.approx(valuation.net_value, abs=0.02)
    # Each lot has its own bracket: the older one is already at 20%.
    assert [lot.income_tax_rate for lot in status.lots] == [0.2, 0.225]
    assert status.next_bracket_date == min(
        lot.next_bracket_date for lot in status.lots if lot.next_bracket_date
    )


def test_exempt_lot_has_no_tax_and_no_next_bracket() -> None:
    status = asset_tax_status(
        _fixed_income(tax_exempt=True), START + timedelta(days=10), curves=CURVES
    )
    lot = status.lots[0]
    assert status.tax_exempt
    assert status.regimes[0].regime == TaxRegime.FIXED_INCOME_EXEMPT
    assert lot.income_tax_rate == 0.0
    assert lot.iof_due == 0.0
    assert lot.income_tax_due == 0.0
    assert lot.next_bracket_date is None
    assert lot.net_value == lot.gross_value


def test_next_bracket_after_maturity_is_not_reported() -> None:
    asset = _fixed_income(maturity=START + timedelta(days=170))
    status = asset_tax_status(asset, START + timedelta(days=100), curves=CURVES)
    assert status.lots[0].next_bracket_date is None


def test_matured_bond_is_valued_at_maturity_without_next_bracket() -> None:
    asset = _fixed_income(maturity=START + timedelta(days=400))
    status = asset_tax_status(asset, START + timedelta(days=500), curves=CURVES)
    lot = status.lots[0]
    assert lot.holding_days == 400
    assert lot.income_tax_rate == 0.175
    assert lot.next_bracket_date is None


def test_fully_redeemed_position_has_no_lots() -> None:
    sale_day = START + timedelta(days=50)
    open_asset = _fixed_income()
    assert open_asset.fixed_income_term is not None
    gross = value_fixed_income_position(
        open_asset.transactions, open_asset.fixed_income_term, sale_day, curves=CURVES
    ).gross_value
    sell = TransactionEntity(
        asset_id=1,
        kind=TransactionKind.SELL,
        trade_date=sale_day,
        quantity=Decimal("1"),
        unit_price=Decimal(str(gross)),
        id=2,
    )
    asset = _fixed_income(transactions=(_buy(START, "10000"), sell))
    status = asset_tax_status(asset, START + timedelta(days=60), curves=CURVES)
    assert status.lots == ()
    assert status.net_value == 0.0
    assert status.next_bracket_date is None


@pytest.mark.parametrize(
    ("asset_type", "regime", "rate"),
    [
        (AssetType.STOCK_BR, TaxRegime.STOCK_SWING_TRADE, 0.15),
        (AssetType.FII, TaxRegime.FII_CAPITAL_GAIN, 0.20),
        (AssetType.STOCK_INTL, TaxRegime.FOREIGN_ANNUAL, 0.15),
        (AssetType.CRYPTO, TaxRegime.CRYPTO_CAPITAL_GAIN, 0.15),
    ],
)
def test_market_assets_get_the_informative_regime(
    asset_type: AssetType, regime: TaxRegime, rate: float
) -> None:
    asset = AssetEntity(id=5, ticker="ABCD3", name="X", asset_type=asset_type)
    status = asset_tax_status(asset, date(2026, 10, 27))
    assert not status.is_fixed_income
    assert status.lots == ()
    assert status.regimes[0].regime == regime
    assert status.regimes[0].current_rate == rate
    assert status.regimes[0].legal_basis


def test_stock_jcp_regime_depends_on_the_reference_date() -> None:
    asset = AssetEntity(id=5, ticker="ITUB4", name="Itaú", asset_type=AssetType.STOCK_BR)
    by_regime_2025 = {
        r.regime: r.current_rate for r in asset_tax_status(asset, date(2025, 6, 1)).regimes
    }
    by_regime_2026 = {
        r.regime: r.current_rate for r in asset_tax_status(asset, date(2026, 6, 1)).regimes
    }
    assert by_regime_2025[TaxRegime.JCP_WITHHOLDING] == 0.15
    assert by_regime_2026[TaxRegime.JCP_WITHHOLDING] == 0.175
    assert by_regime_2025[TaxRegime.DIVIDEND_WITHHOLDING] == 0.0
    assert by_regime_2026[TaxRegime.DIVIDEND_WITHHOLDING] == 0.10
