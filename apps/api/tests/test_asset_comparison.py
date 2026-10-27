"""Unit and integration tests of the asset comparator (Phase 27)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from core.errors import ValidationError
from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.assets.services.history import (
    FundamentalPeriod,
    FundamentalSnapshot,
    historical_metrics,
)
from domain.market.entities import Fundamentals, PricePoint
from domain.portfolio.services.service import PortfolioApplicationService
from domain.research.services.comparison import (
    INDICATORS,
    ComparedAsset,
    IndicatorGroup,
    annual_history,
    compare_assets,
    indicator_value,
    normalize_tickers,
    select_indicators,
    statements_missing,
)
from domain.shared.entities import CatalogInstrument
from domain.shared.enums import AssetType, ChecklistProfile
from infra.providers.gateway import CachedMarketGateway
from tests.conftest import offline_gateway


def _statement(ticker: str, year: int, **metrics: float) -> FundamentalSnapshot:
    return FundamentalSnapshot(
        ticker=ticker,
        reference_date=date(year, 12, 31),
        period=FundamentalPeriod.ANNUAL,
        metrics=metrics,
    )


def _asset(ticker: str, **kw: object) -> ComparedAsset:
    defaults: dict[str, object] = {
        "name": ticker,
        "asset_type": AssetType.STOCK_BR,
        "profile": ChecklistProfile.STOCK,
    }
    defaults.update(kw)
    return ComparedAsset(ticker=ticker, **defaults)  # type: ignore[arg-type]


# --- pure engine -----------------------------------------------------------------------------


def test_normalize_tickers_dedupes_splits_and_limits() -> None:
    assert normalize_tickers(["petr4, vale3", "PETR4"]) == ["PETR4", "VALE3"]
    with pytest.raises(ValidationError):
        normalize_tickers(["PETR4"])
    with pytest.raises(ValidationError):
        normalize_tickers(["A1", "B1", "C1", "D1", "E1", "F1"])


def test_select_indicators_keeps_catalog_order_and_rejects_unknown() -> None:
    assert [i.key for i in select_indicators(["return_on_equity", "price_to_earnings"])] == [
        "price_to_earnings",
        "return_on_equity",
    ]
    assert len(select_indicators(None)) == len(INDICATORS)
    assert {i.group for i in INDICATORS} == set(IndicatorGroup)
    with pytest.raises(ValidationError):
        select_indicators(["nope"])


def test_best_per_row_respects_direction_and_positive_only() -> None:
    a = _asset(
        "AAAA3", fundamentals=Fundamentals("AAAA3", price_to_earnings=-5.0, return_on_equity=0.20)
    )
    b = _asset(
        "BBBB3", fundamentals=Fundamentals("BBBB3", price_to_earnings=8.0, return_on_equity=0.10)
    )
    c = _asset(
        "CCCC3", fundamentals=Fundamentals("CCCC3", price_to_earnings=12.0, return_on_equity=0.20)
    )

    rows = {
        r.key: r
        for r in compare_assets(
            [a, b, c], select_indicators(["price_to_earnings", "return_on_equity"])
        ).rows
    }

    assert rows["price_to_earnings"].best == ["BBBB3"]
    assert rows["return_on_equity"].best == ["AAAA3", "CCCC3"]
    assert rows["price_to_earnings"].values["AAAA3"] == -5.0


def test_row_with_a_single_known_value_has_no_best() -> None:
    a = _asset("AAAA3", fundamentals=Fundamentals("AAAA3", dividend_yield=0.08))
    b = _asset("BBBB3")
    row = compare_assets([a, b], select_indicators(["dividend_yield"])).rows[0]
    assert row.best == []
    assert row.values == {"AAAA3": 0.08, "BBBB3": None}


def test_statement_based_indicators() -> None:
    statements = [
        _statement(
            "WEGE3",
            2023,
            revenue=100.0,
            net_income=10.0,
            equity=50.0,
            ebitda=20.0,
            total_debt=30.0,
            cash=10.0,
        ),
        _statement(
            "WEGE3",
            2024,
            revenue=121.0,
            net_income=14.4,
            equity=60.0,
            ebitda=30.0,
            total_debt=40.0,
            cash=10.0,
        ),
    ]
    asset = _asset(
        "WEGE3",
        fundamentals=Fundamentals("WEGE3", market_cap=270.0),
        statements=statements,
        history=historical_metrics(statements),
    )

    assert indicator_value(asset, "ev_to_ebitda") == pytest.approx((270 + 40 - 10) / 30)
    assert indicator_value(asset, "net_debt_to_equity") == pytest.approx(30 / 60)
    assert indicator_value(asset, "net_debt_to_ebitda") == pytest.approx(30 / 30)
    assert indicator_value(asset, "ebitda_margin") == pytest.approx(30 / 121)
    assert indicator_value(asset, "revenue_cagr") == pytest.approx(0.21)
    assert indicator_value(asset, "margin_of_safety") is None


def test_annual_history_estimates_dy_from_year_end_close() -> None:
    statements = [
        _statement("WEGE3", 2024, revenue=100.0, net_income=10.0, equity=50.0, dividends_paid=-5.0)
    ]
    asset = _asset(
        "WEGE3",
        price=20.0,
        fundamentals=Fundamentals("WEGE3", market_cap=200.0),
        statements=statements,
        prices=[PricePoint(date(2024, 12, 27), 9.0), PricePoint(date(2024, 12, 30), 10.0)],
    )

    point = annual_history(asset).points[0]

    assert point.year == 2024
    assert point.roe == pytest.approx(0.2)
    # 10 shares (200 / 20) x 10 at the last close of 2024 = 100; 5 paid -> 5%.
    assert point.dividend_yield == pytest.approx(0.05)
    assert annual_history(_asset("X", statements=statements)).points[0].dividend_yield is None


def test_mixing_profiles_and_currencies_warns() -> None:
    stock = _asset("ITUB4", currency="BRL", fundamentals=Fundamentals("ITUB4"))
    fii = _asset(
        "HGLG11",
        asset_type=AssetType.FII,
        profile=ChecklistProfile.FII_BRICK,
        currency="USD",
        fundamentals=Fundamentals("HGLG11"),
    )

    warnings = compare_assets([stock, fii], []).warnings

    assert any("FII × ação" in w for w in warnings)
    assert any("Moedas diferentes" in w for w in warnings)
    same = compare_assets(
        [stock, _asset("BBDC4", currency="BRL", fundamentals=Fundamentals("BBDC4"))], []
    )
    assert same.warnings == []


def test_statements_missing_only_for_companies() -> None:
    assert statements_missing(AssetType.STOCK_BR, []) is True
    assert statements_missing(AssetType.FII, []) is False
    assert statements_missing(AssetType.STOCK_BR, [_statement("A", 2024)]) is False


# --- integration -----------------------------------------------------------------------------


def _register(api: SimpleNamespace, ticker: str, asset_type: str = "STOCK_BR") -> int:
    resp = api.client.post(
        "/api/v1/assets",
        json={"ticker": ticker, "name": ticker, "asset_type": asset_type, "manual_price": "10"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _seed_statements(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        uow.fundamentals.upsert(
            [
                _statement("WEGE3", 2023, revenue=100.0, net_income=10.0, equity=50.0),
                _statement("WEGE3", 2024, revenue=120.0, net_income=15.0, equity=60.0),
                _statement("ROMI3", 2024, revenue=80.0, net_income=4.0, equity=40.0),
            ]
        )
        uow.commit()


def test_compare_route_returns_rows_history_and_checklist(api: SimpleNamespace) -> None:
    wege = _register(api, "WEGE3")
    _register(api, "ROMI3")
    _seed_statements(api)

    resp = api.client.get("/api/v1/research/compare?tickers=WEGE3,ROMI3")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [a["ticker"] for a in body["assets"]] == ["WEGE3", "ROMI3"]
    assert body["assets"][0]["asset_id"] == wege
    assert body["assets"][0]["statement_years"] == 2
    assert body["assets"][0]["checklist_max_score"] is not None
    assert len(body["rows"]) == len(INDICATORS)
    assert len(body["groups"]) == 5
    roe_avg = next(r for r in body["rows"] if r["key"] == "roe_average")
    assert roe_avg["best"] == ["WEGE3"]
    wege_history = next(h for h in body["history"] if h["ticker"] == "WEGE3")
    assert [p["year"] for p in wege_history["points"]] == [2023, 2024]
    assert wege_history["points"][1]["roe"] == 0.25
    assert any("Sem indicadores atuais" in w for w in body["warnings"])


def test_compare_route_filters_indicators_and_validates(api: SimpleNamespace) -> None:
    _register(api, "WEGE3")
    _register(api, "ROMI3")

    body = api.client.get(
        "/api/v1/research/compare?tickers=WEGE3&tickers=ROMI3&indicators=price_to_earnings"
    ).json()
    assert [r["key"] for r in body["rows"]] == ["price_to_earnings"]

    one = api.client.get("/api/v1/research/compare?tickers=WEGE3")
    assert one.status_code == 400
    assert one.json()["code"] == "INVALID_COMPARISON_SIZE"
    unknown = api.client.get("/api/v1/research/compare?tickers=WEGE3,ZZZZ3")
    assert unknown.json()["code"] == "UNKNOWN_INSTRUMENT"


def test_catalog_tickers_compare_and_missing_statements_are_fetched(
    api: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    with api.uow_factory() as uow:
        uow.catalog.upsert(
            [
                CatalogInstrument("ITUB4", "Itaú", AssetType.STOCK_BR),
                CatalogInstrument("BBDC4", "Bradesco", AssetType.STOCK_BR),
            ]
        )
        uow.commit()
    requested: list[str] = []

    def fake_statements(
        self: CachedMarketGateway, ticker: str, **_kw: object
    ) -> list[FundamentalSnapshot]:
        requested.append(ticker)
        return [_statement(ticker, 2024, revenue=10.0, net_income=2.0, equity=8.0)]

    monkeypatch.setattr(CachedMarketGateway, "get_annual_statements", fake_statements)

    body = api.client.get("/api/v1/research/compare?tickers=ITUB4,BBDC4").json()

    assert sorted(requested) == ["BBDC4", "ITUB4"]
    assert all(a["asset_id"] is None for a in body["assets"])
    assert all(a["statement_years"] == 1 for a in body["assets"])
    with api.uow_factory() as uow:
        assert set(uow.fundamentals.list_for_many(["ITUB4", "BBDC4"])) == {"ITUB4", "BBDC4"}


def test_mcp_research_compare(api: SimpleNamespace) -> None:
    _register(api, "WEGE3")
    _register(api, "ROMI3")
    op = CATALOG_BY_NAME["research.compare"]
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )

    result = op.invoke(
        handlers, op.input_model(tickers=["WEGE3", "ROMI3"], indicators=["return_on_equity"])
    )

    assert op.kind == "query"
    assert [r.key for r in result.rows] == ["return_on_equity"]
