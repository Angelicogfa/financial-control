"""Phase 26.1/26.2: Tesouro price series, mark-to-market, early-sale signals and routes."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.market.entities import QuoteFreshness, TreasuryBond
from domain.market.services.treasury_prices import (
    TreasuryPricePoint,
    asset_family,
    asset_price_symbol,
    bond_family,
    price_symbol,
    rate_symbol,
)
from domain.policy.services.allocation import ArcaTargets
from domain.portfolio.services.consolidation import consolidate_portfolio
from domain.portfolio.services.fixed_income import RateCurves
from domain.portfolio.services.mark_to_market import (
    EarlySaleRules,
    MarketQuoteTD,
    MarketStatus,
    SaleSignal,
    evaluate_mark_to_market,
    market_history,
    quantity_lots,
)
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.entities import AssetEntity, FixedIncomeTermEntity, TransactionEntity
from domain.shared.enums import (
    ArcaClass,
    AssetType,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    FixedIncomeLiquidity,
    SeriesUnit,
    TransactionKind,
)
from domain.tax.services.rules import DEFAULT_RULE_BOOK
from infra.providers.tesouro import TesouroTransparenteProvider, parse_price_history_csv
from tests.conftest import offline_gateway
from worker.jobs import sync_treasury_prices_job

AS_OF = date(2026, 10, 28)
PURCHASE = date(2026, 3, 17)
MATURITY = date(2029, 1, 1)
PURCHASE_PU = Decimal("700.22")
QTY = Decimal("2.45")

HISTORY_CSV = (
    "Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;"
    "PU Compra Manha;PU Venda Manha;PU Base Manha\n"
    "Tesouro Prefixado;01/01/2029;27/10/2026;14,88;15,00;741,63;739,55;739,55\n"
    "Tesouro Prefixado;01/01/2029;26/10/2026;15,40;15,52;734,03;731,96;731,96\n"
    "Tesouro IPCA+ com Juros Semestrais;15/05/2037;27/10/2026;7,75;7,87;4336,95;4300,84;4300,84\n"
    "Tesouro Selic;01/03/2029;27/10/2026;0,02;0,03;20175,28;20162,27;20162,27\n"
)


def _prefixado(*transactions: TransactionEntity, asset_id: int = 1) -> AssetEntity:
    return AssetEntity(
        id=asset_id,
        ticker="PRE29",
        name="Tesouro Prefixado 2029",
        asset_type=AssetType.TREASURY,
        fixed_income_term=FixedIncomeTermEntity(
            instrument_kind=FixedIncomeInstrumentKind.TESOURO_PRE,
            indexer=FixedIncomeIndexer.PRE,
            contracted_rate=Decimal("0.15"),
            maturity_date=MATURITY,
        ),
        transactions=transactions
        or (
            TransactionEntity(
                asset_id=asset_id,
                kind=TransactionKind.BUY,
                trade_date=PURCHASE,
                quantity=QTY,
                unit_price=PURCHASE_PU,
            ),
        ),
    )


# --- series keys and history file -------------------------------------------------------------


def test_bond_families_tell_same_maturity_bonds_apart() -> None:
    assert bond_family("Tesouro IPCA+") == "IPCA"
    assert bond_family("Tesouro IPCA+ com Juros Semestrais") == "IPCA-S"
    assert bond_family("Tesouro Prefixado com Juros Semestrais") == "PRE-S"
    assert bond_family("Tesouro Selic") == "SELIC"
    assert bond_family("Tesouro Educa+") == "EDUCA"
    assert bond_family("Tesouro Renda+ Aposentadoria Extra") == "RENDA"
    assert bond_family("Tesouro IGPM+ com Juros Semestrais") == "IGPM-S"
    assert price_symbol("IPCA-S", date(2037, 5, 15)) == "TD:IPCA-S:20370515"
    assert rate_symbol("IPCA-S", date(2037, 5, 15)) == "TD:IPCA-S:20370515:R"
    assert len(rate_symbol("IGPM-S", date(2031, 1, 1))) <= 32


def test_asset_family_uses_terms_name_and_coupons() -> None:
    asset = _prefixado()
    assert asset_family(asset) == "PRE"
    assert asset_price_symbol(asset) == "TD:PRE:20290101"
    term = FixedIncomeTermEntity(
        instrument_kind=FixedIncomeInstrumentKind.TESOURO_IPCA,
        indexer=FixedIncomeIndexer.IPCA,
        contracted_rate=Decimal("0.07"),
        maturity_date=date(2037, 5, 15),
        semiannual_coupons=True,
    )
    coupon = AssetEntity(
        ticker="B37",
        name="Tesouro IPCA+ com Juros Semestrais 2037",
        asset_type=AssetType.TREASURY,
        fixed_income_term=term,
    )
    assert asset_family(coupon) == "IPCA-S"
    stock = AssetEntity(ticker="WEGE3", name="WEG", asset_type=AssetType.STOCK_BR)
    assert asset_price_symbol(stock) is None


def test_parse_price_history_filters_families_and_dates() -> None:
    every = parse_price_history_csv(HISTORY_CSV)
    pre = parse_price_history_csv(HISTORY_CSV, families={"PRE"}, since=date(2026, 10, 27))

    assert len(every) == 4
    assert len(pre) == 1
    assert pre[0].sell_price == 739.55
    assert pre[0].sell_rate == 15.0
    assert pre[0].buy_price == 741.63


def test_provider_history_download_and_failure() -> None:
    ok = TesouroTransparenteProvider(
        history_csv_url="https://example.test/history.csv",
        client=httpx.Client(
            transport=httpx.MockTransport(lambda _r: httpx.Response(200, text=HISTORY_CSV))
        ),
    )
    broken = TesouroTransparenteProvider(
        history_csv_url="https://example.test/history.csv",
        client=httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(503))),
    )
    assert len(ok.list_price_history(families={"IPCA-S"})) == 1
    assert broken.list_price_history() == []


# --- mark-to-market engine ---------------------------------------------------------------------


def test_real_prefixado_case_is_below_the_curve() -> None:
    """Validated against the Tesouro PU of 28/10/2026: bought at 13.75%, sell rate 14.91%."""
    valuation = evaluate_mark_to_market(
        _prefixado(), AS_OF, quote=MarketQuoteTD(741.21, AS_OF, 14.91), reference_rate=0.149
    )

    assert valuation.status == MarketStatus.BELOW_CURVE
    assert valuation.curve_value == pytest.approx(1857.02, abs=0.05)
    assert valuation.market_value == pytest.approx(1815.96, abs=0.01)
    assert valuation.premium == pytest.approx(-41.06, abs=0.05)
    lot = valuation.lots[0]
    assert lot.purchase_rate == pytest.approx(0.13751, abs=1e-4)
    assert lot.net_hold_value == pytest.approx(2450 - (2450 - 1715.54) * 0.15, abs=0.05)
    assert lot.breakeven_rate == pytest.approx(0.1522, abs=5e-4)
    assert lot.signals == []
    assert "abaixo da curva" in valuation.explanation


def test_lower_market_rate_flags_an_opportunity() -> None:
    valuation = evaluate_mark_to_market(
        _prefixado(), AS_OF, quote=MarketQuoteTD(790.0, AS_OF, 11.5), reference_rate=0.149
    )

    lot = valuation.lots[0]
    assert valuation.status == MarketStatus.OPPORTUNITY
    assert valuation.premium > 0
    assert lot.market_annual_rate > lot.curve_annual_rate
    assert set(lot.signals) == {SaleSignal.EXCESS_RETURN, SaleSignal.REINVESTMENT}
    assert lot.net_sale_value < lot.market_value  # income tax on the gain
    assert "acima da curva" in valuation.explanation


def test_small_premium_stays_neutral_under_strict_thresholds() -> None:
    curve_pu = 757.97
    valuation = evaluate_mark_to_market(
        _prefixado(),
        AS_OF,
        quote=MarketQuoteTD(curve_pu + 1.0, AS_OF, 13.6),
        reference_rate=0.10,
        early_sale=EarlySaleRules(min_excess_rate=0.05, min_reinvest_spread=0.05),
    )
    assert valuation.status == MarketStatus.NEUTRAL
    assert valuation.premium == pytest.approx(2.45, abs=0.1)


def test_without_quote_the_curve_is_kept() -> None:
    valuation = evaluate_mark_to_market(_prefixado(), AS_OF, quote=None)
    assert valuation.status == MarketStatus.NO_MARKET_DATA
    assert valuation.curve_value > 0
    assert valuation.market_value is None
    stale = evaluate_mark_to_market(
        _prefixado(), AS_OF, quote=MarketQuoteTD(741.21, AS_OF - timedelta(days=20))
    )
    assert stale.stale_price is True


def test_quantity_lots_consume_the_oldest_first() -> None:
    buy = lambda d, q: TransactionEntity(  # noqa: E731
        asset_id=1,
        kind=TransactionKind.BUY,
        trade_date=d,
        quantity=Decimal(q),
        unit_price=PURCHASE_PU,
    )
    sell = TransactionEntity(
        asset_id=1,
        kind=TransactionKind.SELL,
        trade_date=date(2026, 6, 1),
        quantity=Decimal("1.5"),
        unit_price=Decimal("720"),
    )
    lots = quantity_lots([buy(PURCHASE, "1"), buy(date(2026, 4, 1), "2"), sell], AS_OF)
    assert [(lot.start, lot.quantity) for lot in lots] == [(date(2026, 4, 1), pytest.approx(1.5))]


def test_market_history_samples_the_series() -> None:
    prices = [(PURCHASE + timedelta(days=i), 700.0 + i * 0.2) for i in range(0, 220)]
    points = market_history(
        _prefixado(), prices, curves=RateCurves(), rules=DEFAULT_RULE_BOOK, as_of=AS_OF
    )
    assert 100 <= len(points) <= 121
    assert points[-1].day == prices[-1][0]
    assert points[-1].market_value == pytest.approx(float(QTY) * prices[-1][1], abs=0.01)


def test_consolidation_can_value_treasury_at_market() -> None:
    asset = _prefixado()
    targets = ArcaTargets({c: 25.0 for c in ArcaClass})
    curve = consolidate_portfolio([asset], targets, as_of_date=AS_OF)
    market = consolidate_portfolio(
        [asset],
        targets,
        as_of_date=AS_OF,
        treasury_market_prices={"PRE29": 741.21},
    )
    curve_pos, market_pos = curve.positions[0], market.positions[0]
    assert curve_pos.price_freshness == QuoteFreshness.CURVE
    assert market_pos.price_freshness == QuoteFreshness.LIVE
    assert market_pos.gross_current_value_brl == pytest.approx(1815.96, abs=0.01)
    assert market_pos.current_value_brl < curve_pos.current_value_brl


# --- worker job and routes ----------------------------------------------------------------------


def _create_prefixado(api: SimpleNamespace) -> int:
    resp = api.client.post(
        "/api/v1/assets",
        json={
            "ticker": "PRE29",
            "name": "Tesouro Prefixado 2029",
            "asset_type": "TREASURY",
            "arca_class": "CAIXA",
            "fixed_income_term": {
                "instrument_kind": "TESOURO_PRE",
                "indexer": "PRE",
                "contracted_rate": "0.15",
                "maturity_date": MATURITY.isoformat(),
            },
        },
    )
    assert resp.status_code == 201, resp.text
    asset_id = resp.json()["id"]
    trade = api.client.post(
        "/api/v1/transactions",
        json={
            "asset_id": asset_id,
            "kind": "BUY",
            "trade_date": PURCHASE.isoformat(),
            "quantity": str(QTY),
            "unit_price": str(PURCHASE_PU),
        },
    )
    assert trade.status_code == 201, trade.text
    return asset_id


class _HistoryGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[set[str] | None, date | None]] = []

    def get_treasury_price_history(self, *, families=None, since=None):  # noqa: ANN001, ANN201
        self.calls.append((families, since))
        return [
            TreasuryPricePoint("Tesouro Prefixado", MATURITY, date(2026, 3, 16), 699.80, 13.8),
            TreasuryPricePoint("Tesouro Prefixado", MATURITY, date(2026, 10, 26), 731.96, 15.52),
            TreasuryPricePoint("Tesouro Prefixado", MATURITY, date(2026, 10, 27), 739.55, 15.0),
            TreasuryPricePoint(
                "Tesouro Prefixado", date(2032, 1, 1), date(2026, 10, 27), 480.0, 15.1
            ),
        ]


def _today_bond() -> TreasuryBond:
    return TreasuryBond(
        symbol="tesouro-prefixado-01012029",
        name="Tesouro Prefixado 2029",
        bond_type="Tesouro Prefixado",
        instrument_kind=FixedIncomeInstrumentKind.TESOURO_PRE,
        indexer=FixedIncomeIndexer.PRE,
        raw_indexer="prefixado",
        coupon_type="zero",
        maturity_date=MATURITY,
        base_date=AS_OF,
        sell_rate=14.91,
        sell_price=741.21,
        liquidity=FixedIncomeLiquidity.AT_MATURITY,
        updated_at=datetime.now(UTC),
    )


def test_sync_job_backfills_once_and_appends_the_catalog_day(api: SimpleNamespace) -> None:
    _create_prefixado(api)
    with api.uow_factory() as uow:
        uow.treasury_catalog.upsert([_today_bond()])
        uow.commit()
    gateway = _HistoryGateway()

    stored = sync_treasury_prices_job(api.uow_factory, gateway, today=AS_OF)  # type: ignore[arg-type]

    assert stored == {"TD:PRE:20290101": 4}
    assert gateway.calls[0][0] == {"PRE"}
    assert gateway.calls[0][1] == PURCHASE - timedelta(days=365)
    with api.uow_factory() as uow:
        prices = uow.market_series.list_series("TD:PRE:20290101")
        rates = uow.market_series.list_series("TD:PRE:20290101:R")
    assert [p.value for p in prices] == [699.80, 731.96, 739.55, 741.21]
    assert prices[0].unit == SeriesUnit.PRICE
    assert rates[-1].value == 14.91
    assert rates[-1].unit == SeriesUnit.PERCENT_PER_YEAR

    # Coverage is complete now: the next run only adds the catalog point.
    sync_treasury_prices_job(api.uow_factory, gateway, today=AS_OF)  # type: ignore[arg-type]
    assert len(gateway.calls) == 1


def _seed_prices(api: SimpleNamespace, price: float) -> None:
    with api.uow_factory() as uow:
        uow.market_series.upsert_points(
            "TD:PRE:20290101",
            [(PURCHASE + timedelta(days=i), 700.22 + i * 0.18) for i in range(0, 220, 3)]
            + [(AS_OF, price)],
            unit=SeriesUnit.PRICE,
        )
        uow.market_series.upsert_points(
            "TD:PRE:20290101:R", [(AS_OF, 14.91)], unit=SeriesUnit.PERCENT_PER_YEAR
        )
        uow.commit()


def test_treasury_market_routes(api: SimpleNamespace) -> None:
    asset_id = _create_prefixado(api)
    _seed_prices(api, 741.21)

    listing = api.client.get(f"/api/v1/portfolio/treasury-market?as_of_date={AS_OF}")
    detail = api.client.get(f"/api/v1/portfolio/treasury-market/{asset_id}?as_of_date={AS_OF}")
    missing = api.client.get(f"/api/v1/portfolio/treasury-market/9999?as_of_date={AS_OF}")

    assert listing.status_code == 200, listing.text
    item = listing.json()[0]
    assert item["status"] == "BELOW_CURVE"
    assert item["market_value"] == pytest.approx(1815.96, abs=0.01)
    assert item["market_rate"] == 14.91
    assert item["history"] == []
    assert detail.json()["history"]
    assert detail.json()["lots"][0]["breakeven_rate"] is not None
    assert missing.status_code == 404


def test_policy_option_weights_the_quadrant_at_market(api: SimpleNamespace) -> None:
    _create_prefixado(api)
    _seed_prices(api, 741.21)
    before = api.client.get(f"/api/v1/portfolio?as_of_date={AS_OF}").json()["positions"][0]

    policy = api.client.get("/api/v1/policy").json()
    policy["valuation"]["treasury_mark_to_market"] = True
    assert api.client.put("/api/v1/policy", json=policy).status_code == 200
    after = api.client.get(f"/api/v1/portfolio?as_of_date={AS_OF}").json()["positions"][0]

    assert before["price_freshness"] == "CURVE"
    assert after["price_freshness"] == "LIVE"
    assert after["gross_current_value_brl"] == pytest.approx(1815.96, abs=0.01)
    assert after["current_value_brl"] < before["current_value_brl"]


def test_mcp_treasury_market(api: SimpleNamespace) -> None:
    asset_id = _create_prefixado(api)
    _seed_prices(api, 790.0)
    op = CATALOG_BY_NAME["portfolio.treasury_market"]
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )

    result = op.invoke(handlers, op.input_model(as_of_date=AS_OF, asset_id=asset_id))

    assert op.kind == "query"
    assert result[0].status == "OPPORTUNITY"
    assert result[0].history
