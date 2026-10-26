"""API tests for the B3 statement import: preview, commit, deduplication (item 12.3)."""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import Workbook

FIXTURES = Path(__file__).parent / "fixtures"
TRADES = (FIXTURES / "b3_negociacao.csv").read_bytes()
MOVEMENTS = (FIXTURES / "b3_movimentacao.csv").read_bytes()


def _upload(client, path: str, name: str, content: bytes, **form: str):  # type: ignore[no-untyped-def]
    return client.post(f"/api/v1/imports/b3/{path}", files={"file": (name, content)}, data=form)


def _xlsx(csv_bytes: bytes) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    for row in csv.reader(io.StringIO(csv_bytes.decode("utf-8")), delimiter=";"):
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _with_stale_dimension(xlsx: bytes) -> bytes:
    """Rewrite the sheet's <dimension> to "A1", as the B3 Área do Investidor export does."""
    source, target = io.BytesIO(xlsx), io.BytesIO()
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(target, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                data = re.sub(rb'<dimension ref="[^"]*"/>', b'<dimension ref="A1"/>', data)
            zout.writestr(item, data)
    return target.getvalue()


def _positions(client) -> dict[str, dict]:  # type: ignore[no-untyped-def]
    report = client.get("/api/v1/portfolio/consolidated").json()
    return {p["ticker"]: p for p in report["positions"]}


def test_import_trades_then_movements_without_manual_entries(api: SimpleNamespace) -> None:
    client = api.client

    preview = _upload(client, "preview", "negociacao.xlsx", _xlsx(TRADES))
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["kind"] == "NEGOTIATION"
    assert body["counts"] == {"UNKNOWN_ASSET": 6}
    assert {(u["ticker"], u["asset_type"]) for u in body["unknown_tickers"]} == {
        ("HGLG11", "FII"),
        ("ITSA4", "STOCK_BR"),
        ("WEGE3", "STOCK_BR"),
    }
    assert body["lines"][1]["ticker"] == "ITSA4"  # fractional ITSA4F

    committed = _upload(
        client, "commit", "negociacao.csv", TRADES, create_tickers="ITSA4,HGLG11, WEGE3"
    )
    assert committed.status_code == 200, committed.text
    assert committed.json()["created"] == {"TRADE": 6, "EARNING": 0, "EVENT": 0}
    assert committed.json()["created_assets"] == ["HGLG11", "ITSA4", "WEGE3"]

    again = _upload(client, "commit", "negociacao.csv", TRADES)
    assert again.json()["created"]["TRADE"] == 0
    assert again.json()["skipped"] == {"DUPLICATE": 6}

    movements = _upload(client, "preview", "movimentacao.csv", MOVEMENTS).json()
    assert movements["kind"] == "MOVEMENT"
    assert movements["counts"] == {"IGNORED": 3, "NEW": 5, "UNKNOWN_ASSET": 1}
    assert [u["ticker"] for u in movements["unknown_tickers"]] == ["MXRF11"]

    applied = _upload(client, "commit", "movimentacao.csv", MOVEMENTS)
    assert applied.status_code == 200, applied.text
    assert applied.json()["created"] == {"TRADE": 0, "EARNING": 3, "EVENT": 2}

    events = {e["ticker"]: e for e in client.get("/api/v1/corporate-events").json()}
    assert float(events["ITSA4"]["factor"]) == pytest.approx(1.1)
    assert float(events["WEGE3"]["factor"]) == pytest.approx(2.0)
    assert events["WEGE3"]["imported"] is True

    positions = _positions(client)
    assert positions["ITSA4"]["quantity"] == pytest.approx(110)
    assert positions["WEGE3"]["quantity"] == pytest.approx(40)
    assert positions["HGLG11"]["quantity"] == pytest.approx(10)

    earnings = client.get("/api/v1/earnings", params={"page_size": 20}).json()["items"]
    jcp = next(e for e in earnings if e["kind"] == "JCP")
    assert (float(jcp["gross_amount"]), float(jcp["withholding_tax"])) == (2.2, pytest.approx(0.33))
    assert all(e["notes"].startswith("Importado da B3") for e in earnings)

    assert _upload(client, "commit", "movimentacao.csv", MOVEMENTS).json()["created"] == {
        "TRADE": 0,
        "EARNING": 0,
        "EVENT": 0,
    }


def test_preview_reads_every_row_of_an_xlsx_with_a_stale_dimension(api: SimpleNamespace) -> None:
    content = _with_stale_dimension(_xlsx(MOVEMENTS))
    assert b'<dimension ref="A1"/>' in zipfile.ZipFile(io.BytesIO(content)).read(
        "xl/worksheets/sheet1.xml"
    )

    preview = _upload(api.client, "preview", "movimentacao.xlsx", content)

    assert preview.status_code == 200
    expected_lines = len(MOVEMENTS.decode("utf-8").strip().splitlines()) - 1
    assert len(preview.json()["lines"]) == expected_lines


def test_import_rejects_bad_files_and_oversold_ledgers(api: SimpleNamespace) -> None:
    client = api.client
    wrong_type = _upload(client, "preview", "extrato.pdf", b"%PDF")
    assert wrong_type.status_code == 400
    assert wrong_type.json()["code"] == "INVALID_FILE"
    not_b3 = _upload(client, "preview", "other.csv", b"a;b\n1;2\n")
    assert not_b3.json()["code"] == "INVALID_STATEMENT"

    sell_only = (
        "Data do Negócio;Tipo de Movimentação;Código de Negociação;Quantidade;Preço;Valor\n"
        "10/04/2024;Venda;PETR4;10;R$ 38,00;R$ 380,00\n"
    ).encode()
    oversold = _upload(client, "commit", "venda.csv", sell_only, create_tickers="PETR4")
    assert oversold.status_code == 409
    assert oversold.json()["code"] == "LEDGER_CONFLICT"
    # Atomic: neither the trade nor the asset created for it was kept.
    assert client.get("/api/v1/assets", params={"page_size": 50}).json()["items"] == []

    unknown = _upload(
        client, "commit", "x.csv", sell_only.replace(b"PETR4", b"ABCD1"), create_tickers="ABCD1"
    )
    assert unknown.status_code == 400
    assert unknown.json()["code"] == "UNKNOWN_INSTRUMENT"


def _arca_classes(api: SimpleNamespace) -> dict[str, tuple[str, str]]:
    with api.uow_factory() as uow:
        return {
            a.ticker: (a.asset_type.value, a.arca_class.value)
            for a in uow.assets.list_all(active_only=False)
        }


def test_unknown_tickers_are_registered_with_the_type_and_quadrant_chosen(
    api: SimpleNamespace,
) -> None:
    client = api.client
    preview = _upload(client, "preview", "negociacao.csv", TRADES).json()
    suggested = {u["ticker"]: u["arca_class"] for u in preview["unknown_tickers"]}
    assert suggested == {"HGLG11": "REAL_ESTATE", "ITSA4": "ACOES", "WEGE3": "ACOES"}

    committed = _upload(
        client,
        "commit",
        "negociacao.csv",
        TRADES,
        create_tickers="HGLG11",  # the suggestion, as before
        new_assets=json.dumps(
            [
                {"ticker": "wege3", "arca_class": "ATIVOS_INTERNACIONAIS"},
                {"ticker": "ITSA4", "asset_type": "STOCK_BR", "arca_class": "ACOES"},
            ]
        ),
    )
    assert committed.status_code == 200, committed.text
    assert committed.json()["created_assets"] == ["HGLG11", "ITSA4", "WEGE3"]
    assert _arca_classes(api) == {
        "HGLG11": ("FII", "REAL_ESTATE"),
        "ITSA4": ("STOCK_BR", "ACOES"),
        "WEGE3": ("STOCK_BR", "ATIVOS_INTERNACIONAIS"),
    }

    # Already registered tickers are not reported as created again.
    again = _upload(client, "commit", "negociacao.csv", TRADES, create_tickers="HGLG11")
    assert again.json()["created_assets"] == []


def test_a_ticker_of_unknown_type_needs_the_type_chosen_in_the_preview(
    api: SimpleNamespace,
) -> None:
    client = api.client
    statement = (
        "Data do Negócio;Tipo de Movimentação;Mercado;Prazo/Vencimento;Instituição;"
        "Código de Negociação;Quantidade;Preço;Valor\n"
        "02/01/2024;Compra;Mercado à Vista;-;XP INVESTIMENTOS CCTVM S/A;XPTO1;10;R$ 5,00;R$ 50,00\n"
    ).encode()
    preview = _upload(client, "preview", "negociacao.csv", statement).json()
    assert preview["unknown_tickers"] == [
        {"ticker": "XPTO1", "name": None, "asset_type": None, "arca_class": None}
    ]

    untyped = _upload(client, "commit", "negociacao.csv", statement, create_tickers="XPTO1")
    assert untyped.status_code == 400
    assert untyped.json()["code"] == "UNKNOWN_INSTRUMENT"

    typed = _upload(
        client,
        "commit",
        "negociacao.csv",
        statement,
        new_assets=json.dumps([{"ticker": "XPTO1", "asset_type": "STOCK_BR"}]),
    )
    assert typed.status_code == 200, typed.text
    assert typed.json()["created"]["TRADE"] == 1
    assert _arca_classes(api)["XPTO1"] == ("STOCK_BR", "ACOES")


def test_new_assets_must_be_a_json_list(api: SimpleNamespace) -> None:
    response = _upload(api.client, "commit", "negociacao.csv", TRADES, new_assets="{not json")
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_NEW_ASSETS"
