"""Phase 39: every market source a screen shows is read from its own table."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from domain.agentic.services.catalog import OPERATIONS, JobRequestInput
from domain.market.entities import (
    AnnouncedDistributions,
    AnnouncedEarning,
    Fundamentals,
    PricePoint,
    Quote,
)
from domain.market.services.macro import annual_cdi_rate, annual_ipca_rate
from domain.shared.entities import (
    AssetEntity,
    CatalogInstrument,
    MarketSeriesPoint,
    TransactionEntity,
)
from domain.shared.enums import ArcaClass, AssetType, SeriesUnit, TransactionKind
from infra.providers.gateway import CachedMarketGateway
from infra.providers.stored import (
    MAX_LIVE_FETCH,
    distribution_lookup,
    stored_distributions,
    stored_histories,
    stored_macro_rates,
    stored_market_data,
)
from worker.jobs import (
    refresh_catalog_fundamentals_job,
    refresh_distributions_job,
    sync_price_history_job,
)

NOW = datetime(2026, 10, 29, 18, 0, tzinfo=UTC)
TODAY = NOW.date()


def _asset(uow, ticker: str, *, traded: bool = True, active: bool = True) -> AssetEntity:  # type: ignore[no-untyped-def]
    asset = uow.assets.add(
        AssetEntity(
            ticker=ticker,
            name=ticker,
            asset_type=AssetType.STOCK_BR,
            arca_class=ArcaClass.ACOES,
            is_active=active,
        )
    )
    if traded:
        uow.transactions.add(
            TransactionEntity(
                asset_id=asset.id,
                kind=TransactionKind.BUY,
                trade_date=date(2026, 1, 5),
                quantity=Decimal("10"),
                unit_price=Decimal("40"),
            )
        )
    return asset


def _closes(days: int, *, end: date = TODAY, start_price: float = 10.0) -> list[PricePoint]:
    return [
        PricePoint(date=end - timedelta(days=days - i), close=start_price + i * 0.1)
        for i in range(days)
    ]


class _Live:
    """Counts what reached the providers."""

    def __init__(self) -> None:
        self.history: list[tuple[str, str]] = []
        self.distributions: list[str] = []
        self.fundamentals: list[str] = []
        self.declared: dict[str, AnnouncedDistributions] = {}

    def get_history(
        self, symbol: str, *, range_period: str = "1y", **_kw: object
    ) -> list[PricePoint]:
        self.history.append((symbol, range_period))
        return _closes(400 if range_period == "max" else 20)

    def get_distributions(self, symbol: str, **_kw: object) -> AnnouncedDistributions:
        self.distributions.append(symbol)
        return self.declared.get(symbol, AnnouncedDistributions())

    def get_fundamentals(self, symbol: str, **_kw: object) -> Fundamentals:
        self.fundamentals.append(symbol)
        return Fundamentals(symbol=symbol, dividend_yield=0.08)


@pytest.fixture
def live(monkeypatch: pytest.MonkeyPatch) -> _Live:
    fake = _Live()
    monkeypatch.setattr(CachedMarketGateway, "get_history", fake.get_history)
    monkeypatch.setattr(CachedMarketGateway, "get_distributions", fake.get_distributions)
    monkeypatch.setattr(CachedMarketGateway, "get_fundamentals", fake.get_fundamentals)
    return fake


# ---------------------------------------------------------------- 39.1 quote audit
def test_quote_audit_keeps_the_last_quote_of_each_day(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        uow.market_data.save_quotes(
            {"WEGE3": Quote(symbol="WEGE3", price=50.0, provider="brapi")},
            fetched_at=NOW - timedelta(days=1),
        )
        uow.market_data.save_quotes({"WEGE3": Quote(symbol="WEGE3", price=51.0)}, fetched_at=NOW)
        later = NOW + timedelta(minutes=5)
        uow.market_data.save_quotes(
            {"WEGE3": Quote(symbol="WEGE3", price=52.0, provider="yfinance")}, fetched_at=later
        )
        uow.commit()
    body = api.client.get("/api/v1/market/quotes/wege3/history").json()
    assert [(d["day"], d["price"], d["provider"]) for d in body] == [
        (str(TODAY - timedelta(days=1)), 50.0, "brapi"),
        (str(TODAY), 52.0, "yfinance"),
    ]
    one_day = api.client.get(
        "/api/v1/market/quotes/WEGE3/history", params={"date_from": str(TODAY)}
    ).json()
    assert len(one_day) == 1
    assert "market.quote_history" in {spec.name for spec in OPERATIONS}


# ---------------------------------------------------------------- 39.2 price history
def test_price_history_loads_in_full_once_then_extends(api: SimpleNamespace, live: _Live) -> None:
    gateway = CachedMarketGateway()
    with api.uow_factory() as uow:
        _asset(uow, "WEGE3")
        uow.commit()

    assert sync_price_history_job(api.uow_factory, gateway, now=NOW) == {"full": 1, "recent": 0}
    assert live.history == [("WEGE3", "max")]
    assert sync_price_history_job(api.uow_factory, gateway, now=NOW) == {"full": 0, "recent": 1}
    assert live.history[-1] == ("WEGE3", "1mo")

    live.history.clear()
    with api.uow_factory() as uow:
        asset = uow.assets.list_all()[0]
        year = stored_histories(uow, gateway, [asset], range_period="1y", today=TODAY)["WEGE3"]
        everything = stored_histories(uow, gateway, [asset], range_period="max", today=TODAY)
    assert live.history == []  # read from the table
    assert year[0].date >= TODAY - timedelta(days=366)
    assert len(everything["WEGE3"]) == 400


def test_price_chart_route_reads_the_table(api: SimpleNamespace, live: _Live) -> None:
    with api.uow_factory() as uow:
        asset = _asset(uow, "WEGE3")
        uow.price_history.upsert("WEGE3", _closes(300), fetched_at=NOW)
        uow.commit()
    body = api.client.get(f"/api/v1/assets/{asset.id}/prices", params={"range": "6mo"}).json()
    assert live.history == []
    assert 150 <= len(body["points"]) <= 184


def test_a_ticker_never_stored_is_fetched_once_and_saved(api: SimpleNamespace, live: _Live) -> None:
    gateway = CachedMarketGateway()
    probe = AssetEntity(ticker="KLBN11", name="Klabin", asset_type=AssetType.STOCK_BR)
    with api.uow_factory() as uow:
        stored_histories(uow, gateway, [probe], range_period="5y", persist=True)
        uow.commit()
    with api.uow_factory() as uow:
        stored_histories(uow, gateway, [probe], range_period="5y", persist=True)
    assert live.history == [("KLBN11", "5y")]


def test_live_fetches_skip_archived_assets_and_are_capped(
    api: SimpleNamespace, live: _Live
) -> None:
    gateway = CachedMarketGateway()
    archived = AssetEntity(ticker="OLD3", name="x", asset_type=AssetType.STOCK_BR, is_active=False)
    many = [
        AssetEntity(ticker=f"NEW{i}", name="x", asset_type=AssetType.STOCK_BR)
        for i in range(MAX_LIVE_FETCH + 10)
    ]
    with api.uow_factory() as uow:
        stored_market_data(uow, gateway, [archived, *many], include_quotes=False)
    assert "OLD3" not in live.fundamentals
    assert len(live.fundamentals) == MAX_LIVE_FETCH


# ---------------------------------------------------------------- 39.3 declared distributions
def _earning(ticker: str) -> AnnouncedEarning:
    return AnnouncedEarning(
        ticker=ticker,
        label="DIVIDENDO",
        rate=0.5,
        com_date=TODAY + timedelta(days=5),
        payment_date=TODAY + timedelta(days=20),
    )


def test_distributions_are_stored_and_an_empty_answer_keeps_them(
    api: SimpleNamespace, live: _Live
) -> None:
    gateway = CachedMarketGateway()
    with api.uow_factory() as uow:
        _asset(uow, "ITSA4")
        _asset(uow, "WEGE3")
        uow.commit()
    live.declared = {"ITSA4": AnnouncedDistributions(cash=[_earning("ITSA4")])}
    assert refresh_distributions_job(api.uow_factory, gateway, now=NOW) == 2

    live.declared = {}  # the provider answers nothing
    refresh_distributions_job(api.uow_factory, gateway, now=NOW + timedelta(hours=6))
    live.distributions.clear()
    with api.uow_factory() as uow:
        assets = uow.assets.list_all()
        found = stored_distributions(uow, gateway, assets)
    assert live.distributions == []
    assert [e.rate for e in found["ITSA4"].cash] == [0.5]
    assert found["WEGE3"].cash == []

    # The B3 import and the MCP ask through the same lookup.
    lookup = distribution_lookup(api.uow_factory, gateway)
    assert lookup("itsa4", AssetType.STOCK_BR).cash[0].rate == 0.5
    assert live.distributions == []


def test_earnings_agenda_reads_the_table(api: SimpleNamespace, live: _Live) -> None:
    with api.uow_factory() as uow:
        _asset(uow, "ITSA4")
        uow.market_data.save_distributions(
            {"ITSA4": AnnouncedDistributions(cash=[_earning("ITSA4")])}, fetched_at=NOW
        )
        uow.commit()
    body = api.client.get(f"/api/v1/portfolio/earnings-agenda?as_of_date={TODAY}").json()
    assert live.distributions == []
    assert [i["ticker"] for i in body["items"]] == ["ITSA4"]


# ---------------------------------------------------------------- 39.4 annual CDI and IPCA
def _series(
    symbol: str, values: list[tuple[date, float]], unit: SeriesUnit
) -> list[MarketSeriesPoint]:
    return [
        MarketSeriesPoint(symbol=symbol, reference_date=d, value=v, unit=unit) for d, v in values
    ]


def test_annual_rates_follow_the_provider_arithmetic() -> None:
    cdi = _series(
        "CDI", [(TODAY - timedelta(days=2), 0.05), (TODAY, 0.055)], SeriesUnit.PERCENT_PER_DAY
    )
    assert annual_cdi_rate(cdi) == round((1 + 0.00055) ** 252 - 1, 6)
    ipca = _series(
        "IPCA",
        [(TODAY - timedelta(days=31 * i), 0.4) for i in range(12)],
        SeriesUnit.PERCENT_PER_MONTH,
    )
    assert annual_ipca_rate(ipca) == round(1.004**12 - 1, 6)
    assert annual_cdi_rate([]) is None


def test_macro_rates_come_from_the_stored_series(
    api: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_provider(_self: object) -> tuple[float, float]:
        raise AssertionError("the BCB must not be called")

    monkeypatch.setattr(CachedMarketGateway, "get_macro_rates", no_provider)
    with api.uow_factory() as uow:
        uow.market_series.upsert_points("CDI", [(TODAY, 0.05)], unit=SeriesUnit.PERCENT_PER_DAY)
        uow.market_series.upsert_points(
            "IPCA",
            [(TODAY - timedelta(days=31 * i), 0.4) for i in range(12)],
            unit=SeriesUnit.PERCENT_PER_MONTH,
        )
        uow.commit()
        cdi, ipca = stored_macro_rates(uow, CachedMarketGateway(), today=TODAY)
    assert cdi == round(1.0005**252 - 1, 6)
    assert ipca == round(1.004**12 - 1, 6)


# ---------------------------------------------------------------- 39.5 screener catalog
def test_catalog_indicators_are_stored_for_the_screener(api: SimpleNamespace, live: _Live) -> None:
    gateway = CachedMarketGateway()
    with api.uow_factory() as uow:
        uow.catalog.upsert(
            [
                CatalogInstrument(ticker="TAEE11", name="Taesa", asset_type=AssetType.STOCK_BR),
                CatalogInstrument(ticker="SEMTIPO", name="?", asset_type=None),
            ]
        )
        uow.commit()
    assert refresh_catalog_fundamentals_job(api.uow_factory, gateway, now=NOW) == 1
    live.fundamentals.clear()
    assert refresh_catalog_fundamentals_job(api.uow_factory, gateway, now=NOW) == 0
    assert live.fundamentals == []  # still fresh
    with api.uow_factory() as uow:
        stored = uow.market_data.get_many(["TAEE11"])["TAEE11"]
    assert stored.fundamentals is not None and stored.fundamentals.dividend_yield == 0.08


def test_new_jobs_can_be_requested_by_hand() -> None:
    for name in ("sync_price_history", "refresh_distributions", "refresh_catalog_fundamentals"):
        assert JobRequestInput(job_name=name).job_name == name  # type: ignore[arg-type]
