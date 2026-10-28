"""Phase 26.3/26.4: declared distributions (B3), agenda, imported ex dates and new alerts."""

from __future__ import annotations

import base64
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.alerts.services.evaluator import (
    AlertKind,
    MaturityItem,
    agenda_alerts,
    early_sale_alerts,
    maturity_alerts,
    tax_bracket_alerts,
)
from domain.market.entities import AnnouncedDistributions, AnnouncedEarning, AnnouncedStockEvent
from domain.portfolio.services.earnings_agenda import (
    AgendaStatus,
    build_agenda,
    earning_kind,
    ex_date_of,
    resolve_earning_ex_date,
    resolve_ex_date,
)
from domain.portfolio.services.mark_to_market import MarketStatus, TreasuryMarketValuation
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.entities import AssetEntity, TransactionEntity
from domain.shared.enums import AssetType, CorporateEventKind, EarningKind, TransactionKind
from domain.tax.services.status import AssetTaxStatus, LotTaxStatus
from infra.providers.b3_listed import B3ListedProvider, isin_marker, parse_supplement
from infra.providers.gateway import CachedMarketGateway
from tests.conftest import offline_gateway

TODAY = date(2026, 10, 28)
FIXTURES = Path(__file__).parent / "fixtures"

COMPANY = [
    {
        "code": "ITSA",
        "cashDividends": [
            {
                "isinCode": "BRITSAACNOR0",
                "label": "JRS CAP PROPRIO",
                "rate": "0,02424250000",
                "lastDatePrior": "31/10/2026",
                "paymentDate": "01/12/2026",
                "approvedOn": "20/10/2026",
                "relatedTo": "4º Trimestre/2026",
            },
            {
                "isinCode": "BRITSAACNPR7",
                "label": "JRS CAP PROPRIO",
                "rate": "0,02424250000",
                "lastDatePrior": "31/10/2026",
                "paymentDate": "01/12/2026",
                "approvedOn": "20/10/2026",
                "relatedTo": "4º Trimestre/2026",
            },
            {
                "isinCode": "BRITSAACNPR7",
                "label": "DIVIDENDO",
                "rate": "0,10000000000",
                "lastDatePrior": "20/10/2026",
                "paymentDate": "15/11/2026",
                "approvedOn": "10/10/2026",
                "relatedTo": "",
            },
            {
                "isinCode": "BRITSAACNPR7",
                "label": "DIVIDENDO",
                "rate": "0,50000000000",
                "lastDatePrior": "20/06/2026",
                "paymentDate": "15/07/2026",
                "approvedOn": "10/06/2026",
            },
        ],
        "stockDividends": [
            {
                "isinCode": "BRITSAACNPR7",
                "label": "BONIFICACAO",
                "factor": "10,00000000000",
                "lastDatePrior": "15/05/2024",
                "approvedOn": "01/05/2024",
            }
        ],
    }
]


def _itsa(qty: str = "100", bought: date = date(2026, 1, 5)) -> AssetEntity:
    return AssetEntity(
        id=7,
        ticker="ITSA4",
        name="Itaúsa",
        asset_type=AssetType.STOCK_BR,
        transactions=(
            TransactionEntity(
                asset_id=7,
                kind=TransactionKind.BUY,
                trade_date=bought,
                quantity=Decimal(qty),
                unit_price=Decimal("10"),
            ),
        ),
    )


# --- B3 provider -------------------------------------------------------------------------------


def test_isin_markers_follow_the_share_class() -> None:
    assert isin_marker("ITSA4", AssetType.STOCK_BR) == "ACNPR"
    assert isin_marker("ITSA3", AssetType.STOCK_BR) == "ACNOR"
    assert isin_marker("TAEE11", AssetType.STOCK_BR) == "CDAM"
    assert isin_marker("HGLG11", AssetType.FII) == "CTF"


def test_parse_supplement_keeps_the_ticker_class() -> None:
    parsed = parse_supplement("ITSA4", AssetType.STOCK_BR, COMPANY)

    assert len(parsed.cash) == 3
    jcp = parsed.cash[0]
    assert jcp.label == "JRS CAP PROPRIO"
    assert jcp.rate == pytest.approx(0.0242425)
    assert jcp.com_date == date(2026, 10, 31)
    assert jcp.payment_date == date(2026, 12, 1)
    assert parsed.stock[0].factor == 10.0
    assert parse_supplement("X", AssetType.STOCK_BR, []).cash == []


def test_unknown_class_keeps_lines_without_duplicates() -> None:
    parsed = parse_supplement("ITSA9", AssetType.STOCK_BR, COMPANY)
    assert len(parsed.cash) == 3  # ON and PN JCP lines collapse into one


def test_provider_builds_the_b3_urls_and_survives_failures() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, text=json.dumps(COMPANY))

    provider = B3ListedProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert len(provider.get_distributions("ITSA4", AssetType.STOCK_BR).cash) == 3
    provider.get_distributions("HGLG11", AssetType.FII)
    company = json.loads(base64.b64decode(seen[0].rsplit("/", 1)[1]))
    fund = json.loads(base64.b64decode(seen[1].rsplit("/", 1)[1]))
    assert company == {"issuingCompany": "ITSA", "language": "pt-br"}
    assert fund == {"cnpj": "0", "identifierFund": "HGLG", "typeFund": 7}
    assert provider.get_distributions("IVVB11", AssetType.ETF_BR).cash == []

    broken = B3ListedProvider(
        client=httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(500)))
    )
    assert broken.get_distributions("ITSA4", AssetType.STOCK_BR) == AnnouncedDistributions()


# --- agenda ------------------------------------------------------------------------------------


def test_agenda_estimates_held_amounts_and_statuses() -> None:
    declared = parse_supplement("ITSA4", AssetType.STOCK_BR, COMPANY).cash
    watch = AssetEntity(ticker="BBAS3", name="BB", asset_type=AssetType.STOCK_BR, id=9)
    bbas = [
        AnnouncedEarning("BBAS3", "DIVIDENDO", 0.5, date(2026, 11, 3), date(2026, 11, 20)),
    ]

    agenda = build_agenda([_itsa(), watch], {"ITSA4": declared, "BBAS3": bbas}, as_of=TODAY)

    assert [(i.ticker, i.kind) for i in agenda.items] == [
        ("ITSA4", EarningKind.DIVIDEND),
        ("BBAS3", EarningKind.DIVIDEND),
        ("ITSA4", EarningKind.JCP),
    ]
    dividend, watched, jcp = agenda.items
    assert dividend.status == AgendaStatus.AWAITING_PAYMENT
    assert dividend.net_amount == 10.0
    assert jcp.status == AgendaStatus.UPCOMING
    assert jcp.ex_date == date(2026, 11, 3)  # 31/10 is a Saturday; 02/11 is a holiday
    assert jcp.gross_amount == pytest.approx(2.42)
    assert jcp.withholding_tax == pytest.approx(round(2.42 * 0.175, 2))
    assert watched.held is False and watched.net_amount is None
    assert agenda.declared_net_brl == pytest.approx(10.0 + jcp.net_amount)
    assert agenda.declared_by_month["2026-11"] == 10.0


def test_agenda_uses_the_quantity_held_at_the_data_com() -> None:
    late_buyer = _itsa(bought=date(2026, 10, 25))
    declared = [AnnouncedEarning("ITSA4", "DIVIDENDO", 0.1, date(2026, 10, 20), date(2026, 11, 15))]
    item = build_agenda([late_buyer], {"ITSA4": declared}, as_of=TODAY).items[0]
    assert item.held is False


def test_label_mapping_and_ex_date() -> None:
    assert earning_kind("JRS CAP PROPRIO") == EarningKind.JCP
    assert earning_kind("RENDIMENTO") == EarningKind.FII_YIELD
    assert earning_kind("DIVIDENDO") == EarningKind.DIVIDEND
    assert ex_date_of(date(2026, 10, 30)) == date(2026, 11, 3)
    assert ex_date_of(None) is None


def test_resolve_imported_ex_dates() -> None:
    events = [AnnouncedStockEvent("WEGE3", "DESDOBRAMENTO", 2.0, date(2024, 5, 28))]
    earnings = [AnnouncedEarning("ITSA4", "DIVIDENDO", 0.02, date(2024, 2, 20), date(2024, 3, 1))]

    assert resolve_ex_date(CorporateEventKind.SPLIT, date(2024, 6, 3), events) == date(2024, 5, 29)
    assert resolve_ex_date(CorporateEventKind.BONUS, date(2024, 6, 3), events) is None
    assert resolve_ex_date(CorporateEventKind.SPLIT, date(2024, 9, 3), events) is None
    assert resolve_earning_ex_date(EarningKind.DIVIDEND, date(2024, 3, 1), earnings) == date(
        2024, 2, 21
    )
    assert resolve_earning_ex_date(EarningKind.JCP, date(2024, 3, 1), earnings) is None


# --- alerts ------------------------------------------------------------------------------------


def test_new_alert_rules() -> None:
    declared = parse_supplement("ITSA4", AssetType.STOCK_BR, COMPANY).cash
    agenda = build_agenda([_itsa()], {"ITSA4": declared}, as_of=TODAY)
    com = agenda_alerts(agenda, today=TODAY)
    assert [a.kind for a in com] == [AlertKind.EARNING_COM_DATE]
    assert "31/10/2026" in com[0].title
    assert "R$ 2,00" in com[0].detail

    maturity = maturity_alerts(
        [
            MaturityItem("CDB-X", 1, TODAY + timedelta(days=10), 5000.0),
            MaturityItem("CDB-Y", 2, TODAY + timedelta(days=90), 5000.0),
        ],
        today=TODAY,
    )
    assert [a.subject for a in maturity] == ["CDB-X"]

    lot = LotTaxStatus(
        start_date=date(2025, 11, 10),
        principal=1000.0,
        gross_value=1100.0,
        gross_yield=100.0,
        holding_days=352,
        income_tax_rate=0.2,
        iof_rate=0.0,
        iof_due=0.0,
        iof_free_date=None,
        income_tax_due=20.0,
        net_value=1080.0,
        next_bracket_date=TODAY + timedelta(days=8),
        days_to_next_bracket=8,
        next_income_tax_rate=0.175,
        tax_saving_by_waiting=2.5,
    )
    status = AssetTaxStatus(
        asset_id=3,
        ticker="CDB-Z",
        asset_type=AssetType.FIXED_INCOME,
        as_of_date=TODAY,
        is_fixed_income=True,
        tax_exempt=False,
        regimes=(),
        lots=(lot,),
    )
    assert len(tax_bracket_alerts([status], window_days=30, today=TODAY)) == 1
    assert tax_bracket_alerts([status], window_days=5, today=TODAY) == []

    opportunity = TreasuryMarketValuation(
        asset_id=4,
        ticker="PRE29",
        name="Tesouro Prefixado 2029",
        as_of_date=TODAY,
        status=MarketStatus.OPPORTUNITY,
        explanation="Mercado acima da curva.",
        price_date=TODAY,
    )
    below = TreasuryMarketValuation(
        asset_id=5,
        ticker="IPCA32",
        name="Tesouro IPCA+ 2032",
        as_of_date=TODAY,
        status=MarketStatus.BELOW_CURVE,
        explanation="",
        price_date=TODAY,
    )
    sale = early_sale_alerts([opportunity, below])
    assert [a.subject for a in sale] == ["PRE29"]
    assert sale[0].route == "/asset/4?tab=market"


# --- integration -------------------------------------------------------------------------------


def _upload(client, path: str, name: str, content: bytes, **form: str):  # type: ignore[no-untyped-def]
    return client.post(f"/api/v1/imports/b3/{path}", files={"file": (name, content)}, data=form)


def test_import_uses_the_declared_ex_dates(
    api: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def declared(self: CachedMarketGateway, ticker: str, **_kw: object) -> AnnouncedDistributions:
        if ticker == "WEGE3":
            return AnnouncedDistributions(
                stock=[AnnouncedStockEvent("WEGE3", "DESDOBRAMENTO", 2.0, date(2024, 5, 28))]
            )
        if ticker == "ITSA4":
            return AnnouncedDistributions(
                cash=[
                    AnnouncedEarning(
                        "ITSA4", "DIVIDENDO", 0.02, date(2024, 2, 20), date(2024, 3, 1)
                    )
                ]
            )
        return AnnouncedDistributions()

    monkeypatch.setattr(CachedMarketGateway, "get_distributions", declared)
    trades = (FIXTURES / "b3_negociacao.csv").read_bytes()
    movements = (FIXTURES / "b3_movimentacao.csv").read_bytes()
    assert (
        _upload(
            api.client, "commit", "negociacao.csv", trades, create_tickers="ITSA4,HGLG11,WEGE3"
        ).status_code
        == 200
    )
    applied = _upload(api.client, "commit", "movimentacao.csv", movements)
    assert applied.status_code == 200, applied.text

    events = {e["ticker"]: e for e in api.client.get("/api/v1/corporate-events").json()}
    assert events["WEGE3"]["ex_date"] == "2024-05-29"
    assert events["ITSA4"]["ex_date"] == "2024-05-20"  # no declared bonus: credit date kept
    earnings = api.client.get("/api/v1/earnings", params={"page_size": 50}).json()["items"]
    dividend = next(e for e in earnings if e["kind"] == "DIVIDEND")
    assert dividend["ex_date"] == "2024-02-21"


def test_agenda_route_and_mcp(api: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        CachedMarketGateway,
        "get_distributions",
        lambda self, ticker, **_kw: parse_supplement(ticker, AssetType.STOCK_BR, COMPANY),
    )
    resp = api.client.post(
        "/api/v1/assets", json={"ticker": "ITSA4", "name": "Itaúsa", "asset_type": "STOCK_BR"}
    )
    asset_id = resp.json()["id"]
    api.client.post(
        "/api/v1/transactions",
        json={
            "asset_id": asset_id,
            "kind": "BUY",
            "trade_date": "2026-01-05",
            "quantity": "100",
            "unit_price": "10",
        },
    )

    body = api.client.get(f"/api/v1/portfolio/earnings-agenda?as_of_date={TODAY}").json()

    assert [i["kind"] for i in body["items"]] == ["DIVIDEND", "JCP"]
    assert body["items"][0]["net_amount"] == 10.0
    assert body["covered_tickers"] == ["ITSA4"]

    alerts = api.client.get("/api/v1/alerts").json()["alerts"]
    assert all(a["kind"] != "EARNING_COM_DATE" or a["subject"] == "ITSA4" for a in alerts)

    op = CATALOG_BY_NAME["portfolio.earnings_agenda"]
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    result = op.invoke(handlers, op.input_model(as_of_date=TODAY))
    assert result.items[0].ticker == "ITSA4"
