"""Unit tests for generated asset codes (item 10.5)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from domain.assets.services.codes import MAX_CODE_LENGTH, generated_asset_code
from domain.shared.entities import FixedIncomeTermEntity
from domain.shared.enums import AssetType, FixedIncomeIndexer, FixedIncomeInstrumentKind


def _term(issuer: str | None, maturity: date | None) -> FixedIncomeTermEntity:
    return FixedIncomeTermEntity(
        instrument_kind=FixedIncomeInstrumentKind.LCI,
        indexer=FixedIncomeIndexer.CDI,
        contracted_rate=Decimal("0.95"),
        issue_date=date(2025, 1, 2),
        maturity_date=maturity,
        issuer=issuer,
    )


def test_codes_from_kind_issuer_and_maturity() -> None:
    free = lambda _code: False  # noqa: E731
    assert (
        generated_asset_code(
            AssetType.FIXED_INCOME, "x", _term("Caixa Econômica", date(2026, 5, 4)), free
        )
        == "LCI-CAIXAECONO-20260504"
    )
    assert generated_asset_code(AssetType.FIXED_INCOME, "Minha LCI", _term(None, None), free) == (
        "LCI-MINHALCI-LIQ"
    )
    assert generated_asset_code(AssetType.CASH, "Conta Nubank", None, free) == "CAIXA-CONTANUBANK"


def test_codes_are_unique_and_short() -> None:
    taken = {"CAIXA-RESERVA", "CAIXA-RESERVA-2"}
    code = generated_asset_code(AssetType.CASH, "Reserva", None, taken.__contains__)
    assert code == "CAIXA-RESERVA-3"
    long_code = generated_asset_code(
        AssetType.CASH, "Um nome extremamente longo para uma conta", None, lambda _c: False
    )
    assert len(long_code) <= MAX_CODE_LENGTH
