"""Unit tests for the fixed income curve engine (ADR 0006 units, SELIC/IPCA, redemptions)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.errors import ValidationError
from core.helpers.calendar import business_days_between
from domain.portfolio.services.fixed_income import (
    RateCurves,
    accrual_factor,
    implied_purchase_rate,
    replay_lots,
    value_fixed_income_position,
)
from domain.portfolio.services.positions import InsufficientQuantityError
from domain.shared.entities import FixedIncomeTermEntity, TransactionEntity
from domain.shared.enums import (
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    TransactionKind,
)


def _term(indexer: FixedIncomeIndexer, rate: str, **kwargs) -> FixedIncomeTermEntity:
    return FixedIncomeTermEntity(
        instrument_kind=FixedIncomeInstrumentKind.CDB,
        indexer=indexer,
        contracted_rate=Decimal(rate),
        issue_date=kwargs.pop("issue_date", date(2025, 1, 2)),
        **kwargs,
    )


def _tx(kind: TransactionKind, on: date, amount: str, fees: str = "0") -> TransactionEntity:
    return TransactionEntity(
        asset_id=1,
        kind=kind,
        trade_date=on,
        quantity=Decimal("1"),
        unit_price=Decimal(amount),
        fees=Decimal(fees),
    )


@pytest.mark.parametrize(
    ("indexer", "rate"),
    [
        (FixedIncomeIndexer.CDI, "110"),
        (FixedIncomeIndexer.CDI, "0.10"),
        (FixedIncomeIndexer.SELIC, "100"),
        (FixedIncomeIndexer.PRE, "12"),
        (FixedIncomeIndexer.IPCA, "6.5"),
        (FixedIncomeIndexer.IPCA, "-0.01"),
    ],
)
def test_contracted_rate_outside_canonical_range_is_rejected(
    indexer: FixedIncomeIndexer, rate: str
) -> None:
    with pytest.raises(ValidationError, match="ADR 0006") as err:
        _term(indexer, rate)
    assert err.value.code == "INVALID_CONTRACTED_RATE"


def test_cdi_accrual_falls_back_for_missing_days_and_reports_coverage() -> None:
    start, end = date(2025, 6, 2), date(2025, 6, 9)
    days = business_days_between(start, end)
    curves = RateCurves(cdi_daily={days[0]: 0.0005}, annual_cdi_rate=0.15)

    accrual = accrual_factor(_term(FixedIncomeIndexer.CDI, "1.0"), start, end, curves)

    fallback = 1.15 ** (1 / 252) - 1
    assert accrual.business_days == len(days) == 5
    assert accrual.covered_days == 1
    assert accrual.factor == pytest.approx(1.0005 * (1 + fallback) ** 4)


def test_selic_uses_selic_series_then_cdi_series() -> None:
    start, end = date(2025, 6, 2), date(2025, 6, 4)
    d1, d2 = business_days_between(start, end)
    curves = RateCurves(selic_daily={d1: 0.0006}, cdi_daily={d1: 0.0001, d2: 0.0004})

    accrual = accrual_factor(_term(FixedIncomeIndexer.SELIC, "1.0"), start, end, curves)

    assert accrual.factor == pytest.approx(1.0006 * 1.0004)
    assert accrual.covered_days == 2


def test_ipca_accrues_monthly_index_pro_rata_by_business_days() -> None:
    # (Feb 28, Mar 31] 2025: all March business days (19, Carnival excluded).
    start, end = date(2025, 2, 28), date(2025, 3, 31)
    curves = RateCurves(ipca_monthly={(2025, 3): 0.0056})

    accrual = accrual_factor(_term(FixedIncomeIndexer.IPCA, "0.06"), start, end, curves)

    assert accrual.business_days == 19
    assert accrual.factor == pytest.approx(1.0056 * 1.06 ** (19 / 252))


def test_ipca_month_without_index_uses_annual_fallback() -> None:
    curves = RateCurves(annual_ipca_rate=0.045)
    accrual = accrual_factor(
        _term(FixedIncomeIndexer.IPCA, "0.0"), date(2025, 2, 28), date(2025, 3, 31), curves
    )
    assert accrual.covered_days == 0
    assert accrual.factor == pytest.approx(1.045 ** (1 / 12))


def test_full_redemption_realizes_net_yield_and_closes_position() -> None:
    term = _term(FixedIncomeIndexer.PRE, "0.12", issue_date=date(2024, 1, 2))
    redeem_on = date(2025, 1, 2)
    open_value = value_fixed_income_position(
        [_tx(TransactionKind.BUY, date(2024, 1, 2), "1000")], term, redeem_on
    )

    closed = value_fixed_income_position(
        [
            _tx(TransactionKind.BUY, date(2024, 1, 2), "1000"),
            _tx(TransactionKind.SELL, redeem_on, str(open_value.gross_value), fees="1"),
        ],
        term,
        redeem_on,
    )

    assert closed.invested_principal == 0.0
    assert closed.net_value == 0.0
    # 366 days held -> 17.5% income tax on the yield; fees reduce the realized result.
    assert closed.realized_pnl == pytest.approx(open_value.gross_yield * 0.825 - 1, abs=0.02)


def test_redemption_above_position_value_is_rejected() -> None:
    term = _term(FixedIncomeIndexer.PRE, "0.10")
    with pytest.raises(InsufficientQuantityError, match="exceeds the position value"):
        value_fixed_income_position(
            [
                _tx(TransactionKind.BUY, date(2025, 1, 2), "1000"),
                _tx(TransactionKind.SELL, date(2025, 2, 3), "2000"),
            ],
            term,
            date(2025, 3, 3),
        )


def test_accrual_stops_at_maturity_and_projection_is_zero_afterwards() -> None:
    term = _term(FixedIncomeIndexer.PRE, "0.10", maturity_date=date(2025, 6, 30))
    txs = [_tx(TransactionKind.BUY, date(2025, 1, 2), "1000")]

    at_maturity = value_fixed_income_position(txs, term, date(2025, 6, 30))
    after = value_fixed_income_position(txs, term, date(2025, 9, 30))

    assert after.gross_value == at_maturity.gross_value
    assert after.projected_12m_net_yield == 0.0


def test_projection_is_capped_at_maturity() -> None:
    term = _term(FixedIncomeIndexer.PRE, "0.10", maturity_date=date(2025, 9, 30))
    txs = [_tx(TransactionKind.BUY, date(2025, 1, 2), "1000")]

    now = value_fixed_income_position(txs, term, date(2025, 6, 30))
    at_maturity = value_fixed_income_position(txs, term, date(2025, 9, 30))

    assert now.projected_12m_net_yield == pytest.approx(
        at_maturity.net_value - now.net_value, abs=0.02
    )


def _treasury_term(**kwargs) -> FixedIncomeTermEntity:
    return FixedIncomeTermEntity(
        instrument_kind=kwargs.pop("instrument_kind", FixedIncomeInstrumentKind.TESOURO_PRE),
        indexer=FixedIncomeIndexer.PRE,
        contracted_rate=Decimal(kwargs.pop("rate", "0.1526")),
        maturity_date=kwargs.pop("maturity_date", date(2029, 1, 1)),
        **kwargs,
    )


def _ltn_buy(on: date, quantity: str, unit_price: str) -> TransactionEntity:
    return TransactionEntity(
        asset_id=1,
        kind=TransactionKind.BUY,
        trade_date=on,
        quantity=Decimal(quantity),
        unit_price=Decimal(unit_price),
    )


def _ltn_price(rate: float, on: date, maturity: date = date(2029, 1, 1)) -> str:
    business_days = len(business_days_between(on, maturity))
    return f"{1000.0 / (1.0 + rate) ** (business_days / 252.0):.6f}"


def test_issue_date_is_optional_and_informational() -> None:
    txs = [_tx(TransactionKind.BUY, date(2025, 2, 20), "1000")]
    without = value_fixed_income_position(
        txs, _term(FixedIncomeIndexer.PRE, "0.12", issue_date=None), date(2025, 8, 1)
    )
    later = value_fixed_income_position(
        txs, _term(FixedIncomeIndexer.PRE, "0.12", issue_date=date(2025, 6, 1)), date(2025, 8, 1)
    )
    business_days = len(business_days_between(date(2025, 2, 20), date(2025, 8, 1)))

    assert without == later
    assert without.gross_yield == pytest.approx(
        1000.0 * (1.12 ** (business_days / 252.0) - 1.0), abs=0.01
    )


def test_implied_purchase_rate_recovers_the_ltn_rate_from_the_price() -> None:
    on = date(2026, 3, 17)
    term = _treasury_term()

    rate = implied_purchase_rate(term, on, float(_ltn_price(0.1375, on)))

    assert rate == pytest.approx(0.1375, abs=1e-6)


@pytest.mark.parametrize(
    ("term_kwargs", "unit_price", "on"),
    [
        ({"semiannual_coupons": True}, 700.0, date(2026, 3, 17)),
        ({"instrument_kind": FixedIncomeInstrumentKind.TESOURO_IPCA}, 700.0, date(2026, 3, 17)),
        ({"maturity_date": None}, 700.0, date(2026, 3, 17)),
        ({}, 700.0, date(2029, 1, 1)),
        ({}, 1000.0, date(2026, 3, 17)),
        ({}, 0.0, date(2026, 3, 17)),
        ({}, 1.0, date(2028, 12, 1)),
    ],
)
def test_implied_purchase_rate_is_none_when_it_cannot_be_implied(
    term_kwargs: dict, unit_price: float, on: date
) -> None:
    if term_kwargs.get("instrument_kind") == FixedIncomeInstrumentKind.TESOURO_IPCA:
        term = FixedIncomeTermEntity(
            instrument_kind=FixedIncomeInstrumentKind.TESOURO_IPCA,
            indexer=FixedIncomeIndexer.IPCA,
            contracted_rate=Decimal("0.07"),
            maturity_date=date(2029, 5, 15),
        )
    else:
        term = _treasury_term(**term_kwargs)

    assert implied_purchase_rate(term, on, unit_price) is None


def test_each_ltn_purchase_accrues_at_the_rate_it_was_bought() -> None:
    first, second, today = date(2025, 3, 17), date(2026, 3, 17), date(2026, 10, 27)
    txs = [
        _ltn_buy(first, "1", _ltn_price(0.15, first)),
        _ltn_buy(second, "2", _ltn_price(0.13, second)),
    ]
    term = _treasury_term(rate="0.20")

    lots, _ = replay_lots(txs, term, today)
    valuation = value_fixed_income_position(txs, term, today)

    assert [round(lot.rate or 0.0, 6) for lot in lots] == [0.15, 0.13]
    expected = sum(
        lot.principal
        * ((1.0 + (lot.rate or 0.0)) ** (len(business_days_between(lot.start, today)) / 252.0))
        for lot in lots
    )
    assert valuation.gross_value == pytest.approx(expected, abs=0.02)


def test_ltn_reaches_face_value_at_maturity() -> None:
    on = date(2026, 3, 17)
    txs = [_ltn_buy(on, "2.45", _ltn_price(0.1375, on))]

    valuation = value_fixed_income_position(txs, _treasury_term(), date(2029, 1, 1))

    assert valuation.gross_value == pytest.approx(2450.0, abs=0.01)


def test_partial_redemption_keeps_the_lot_purchase_rate() -> None:
    on = date(2025, 3, 17)
    term = _treasury_term(rate="0.20")
    txs = [
        _ltn_buy(on, "2", _ltn_price(0.14, on)),
        TransactionEntity(
            asset_id=1,
            kind=TransactionKind.SELL,
            trade_date=date(2026, 3, 17),
            quantity=Decimal("1"),
            unit_price=Decimal("500"),
        ),
    ]

    lots, realized = replay_lots(txs, term, date(2026, 10, 27))

    assert len(lots) == 1
    assert lots[0].rate == pytest.approx(0.14, abs=1e-6)
    assert realized > 0


def test_semiannual_prefixado_falls_back_to_the_contracted_rate() -> None:
    on = date(2026, 3, 17)
    txs = [_ltn_buy(on, "1", "950")]
    term = _treasury_term(rate="0.13", semiannual_coupons=True)

    valuation = value_fixed_income_position(txs, term, date(2026, 10, 27))
    business_days = len(business_days_between(on, date(2026, 10, 27)))

    assert valuation.gross_value == pytest.approx(950.0 * 1.13 ** (business_days / 252.0), abs=0.01)
