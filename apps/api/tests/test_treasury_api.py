"""Unit and integration tests for Tesouro Direto search via Brapi (/api/v2/treasury/list)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from composition import get_market_gateway
from domain.market.entities import TreasuryBond
from domain.shared.enums import (
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    FixedIncomeLiquidity,
)
from infra.cache.redis_cache import InMemoryCache
from infra.providers.bcb import BcbSgsProvider
from infra.providers.brapi import (
    BrapiProvider,
    classify_brapi_treasury_indexer,
    parse_brapi_treasury_item,
)
from infra.providers.gateway import CachedMarketGateway
from infra.providers.yfinance_provider import YFinanceProvider

SAMPLE_TREASURY_ITEMS: list[dict[str, Any]] = [
    {
        "symbol": "tesouro-selic-01032031",
        "bondType": "Tesouro Selic",
        "indexer": "selic",
        "couponType": "zero",
        "maturityDate": "2031-03-01",
        "durationDays": 1590,
        "baseDate": "2026-10-23",
        "buyRate": 0.10,
        "sellRate": 0.11,
        "buyPrice": 20074.43,
        "sellPrice": 20055.44,
        "basePrice": 20055.44,
        "rateInfo": {
            "rateType": "spreadOverSelic",
            "rateUnit": "% a.a.",
            "description": "Spread sobre a taxa Selic.",
        },
    },
    {
        "symbol": "tesouro-prefixado-01012027",
        "bondType": "Tesouro Prefixado",
        "indexer": "prefixado",
        "couponType": "zero",
        "maturityDate": "2027-01-01",
        "durationDays": 231,
        "baseDate": "2026-10-23",
        "buyRate": 13.96,
        "sellRate": 14.08,
        "buyPrice": 921.33,
        "sellPrice": 920.24,
        "basePrice": 920.24,
        "rateInfo": {
            "rateType": "nominalAnnualRate",
            "rateUnit": "% a.a.",
            "description": "Taxa nominal anual contratada.",
        },
    },
    {
        "symbol": "tesouro-ipca-com-juros-semestrais-15082060",
        "bondType": "Tesouro IPCA+ com Juros Semestrais",
        "indexer": "ipca",
        "couponType": "semestral",
        "maturityDate": "2060-08-15",
        "durationDays": 12511,
        "baseDate": "2026-10-23",
        "buyRate": 7.22,
        "sellRate": 7.34,
        "buyPrice": 4086.85,
        "sellPrice": 4023.39,
        "basePrice": 4023.39,
        "rateInfo": {
            "rateType": "realAnnualRateOverIpca",
            "rateUnit": "% a.a.",
            "description": "Taxa real anual acima do IPCA.",
        },
    },
]


def test_classify_brapi_treasury_indexer_mappings() -> None:
    assert classify_brapi_treasury_indexer("selic") == (
        FixedIncomeInstrumentKind.TESOURO_SELIC,
        FixedIncomeIndexer.SELIC,
        FixedIncomeLiquidity.DAILY,
    )
    assert classify_brapi_treasury_indexer("prefixado") == (
        FixedIncomeInstrumentKind.TESOURO_PRE,
        FixedIncomeIndexer.PRE,
        FixedIncomeLiquidity.AT_MATURITY,
    )
    assert classify_brapi_treasury_indexer("ipca") == (
        FixedIncomeInstrumentKind.TESOURO_IPCA,
        FixedIncomeIndexer.IPCA,
        FixedIncomeLiquidity.AT_MATURITY,
    )
    assert classify_brapi_treasury_indexer("igpm") == (
        FixedIncomeInstrumentKind.TESOURO_IPCA,
        FixedIncomeIndexer.IPCA,
        FixedIncomeLiquidity.AT_MATURITY,
    )


def test_parse_brapi_treasury_item_and_serialization_roundtrip() -> None:
    selic = parse_brapi_treasury_item(SAMPLE_TREASURY_ITEMS[0])
    assert selic is not None
    assert selic.name == "Tesouro Selic 2031"
    assert selic.instrument_kind == FixedIncomeInstrumentKind.TESOURO_SELIC
    assert selic.indexer == FixedIncomeIndexer.SELIC
    assert selic.contracted_rate_percent == 100.0
    assert selic.liquidity == FixedIncomeLiquidity.DAILY
    assert TreasuryBond.from_dict(selic.to_dict()) == selic

    pre = parse_brapi_treasury_item(SAMPLE_TREASURY_ITEMS[1])
    assert pre is not None
    assert pre.name == "Tesouro Prefixado 2027"
    assert pre.contracted_rate_percent == pytest.approx(13.96)
    assert pre.liquidity == FixedIncomeLiquidity.AT_MATURITY

    assert parse_brapi_treasury_item({"symbol": "", "maturityDate": "2031-03-01"}) is None
    assert parse_brapi_treasury_item({"symbol": "x", "maturityDate": "invalid"}) is None


def test_brapi_provider_list_treasury_bonds_happy_path_and_403() -> None:
    def ok_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v2/treasury/list")
        return httpx.Response(
            200,
            json={
                "results": SAMPLE_TREASURY_ITEMS,
                "pagination": {"page": 1, "totalPages": 1, "hasNextPage": False},
            },
        )

    provider = BrapiProvider(token="pro-token", client=httpx.Client(transport=httpx.MockTransport(ok_handler)))
    outcome = provider.list_treasury_bonds()
    assert outcome.unavailable_reason is None
    assert [b.symbol for b in outcome.results] == [
        "tesouro-selic-01032031",
        "tesouro-prefixado-01012027",
        "tesouro-ipca-com-juros-semestrais-15082060",
    ]

    def forbidden_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "error": True,
                "message": "Tesouro Direto e renda fixa requer o plano Pro.",
                "code": "FEATURE_NOT_AVAILABLE",
            },
        )

    free_provider = BrapiProvider(
        token="free-token", client=httpx.Client(transport=httpx.MockTransport(forbidden_handler))
    )
    denied = free_provider.list_treasury_bonds()
    assert denied.results == []
    assert denied.unavailable_reason == "Tesouro Direto e renda fixa requer o plano Pro."


def test_gateway_caches_treasury_bonds() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "results": SAMPLE_TREASURY_ITEMS[:1],
                "pagination": {"page": 1, "totalPages": 1, "hasNextPage": False},
            },
        )

    gw = CachedMarketGateway(
        brapi=BrapiProvider(client=httpx.Client(transport=httpx.MockTransport(handler))),
        yfinance=YFinanceProvider(),
        bcb=BcbSgsProvider(),
        cache=InMemoryCache(),
    )
    first = gw.list_treasury_bonds()
    second = gw.list_treasury_bonds()
    assert len(first.results) == 1
    assert second == first
    assert calls == 1


def test_research_treasury_endpoint_filters_and_matches_registered_assets(
    api: SimpleNamespace,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": SAMPLE_TREASURY_ITEMS,
                "pagination": {"page": 1, "totalPages": 1, "hasNextPage": False},
            },
        )

    gateway = CachedMarketGateway(
        brapi=BrapiProvider(client=httpx.Client(transport=httpx.MockTransport(handler))),
        yfinance=YFinanceProvider(),
        bcb=BcbSgsProvider(),
        cache=InMemoryCache(),
    )
    api.app.dependency_overrides[get_market_gateway] = lambda: gateway
    client = api.client

    all_bonds = client.get("/api/v1/research/treasury").json()
    assert all_bonds["total"] == 3
    assert all_bonds["unavailable_reason"] is None
    assert all(b["asset_id"] is None for b in all_bonds["results"])

    # Filter by indexer and coupon_type and query string
    ipca_semestral = client.get(
        "/api/v1/research/treasury",
        params={"indexer": "IPCA", "coupon_type": "semestral", "q": "2060"},
    ).json()
    assert [b["symbol"] for b in ipca_semestral["results"]] == [
        "tesouro-ipca-com-juros-semestrais-15082060"
    ]

    # Register Tesouro Selic 2031 and verify asset_id is matched in /research/treasury
    created = client.post(
        "/api/v1/assets",
        json={
            "name": "Tesouro Selic 2031",
            "asset_type": "TREASURY",
            "arca_class": "CAIXA",
            "purpose": "ARCA",
            "fixed_income_term": {
                "instrument_kind": "TESOURO_SELIC",
                "indexer": "SELIC",
                "contracted_rate": 1.0,
                "issue_date": str(date.today()),
                "maturity_date": "2031-03-01",
                "tax_exempt": False,
                "liquidity": "DAILY",
                "issuer": "Tesouro Nacional",
            },
        },
    )
    assert created.status_code == 201, created.text
    created_id = created.json()["id"]

    selic_search = client.get("/api/v1/research/treasury", params={"q": "Selic 2031"}).json()
    assert len(selic_search["results"]) == 1
    assert selic_search["results"][0]["asset_id"] == created_id
