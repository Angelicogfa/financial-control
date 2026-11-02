"""Instrument page and global search (Phase 48.R2): any ticker opens without registering it."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from composition import get_market_gateway
from core.errors import ValidationError
from domain.agentic.services.catalog import (
    CATALOG_BY_NAME,
    AgenticRuntimeHandlers,
    InstrumentKeyInput,
    InstrumentSearchInput,
)
from domain.instruments.read_models import InstrumentKind, MatchKind, instrument_key
from domain.instruments.services import fold, match_kind
from domain.market.entities import Fundamentals, PricePoint, Quote, TreasuryBond
from domain.recommendation.lenses import AssetLenses, LensScore
from domain.shared.entities import CatalogInstrument
from domain.shared.enums import (
    AssetType,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
)

NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)


class _NoProviderGateway:
    """Any provider call during a request fails the test (rule of Phase 39)."""

    def __getattr__(self, name: str):
        raise AssertionError(f"provider called during the request: {name}")


def _seed(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        uow.catalog.upsert(
            [
                CatalogInstrument(
                    ticker="PETR4",
                    name="Petrobras PN",
                    asset_type=AssetType.STOCK_BR,
                    sector="Petróleo, Gás e Biocombustíveis",
                    close=38.5,
                    change_pct=1.2,
                    volume_brl=2.0e9,
                    updated_at=NOW,
                ),
                CatalogInstrument(
                    ticker="PETR3",
                    name="Petrobras ON",
                    asset_type=AssetType.STOCK_BR,
                    close=41.0,
                    volume_brl=5.0e8,
                ),
                CatalogInstrument(
                    ticker="ITSA4",
                    name="Itaúsa PN",
                    asset_type=AssetType.STOCK_BR,
                    sector="Financeiro",
                    close=10.2,
                    volume_brl=3.0e8,
                ),
            ]
        )
        uow.market_data.save_quotes({"ITSA4": Quote("ITSA4", 10.5, change_pct=0.4)}, fetched_at=NOW)
        uow.market_data.save_fundamentals(
            {"ITSA4": Fundamentals("ITSA4", price_to_earnings=7.5, dividend_yield=0.08)},
            fetched_at=NOW,
        )
        uow.price_history.upsert(
            "ITSA4",
            [
                PricePoint(date=date(2026, 10, 1) + timedelta(days=i), close=10.0 + i * 0.01)
                for i in range(30)
            ],
            fetched_at=NOW,
        )
        uow.treasury_catalog.upsert(
            [
                TreasuryBond(
                    symbol="tesouro-ipca-15052035",
                    name="Tesouro IPCA+ 2035",
                    bond_type="Tesouro IPCA+",
                    instrument_kind=FixedIncomeInstrumentKind.TESOURO_IPCA,
                    indexer=FixedIncomeIndexer.IPCA,
                    raw_indexer="IPCA",
                    coupon_type="NONE",
                    maturity_date=date(2035, 5, 15),
                    buy_rate=7.1,
                    buy_price=2100.5,
                    updated_at=NOW,
                )
            ]
        )
        uow.recommendation.replace_lenses(
            date(2026, 11, 1),
            [
                AssetLenses(
                    ticker="ITSA4",
                    as_of=date(2026, 11, 1),
                    source="CATALOG",
                    arca_class="ACOES",
                    sector="Financeiro",
                    lenses=[LensScore("VALUATION", 1.1, 0.8, 0.9, "barata contra o setor")],
                )
            ],
        )
        uow.commit()


def _register(api: SimpleNamespace, ticker: str) -> int:
    resp = api.client.post(
        "/api/v1/assets", json={"ticker": ticker, "name": ticker, "asset_type": "STOCK_BR"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# --- keys and matching ----------------------------------------------------------------------


def test_instrument_key_normalizes_tickers_and_tesouro_symbols() -> None:
    assert instrument_key(" itsa4 ").value == "ITSA4"
    assert instrument_key("ITSA4").kind == InstrumentKind.LISTED
    assert instrument_key("BRK.B").value == "BRK.B"
    treasury = instrument_key("Tesouro-IPCA-15052035")
    assert (treasury.value, treasury.kind) == ("tesouro-ipca-15052035", InstrumentKind.TREASURY)


@pytest.mark.parametrize("raw", ["", "  ", "IT SA4", "../etc", "tesouro-", "A" * 40])
def test_instrument_key_rejects_invalid_codes(raw: str) -> None:
    with pytest.raises(ValidationError):
        instrument_key(raw)


def test_fold_ignores_case_and_accents() -> None:
    assert fold("  Itaúsa PN ") == "itausa pn"


def test_match_kind_orders_ticker_before_name() -> None:
    assert match_kind("petr4", "PETR4", "Petrobras PN") == MatchKind.TICKER_EXACT
    assert match_kind("petr", "PETR4", "Petrobras PN") == MatchKind.TICKER_PREFIX
    assert match_kind("itausa", "ITSA4", "Itaúsa PN") == MatchKind.NAME_PREFIX
    assert match_kind("2035", "tesouro-x", "Tesouro IPCA+ 2035") == MatchKind.NAME_PREFIX
    assert match_kind("bras", "PETR4", "Petrobras PN") == MatchKind.NAME_CONTAINS
    assert match_kind("vale", "PETR4", "Petrobras PN") is None


# --- instrument page ------------------------------------------------------------------------


def test_a_catalog_ticker_opens_without_registering_it(api: SimpleNamespace) -> None:
    _seed(api)

    resp = api.client.get("/api/v1/instruments/petr4")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["key"] == "PETR4"
    assert body["kind"] == "LISTED"
    assert body["name"] == "Petrobras PN"
    assert body["sector"] == "Petróleo, Gás e Biocombustíveis"
    assert body["in_catalog"] is True
    assert body["quote"]["source"] == "CATALOG_CLOSE"
    assert body["quote"]["price"] == 38.5
    assert body["tracking"] is None
    assert body["indicators"] is None
    assert body["forecast"]["status"] == "NOT_COMPUTED"
    assert any("catálogo" in g for g in body["data_gaps"])
    # Opening it never writes: still no asset.
    with api.uow_factory() as uow:
        assert uow.assets.get_by_ticker("PETR4") is None


def test_a_stored_quote_wins_over_the_catalog_close(api: SimpleNamespace) -> None:
    _seed(api)

    body = api.client.get("/api/v1/instruments/ITSA4").json()

    assert body["quote"]["source"] == "STORED_QUOTE"
    assert body["quote"]["price"] == 10.5
    assert body["indicators"]["price_to_earnings"] == 7.5
    assert body["lenses"]["arca_class"] == "ACOES"
    assert body["lenses"]["items"][0]["lens"] == "VALUATION"
    assert body["lenses"]["eligible"] is None


def test_a_registered_asset_shows_its_tracking(api: SimpleNamespace) -> None:
    _seed(api)
    asset_id = _register(api, "ITSA4")

    body = api.client.get("/api/v1/instruments/ITSA4").json()
    assert body["tracking"] == {
        "asset_id": asset_id,
        "is_active": True,
        "holds_position": False,
        "arca_class": body["tracking"]["arca_class"],
        "purpose": "ARCA",
    }

    trade = api.client.post(
        "/api/v1/transactions",
        json={
            "asset_id": asset_id,
            "kind": "BUY",
            "trade_date": "2026-10-20",
            "quantity": "100",
            "unit_price": "10.00",
        },
    )
    assert trade.status_code == 201, trade.text
    assert api.client.get("/api/v1/instruments/ITSA4").json()["tracking"]["holds_position"]


def test_a_registered_asset_outside_the_catalog_still_opens(api: SimpleNamespace) -> None:
    _register(api, "XPTO3")

    body = api.client.get("/api/v1/instruments/XPTO3").json()

    assert body["in_catalog"] is False
    assert body["quote"] is None
    assert body["tracking"]["asset_id"] > 0
    assert "Ainda não há cotação guardada deste ativo." in body["data_gaps"]


def test_unknown_and_invalid_keys(api: SimpleNamespace) -> None:
    missing = api.client.get("/api/v1/instruments/ZZZZ3")
    assert missing.status_code == 404
    assert missing.json()["code"] == "INSTRUMENT_NOT_FOUND"
    assert api.client.get("/api/v1/instruments/tesouro-nada-2099").status_code == 404
    invalid = api.client.get("/api/v1/instruments/IT%20SA4")
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "INVALID_INSTRUMENT"


def test_a_tesouro_bond_opens_with_its_terms(api: SimpleNamespace) -> None:
    _seed(api)

    body = api.client.get("/api/v1/instruments/tesouro-ipca-15052035").json()

    assert body["kind"] == "TREASURY"
    assert body["name"] == "Tesouro IPCA+ 2035"
    assert body["quote"]["source"] == "TREASURY_PRICE"
    assert body["quote"]["price"] == 2100.5
    assert body["treasury"]["maturity_date"] == "2035-05-15"
    assert body["treasury"]["indexer"] == "IPCA"


def test_a_forecast_without_enough_history_says_so(api: SimpleNamespace) -> None:
    _seed(api)
    with api.uow_factory() as uow:
        uow.forecasts.save(
            "ITSA4",
            date(2026, 11, 1),
            {"status": "INSUFFICIENT_HISTORY", "months": 4},
            model_version="test",
        )
        uow.commit()

    forecast = api.client.get("/api/v1/instruments/ITSA4").json()["forecast"]

    assert forecast["status"] == "INSUFFICIENT_HISTORY"
    assert forecast["bands"] == []


def test_prices_come_from_the_stored_history(api: SimpleNamespace) -> None:
    _seed(api)

    body = api.client.get("/api/v1/instruments/itsa4/prices?range=max").json()

    assert body["range"] == "max"
    assert len(body["points"]) == 30
    assert body["high"]["price"] == pytest.approx(10.29)
    assert api.client.get("/api/v1/instruments/PETR4/prices").json()["points"] == []
    assert api.client.get("/api/v1/instruments/ITSA4/prices?range=3d").status_code == 422


def test_no_provider_is_called_during_the_request(api: SimpleNamespace) -> None:
    _seed(api)
    api.app.dependency_overrides[get_market_gateway] = lambda: _NoProviderGateway()

    for path in (
        "/api/v1/instruments/PETR4",
        "/api/v1/instruments/ITSA4",
        "/api/v1/instruments/ITSA4/prices",
        "/api/v1/instruments/tesouro-ipca-15052035",
        "/api/v1/search?q=petr",
    ):
        assert api.client.get(path).status_code == 200, path


# --- search ---------------------------------------------------------------------------------


def test_search_puts_the_exact_ticker_first_then_prefixes_by_volume(api: SimpleNamespace) -> None:
    _seed(api)

    hits = api.client.get("/api/v1/search?q=petr").json()["hits"]
    assert [h["ticker"] for h in hits] == ["PETR4", "PETR3"]  # same match, more volume first

    exact = api.client.get("/api/v1/search?q=PETR3").json()["hits"]
    assert exact[0]["ticker"] == "PETR3"
    assert exact[0]["match"] == "TICKER_EXACT"


def test_search_matches_names_without_accents_and_tesouro_bonds(api: SimpleNamespace) -> None:
    _seed(api)

    itausa = api.client.get("/api/v1/search?q=itausa").json()["hits"]
    assert itausa[0]["ticker"] == "ITSA4"
    assert itausa[0]["match"] == "NAME_PREFIX"

    bonds = api.client.get("/api/v1/search?q=ipca").json()["hits"]
    assert bonds[0]["kind"] == "TREASURY"
    assert bonds[0]["key"] == "tesouro-ipca-15052035"


def test_search_marks_registered_assets_and_finds_those_outside_the_catalog(
    api: SimpleNamespace,
) -> None:
    _seed(api)
    itsa = _register(api, "ITSA4")
    other = _register(api, "XPTO3")

    hit = api.client.get("/api/v1/search?q=ITSA4").json()["hits"][0]
    assert hit["tracked_asset_id"] == itsa
    assert hit["name"] == "ITSA4"  # the registered name wins

    outside = api.client.get("/api/v1/search?q=xpto").json()["hits"]
    assert [(h["ticker"], h["tracked_asset_id"]) for h in outside] == [("XPTO3", other)]


def test_search_limits_and_validates(api: SimpleNamespace) -> None:
    _seed(api)

    body = api.client.get("/api/v1/search?q=p&limit=1").json()
    assert len(body["hits"]) == 1
    assert body["total"] >= 2
    assert api.client.get("/api/v1/search?q=").status_code == 422
    assert api.client.get("/api/v1/search?q=a&limit=99").status_code == 422
    assert api.client.get("/api/v1/search?q=zzzz").json() == {
        "query": "zzzz",
        "hits": [],
        "total": 0,
    }


# --- MCP ------------------------------------------------------------------------------------


def test_mcp_operations_reuse_the_same_handlers(api: SimpleNamespace) -> None:
    _seed(api)
    handlers = AgenticRuntimeHandlers(uow_factory=api.uow_factory, portfolio_service=None)  # type: ignore[arg-type]

    view = CATALOG_BY_NAME["instruments.get"].invoke(handlers, InstrumentKeyInput(key="petr4"))
    found = CATALOG_BY_NAME["instruments.search"].invoke(
        handlers, InstrumentSearchInput(q="itausa")
    )

    assert view.quote.source == "CATALOG_CLOSE"
    assert found.hits[0].ticker == "ITSA4"
    assert CATALOG_BY_NAME["instruments.get"].kind == "query"
