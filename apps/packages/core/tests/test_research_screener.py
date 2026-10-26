"""Unit tests for the catalog screener and brapi catalog parsing (11.6, 11.7)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from fincontrol_core.domain.entities import AssetEntity, CatalogInstrument
from fincontrol_core.domain.enums import ArcaClass, AssetLifecycle, AssetType
from fincontrol_core.market.brapi import BrapiProvider, classify_brapi_type, parse_brapi_list_item
from fincontrol_core.market.models import Fundamentals
from fincontrol_core.research.screener import (
    ScreenerCriteria,
    passes_fundamentals,
    prefilter,
    screen,
)

CATALOG = [
    CatalogInstrument("ITUB4", "Itau PN", AssetType.STOCK_BR, "Finance", 32.0, None, 8e8),
    CatalogInstrument("HGLG11", "CSHG Log", AssetType.FII, "Real Estate", 155.0, None, 6e6),
    CatalogInstrument("AAPL34", "Apple DRN", AssetType.BDR, "Tech", 60.0, None, 3e7, 3e12),
    CatalogInstrument("TINY3", "Tiny", AssetType.STOCK_BR, "Finance", 1.0, None, 1e3),
    CatalogInstrument("ODD", "Unknown kind", None),
]


def test_classify_brapi_types_and_parse_items() -> None:
    assert classify_brapi_type("stock", "X") == AssetType.STOCK_BR
    assert classify_brapi_type("bdr", "X") == AssetType.BDR
    assert classify_brapi_type("fund", "ISHARES BOVA ETF") == AssetType.ETF_BR
    assert classify_brapi_type("fund", "CSHG LOGISTICA") == AssetType.FII
    assert classify_brapi_type(None, "X") is None

    at = datetime(2026, 1, 2, tzinfo=UTC)
    item = parse_brapi_list_item(
        {
            "stock": "wege3",
            "name": "WEG ON",
            "close": 50,
            "change": 1.5,
            "volume": 10,
            "type": "stock",
        },
        at,
    )
    assert item is not None
    assert (item.ticker, item.volume_brl, item.change_pct, item.updated_at) == (
        "WEGE3",
        500.0,
        0.015,
        at,
    )
    assert parse_brapi_list_item({"name": "no ticker"}, at) is None


def test_list_instruments_paginates_and_dedups() -> None:
    pages: dict[int, dict[str, Any]] = {
        1: {"stocks": [{"stock": "A3", "type": "stock"}], "hasNextPage": True, "totalPages": 2},
        2: {"stocks": [{"stock": "A3"}, {"stock": "B11", "type": "fund"}], "hasNextPage": False},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pages[int(request.url.params["page"])])

    provider = BrapiProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert [i.ticker for i in provider.list_instruments()] == ["A3", "B11"]
    failing = BrapiProvider(
        client=httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(503)))
    )
    assert failing.list_instruments() == []


def test_prefilter_by_catalog_criteria() -> None:
    assert [i.ticker for i in prefilter(CATALOG, ScreenerCriteria())] == [
        "ITUB4",
        "HGLG11",
        "AAPL34",
        "TINY3",
    ]
    by_class = ScreenerCriteria(arca_classes=frozenset({ArcaClass.ATIVOS_INTERNACIONAIS}))
    assert [i.ticker for i in prefilter(CATALOG, by_class)] == ["AAPL34"]
    liquid = ScreenerCriteria(sectors=frozenset({"FINANCE"}), min_volume_brl=1e6)
    assert [i.ticker for i in prefilter(CATALOG, liquid)] == ["ITUB4"]
    assert [i.ticker for i in prefilter(CATALOG, ScreenerCriteria(query="log"))] == ["HGLG11"]
    big = ScreenerCriteria(min_market_cap=1e12)
    assert [i.ticker for i in prefilter(CATALOG, big)] == ["AAPL34"]
    registered = {"ITUB4": AssetEntity(ticker="ITUB4", name="Itau", asset_type=AssetType.STOCK_BR)}
    fresh = ScreenerCriteria(asset_types=frozenset({AssetType.STOCK_BR}), exclude_registered=True)
    assert [i.ticker for i in prefilter(CATALOG, fresh, registered)] == ["TINY3"]


def test_fundamental_criteria_fail_on_missing_data() -> None:
    criteria = ScreenerCriteria(max_pe=10, min_dy=0.05, max_pb=2, min_roe=0.1)
    good = Fundamentals(
        symbol="X",
        price_to_earnings=8,
        dividend_yield=0.06,
        price_to_book=1.5,
        return_on_equity=0.2,
    )
    assert passes_fundamentals(good, criteria)
    assert not passes_fundamentals(None, criteria)
    assert not passes_fundamentals(Fundamentals(symbol="X", price_to_earnings=8), criteria)
    negative_pe = Fundamentals(
        symbol="X", price_to_earnings=-3, dividend_yield=0.06, price_to_book=1, return_on_equity=0.2
    )
    assert not passes_fundamentals(negative_pe, criteria)
    assert passes_fundamentals(None, ScreenerCriteria())


def test_screen_limits_scan_and_annotates_results() -> None:
    loaded: list[list[str]] = []

    def loader(items: list[CatalogInstrument]) -> dict[str, Fundamentals]:
        loaded.append([i.ticker for i in items])
        return {
            "ITUB4": Fundamentals(symbol="ITUB4", dividend_yield=0.07, dividends_per_share_ttm=2.2),
            "HGLG11": Fundamentals(symbol="HGLG11", dividend_yield=0.08, price_to_book=0.95),
        }

    asset = AssetEntity(ticker="HGLG11", name="CSHG", asset_type=AssetType.FII, id=9)
    outcome = screen(
        CATALOG,
        ScreenerCriteria(min_dy=0.05, scan_limit=2),
        load_fundamentals=loader,
        registered={"HGLG11": asset},
        lifecycles={"HGLG11": AssetLifecycle.HELD},
    )
    assert loaded == [["ITUB4", "HGLG11"]]
    assert [r.instrument.ticker for r in outcome.results] == ["ITUB4", "HGLG11"]
    assert (outcome.candidates, outcome.scanned, outcome.truncated) == (4, 2, True)
    fii = outcome.results[1]
    assert (fii.asset_id, fii.lifecycle_status) == (9, AssetLifecycle.HELD)
    assert fii.valuation is not None and fii.valuation.profile.value == "FII_BRICK"

    quick = screen(CATALOG, ScreenerCriteria(limit=1), load_fundamentals=lambda _i: {})
    assert [r.instrument.ticker for r in quick.results] == ["ITUB4"]
    assert quick.scanned == 1 and not quick.truncated
    assert screen([], ScreenerCriteria(), load_fundamentals=loader).results == []
