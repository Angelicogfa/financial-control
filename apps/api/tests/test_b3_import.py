"""Unit tests for the B3 statement parser and classifier (item 12.3)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from domain.ledger.services.b3_import import (
    LineAction,
    LineStatus,
    StatementKind,
    classify,
    detect_kind,
    event_factor,
    guess_asset_type,
    parse_statement,
    resolve_fixed_income,
)
from domain.shared.entities import AssetEntity, FixedIncomeTermEntity
from domain.shared.enums import (
    AssetType,
    CorporateEventKind,
    EarningKind,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    TransactionKind,
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
    assert (lines[8].earning_kind, lines[8].ticker) == (
        EarningKind.FIXED_INCOME_COUPON,
        "TESOURO_SELIC-2029",
    )
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


def test_fractional_suffix_is_dropped_from_issuer_codes_with_digits() -> None:
    rows = [{**TRADES[0], "Código de Negociação": code} for code in ("B3SA3F", "BBAS3F", "B3SA3")]
    assert [line.ticker for line in parse_statement(rows).lines] == ["B3SA3", "BBAS3", "B3SA3"]


ITAU = "ITAU UNIBANCO S.A."


def _fixed_income(
    kind: str,
    product: str,
    qty: object,
    price: object,
    value: object,
    when: str = "17/03/2026",
    institution: str = "NU INVESTIMENTOS S.A. - CTVM",
) -> dict[str, object]:
    return {
        **_movement(kind, product, qty, value, when),
        "Instituição": institution,
        "Preço unitário": price,
    }


def test_treasury_movements_become_trades_and_coupons_keyed_by_bond() -> None:
    lines = parse_statement(
        [
            _fixed_income("Compra", "Tesouro IPCA+ 2032", 0.67, 2944.7, 1972.95),
            _fixed_income(
                "Compra", "Tesouro IPCA+ com Juros Semestrais 2037", 0.01, 4351.27, 43.51
            ),
            _fixed_income("Venda", "Tesouro Prefixado 2028", 0.13, 780.25, 101.43),
            _fixed_income("Juros", "Tesouro IPCA+ com Juros Semestrais 2037", 1, "-", "12,30"),
            _fixed_income("Compra", "Tesouro Selic 2029", "-", "-", "-"),
            _fixed_income("Atualização", "Tesouro Selic 2029", 1, "-", "-"),
        ]
    ).lines
    buy, semiannual, sell, coupon, broken, other = lines
    assert (buy.action, buy.trade_kind, buy.ticker) == (
        LineAction.TRADE,
        TransactionKind.BUY,
        "TESOURO_IPCA-2032",
    )
    assert (buy.quantity, buy.unit_price) == (Decimal("0.67"), Decimal("2944.7"))
    ref = buy.fixed_income
    assert ref is not None
    assert (ref.asset_type, ref.instrument_kind, ref.indexer, ref.maturity_year) == (
        AssetType.TREASURY,
        FixedIncomeInstrumentKind.TESOURO_IPCA,
        FixedIncomeIndexer.IPCA,
        2032,
    )
    assert (ref.name, ref.issuer, ref.semiannual) == (
        "Tesouro IPCA+ 2032",
        "Tesouro Nacional",
        False,
    )
    assert semiannual.ticker == "TESOURO_IPCA-JS-2037"
    assert semiannual.fixed_income is not None and semiannual.fixed_income.semiannual
    assert (sell.trade_kind, sell.ticker) == (TransactionKind.SELL, "TESOURO_PRE-2028")
    assert (coupon.action, coupon.earning_kind, coupon.gross_amount) == (
        LineAction.EARNING,
        EarningKind.FIXED_INCOME_COUPON,
        Decimal("12.30"),
    )
    assert broken.status == LineStatus.INVALID
    assert (other.status, other.note) == (LineStatus.IGNORED, "Movimentação não suportada")


def test_bank_security_movements_share_one_key_per_issuer() -> None:
    application, redemption, lca = parse_statement(
        [
            _fixed_income(
                "APLICAÇÃO", "CDB - CDB3268K63R", 857575, 0.01, 8575.75, institution=ITAU
            ),
            _fixed_income(
                "RESGATE ANTECIPADO",
                "CDB - CDB3268K63R - ITAU UNIBANCO S.A.",
                822955,
                0.0100001,
                8229.63,
                when="18/03/2026",
                institution=ITAU,
            ),
            _fixed_income(
                "APLICAÇÃO", "LCA - LCA24001ABC", 1000, 1, 1000, institution="BANCO INTER S.A."
            ),
        ]
    ).lines
    assert (application.trade_kind, redemption.trade_kind) == (
        TransactionKind.BUY,
        TransactionKind.SELL,
    )
    assert application.ticker == redemption.ticker == "CDB3268K63R"  # B3 code before matching
    assert application.fixed_income is not None and redemption.fixed_income is not None
    assert application.fixed_income.key == redemption.fixed_income.key == "CDB-ITAUUNIBANCO"
    assert application.fixed_income.issuer == redemption.fixed_income.issuer == ITAU
    assert application.fixed_income.asset_type == AssetType.FIXED_INCOME
    assert application.fixed_income.indexer == FixedIncomeIndexer.CDI
    assert lca.fixed_income is not None
    assert (lca.fixed_income.instrument_kind, lca.fixed_income.key) == (
        FixedIncomeInstrumentKind.LCA,
        "LCA-BANCOINTERSA",
    )


def _treasury_asset(
    ticker: str, name: str, kind: FixedIncomeInstrumentKind, maturity: date
) -> AssetEntity:
    return AssetEntity(
        ticker=ticker,
        name=name,
        asset_type=AssetType.TREASURY,
        fixed_income_term=FixedIncomeTermEntity(
            instrument_kind=kind,
            indexer=FixedIncomeIndexer.IPCA,
            contracted_rate=Decimal("0.07"),
            issue_date=date(2026, 1, 1),
            maturity_date=maturity,
        ),
    )


def _cdb_asset(ticker: str, issuer: str | None) -> AssetEntity:
    return AssetEntity(
        ticker=ticker,
        name=f"CDB {issuer}",
        asset_type=AssetType.FIXED_INCOME,
        fixed_income_term=FixedIncomeTermEntity(
            instrument_kind=FixedIncomeInstrumentKind.CDB,
            indexer=FixedIncomeIndexer.CDI,
            contracted_rate=Decimal("1.00"),
            issue_date=date(2026, 1, 1),
            issuer=issuer,
        ),
    )


def test_resolve_points_fixed_income_lines_at_registered_assets() -> None:
    parsed = parse_statement(
        [
            _fixed_income("Compra", "Tesouro IPCA+ 2032", 0.67, 2944.7, 1972.95),
            _fixed_income(
                "Compra", "Tesouro IPCA+ com Juros Semestrais 2037", 0.01, 4351.27, 43.51
            ),
            _fixed_income("Venda", "Tesouro Prefixado 2028", 0.13, 780.25, 101.43),
            _fixed_income(
                "APLICAÇÃO", "CDB - CDB3268K63R", 857575, 0.01, 8575.75, institution=ITAU
            ),
            _fixed_income(
                "APLICAÇÃO", "CDB - CDBA261298C", 812624, 0.01, 8126.24, institution=ITAU
            ),
            _movement("Dividendo", "ITSA4 - ITAUSA", 110, "2,20"),
        ]
    )
    assets = [
        # Named as the Treasury catalog names it: matched by name.
        _treasury_asset(
            "TESOURO_IPCA-TESOURONAC-2032",
            "Tesouro IPCA+ 2032",
            FixedIncomeInstrumentKind.TESOURO_IPCA,
            date(2032, 8, 15),
        ),
        # Renamed: matched by kind and maturity year, the coupon flag telling it apart.
        _treasury_asset(
            "MEU-IPCA-JS",
            "Tesouro IPCA+ com Juros Semestrais (aposentadoria)",
            FixedIncomeInstrumentKind.TESOURO_IPCA,
            date(2037, 5, 15),
        ),
        _cdb_asset("CDB-ITAU-LIQ", "Itaú Unibanco"),
        _cdb_asset("CDBA261298C", None),  # registered under its own B3 code
    ]
    resolved = resolve_fixed_income(parsed, assets).lines
    assert [line.ticker for line in resolved] == [
        "TESOURO_IPCA-TESOURONAC-2032",
        "MEU-IPCA-JS",
        "TESOURO_PRE-2028",  # not registered: the group key
        "CDB-ITAU-LIQ",
        "CDBA261298C",
        "ITSA4",
    ]
    assert [line.hash for line in resolved] == [line.hash for line in parsed.lines]

    chosen = resolve_fixed_income(parsed, [], chosen={"TESOURO_PRE-2028": "NEW-PRE"}).lines
    assert chosen[2].ticker == "NEW-PRE"

    classified = classify(
        resolve_fixed_income(parsed, assets),
        known_tickers={a.ticker for a in assets} | {"ITSA4"},
        existing_hashes=set(),
    )
    assert classified.unknown_tickers == ["TESOURO_PRE-2028"]


def test_resolve_rejects_a_security_matching_two_assets() -> None:
    parsed = parse_statement(
        [_fixed_income("APLICAÇÃO", "CDB - CDB3268K63R", 100, 0.01, 1, institution=ITAU)]
    )
    resolved = resolve_fixed_income(
        parsed, [_cdb_asset("CDB-A", "Itaú Unibanco S/A"), _cdb_asset("CDB-B", ITAU)]
    ).lines
    assert resolved[0].status == LineStatus.INVALID
    assert "CDB-A, CDB-B" in resolved[0].note
