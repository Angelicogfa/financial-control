"""Unit tests for the B3 statement parser and classifier (item 12.3)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from fincontrol_core.domain.enums import (
    AssetType,
    CorporateEventKind,
    EarningKind,
    TransactionKind,
)
from fincontrol_core.imports.b3 import (
    LineAction,
    LineStatus,
    StatementKind,
    classify,
    detect_kind,
    event_factor,
    guess_asset_type,
    parse_statement,
)

TRADES = [
    {
        "Data do Negócio": "02/01/2024",
        "Tipo de Movimentação": "Compra",
        "Mercado": "Mercado Fracionário",
        "Instituição": "XP",
        "Código de Negociação": "ITSA4F",
        "Quantidade": 5,
        "Preço": "R$ 9,80",
        "Valor": "R$ 49,00",
    },
    {
        "Data do Negócio": datetime(2024, 1, 2),
        "Tipo de Movimentação": "Compra",
        "Mercado": "Mercado Fracionário",
        "Instituição": "XP",
        "Código de Negociação": "ITSA4F",
        "Quantidade": 5,
        "Preço": "9,80",
        "Valor": "49,00",
    },
    {
        "Data do Negócio": "10/04/2024",
        "Tipo de Movimentação": "Venda",
        "Código de Negociação": "ITSA4",
        "Quantidade": "2",
        "Preço": "10,40",
        "Valor": "20,80",
    },
    {"Data do Negócio": "", "Tipo de Movimentação": "Compra", "Código de Negociação": "X"},
    {"Data do Negócio": None, "Tipo de Movimentação": None, "Código de Negociação": None},
]


def _movement(
    kind: str, product: str, qty: object, value: object, when: str = "01/03/2024"
) -> dict[str, object]:
    return {
        "Entrada/Saída": "Credito",
        "Data": when,
        "Movimentação": kind,
        "Produto": product,
        "Instituição": "XP",
        "Quantidade": qty,
        "Preço unitário": "-",
        "Valor da Operação": value,
    }


def test_detects_statement_kind() -> None:
    assert detect_kind(TRADES[0].keys()) == StatementKind.NEGOTIATION
    assert detect_kind(_movement("Dividendo", "X", 1, 1).keys()) == StatementKind.MOVEMENT
    with pytest.raises(ValueError):
        detect_kind(["foo", "bar"])
    with pytest.raises(ValueError):
        parse_statement([])


def test_negotiation_lines_normalize_and_hash_identical_rows_apart() -> None:
    preview = parse_statement(TRADES)
    first, second, sell, broken = preview.lines
    assert (first.ticker, first.trade_kind, first.quantity, first.unit_price) == (
        "ITSA4",
        TransactionKind.BUY,
        Decimal("5"),
        Decimal("9.80"),
    )
    assert first.when == second.when == date(2024, 1, 2)
    assert first.hash != second.hash  # same content, different occurrence
    assert sell.trade_kind == TransactionKind.SELL
    assert sell.line_no == 4
    assert broken.status == LineStatus.INVALID
    assert parse_statement(TRADES).lines[0].hash == first.hash  # stable across parses


def test_movement_lines_map_to_earnings_events_and_ignored() -> None:
    preview = parse_statement(
        [
            _movement("Dividendo", "ITSA4 - ITAUSA S.A.", 110, "R$ 2,20"),
            _movement("Juros Sobre Capital Próprio", "ITSA4 - ITAUSA S.A.", 110, "R$ 8,50"),
            _movement("Rendimento", "HGLG11 - CSHG LOG", 10, "11,00"),
            _movement("Desdobro", "WEGE3 - WEG", 20, "-"),
            _movement("Grupamento", "MGLU3 - MAGALU", 10, "-"),
            _movement("Bonificação em Ativos", "ITSA4 - ITAUSA", 10, "-"),
            _movement("Transferência - Liquidação", "ITSA4 - ITAUSA", 110, "1.078,00"),
            _movement("Leilão de Fração", "ITSA4 - ITAUSA", 0.4, "3,00"),
            _movement("Juros", "Tesouro Selic 2029", 1, "5,00"),
            _movement("Dividendo", "ITSA4 - ITAUSA", 1, "-"),
            _movement("Desdobro", "WEGE3 - WEG", "-", "-"),
        ]
    )
    lines = preview.lines
    assert lines[0].earning_kind == EarningKind.DIVIDEND
    assert lines[0].gross_amount == Decimal("2.20")
    jcp = lines[1]
    assert (jcp.earning_kind, jcp.gross_amount, jcp.withholding_tax) == (
        EarningKind.JCP,
        Decimal("10.00"),
        Decimal("1.50"),
    )
    assert lines[2].earning_kind == EarningKind.FII_YIELD
    assert [line.event_kind for line in lines[3:6]] == [
        CorporateEventKind.SPLIT,
        CorporateEventKind.REVERSE_SPLIT,
        CorporateEventKind.BONUS,
    ]
    assert lines[6].action == LineAction.IGNORED
    assert "Negociação" in lines[6].note
    assert lines[7].note == "Movimentação não suportada"
    assert lines[8].note == "Sem data ou ativo"
    assert [line.status for line in lines[9:]] == [LineStatus.INVALID, LineStatus.INVALID]


def test_classify_marks_duplicates_unknown_and_events_without_position() -> None:
    preview = parse_statement(
        [
            _movement("Dividendo", "ITSA4 - ITAUSA", 110, "2,20"),
            _movement("Dividendo", "MXRF11 - MAXI", 100, "10,00"),
            _movement("Desdobro", "WEGE3 - WEG", 20, "-"),
            _movement("Desdobro", "ITSA4 - ITAUSA", 20, "-"),
            _movement("Leilão de Fração", "ITSA4 - ITAUSA", 1, "1,00"),
        ]
    )
    held = {"ITSA4": Decimal("100"), "WEGE3": Decimal("0")}
    classified = classify(
        preview,
        known_tickers={"ITSA4", "WEGE3"},
        existing_hashes={preview.lines[0].hash},
        held_before=lambda ticker, _when: held[ticker],
    )
    assert [line.status for line in classified.lines] == [
        LineStatus.DUPLICATE,
        LineStatus.UNKNOWN_ASSET,
        LineStatus.INVALID,
        LineStatus.NEW,
        LineStatus.IGNORED,
    ]
    assert classified.unknown_tickers == ["MXRF11"]
    assert classified.counts == {
        "DUPLICATE": 1,
        "UNKNOWN_ASSET": 1,
        "INVALID": 1,
        "NEW": 1,
        "IGNORED": 1,
    }
    assert [line.ticker for line in classified.new_lines] == ["ITSA4"]


def test_event_factor_and_type_guess() -> None:
    assert event_factor(CorporateEventKind.SPLIT, Decimal("20"), Decimal("20")) == Decimal("2")
    assert event_factor(CorporateEventKind.BONUS, Decimal("10"), Decimal("100")) == Decimal("1.1")
    reverse = event_factor(CorporateEventKind.REVERSE_SPLIT, Decimal("10"), Decimal("100"))
    assert reverse == Decimal("0.1")
    assert event_factor(CorporateEventKind.REVERSE_SPLIT, Decimal("200"), Decimal("100")) is None
    assert event_factor(CorporateEventKind.SPLIT, Decimal("1"), Decimal("0")) is None
    assert guess_asset_type("PETR4") == AssetType.STOCK_BR
    assert guess_asset_type("MXRF11") == AssetType.FII
    assert guess_asset_type("AAPL34") == AssetType.BDR
    assert guess_asset_type("TESOURO") is None
    assert guess_asset_type("ITSA1") is None
