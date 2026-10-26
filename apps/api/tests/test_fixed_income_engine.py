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
