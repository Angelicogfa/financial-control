"""Monthly income tax on stock exchange gains (Phase 48.R7, TD-04).

The cases follow the rules of the Receita Federal for individuals (IN RFB 1.585/2015 and the
"Perguntas e Respostas IRPF"): exemption of R$ 20 thousand in ações sales per month, separate
loss pools for common operations, day trade and FII, the withholding deducted, DARF below
R$ 10 carried, and the annual assessment of applications abroad (Lei 14.754/2023).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.shared.entities import AssetEntity, CorporateEventEntity, TransactionEntity
from domain.shared.enums import AssetType, CorporateEventKind, TransactionKind
from domain.tax.assessment import (
    TaxCategory,
    assess_foreign,
    assess_months,
    darf_due_date,
    last_business_day,
    realized_sales,
)
from domain.tax.services.rules import rule_book

BOOK = rule_book(None)
D = Decimal


def _asset(asset_id: int, ticker: str, asset_type: AssetType, trades, events=()) -> AssetEntity:
    return AssetEntity(
        id=asset_id,
        ticker=ticker,
        name=ticker,
        asset_type=asset_type,
        transactions=tuple(
            TransactionEntity(
                id=i,
                asset_id=asset_id,
                kind=TransactionKind(kind),
                trade_date=on,
                quantity=D(qty),
                unit_price=D(price),
                fees=D(fees),
                fx_rate=D(fx),
            )
            for i, (kind, on, qty, price, fees, fx) in enumerate(
                (t if len(t) == 6 else (*t, "0", "1")[:6] for t in trades), start=1
            )
        ),
        corporate_events=tuple(events),
    )


def _sales(*assets: AssetEntity):
    out = []
    for asset in assets:
        sales, issues = realized_sales(asset)
        assert issues == []
        out.extend(sales)
    return out


def _month(months, year: int, month: int):
    return next(m for m in months if m.month == date(year, month, 1))


def _cat(month, category: TaxCategory):
    return next(c for c in month.categories if c.category == category)


# --- realized sales ---------------------------------------------------------------------------


def test_swing_sale_uses_the_average_cost_with_buy_fees() -> None:
    petr = _asset(
        1,
        "PETR4",
        AssetType.STOCK_BR,
        [
            ("BUY", date(2026, 1, 5), "100", "20", "10", "1"),
            ("BUY", date(2026, 2, 5), "100", "30", "10", "1"),
            ("SELL", date(2026, 3, 5), "50", "40", "5", "1"),
        ],
    )
    [sale] = _sales(petr)
    assert sale.day_trade is False and sale.category == TaxCategory.COMMON
    assert sale.cost_brl == D("1255")  # (2000 + 10 + 3000 + 10) / 200 x 50
    assert sale.sale_value_brl == D("2000") and sale.fees_brl == D("5")
    assert sale.gain_brl == D("740")


def test_same_day_buy_and_sell_is_a_day_trade_and_the_rest_swing() -> None:
    vale = _asset(
        2,
        "VALE3",
        AssetType.STOCK_BR,
        [
            ("BUY", date(2026, 1, 5), "100", "50"),
            ("BUY", date(2026, 3, 10), "30", "60"),
            ("SELL", date(2026, 3, 10), "50", "62"),
        ],
    )
    day, swing = _sales(vale)
    assert (day.day_trade, day.quantity, day.cost_brl, day.gain_brl) == (
        True,
        30,
        D("1800"),
        D("60"),
    )
    assert day.category == TaxCategory.DAY_TRADE
    assert (swing.day_trade, swing.quantity, swing.cost_brl, swing.gain_brl) == (
        False,
        20,
        D("1000"),
        D("240"),
    )


def test_splits_keep_the_cost_and_bonus_adds_its_cost() -> None:
    split = CorporateEventEntity(
        asset_id=3, kind=CorporateEventKind.SPLIT, ex_date=date(2026, 2, 1), factor=D("2")
    )
    bonus = CorporateEventEntity(
        asset_id=3,
        kind=CorporateEventKind.BONUS,
        ex_date=date(2026, 3, 1),
        factor=D("1.1"),
        unit_cost=D("5"),
    )
    itsa = _asset(
        3,
        "ITSA4",
        AssetType.STOCK_BR,
        [("BUY", date(2026, 1, 5), "100", "10"), ("SELL", date(2026, 4, 1), "220", "6")],
        events=[split, bonus],
    )
    [sale] = _sales(itsa)
    assert sale.cost_brl == D("1100")  # 1000 + 20 bonus shares x R$ 5
    assert sale.gain_brl == D("220")


def test_selling_more_than_held_is_reported() -> None:
    broken = _asset(4, "BBAS3", AssetType.STOCK_BR, [("SELL", date(2026, 1, 5), "10", "20")])
    sales, issues = realized_sales(broken)
    assert issues and "sem posição" in issues[0].message
    assert realized_sales(
        _asset(5, "CDB", AssetType.FIXED_INCOME, [("BUY", date(2026, 1, 5), "1", "1000")])
    ) == ([], [])


# --- monthly assessment -----------------------------------------------------------------------


def test_stocks_sold_up_to_20_thousand_in_the_month_are_exempt() -> None:
    petr = _asset(
        1,
        "PETR4",
        AssetType.STOCK_BR,
        [("BUY", date(2026, 1, 5), "1000", "15"), ("SELL", date(2026, 3, 5), "1000", "18")],
    )
    march = _month(assess_months(_sales(petr), BOOK, through=date(2026, 3, 31)), 2026, 3)
    assert march.exempt and march.stock_sales_brl == D("18000.00")
    common = _cat(march, TaxCategory.COMMON)
    assert (common.exempt_gain_brl, common.taxable_brl, common.tax_brl) == (D("3000.00"), 0, 0)
    assert march.darf_brl == 0


def test_stocks_above_20_thousand_pay_15_percent_minus_the_withholding() -> None:
    petr = _asset(
        1,
        "PETR4",
        AssetType.STOCK_BR,
        [("BUY", date(2026, 1, 5), "1000", "22"), ("SELL", date(2026, 3, 5), "1000", "25")],
    )
    march = _month(assess_months(_sales(petr), BOOK, through=date(2026, 3, 31)), 2026, 3)
    assert not march.exempt
    assert _cat(march, TaxCategory.COMMON).tax_brl == D("450.00")
    assert march.withheld_brl == D("1.25")  # 0.005% of R$ 25,000
    assert march.darf_brl == D("448.75")
    assert march.due_date == date(2026, 4, 30)


def test_a_loss_in_an_exempt_month_offsets_a_later_taxable_gain() -> None:
    petr = _asset(
        1,
        "PETR4",
        AssetType.STOCK_BR,
        [
            ("BUY", date(2026, 1, 5), "2000", "15"),
            (
                "SELL",
                date(2026, 2, 5),
                "1000",
                "13",
            ),  # R$ 13,000 sold (exempt month), loss R$ 2,000
            ("SELL", date(2026, 3, 5), "1000", "30"),  # R$ 30,000 sold, gain R$ 15,000
        ],
    )
    months = assess_months(_sales(petr), BOOK, through=date(2026, 3, 31))
    feb, mar = _month(months, 2026, 2), _month(months, 2026, 3)
    assert _cat(feb, TaxCategory.COMMON).loss_out_brl == D("2000.00")
    common = _cat(mar, TaxCategory.COMMON)
    assert (common.loss_in_brl, common.loss_used_brl, common.taxable_brl) == (
        D("2000.00"),
        D("2000.00"),
        D("13000.00"),
    )
    assert common.tax_brl == D("1950.00")


def test_etf_and_bdr_are_never_exempt_but_share_the_common_loss_pool() -> None:
    bova = _asset(
        6,
        "BOVA11",
        AssetType.ETF_BR,
        [("BUY", date(2026, 1, 5), "10", "100"), ("SELL", date(2026, 3, 5), "10", "150")],
    )
    petr = _asset(
        1,
        "PETR4",
        AssetType.STOCK_BR,
        [("BUY", date(2026, 1, 5), "100", "30"), ("SELL", date(2026, 3, 5), "100", "28")],
    )
    march = _month(assess_months(_sales(bova, petr), BOOK, through=date(2026, 3, 31)), 2026, 3)
    assert march.exempt  # ações sales of R$ 2,800
    common = _cat(march, TaxCategory.COMMON)
    # ETF gain R$ 500 taxable; the ações loss of R$ 200 offsets it (losses are never exempt).
    assert (common.result_brl, common.taxable_brl, common.tax_brl) == (
        D("300.00"),
        D("300.00"),
        D("45.00"),
    )


def test_day_trade_pays_20_percent_and_keeps_its_own_loss_pool() -> None:
    vale = _asset(
        2,
        "VALE3",
        AssetType.STOCK_BR,
        [
            ("BUY", date(2026, 3, 10), "100", "60"),
            ("SELL", date(2026, 3, 10), "100", "70"),  # day trade gain R$ 1,000
            ("BUY", date(2026, 3, 1), "100", "60"),
            ("SELL", date(2026, 3, 20), "100", "50"),  # swing loss R$ 1,000
        ],
    )
    march = _month(assess_months(_sales(vale), BOOK, through=date(2026, 3, 31)), 2026, 3)
    day = _cat(march, TaxCategory.DAY_TRADE)
    assert (day.taxable_brl, day.rate, day.tax_brl) == (D("1000.00"), D("0.20"), D("200.00"))
    assert _cat(march, TaxCategory.COMMON).loss_out_brl == D(
        "1000.00"
    )  # does not offset the day trade
    assert march.withheld_brl == D("10.25")  # 1% of R$ 1,000 + 0.005% of R$ 5,000 swing sales
    assert march.darf_brl == D("189.75")


def test_fii_pays_20_percent_without_exemption() -> None:
    hglg = _asset(
        7,
        "HGLG11",
        AssetType.FII,
        [("BUY", date(2026, 1, 5), "10", "150"), ("SELL", date(2026, 3, 5), "10", "200")],
    )
    march = _month(assess_months(_sales(hglg), BOOK, through=date(2026, 3, 31)), 2026, 3)
    fii = _cat(march, TaxCategory.FII)
    assert (fii.taxable_brl, fii.tax_brl) == (D("500.00"), D("100.00"))
    assert march.darf_brl == D("99.90")  # 0.005% of R$ 2,000 withheld


def test_darf_below_10_reais_is_carried_to_the_next_month() -> None:
    bova = _asset(
        6,
        "BOVA11",
        AssetType.ETF_BR,
        [
            ("BUY", date(2026, 1, 5), "10", "100"),
            ("SELL", date(2026, 2, 5), "5", "110"),  # gain R$ 50 -> tax R$ 7.50
            ("SELL", date(2026, 3, 5), "5", "110"),  # gain R$ 50 -> tax R$ 7.50
        ],
    )
    months = assess_months(_sales(bova), BOOK, through=date(2026, 4, 30))
    feb, mar, apr = _month(months, 2026, 2), _month(months, 2026, 3), _month(months, 2026, 4)
    assert feb.darf_brl == 0 and feb.carried_darf_out_brl == D("7.47")
    assert mar.carried_darf_in_brl == D("7.47") and mar.darf_brl == D("14.94")
    assert apr.categories == [] and apr.darf_brl == 0


def test_abroad_is_assessed_per_year_in_reais() -> None:
    aapl = _asset(
        8,
        "AAPL",
        AssetType.STOCK_INTL,
        [
            ("BUY", date(2024, 1, 5), "10", "100", "0", "5"),  # R$ 5,000
            ("SELL", date(2024, 6, 5), "5", "90", "0", "5"),  # R$ 2,250 for R$ 2,500: loss R$ 250
            (
                "SELL",
                date(2025, 6, 5),
                "5",
                "150",
                "0",
                "5.5",
            ),  # R$ 4,125 for R$ 2,500: gain R$ 1,625
        ],
    )
    sales = _sales(aapl)
    assert assess_months(sales, BOOK, through=date(2025, 12, 31)) == []
    y2024, y2025 = assess_foreign(sales, BOOK, through=date(2025, 12, 31))
    assert (y2024.result_brl, y2024.loss_out_brl, y2024.tax_brl) == (D("-250.00"), D("250.00"), 0)
    assert (y2025.taxable_brl, y2025.rate, y2025.tax_brl) == (D("1375.00"), D("0.15"), D("206.25"))


@pytest.mark.parametrize(
    ("year", "month", "expected"),
    [(2026, 10, date(2026, 10, 30)), (2026, 5, date(2026, 5, 29)), (2026, 11, date(2026, 11, 30))],
)
def test_last_business_day(year: int, month: int, expected: date) -> None:
    assert last_business_day(year, month) == expected


def test_darf_due_date_crosses_the_year() -> None:
    assert darf_due_date(date(2026, 12, 1)) == date(2027, 1, 29)


# --- API --------------------------------------------------------------------------------------


def _trade(api, asset_id: int, kind: str, on: str, qty: str, price: str) -> None:
    resp = api.client.post(
        "/api/v1/transactions",
        json={
            "asset_id": asset_id,
            "kind": kind,
            "trade_date": on,
            "quantity": qty,
            "unit_price": price,
        },
    )
    assert resp.status_code == 201, resp.text


def test_year_month_darf_payment_and_alert(api) -> None:
    asset_id = api.client.post(
        "/api/v1/assets", json={"ticker": "PETR4", "name": "Petrobras", "asset_type": "STOCK_BR"}
    ).json()["id"]
    _trade(api, asset_id, "BUY", "2025-01-06", "1000", "22")
    _trade(api, asset_id, "SELL", "2025-03-05", "1000", "25")

    year = api.client.get("/api/v1/tax/monthly?year=2025").json()
    march = next(m for m in year["months"] if m["month"] == "2025-03")
    assert (march["darf_brl"], march["due_date"], march["darf_code"]) == (
        448.75,
        "2025-04-30",
        "6015",
    )
    assert year["open_darf_brl"] == 448.75 and year["foreign"] is None
    assert march["sales"] == []  # the year lists months; the month detail lists the sales

    detail = api.client.get("/api/v1/tax/monthly/2025-03").json()
    [sale] = detail["sales"]
    assert (sale["ticker"], sale["gain_brl"], sale["category"]) == ("PETR4", 3000.0, "COMMON")

    darf = [a for a in api.client.get("/api/v1/alerts").json()["alerts"] if a["kind"] == "DARF_DUE"]
    assert (
        darf
        and darf[0]["severity"] == "CRITICAL"
        and darf[0]["route"] == "/carteira/imposto?mes=2025-03"
    )

    paid = api.client.put("/api/v1/tax/monthly/2025-03/darf", json={"paid_on": "2025-04-25"}).json()
    assert paid["paid_on"] == "2025-04-25"
    assert api.client.get("/api/v1/tax/monthly?year=2025").json()["open_darf_brl"] == 0
    assert not [
        a for a in api.client.get("/api/v1/alerts").json()["alerts"] if a["kind"] == "DARF_DUE"
    ]


def test_tax_routes_validate_months_and_years(api) -> None:
    assert api.client.get("/api/v1/tax/monthly/2025-13").json()["code"] == "INVALID_MONTH"
    assert api.client.get("/api/v1/tax/monthly/2025-02").json()["code"] == "NO_SALES"
    assert api.client.get("/api/v1/tax/monthly?year=2999").json()["code"] == "INVALID_YEAR"
    assert (
        api.client.put("/api/v1/tax/monthly/2025-02/darf", json={"paid_on": None}).status_code
        == 404
    )
    assert api.client.get("/api/v1/tax/monthly").json()["months"] == []
