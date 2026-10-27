"""Unit and integration tests for Tesouro Direto catalog via Tesouro Transparente + Worker."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from composition import get_market_gateway
from domain.market.entities import TreasuryBond, TreasuryCatalogResult
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
from infra.providers.tesouro import (
    TesouroTransparenteProvider,
    classify_tesouro_bond_type,
    merge_invest_and_redeem_bonds,
    parse_tesouro_transparente_csv,
    slugify_treasury_symbol,
)
from infra.providers.yfinance_provider import YFinanceProvider
from worker.jobs import sync_treasury_catalog_job

SAMPLE_TESOURO_CSV = (
    "Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;"
    "Taxa Venda Manha;PU Compra Manha;PU Venda Manha;PU Base Manha\n"
    "Tesouro Selic;01/03/2031;22/10/2026;0,09;0,10;20050,00;20030,00;20030,00\n"
    "Tesouro Selic;01/03/2031;23/10/2026;0,10;0,11;20074,43;20055,44;20055,44\n"
    "Tesouro Prefixado;01/01/2027;23/10/2026;13,96;14,08;921,33;920,24;920,24\n"
    "Tesouro IPCA+ com Juros Semestrais;15/08/2060;23/10/2026;7,22;7,34;4086,85;4023,39;4023,39\n"
    "Tesouro IPCA+;15/05/2024;23/10/2026;6,00;6,10;3000,00;2990,00;2990,00\n"
)

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
]


def test_classify_tesouro_bond_type_and_slugify() -> None:
    assert slugify_treasury_symbol("Tesouro Selic", date(2031, 3, 1)) == "tesouro-selic-01032031"
    assert (
        slugify_treasury_symbol("Tesouro IPCA+ com Juros Semestrais", date(2060, 8, 15))
        == "tesouro-ipca-com-juros-semestrais-15082060"
    )

    selic = classify_tesouro_bond_type("Tesouro Selic")
    assert selic[:5] == (
        FixedIncomeInstrumentKind.TESOURO_SELIC,
        FixedIncomeIndexer.SELIC,
        "selic",
        "zero",
        FixedIncomeLiquidity.DAILY,
    )

    pre_semestral = classify_tesouro_bond_type("Tesouro Prefixado com Juros Semestrais")
    assert pre_semestral[:5] == (
        FixedIncomeInstrumentKind.TESOURO_PRE,
        FixedIncomeIndexer.PRE,
        "prefixado",
        "semestral",
        FixedIncomeLiquidity.AT_MATURITY,
    )

    ipca = classify_tesouro_bond_type("Tesouro Renda+ Aposentadoria Extra")
    assert ipca[:5] == (
        FixedIncomeInstrumentKind.TESOURO_IPCA,
        FixedIncomeIndexer.IPCA,
        "ipca",
        "zero",
        FixedIncomeLiquidity.AT_MATURITY,
    )

    igpm = classify_tesouro_bond_type("Tesouro IGPM+ com Juros Semestrais")
    assert igpm[2] == "igpm"
    assert igpm[3] == "semestral"


def test_parse_tesouro_transparente_csv_picks_latest_base_date_and_filters_matured() -> None:
    now = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
    bonds = parse_tesouro_transparente_csv(
        SAMPLE_TESOURO_CSV,
        reference_date=date(2026, 10, 23),
        fetched_at=now,
    )
    assert [b.symbol for b in bonds] == [
        "tesouro-prefixado-01012027",
        "tesouro-selic-01032031",
        "tesouro-ipca-com-juros-semestrais-15082060",
    ]
    selic = next(b for b in bonds if b.symbol == "tesouro-selic-01032031")
    assert selic.name == "Tesouro Selic 2031"
    assert selic.base_date == date(2026, 10, 23)
    assert selic.buy_rate == pytest.approx(0.10)
    assert selic.buy_price == pytest.approx(20074.43)
    assert selic.contracted_rate_percent == 100.0
    assert selic.updated_at == now
    assert TreasuryBond.from_dict(selic.to_dict()) == selic

    pre = next(b for b in bonds if b.symbol == "tesouro-prefixado-01012027")
    assert pre.contracted_rate_percent == pytest.approx(13.96)

    # Rejects HTML WAF challenge or empty text
    assert parse_tesouro_transparente_csv("<html><head></head><body>429</body></html>") == []
    assert parse_tesouro_transparente_csv("") == []


def test_parse_tesouro_direto_invest_and_redeem_csv_and_merge() -> None:
    invest_csv = (
        "\ufeffT\ufffdtulo;Rendimento anual do t\ufffdtulo;Investimento m\ufffdnimo;"
        "Pre\ufffdo unit\ufffdrio de investimento;Vencimento do T\ufffdtulo\n"
        "Tesouro Selic 2031;SELIC + 0,0992%;R$\xa0200,84;R$\xa020.084,44;01/03/2031\n"
        "Tesouro Prefixado 2029;15,26%;R$\xa07,35;R$\xa0735,95;01/01/2029\n"
    )
    redeem_csv = (
        "\ufeffT\ufffdtulo;Rendimento anual do t\ufffdtulo;"
        "Pre\ufffdo unit\ufffdrio de resgate;Vencimento do T\ufffdtulo\n"
        "Tesouro Selic 2031;SELIC + 0,1092%;R$\xa020.075,79;01/03/2031\n"
        "Tesouro IPCA+ 2029;IPCA + 7,91%;R$\xa03.937,55;15/05/2029\n"
    )
    ref = date(2026, 10, 26)
    invest_bonds = parse_tesouro_transparente_csv(invest_csv, reference_date=ref)
    redeem_bonds = parse_tesouro_transparente_csv(redeem_csv, reference_date=ref)
    merged = merge_invest_and_redeem_bonds(invest_bonds, redeem_bonds)

    assert [b.symbol for b in merged] == [
        "tesouro-prefixado-01012029",
        "tesouro-ipca-15052029",
        "tesouro-selic-01032031",
    ]
    selic = next(b for b in merged if b.symbol == "tesouro-selic-01032031")
    assert selic.buy_rate == pytest.approx(0.0992)
    assert selic.buy_price == pytest.approx(20084.44)
    assert selic.sell_rate == pytest.approx(0.1092)
    assert selic.sell_price == pytest.approx(20075.79)
    assert selic.base_price == pytest.approx(20075.79)

    ipca = next(b for b in merged if b.symbol == "tesouro-ipca-15052029")
    assert ipca.buy_rate is None
    assert ipca.sell_rate == pytest.approx(7.91)
    assert ipca.contracted_rate_percent == pytest.approx(7.91)


def test_tesouro_transparente_provider_happy_path_and_waf_or_http_error() -> None:
    def csv_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=SAMPLE_TESOURO_CSV.encode("latin-1"))

    provider = TesouroTransparenteProvider(
        client=httpx.Client(transport=httpx.MockTransport(csv_handler))
    )
    outcome = provider.list_treasury_bonds(reference_date=date(2026, 10, 23))
    assert outcome.unavailable_reason is None
    assert len(outcome.results) == 3

    def html_challenge_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<!DOCTYPE html><html><body>Challenge</body></html>")

    waf_provider = TesouroTransparenteProvider(
        client=httpx.Client(transport=httpx.MockTransport(html_challenge_handler))
    )
    blocked = waf_provider.list_treasury_bonds()
    assert blocked.results == []
    assert blocked.unavailable_reason is not None

    def rate_limit_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Too Many Requests")

    error_provider = TesouroTransparenteProvider(
        client=httpx.Client(transport=httpx.MockTransport(rate_limit_handler))
    )
    failed = error_provider.list_treasury_bonds()
    assert failed.results == []
    assert failed.unavailable_reason is not None


def test_classify_and_parse_brapi_treasury_helpers_preserved() -> None:
    assert classify_brapi_treasury_indexer("selic") == (
        FixedIncomeInstrumentKind.TESOURO_SELIC,
        FixedIncomeIndexer.SELIC,
        FixedIncomeLiquidity.DAILY,
    )
    selic = parse_brapi_treasury_item(SAMPLE_TREASURY_ITEMS[0])
    assert selic is not None
    assert selic.symbol == "tesouro-selic-01032031"


def test_script_00018_migration_upgrade_and_downgrade(tmp_path: Path) -> None:
    api_dir = Path(__file__).resolve().parents[1]
    db_url = f"sqlite:///{(tmp_path / 'treasury_mig.db').as_posix()}"
    cfg = Config(str(api_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_dir / "infra" / "data" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    engine = create_engine(db_url, future=True)
    try:
        command.upgrade(cfg, "script_00017")
        assert "treasury_catalog" not in inspect(engine).get_table_names()

        command.upgrade(cfg, "script_00018")
        assert "treasury_catalog" in inspect(engine).get_table_names()

        command.downgrade(cfg, "script_00017")
        assert "treasury_catalog" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_sync_treasury_catalog_job_and_repository_roundtrip(api: SimpleNamespace) -> None:
    def csv_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=SAMPLE_TESOURO_CSV.encode("utf-8"))

    gateway = CachedMarketGateway(
        brapi=BrapiProvider(),
        yfinance=YFinanceProvider(),
        bcb=BcbSgsProvider(),
        tesouro=TesouroTransparenteProvider(
            client=httpx.Client(transport=httpx.MockTransport(csv_handler))
        ),
        cache=InMemoryCache(),
    )

    stored = sync_treasury_catalog_job(api.uow_factory, gateway)
    assert stored == 3

    with api.uow_factory() as uow:
        all_stored = uow.treasury_catalog.list_all()
        assert len(all_stored) == 3
        selic = uow.treasury_catalog.get("TESOURO-SELIC-01032031")
        assert selic is not None
        assert selic.name == "Tesouro Selic 2031"
        assert uow.treasury_catalog.get("non-existent") is None

    # When upstream fails, sync_treasury_catalog_job keeps the existing catalog in PostgreSQL
    class _EmptyGateway:
        def list_treasury_bonds(self, *, bypass_cache: bool = False) -> TreasuryCatalogResult:
            return TreasuryCatalogResult(results=[], unavailable_reason="timeout")

    assert sync_treasury_catalog_job(api.uow_factory, _EmptyGateway()) == 0  # type: ignore[arg-type]
    with api.uow_factory() as uow:
        assert len(uow.treasury_catalog.list_all()) == 3


def test_gateway_caches_treasury_bonds() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=SAMPLE_TESOURO_CSV.encode("utf-8"))

    gw = CachedMarketGateway(
        brapi=BrapiProvider(),
        yfinance=YFinanceProvider(),
        bcb=BcbSgsProvider(),
        tesouro=TesouroTransparenteProvider(
            client=httpx.Client(transport=httpx.MockTransport(handler))
        ),
        cache=InMemoryCache(),
    )
    first = gw.list_treasury_bonds()
    second = gw.list_treasury_bonds()
    assert len(first.results) == 3
    assert second == first
    assert calls == 1


def test_research_treasury_endpoint_filters_and_matches_registered_assets(
    api: SimpleNamespace,
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=SAMPLE_TESOURO_CSV.encode("utf-8"))

    gateway = CachedMarketGateway(
        brapi=BrapiProvider(),
        yfinance=YFinanceProvider(),
        bcb=BcbSgsProvider(),
        tesouro=TesouroTransparenteProvider(
            client=httpx.Client(transport=httpx.MockTransport(handler))
        ),
        cache=InMemoryCache(),
    )
    api.app.dependency_overrides[get_market_gateway] = lambda: gateway
    client = api.client

    all_bonds = client.get("/api/v1/research/treasury").json()
    assert all_bonds["total"] == 3
    assert all_bonds["catalog_size"] == 3
    assert all_bonds["unavailable_reason"] is None
    assert all(b["asset_id"] is None for b in all_bonds["results"])
    assert calls == 1

    # Subsequent searches read directly from PostgreSQL (treasury_catalog) without upstream calls
    ipca_semestral = client.get(
        "/api/v1/research/treasury",
        params={"indexer": "IPCA", "coupon_type": "semestral", "q": "2060"},
    ).json()
    assert [b["symbol"] for b in ipca_semestral["results"]] == [
        "tesouro-ipca-com-juros-semestrais-15082060"
    ]
    assert calls == 1

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
