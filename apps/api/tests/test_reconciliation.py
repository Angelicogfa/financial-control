"""Position check against the B3 Posição statement (Phase 48.R5) and earnings received."""

from __future__ import annotations

import base64
import io
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from openpyxl import Workbook

from domain.agentic.services.catalog import (
    CATALOG_BY_NAME,
    AgenticRuntimeHandlers,
    ReconciliationToolInput,
)
from domain.portfolio.services.income import summarize
from domain.reconciliation.entities import LineStatus, StatementPosition
from domain.reconciliation.reconciler import match_account, reconcile
from domain.reconciliation.statement import (
    date_in_file_name,
    parse_position_statement,
    parse_sheet,
    trading_code,
)
from domain.shared.entities import (
    AccountEntity,
    AssetEntity,
    CorporateEventEntity,
    EarningEntity,
    TransactionEntity,
)
from domain.shared.enums import AssetType, CorporateEventKind, EarningKind, TransactionKind

ON = date(2026, 10, 31)
ACOES_HEADER = [
    "Produto",
    "Instituição",
    "Conta",
    "Código de Negociação",
    "CNPJ da Empresa",
    "Código ISIN / Distribuição",
    "Tipo",
    "Escriturador",
    "Quantidade",
    "Quantidade Disponível",
    "Quantidade Indisponível",
    "Motivo",
    "Preço de Fechamento",
    "Valor Atualizado",
]


def _acao(ticker: str, institution: str, qty: object) -> list[object]:
    return [
        f"{ticker} - EMPRESA",
        institution,
        "123",
        ticker,
        "",
        "",
        "ON",
        "",
        qty,
        qty,
        0,
        "",
        10,
        100,
    ]


def _xlsx(sheets: dict[str, list[list[object]]]) -> bytes:
    book = Workbook()
    book.remove(book.active)
    for name, rows in sheets.items():
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _asset(
    asset_id: int, ticker: str, trades: list[tuple[str, int | None, str, date]], **kw
) -> AssetEntity:
    return AssetEntity(
        id=asset_id,
        ticker=ticker,
        name=ticker,
        asset_type=kw.pop("asset_type", AssetType.STOCK_BR),
        transactions=tuple(
            TransactionEntity(
                asset_id=asset_id,
                kind=TransactionKind(kind),
                trade_date=when,
                quantity=Decimal(qty),
                unit_price=Decimal("10"),
                account_id=account,
            )
            for kind, account, qty, when in trades
        ),
        **kw,
    )


# --- statement --------------------------------------------------------------------------------


def test_trading_code_and_file_date() -> None:
    assert trading_code("PETR4F") == "PETR4"
    assert trading_code("ITSA4 - ITAUSA S.A.") == "ITSA4"
    assert trading_code("") is None
    assert date_in_file_name("posicao-2026-10-31.xlsx") == ON
    assert date_in_file_name("posicao.xlsx") is None
    assert date_in_file_name("posicao-2026-13-40.xlsx") is None


def test_parse_sheet_skips_titles_totals_and_blank_rows() -> None:
    rows = [
        ["Posição em 31/10/2026"],
        ACOES_HEADER,
        _acao("PETR4", "XP INVESTIMENTOS CCTVM S/A", 100),
        _acao("PETR4F", "XP INVESTIMENTOS CCTVM S/A", "7"),
        [None] * 14,
        ["Total", None, None, None, None, None, None, None, 107],
    ]
    found = parse_sheet("Acoes", rows)
    assert [(p.ticker, p.quantity, p.institution) for p in found] == [
        ("PETR4", Decimal("100"), "XP INVESTIMENTOS CCTVM S/A"),
        ("PETR4", Decimal("7"), "XP INVESTIMENTOS CCTVM S/A"),
    ]
    assert found[0].product == "Acoes"


def test_parse_statement_reads_tesouro_without_code_and_rejects_other_files() -> None:
    tesouro = [
        ["Produto", "Instituição", "Código ISIN", "Indexador", "Vencimento", "Quantidade"],
        ["Tesouro IPCA+ 2035", "XP INVESTIMENTOS", "BRSTN", "IPCA", "15/05/2035", "1,25"],
    ]
    found = parse_position_statement([("Tesouro Direto", tesouro)])
    assert found == [
        StatementPosition(
            product="Tesouro Direto",
            description="Tesouro IPCA+ 2035",
            quantity=Decimal("1.25"),
            ticker=None,
            institution="XP INVESTIMENTOS",
        )
    ]
    with pytest.raises(ValueError, match="Posição"):
        parse_position_statement([("Negociação", [["Data do Negócio", "Preço"]])])


# --- reconciler ------------------------------------------------------------------------------


def test_match_account_by_the_words_of_the_institution() -> None:
    xp = AccountEntity(id=1, name="XP", institution="XP Investimentos")
    inter = AccountEntity(id=2, name="Inter", institution="Banco Inter")
    accounts = [xp, inter]
    assert match_account("XP INVESTIMENTOS CCTVM S/A", accounts) is xp
    assert match_account("BANCO INTER S.A.", accounts) is inter
    assert match_account("NU INVEST CORRETORA", accounts) is None
    assert match_account(None, accounts) is None
    # Two accounts at the same institution: ambiguous, no match.
    assert (
        match_account("XP INVESTIMENTOS", [xp, AccountEntity(id=3, name="XP 2", institution="XP")])
        is None
    )


def test_reconcile_gives_each_status_with_the_difference() -> None:
    accounts = [AccountEntity(id=1, name="XP", institution="XP Investimentos")]
    assets = [
        _asset(1, "PETR4", [("BUY", 1, "100", date(2026, 1, 5))]),
        _asset(2, "ITSA4", [("BUY", 1, "50", date(2026, 2, 5))]),
        _asset(3, "WEGE3", [("BUY", 1, "10", date(2026, 3, 5))]),
        _asset(4, "BBAS3", [("BUY", 1, "5", date(2026, 11, 20))]),  # after the reference date
    ]
    xp = "XP INVESTIMENTOS CCTVM S/A"
    positions = [
        StatementPosition("Acoes", "PETR4", Decimal("100"), "PETR4", xp),
        StatementPosition("Acoes", "ITSA4", Decimal("40"), "ITSA4", xp),
        StatementPosition("Acoes", "VALE3", Decimal("20"), "VALE3", xp),
        StatementPosition("Tesouro Direto", "Tesouro Selic 2029", Decimal("1.5"), None, xp),
    ]

    lines = {(ln.ticker, ln.status): ln for ln in reconcile(positions, assets, accounts, ON)}

    assert lines[("PETR4", LineStatus.MATCH)].difference == 0
    divergent = lines[("ITSA4", LineStatus.DIVERGENT)]
    assert (divergent.b3_quantity, divergent.ledger_quantity, divergent.difference) == (40, 50, -10)
    assert divergent.account_id == 1 and divergent.asset_id == 2
    only_b3 = lines[("VALE3", LineStatus.ONLY_B3)]
    assert only_b3.asset_id is None and "não cadastrado" in only_b3.note
    assert lines[("WEGE3", LineStatus.ONLY_LEDGER)].institution == "XP"
    assert lines[(None, LineStatus.NOT_COMPARED)].product == "Tesouro Direto"
    assert not any(t == "BBAS3" for t, _ in lines)  # bought after the date: nothing held then


def test_reconcile_pools_unmatched_institutions_and_accounts() -> None:
    accounts = [AccountEntity(id=1, name="Minha corretora")]  # no institution set up
    assets = [
        _asset(
            1,
            "PETR4",
            [("BUY", 1, "60", date(2026, 1, 5)), ("BUY", None, "40", date(2026, 1, 6))],
        )
    ]
    positions = [
        StatementPosition("Acoes", "PETR4", Decimal("70"), "PETR4", "XP INVESTIMENTOS"),
        StatementPosition("Acoes", "PETR4", Decimal("30"), "PETR4", "NU INVEST"),
    ]
    [line] = reconcile(positions, assets, accounts, ON)
    assert (line.status, line.account_id, line.b3_quantity, line.ledger_quantity) == (
        LineStatus.MATCH,
        None,
        100,
        100,
    )
    assert line.institution == "NU INVEST, XP INVESTIMENTOS"


def test_reconcile_applies_splits_and_flags_a_ledger_that_sells_too_much() -> None:
    split = CorporateEventEntity(
        asset_id=1, kind=CorporateEventKind.SPLIT, ex_date=date(2026, 6, 1), factor=Decimal("2")
    )
    assets = [
        _asset(1, "PETR4", [("BUY", 1, "50", date(2026, 1, 5))], corporate_events=(split,)),
        _asset(
            2, "ITSA4", [("BUY", 1, "10", date(2026, 1, 5)), ("SELL", 1, "15", date(2026, 2, 5))]
        ),
    ]
    positions = [
        StatementPosition("Acoes", "PETR4", Decimal("100"), "PETR4", None),
        StatementPosition("Acoes", "ITSA4", Decimal("0"), "ITSA4", None),
    ]
    lines = reconcile(positions, assets, [AccountEntity(id=1, name="XP")], ON)
    assert [(ln.ticker, ln.status) for ln in lines] == [("PETR4", LineStatus.MATCH)]

    lines = reconcile(
        [StatementPosition("Acoes", "ITSA4", Decimal("3"), "ITSA4", None)], assets, [], ON
    )
    assert lines[0].status == LineStatus.ONLY_B3
    assert "vende mais" in lines[0].note


def test_reconcile_compares_only_b3_listed_assets() -> None:
    cash = _asset(9, "CAIXA-XP", [("BUY", 1, "1000", date(2026, 1, 5))], asset_type=AssetType.CASH)
    assert reconcile([], [cash], [], ON) == []


# --- API --------------------------------------------------------------------------------------


def _register(api: SimpleNamespace, ticker: str, qty: str, when: str = "2026-10-01") -> int:
    asset_id = api.client.post(
        "/api/v1/assets", json={"ticker": ticker, "name": ticker, "asset_type": "STOCK_BR"}
    ).json()["id"]
    trade = api.client.post(
        "/api/v1/transactions",
        json={
            "asset_id": asset_id,
            "kind": "BUY",
            "trade_date": when,
            "quantity": qty,
            "unit_price": "10",
        },
    )
    assert trade.status_code == 201, trade.text
    return asset_id


def _statement() -> bytes:
    xp = "XP INVESTIMENTOS CCTVM S/A"
    return _xlsx(
        {
            "Acoes": [ACOES_HEADER, _acao("PETR4", xp, 100), _acao("ITSA4", xp, 30), ["Total"]],
            "Tesouro Direto": [
                ["Produto", "Instituição", "Vencimento", "Quantidade"],
                ["Tesouro Selic 2029", xp, "01/03/2029", 1.5],
            ],
        }
    )


def test_preview_commit_list_and_resolve_never_touch_the_ledger(api: SimpleNamespace) -> None:
    _register(api, "PETR4", "100")
    _register(api, "ITSA4", "50")
    trades_before = api.client.get("/api/v1/transactions").json()["meta"]["total_items"]
    files = {"file": ("posicao-2026-10-31.xlsx", _statement(), "application/vnd.ms-excel")}

    preview = api.client.post("/api/v1/reconciliation/b3/preview", files=files)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["id"] is None
    assert body["reference_date"] == "2026-10-31"
    assert body["counts"] == {
        "match": 1,
        "divergent": 1,
        "only_b3": 0,
        "only_ledger": 0,
        "not_compared": 1,
        "open_issues": 1,
    }
    divergent = next(ln for ln in body["lines"] if ln["status"] == "DIVERGENT")
    assert (divergent["ticker"], divergent["difference"]) == ("ITSA4", -20.0)
    assert api.client.get("/api/v1/reconciliation").json() == []

    saved = api.client.post("/api/v1/reconciliation/b3/commit", files=files).json()
    again = api.client.post("/api/v1/reconciliation/b3/commit", files=files).json()
    assert saved["id"] and again["id"] == saved["id"]  # same file, same date: not duplicated
    [summary] = api.client.get("/api/v1/reconciliation").json()
    assert summary["counts"]["open_issues"] == 1

    line = next(ln for ln in saved["lines"] if ln["status"] == "DIVERGENT")
    resolved = api.client.put(
        f"/api/v1/reconciliation/{saved['id']}/lines/{line['id']}",
        json={"resolution": "RESOLVED", "note": "venda lançada na outra corretora"},
    ).json()
    assert resolved["resolution"] == "RESOLVED" and resolved["resolved_at"]
    detail = api.client.get(f"/api/v1/reconciliation/{saved['id']}").json()
    assert detail["counts"]["open_issues"] == 0
    assert api.client.get("/api/v1/transactions").json()["meta"]["total_items"] == trades_before


def test_reference_date_rules(api: SimpleNamespace) -> None:
    content = _statement()
    no_date = api.client.post(
        "/api/v1/reconciliation/b3/preview", files={"file": ("posicao.xlsx", content)}
    )
    assert no_date.status_code == 400 and no_date.json()["code"] == "REFERENCE_DATE_REQUIRED"
    future = api.client.post(
        "/api/v1/reconciliation/b3/preview",
        files={"file": ("posicao.xlsx", content)},
        data={"reference_date": (date.today() + timedelta(days=3)).isoformat()},
    )
    assert future.json()["code"] == "REFERENCE_DATE_FUTURE"
    given = api.client.post(
        "/api/v1/reconciliation/b3/preview",
        files={"file": ("posicao.xlsx", content)},
        data={"reference_date": "2026-10-30"},
    )
    assert given.json()["reference_date"] == "2026-10-30"
    other = api.client.post(
        "/api/v1/reconciliation/b3/preview",
        files={"file": ("posicao-2026-10-31.pdf", b"%PDF")},
    )
    assert other.json()["code"] == "INVALID_FILE"


def test_unknown_reconciliation_and_line(api: SimpleNamespace) -> None:
    assert api.client.get("/api/v1/reconciliation/99").status_code == 404
    assert (
        api.client.put(
            "/api/v1/reconciliation/99/lines/1", json={"resolution": "RESOLVED"}
        ).status_code
        == 404
    )


def test_mcp_preview_takes_the_statement_in_base64(api: SimpleNamespace) -> None:
    _register(api, "PETR4", "100")
    handlers = AgenticRuntimeHandlers(uow_factory=api.uow_factory, portfolio_service=None)  # type: ignore[arg-type]
    result = CATALOG_BY_NAME["reconciliation.preview"].invoke(
        handlers,
        ReconciliationToolInput(
            filename="posicao-2026-10-31.xlsx",
            content_base64=base64.b64encode(_statement()).decode(),
        ),
    )
    assert result.counts.match == 1 and result.counts.only_b3 == 1
    assert CATALOG_BY_NAME["reconciliation.commit"].kind == "command"


# --- earnings received ------------------------------------------------------------------------


def _earning(asset_id: int, on: date, net: str, fx: str = "1") -> EarningEntity:
    return EarningEntity(
        asset_id=asset_id,
        kind=EarningKind.DIVIDEND,
        payment_date=on,
        gross_amount=Decimal(net),
        net_amount=Decimal(net),
        fx_rate=Decimal(fx),
    )


def test_income_by_month_year_last_12_months_and_yield_on_cost() -> None:
    today = date(2026, 11, 2)
    petr = _asset(
        1,
        "PETR4",
        [("BUY", 1, "100", date(2024, 1, 5))],  # cost 1000
        earnings=(
            _earning(1, date(2026, 10, 15), "50"),
            _earning(1, date(2026, 1, 15), "30"),
            _earning(1, date(2025, 6, 15), "20"),  # previous 12 months
            _earning(1, date(2026, 12, 1), "99"),  # future: not received yet
        ),
    )
    aapl = _asset(
        2,
        "AAPL34",
        [("BUY", 1, "10", date(2024, 1, 5))],
        earnings=(_earning(2, date(2026, 9, 1), "2", "5"),),
    )

    s = summarize([petr, aapl], today, months=12)

    assert s.last_12m_brl == 90.0  # 50 + 30 + 2 x 5
    assert s.previous_12m_brl == 20.0
    assert s.total_brl == 110.0
    assert s.by_year == {2025: 20.0, 2026: 90.0}
    assert (
        len(s.months) == 12 and s.months[-1].month == "2026-11" and s.months[0].month == "2025-12"
    )
    assert next(m for m in s.months if m.month == "2026-10").net_brl == 50.0
    assert [a.ticker for a in s.assets] == ["PETR4", "AAPL34"]
    assert s.assets[0].yield_on_cost == 0.08
    assert s.yield_on_cost == pytest.approx(90 / 1100, abs=1e-4)


def test_income_route(api: SimpleNamespace) -> None:
    body = api.client.get("/api/v1/portfolio/income?months=6").json()
    assert body["last_12m_brl"] == 0 and len(body["months"]) == 6 and body["yield_on_cost"] is None
    assert api.client.get("/api/v1/portfolio/income?months=0").status_code == 422


# --- alert ------------------------------------------------------------------------------------


def test_position_check_alerts() -> None:
    from domain.alerts.services.evaluator import AlertKind, AlertSeverity, position_check_alerts

    today = date(2026, 11, 2)
    assert position_check_alerts(None, 0, has_b3_positions=False, today=today) == []
    [never] = position_check_alerts(None, 0, has_b3_positions=True, today=today)
    assert never.kind == AlertKind.POSITION_NOT_CHECKED and never.route == "/carteira/conferir"
    assert position_check_alerts(date(2026, 10, 31), 0, has_b3_positions=True, today=today) == []
    (stale,) = position_check_alerts(date(2026, 9, 1), 0, has_b3_positions=True, today=today)
    assert stale.title == "Posição não conferida há 62 dias"
    (open_,) = position_check_alerts(date(2026, 10, 31), 2, has_b3_positions=True, today=today)
    assert open_.severity == AlertSeverity.WARNING and "2 diferença(s)" in open_.title
