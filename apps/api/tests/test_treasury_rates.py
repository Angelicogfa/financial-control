"""Unit tests for the rates implied by Tesouro Direto prices (LTN, NTN-F, NTN-B and VNA)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.helpers.calendar import business_days_between
from domain.portfolio.services.treasury_rates import (
    NTNB_COUPON,
    NTNF_COUPON,
    implied_purchase_rate,
    vna_on,
)
from domain.shared.entities import FixedIncomeTermEntity
from domain.shared.enums import FixedIncomeIndexer, FixedIncomeInstrumentKind

MONTHLY_IPCA = 0.004


def _ipca(last: tuple[int, int] = (2026, 9), rate: float = MONTHLY_IPCA) -> dict:
    months: dict[tuple[int, int], float] = {}
    year, month = 2000, 7
    while (year, month) <= last:
        months[(year, month)] = rate
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _months_since_base(day: date) -> int:
    """IPCA months already applied to the VNA on the 15th on or before `day`."""
    months = (day.year - 2000) * 12 + day.month - 7
    return months if day.day >= 15 else months - 1


def _du(start: date, end: date) -> int:
    return len(business_days_between(start, end))


def _term(kind: FixedIncomeInstrumentKind, maturity: date, **kwargs) -> FixedIncomeTermEntity:
    indexer = FixedIncomeIndexer.PRE
    if kind == FixedIncomeInstrumentKind.TESOURO_IPCA:
        indexer = FixedIncomeIndexer.IPCA
    return FixedIncomeTermEntity(
        instrument_kind=kind,
        indexer=indexer,
        contracted_rate=Decimal("0.07"),
        maturity_date=maturity,
        **kwargs,
    )


def _coupon_price(
    trade: date, maturity: date, coupon: float, rate: float, principal: float
) -> float:
    flows = [(maturity, principal * (1 + coupon))]
    for step in range(1, 200):
        index = maturity.year * 12 + maturity.month - 1 - 6 * step
        paid = date(index // 12, index % 12 + 1, maturity.day)
        if paid <= trade:
            break
        flows.append((paid, principal * coupon))
    return sum(amount / (1 + rate) ** (_du(trade, when) / 252) for when, amount in flows)


def test_vna_is_the_base_value_on_the_base_date() -> None:
    assert vna_on(date(2000, 7, 15), _ipca(), 0.045) == pytest.approx(1000.0)


def test_vna_compounds_the_previous_months_on_the_15th() -> None:
    day = date(2026, 6, 15)
    expected = 1000.0 * (1 + MONTHLY_IPCA) ** _months_since_base(day)

    assert vna_on(day, _ipca(), 0.045) == pytest.approx(expected, rel=1e-12)


def test_vna_grows_pro_rata_by_business_days_between_15ths() -> None:
    day = date(2026, 6, 25)
    on_15th = vna_on(date(2026, 6, 15), _ipca(), 0.045)
    share = _du(date(2026, 6, 15), day) / _du(date(2026, 6, 15), date(2026, 7, 15))

    assert vna_on(day, _ipca(), 0.045) == pytest.approx(
        on_15th * (1 + MONTHLY_IPCA) ** share, rel=1e-12
    )


def test_vna_projects_unpublished_months_with_the_annual_fallback() -> None:
    day = date(2026, 10, 20)
    published = vna_on(day, _ipca(last=(2026, 10)), 0.045)
    projected = vna_on(day, _ipca(last=(2026, 8)), 0.0)

    assert projected is not None and published is not None
    assert projected < published


@pytest.mark.parametrize(
    ("ipca", "day"),
    [
        ({}, date(2026, 6, 16)),
        ({k: v for k, v in _ipca().items() if k != (2010, 3)}, date(2026, 6, 16)),
        ({k: v for k, v in _ipca().items() if k[0] >= 2016}, date(2026, 6, 16)),
        (_ipca(), date(2000, 7, 14)),
    ],
)
def test_vna_is_unknown_with_a_gap_in_the_ipca_history(ipca: dict, day: date) -> None:
    assert vna_on(day, ipca, 0.045) is None


def test_ltn_rate_is_recovered_from_its_price() -> None:
    trade, maturity = date(2026, 3, 17), date(2029, 1, 1)
    price = 1000.0 / 1.1375 ** (_du(trade, maturity) / 252)
    term = _term(FixedIncomeInstrumentKind.TESOURO_PRE, maturity)

    assert implied_purchase_rate(term, trade, price) == pytest.approx(0.1375, abs=1e-8)


def test_ntnf_rate_is_recovered_with_semiannual_coupons() -> None:
    trade, maturity = date(2026, 3, 17), date(2035, 1, 1)
    price = _coupon_price(trade, maturity, NTNF_COUPON, 0.1350, 1000.0)
    term = _term(FixedIncomeInstrumentKind.TESOURO_PRE, maturity, semiannual_coupons=True)

    assert implied_purchase_rate(term, trade, price) == pytest.approx(0.1350, abs=1e-8)


def test_ntnb_principal_rate_is_recovered_through_the_vna() -> None:
    trade, maturity = date(2026, 6, 16), date(2032, 8, 15)
    vna = vna_on(trade, _ipca(), 0.045)
    assert vna is not None
    price = vna / 1.0804 ** (_du(trade, maturity) / 252)
    term = _term(FixedIncomeInstrumentKind.TESOURO_IPCA, maturity)

    rate = implied_purchase_rate(term, trade, price, ipca_monthly=_ipca(), annual_ipca_rate=0.045)

    assert rate == pytest.approx(0.0804, abs=1e-8)


def test_ntnb_rate_is_recovered_with_semiannual_coupons() -> None:
    trade, maturity = date(2026, 9, 22), date(2037, 5, 15)
    vna = vna_on(trade, _ipca(), 0.045)
    assert vna is not None
    price = vna * _coupon_price(trade, maturity, NTNB_COUPON, 0.0750, 1.0)
    term = _term(FixedIncomeInstrumentKind.TESOURO_IPCA, maturity, semiannual_coupons=True)

    rate = implied_purchase_rate(term, trade, price, ipca_monthly=_ipca(), annual_ipca_rate=0.045)

    assert rate == pytest.approx(0.0750, abs=1e-8)


def test_ipca_bond_without_ipca_history_has_no_implied_rate() -> None:
    term = _term(FixedIncomeInstrumentKind.TESOURO_IPCA, date(2032, 8, 15))

    assert implied_purchase_rate(term, date(2026, 6, 16), 2944.70) is None


@pytest.mark.parametrize(
    ("kind", "maturity", "price", "trade"),
    [
        (FixedIncomeInstrumentKind.TESOURO_SELIC, date(2029, 3, 1), 15000.0, date(2026, 3, 17)),
        (FixedIncomeInstrumentKind.CDB, date(2029, 3, 1), 1000.0, date(2026, 3, 17)),
        (FixedIncomeInstrumentKind.TESOURO_PRE, None, 700.0, date(2026, 3, 17)),
        (FixedIncomeInstrumentKind.TESOURO_PRE, date(2029, 1, 1), 700.0, date(2029, 1, 1)),
        (FixedIncomeInstrumentKind.TESOURO_PRE, date(2029, 1, 1), 0.0, date(2026, 3, 17)),
        (FixedIncomeInstrumentKind.TESOURO_PRE, date(2029, 1, 1), 1000.0, date(2026, 3, 17)),
        (FixedIncomeInstrumentKind.TESOURO_PRE, date(2029, 1, 1), 1.0, date(2028, 12, 1)),
    ],
)
def test_no_rate_is_implied_when_the_price_cannot_imply_one(
    kind: FixedIncomeInstrumentKind, maturity: date | None, price: float, trade: date
) -> None:
    indexer = {
        FixedIncomeInstrumentKind.TESOURO_SELIC: FixedIncomeIndexer.SELIC,
        FixedIncomeInstrumentKind.CDB: FixedIncomeIndexer.CDI,
    }.get(kind, FixedIncomeIndexer.PRE)
    rate = (
        Decimal("1.0")
        if indexer in (FixedIncomeIndexer.SELIC, FixedIncomeIndexer.CDI)
        else (Decimal("0.12"))
    )
    term = FixedIncomeTermEntity(
        instrument_kind=kind, indexer=indexer, contracted_rate=rate, maturity_date=maturity
    )

    assert implied_purchase_rate(term, trade, price, ipca_monthly=_ipca()) is None


def test_coupon_bond_price_above_par_at_zero_rate_has_no_implied_rate() -> None:
    trade, maturity = date(2026, 3, 17), date(2035, 1, 1)
    term = _term(FixedIncomeInstrumentKind.TESOURO_PRE, maturity, semiannual_coupons=True)
    above_zero_rate = _coupon_price(trade, maturity, NTNF_COUPON, 0.0, 1000.0) + 1.0

    assert implied_purchase_rate(term, trade, above_zero_rate) is None
