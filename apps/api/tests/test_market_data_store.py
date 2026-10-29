"""Phase 38: quotes and fundamentals stored by the worker and read by the screens."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from domain.agentic.services.catalog import OPERATIONS, JobRequestInput
from domain.market.entities import Fundamentals, Quote, QuoteFreshness
from domain.shared.entities import AssetEntity, TransactionEntity
from domain.shared.enums import ArcaClass, AssetType, TransactionKind
from infra.providers.gateway import CachedMarketGateway
from infra.providers.stored import FX_SYMBOL, stored_market_data, stored_usd_brl
from worker.jobs import refresh_watchlist_quotes_job, warm_portfolio_quotes_job

NOW = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)


class _Provider:
    """Counts the provider calls and answers a fixed price per ticker."""

    def __init__(self, prices: dict[str, float]) -> None:
        self.prices = prices
        self.quotes: list[str] = []
        self.fundamentals: list[str] = []

    def quote(self, symbol: str, **_kw: object) -> Quote | None:
        self.quotes.append(symbol)
        price = self.prices.get(symbol)
        return None if price is None else Quote(symbol=symbol, price=price, provider="test")

    def fund(self, symbol: str, **_kw: object) -> Fundamentals | None:
        self.fundamentals.append(symbol)
        return Fundamentals(symbol=symbol, price_to_earnings=10.0)


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> _Provider:
    fake = _Provider({"WEGE3": 50.0, "ITUB4": 30.0, "BBAS3": 25.0, "USDBRL=X": 5.4})
    monkeypatch.setattr(CachedMarketGateway, "get_quote", fake.quote)
    monkeypatch.setattr(CachedMarketGateway, "get_fundamentals", fake.fund)
    return fake


def _asset(uow, ticker: str, *, traded: bool) -> AssetEntity:  # type: ignore[no-untyped-def]
    asset = uow.assets.add(
        AssetEntity(
            ticker=ticker, name=ticker, asset_type=AssetType.STOCK_BR, arca_class=ArcaClass.ACOES
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


def test_repository_keeps_quote_and_fundamentals_apart(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        uow.market_data.save_fundamentals(
            {"wege3": Fundamentals(symbol="WEGE3", price_to_earnings=30.0)}, fetched_at=NOW
        )
        uow.market_data.save_quotes({"WEGE3": Quote(symbol="WEGE3", price=50.0)}, fetched_at=NOW)
        later = NOW + timedelta(minutes=5)
        uow.market_data.save_quotes({"WEGE3": Quote(symbol="WEGE3", price=51.0)}, fetched_at=later)
        uow.commit()
    with api.uow_factory() as uow:
        data = uow.market_data.get_many(["wege3", "NONE3"])
    assert set(data) == {"WEGE3"}
    assert data["WEGE3"].quote is not None and data["WEGE3"].quote.price == 51.0
    # Saving a quote does not drop the fundamentals fetched earlier.
    assert data["WEGE3"].fundamentals is not None
    assert data["WEGE3"].fundamentals.price_to_earnings == 30.0
    assert data["WEGE3"].fundamentals_fetched_at is not None


def test_screens_read_the_database_and_go_live_only_for_never_stored(
    api: SimpleNamespace, provider: _Provider
) -> None:
    gateway = CachedMarketGateway()
    with api.uow_factory() as uow:
        stored = _asset(uow, "WEGE3", traded=True)
        fresh = _asset(uow, "ITUB4", traded=True)
        uow.market_data.save_quotes({"WEGE3": Quote(symbol="WEGE3", price=48.0)}, fetched_at=NOW)
        uow.commit()
        market = stored_market_data(uow, gateway, [stored, fresh])

    assert market.quotes["WEGE3"].price == 48.0
    assert market.quotes["WEGE3"].freshness == QuoteFreshness.CACHED
    assert market.quotes["ITUB4"].price == 30.0
    # Only the ticker without a stored row reached the provider.
    assert provider.quotes == ["ITUB4"]
    assert provider.fundamentals == ["ITUB4"]


def test_worker_stores_holdings_and_watchlist_on_their_own_jobs(
    api: SimpleNamespace, provider: _Provider
) -> None:
    gateway = CachedMarketGateway()
    with api.uow_factory() as uow:
        _asset(uow, "WEGE3", traded=True)
        _asset(uow, "BBAS3", traded=False)
        uow.commit()

    assert warm_portfolio_quotes_job(api.uow_factory, gateway, now=NOW) == 1
    assert provider.quotes == ["WEGE3", FX_SYMBOL]
    with api.uow_factory() as uow:
        assert set(uow.market_data.get_many(["WEGE3", "BBAS3"])) == {"WEGE3"}
        # The exchange rate is stored with the holdings and read back without a provider call.
        assert stored_usd_brl(uow, gateway) == 5.4

    assert refresh_watchlist_quotes_job(api.uow_factory, gateway, now=NOW) == 1
    with api.uow_factory() as uow:
        data = uow.market_data.get_many(["WEGE3", "BBAS3"])
    assert data["BBAS3"].quote is not None and data["BBAS3"].quote.price == 25.0

    # Five minutes later the quotes are asked again but the fundamentals are still fresh.
    provider.quotes.clear()
    provider.fundamentals.clear()
    warm_portfolio_quotes_job(api.uow_factory, gateway, now=NOW + timedelta(minutes=5))
    assert provider.quotes == ["WEGE3", FX_SYMBOL]
    assert provider.fundamentals == []
    warm_portfolio_quotes_job(api.uow_factory, gateway, now=NOW + timedelta(hours=25))
    assert provider.fundamentals == ["WEGE3"]


def test_a_failed_refresh_keeps_the_last_quote(api: SimpleNamespace, provider: _Provider) -> None:
    gateway = CachedMarketGateway()
    with api.uow_factory() as uow:
        _asset(uow, "WEGE3", traded=True)
        uow.commit()
    warm_portfolio_quotes_job(api.uow_factory, gateway, now=NOW)
    provider.prices.clear()  # the provider is down
    assert warm_portfolio_quotes_job(api.uow_factory, gateway, now=NOW + timedelta(minutes=5)) == 0
    with api.uow_factory() as uow:
        data = uow.market_data.get_many(["WEGE3"])["WEGE3"]
    assert data.quote is not None and data.quote.price == 50.0
    assert data.quote_fetched_at is not None
    assert data.quote_fetched_at.replace(tzinfo=UTC) == NOW


def test_the_report_prices_holdings_from_the_database(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        _asset(uow, "WEGE3", traded=True)
        uow.market_data.save_quotes({"WEGE3": Quote(symbol="WEGE3", price=55.0)}, fetched_at=NOW)
        uow.commit()
    report = api.client.get("/api/v1/portfolio/consolidated").json()
    position = next(p for p in report["positions"] if p["ticker"] == "WEGE3")
    assert position["current_unit_price"] == 55.0
    assert position["price_freshness"] == "CACHED"


def test_quote_status_tells_how_old_the_holdings_quotes_are(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        _asset(uow, "WEGE3", traded=True)
        _asset(uow, "ITUB4", traded=True)
        _asset(uow, "BBAS3", traded=False)
        uow.market_data.save_quotes(
            {"WEGE3": Quote(symbol="WEGE3", price=50.0)}, fetched_at=datetime.now(UTC)
        )
        uow.commit()
    body = api.client.get("/api/v1/market/quotes/status").json()
    assert body["holdings"] == 2
    assert body["stored"] == 1
    assert body["stale"] == 1  # ITUB4 has no stored quote yet
    assert body["stale_minutes"] == 30
    assert body["oldest_at"] is not None

    queued = api.client.post("/api/v1/market/job-runs/warm_portfolio_quotes/request")
    assert queued.status_code == 202
    assert queued.json()["status"] == "REQUESTED"


def test_quote_status_and_refresh_are_mcp_operations() -> None:
    names = {spec.name for spec in OPERATIONS}
    assert "market.quote_status" in names
    assert JobRequestInput(job_name="warm_portfolio_quotes").job_name == "warm_portfolio_quotes"
