"""Is each indicator good? Ratings against the strategy's own references."""

from __future__ import annotations

from types import SimpleNamespace

from domain.assets.services.history import HistoricalMetrics
from domain.assets.services.ratings import BAD, CAUTION, GOOD, SUSPICIOUS, rate_indicators
from domain.market.entities import Fundamentals
from domain.policy.services.policy import ValuationPolicy
from domain.shared.enums import ChecklistProfile

POLICY = ValuationPolicy()


def _fund(**kw) -> Fundamentals:
    return Fundamentals(symbol="X", **kw)


def test_the_screen_of_the_request() -> None:
    # The indicators of the asset in the request.
    fund = _fund(
        price_to_earnings=7.92,
        price_to_book=1.53,
        dividend_yield=0.023,
        return_on_equity=0.189,
        profit_margin=2.143,
        net_debt_to_ebitda=2.9,
        earnings_per_share=1.62,
        book_value_per_share=8.37,
        market_cap=143.8e9,
        avg_daily_volume=405.6e6,
    )
    metrics = HistoricalMetrics(
        years=5,
        first_year=2021,
        last_year=2025,
        roe_average=0.175,
        revenue_cagr=None,
        earnings_cagr=None,
        profitable_years=4,
        dividend_years=1,
        payout_average=None,
    )
    r = rate_indicators(ChecklistProfile.STOCK, fund, metrics, POLICY)
    status = {k: v.status for k, v in r.items()}
    assert status == {
        "price_to_earnings": GOOD,
        "price_to_book": GOOD,  # 7.92 x 1.53 = 12.1, within Graham's 22.5
        "dividend_yield": CAUTION,  # below the 6% Bazin asks; never "bad"
        "return_on_equity": GOOD,
        "profit_margin": SUSPICIOUS,  # 214% of the revenue is not possible
        "net_debt_to_ebitda": CAUTION,
        "earnings_per_share": GOOD,
        "book_value_per_share": GOOD,
        "avg_daily_volume": GOOD,
        "roe_average": GOOD,
        "profitable_years": CAUTION,
        "dividend_years": CAUTION,
    }
    assert "market_cap" not in r  # size is not good or bad
    assert "12,1" in r["price_to_book"].reference and "Graham" in r["price_to_book"].reference
    assert r["price_to_earnings"].reference == "Até 15, o máximo da estratégia."


def test_bad_values_and_the_policy_limits() -> None:
    fund = _fund(
        price_to_earnings=-4.0,
        price_to_book=3.0,
        return_on_equity=0.02,
        profit_margin=-0.05,
        net_debt_to_ebitda=4.5,
        earnings_per_share=-0.3,
        avg_daily_volume=300e3,
        dividend_yield=0.08,
    )
    r = rate_indicators(ChecklistProfile.STOCK, fund, None, POLICY)
    assert r["price_to_earnings"].status == BAD
    assert r["price_to_book"].status == CAUTION  # no profit for Graham
    assert r["return_on_equity"].status == BAD
    assert r["profit_margin"].status == BAD
    assert r["net_debt_to_ebitda"].status == BAD
    assert r["earnings_per_share"].status == BAD
    assert r["avg_daily_volume"].status == CAUTION
    assert r["dividend_yield"].status == GOOD
    # The strategy's maximum moves the rating.
    strict = ValuationPolicy(max_price_to_earnings=6.0)
    assert (
        rate_indicators(ChecklistProfile.STOCK, _fund(price_to_earnings=7.92), None, strict)[
            "price_to_earnings"
        ].status
        == CAUTION
    )


def test_banks_and_funds_use_their_own_references() -> None:
    bank = rate_indicators(
        ChecklistProfile.BANK,
        _fund(price_to_book=1.6, net_debt_to_ebitda=9.0, profit_margin=0.2),
        None,
        POLICY,
    )
    assert bank["price_to_book"].status == GOOD and "2,00" in bank["price_to_book"].reference
    assert "net_debt_to_ebitda" not in bank  # does not apply to a bank
    fund = rate_indicators(
        ChecklistProfile.FII_BRICK, _fund(price_to_book=1.2, profit_margin=0.9), None, POLICY
    )
    assert fund["price_to_book"].status == CAUTION and "1,05" in fund["price_to_book"].reference
    assert "profit_margin" not in fund


def test_history_growth_and_payout() -> None:
    metrics = HistoricalMetrics(5, 2021, 2025, 0.12, 0.08, -0.03, 5, 5, 1.3)
    r = rate_indicators(ChecklistProfile.STOCK, None, metrics, POLICY)
    assert r["revenue_cagr"].status == GOOD and r["earnings_cagr"].status == BAD
    assert r["profitable_years"].status == GOOD and r["dividend_years"].status == GOOD
    assert r["payout_average"].status == BAD


def test_analysis_carries_the_ratings(api: SimpleNamespace) -> None:
    asset_id = api.client.post(
        "/api/v1/assets", json={"ticker": "WEGE3", "name": "WEG", "asset_type": "STOCK_BR"}
    ).json()["id"]
    data = api.client.get(f"/api/v1/assets/{asset_id}/analysis").json()
    assert isinstance(data["indicator_ratings"], dict)
    for rating in data["indicator_ratings"].values():
        assert rating["status"] in {GOOD, CAUTION, BAD, SUSPICIOUS} and rating["reference"]
