"""Unit tests for valuation by instrument profile (item 11.5)."""

from __future__ import annotations

from datetime import date

import pytest
from fincontrol_core.domain.enums import ChecklistProfile
from fincontrol_core.errors import ValidationError
from fincontrol_core.fundamentals.history import FundamentalPeriod, FundamentalSnapshot
from fincontrol_core.fundamentals.valuation import (
    MethodKind,
    ValuationVerdict,
    ev_to_ebitda,
    value_asset,
)
from fincontrol_core.market.models import Fundamentals
from fincontrol_core.policy.models import ValuationPolicy

STATEMENT = FundamentalSnapshot(
    "WEGE3",
    date(2024, 12, 31),
    FundamentalPeriod.ANNUAL,
    {"ebitda": 100.0, "total_debt": 50.0, "cash": 30.0},
)


def _methods(valuation: object) -> dict[str, object]:
    return {m.method: m for m in valuation.methods}  # type: ignore[attr-defined]


def test_stock_combines_fair_prices_and_checks_multiples() -> None:
    f = Fundamentals(
        symbol="WEGE3",
        earnings_per_share=5.0,
        book_value_per_share=25.0,
        dividends_per_share_ttm=3.0,
        price_to_earnings=8.0,
        market_cap=880.0,
    )
    valuation = value_asset(ChecklistProfile.STOCK, 40.0, f, latest_statement=STATEMENT)
    methods = _methods(valuation)

    assert methods["GRAHAM"].value == pytest.approx(53.03, abs=0.01)
    assert methods["BAZIN"].value == pytest.approx(50.0)
    assert methods["PE"].passes is True
    assert methods["EV_EBITDA"].value == pytest.approx(9.0)
    assert methods["EV_EBITDA"].passes is True
    assert valuation.fair_value == pytest.approx((53.03 + 50.0) / 2, abs=0.01)
    assert valuation.margin == pytest.approx(1 - 40.0 / valuation.fair_value, abs=1e-3)
    assert valuation.verdict == ValuationVerdict.DISCOUNTED


@pytest.mark.parametrize(
    ("price", "verdict"),
    [(48.0, ValuationVerdict.FAIR), (60.0, ValuationVerdict.EXPENSIVE)],
)
def test_stock_verdict_follows_margin_of_safety(price: float, verdict: ValuationVerdict) -> None:
    f = Fundamentals(symbol="X", dividends_per_share_ttm=3.0)
    assert value_asset(ChecklistProfile.STOCK, price, f).verdict == verdict


def test_bank_uses_justified_price_to_book() -> None:
    f = Fundamentals(
        symbol="ITUB4",
        book_value_per_share=20.0,
        return_on_equity=0.21,
        price_to_book=1.5,
        dividend_yield=0.07,
    )
    valuation = value_asset(ChecklistProfile.BANK, 30.0, f)
    methods = _methods(valuation)
    assert methods["JUSTIFIED_PB"].value == pytest.approx(30.0)
    assert methods["BAZIN"].value == pytest.approx(35.0)
    assert methods["PB"].passes is True
    assert valuation.fair_value == pytest.approx(32.5)


def test_fii_checks_pvp_yield_and_spread_over_real_yield() -> None:
    policy = ValuationPolicy(reference_real_yield=0.065, min_fii_spread=0.02)
    cheap = value_asset(
        ChecklistProfile.FII_PAPER,
        95.0,
        Fundamentals(symbol="KNCR11", price_to_book=0.97, dividend_yield=0.11),
        policy,
    )
    methods = _methods(cheap)
    assert methods["SPREAD"].value == pytest.approx(0.045)
    assert methods["SPREAD"].passes is True
    assert "6.50%" in methods["SPREAD"].note
    assert all(m.kind != MethodKind.PRICE for m in cheap.methods)
    assert cheap.fair_value is None
    assert cheap.verdict == ValuationVerdict.DISCOUNTED

    mixed = value_asset(
        ChecklistProfile.FII_BRICK,
        150.0,
        Fundamentals(symbol="HGLG11", price_to_book=1.2, dividend_yield=0.07),
        policy,
    )
    assert mixed.verdict == ValuationVerdict.FAIR
    expensive = value_asset(
        ChecklistProfile.FII_BRICK,
        150.0,
        Fundamentals(symbol="X11", price_to_book=1.3, dividend_yield=0.04),
        policy,
    )
    assert expensive.verdict == ValuationVerdict.EXPENSIVE


@pytest.mark.parametrize(
    "profile", [ChecklistProfile.ETF, ChecklistProfile.CRYPTO, ChecklistProfile.FIXED_INCOME]
)
def test_profiles_without_intrinsic_value_are_not_applicable(profile: ChecklistProfile) -> None:
    valuation = value_asset(profile, 10.0, Fundamentals(symbol="X", price_to_earnings=5.0))
    assert not valuation.applicable
    assert valuation.verdict == ValuationVerdict.NOT_APPLICABLE
    assert valuation.reason
    assert valuation.methods == ()


def test_missing_data_is_undefined() -> None:
    assert value_asset(ChecklistProfile.STOCK, 10.0, None).verdict == ValuationVerdict.UNDEFINED
    intl = value_asset(
        ChecklistProfile.INTL_STOCK, 10.0, Fundamentals(symbol="AAPL", price_to_earnings=-3.0)
    )
    assert intl.verdict == ValuationVerdict.UNDEFINED
    assert _methods(intl)["PE"].note == "Sem dado ou negativo"
    assert "BAZIN" not in _methods(intl)


def test_ev_to_ebitda_requires_positive_ebitda_and_market_cap() -> None:
    f = Fundamentals(symbol="X", market_cap=100.0)
    assert ev_to_ebitda(f, None) is None
    assert ev_to_ebitda(Fundamentals(symbol="X"), STATEMENT) is None
    negative = FundamentalSnapshot("X", date(2024, 1, 1), FundamentalPeriod.ANNUAL, {"ebitda": -1})
    assert ev_to_ebitda(f, negative) is None


def test_policy_validates_new_premises() -> None:
    assert ValuationPolicy().as_dict()["max_price_to_earnings"] == 15.0
    with pytest.raises(ValidationError):
        ValuationPolicy(max_ev_to_ebitda=0)
    with pytest.raises(ValidationError):
        ValuationPolicy(bank_cost_of_equity=1.5)
    with pytest.raises(ValidationError):
        ValuationPolicy(reference_real_yield=6.0)
