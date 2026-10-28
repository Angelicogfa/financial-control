"""Shared test fixtures: migrated SQLite DB, offline gateway, and reference portfolio."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from composition import get_market_gateway, get_uow_factory
from controllers.auth.dependencies import require_user
from core.helpers.units import daily_rates, monthly_rates
from domain.market.entities import Quote
from domain.policy.services.allocation import ArcaTargets
from domain.portfolio.services.consolidation import (
    ConsolidatedPortfolioReport,
    consolidate_portfolio,
)
from domain.portfolio.services.fixed_income import RateCurves
from domain.shared.entities import (
    AssetEntity,
    EarningEntity,
    FixedIncomeTermEntity,
    MarketSeriesPoint,
    TransactionEntity,
)
from domain.shared.enums import (
    AssetType,
    EarningKind,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    SeriesUnit,
    TransactionKind,
)
from infra.cache.redis_cache import InMemoryCache
from infra.data.unit_of_work import SqlAlchemyUnitOfWork
from infra.providers.b3_listed import B3ListedProvider
from infra.providers.bcb import BcbSgsProvider
from infra.providers.brapi import BrapiProvider
from infra.providers.gateway import CachedMarketGateway
from infra.providers.yfinance_provider import YFinanceProvider
from main import create_app

API_DIR = Path(__file__).resolve().parents[1]
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


class _OfflineTicker:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.info: dict[str, Any] = {}

    def history(self, period: str = "1y", interval: str = "1d") -> Any:
        import pandas as pd

        return pd.DataFrame()


def offline_gateway() -> CachedMarketGateway:
    """Gateway whose providers return no data (quotes fall back, BCB uses annual rates)."""
    empty_brapi = httpx.MockTransport(lambda _r: httpx.Response(200, json={"results": []}))
    empty_bcb = httpx.MockTransport(lambda _r: httpx.Response(200, json=[]))
    return CachedMarketGateway(
        brapi=BrapiProvider(client=httpx.Client(transport=empty_brapi)),
        yfinance=YFinanceProvider(ticker_factory=_OfflineTicker),
        bcb=BcbSgsProvider(client=httpx.Client(transport=empty_bcb)),
        b3=B3ListedProvider(client=httpx.Client(transport=empty_bcb)),
        cache=InMemoryCache(),
    )


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    """FastAPI app wired to a freshly migrated SQLite database and an offline gateway."""
    db_url = f"sqlite:///{(tmp_path / 'api.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    alembic_cfg = Config(str(API_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(API_DIR / "infra" / "data" / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory=factory)

    app = create_app()
    gateway = offline_gateway()
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    app.dependency_overrides[get_market_gateway] = lambda: gateway
    app.dependency_overrides[require_user] = lambda: "tester"

    yield SimpleNamespace(app=app, client=TestClient(app), uow_factory=uow_factory)
    engine.dispose()


def _load_reference_data() -> dict[str, Any]:
    return json.loads((GOLDEN_DIR / "reference_portfolio.json").read_text(encoding="utf-8"))


def _rate_curves(data: dict[str, Any]) -> RateCurves:
    holidays = {date.fromisoformat(h) for h in data["holidays"]}
    months = sorted(data["cdi_daily_pct_by_month"])
    current = date.fromisoformat(f"{months[0]}-01")
    end = date.fromisoformat(data["as_of_date"])
    cdi_points: list[MarketSeriesPoint] = []
    while current <= end:
        if current.weekday() < 5 and current not in holidays:
            pct = data["cdi_daily_pct_by_month"][current.strftime("%Y-%m")]
            cdi_points.append(
                MarketSeriesPoint("CDI", current, pct, unit=SeriesUnit.PERCENT_PER_DAY)
            )
        current += timedelta(days=1)
    ipca_points = [
        MarketSeriesPoint(
            "IPCA", date.fromisoformat(f"{month}-01"), pct, unit=SeriesUnit.PERCENT_PER_MONTH
        )
        for month, pct in data["ipca_monthly_pct"].items()
    ]
    return RateCurves(
        cdi_daily=daily_rates(cdi_points),
        ipca_monthly=monthly_rates(ipca_points),
        annual_cdi_rate=data["annual_cdi_rate_fallback"],
        annual_ipca_rate=data["annual_ipca_rate_fallback"],
    )


def _build_asset(raw: dict[str, Any]) -> AssetEntity:
    asset_id = raw["id"]
    transactions = tuple(
        TransactionEntity(
            asset_id=asset_id,
            kind=TransactionKind(tx["kind"]),
            trade_date=date.fromisoformat(tx["date"]),
            quantity=Decimal(tx["qty"]),
            unit_price=Decimal(tx["price"]),
            fees=Decimal(tx["fees"]),
            fx_rate=Decimal(tx["fx"]),
            id=asset_id * 100 + index,
        )
        for index, tx in enumerate(raw["transactions"])
    )
    earnings = tuple(
        EarningEntity(
            asset_id=asset_id,
            kind=EarningKind(e["kind"]),
            payment_date=date.fromisoformat(e["date"]),
            gross_amount=Decimal(e["gross"]),
            withholding_tax=Decimal(e["tax"]),
        )
        for e in raw["earnings"]
    )
    term = None
    if raw_term := raw.get("fixed_income_term"):
        term = FixedIncomeTermEntity(
            instrument_kind=FixedIncomeInstrumentKind(raw_term["instrument_kind"]),
            indexer=FixedIncomeIndexer(raw_term["indexer"]),
            contracted_rate=Decimal(raw_term["contracted_rate"]),
            issue_date=date.fromisoformat(raw_term["issue_date"]),
            tax_exempt=raw_term["tax_exempt"],
        )
    return AssetEntity(
        id=asset_id,
        ticker=raw["ticker"],
        name=raw["name"],
        asset_type=AssetType(raw["asset_type"]),
        use_cerrado=False,
        fixed_income_term=term,
        transactions=transactions,
        earnings=earnings,
    )


@pytest.fixture(scope="session")
def reference_portfolio_data() -> dict[str, Any]:
    return _load_reference_data()


@pytest.fixture(scope="session")
def reference_assets(reference_portfolio_data: dict[str, Any]) -> list[AssetEntity]:
    return [_build_asset(raw) for raw in reference_portfolio_data["assets"]]


@pytest.fixture(scope="session")
def reference_curves(reference_portfolio_data: dict[str, Any]) -> RateCurves:
    return _rate_curves(reference_portfolio_data)


@pytest.fixture(scope="session")
def reference_report(
    reference_portfolio_data: dict[str, Any],
    reference_assets: list[AssetEntity],
) -> ConsolidatedPortfolioReport:
    data = reference_portfolio_data
    quotes = {
        raw["ticker"]: Quote(symbol=raw["ticker"], price=raw["quote"])
        for raw in data["assets"]
        if "quote" in raw
    }
    return consolidate_portfolio(
        reference_assets,
        ArcaTargets.default(),
        quotes=quotes,
        usd_brl_rate=data["usd_brl_rate"],
        curves=_rate_curves(data),
        as_of_date=date.fromisoformat(data["as_of_date"]),
    )
