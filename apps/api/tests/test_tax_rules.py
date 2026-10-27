"""Unit tests for the tax rule registry with validity periods (item 24.1)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.errors import ValidationError
from domain.portfolio.services.fixed_income import (
    regressive_iof_rate,
    regressive_ir_rate,
    value_fixed_income_position,
)
from domain.shared.entities import FixedIncomeTermEntity, TransactionEntity
from domain.shared.enums import (
    AssetType,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    TransactionKind,
)
from domain.tax.entities import (
    NextBracket,
    TaxBracket,
    TaxKind,
    TaxRegime,
    TaxRule,
    TaxRuleBook,
    TaxRuleNotFoundError,
)
from domain.tax.services.rules import (
    DEFAULT_RULE_BOOK,
    DEFAULT_TAX_RULES,
    IOF_TABLE,
    REGRESSIVE_IR_BRACKETS,
    regimes_for,
    rule_book,
)

TODAY = date(2026, 10, 27)


@pytest.mark.parametrize(
    ("days", "rate"),
    [
        (0, 0.225),
        (1, 0.225),
        (180, 0.225),
        (181, 0.200),
        (360, 0.200),
        (361, 0.175),
        (720, 0.175),
        (721, 0.150),
        (5000, 0.150),
    ],
)
def test_regressive_ir_bracket_boundaries(days: int, rate: float) -> None:
    assert regressive_ir_rate(days, on=TODAY) == rate


@pytest.mark.parametrize(
    ("days", "rate"),
    [(-3, 0.0), (0, 0.0), (1, 0.96), (15, 0.50), (29, 0.03), (30, 0.0), (31, 0.0)],
)
def test_regressive_iof_boundaries(days: int, rate: float) -> None:
    assert regressive_iof_rate(days, on=TODAY) == rate


def test_iof_table_is_the_official_one() -> None:
    assert len(IOF_TABLE) == 29
    assert [regressive_iof_rate(d) for d in range(1, 30)] == list(IOF_TABLE)


def test_exempt_fixed_income_pays_no_ir_nor_iof() -> None:
    assert regressive_ir_rate(10, tax_exempt=True) == 0.0
    assert regressive_iof_rate(10, tax_exempt=True) == 0.0


def test_jcp_rate_follows_its_validity_period() -> None:
    assert DEFAULT_RULE_BOOK.rate(TaxRegime.JCP_WITHHOLDING, 0, date(2025, 12, 31)) == 0.15
    assert DEFAULT_RULE_BOOK.rate(TaxRegime.JCP_WITHHOLDING, 0, date(2026, 1, 1)) == 0.175
    assert DEFAULT_RULE_BOOK.rule(TaxRegime.JCP_WITHHOLDING, TODAY).legal_basis == "LC 224/2025"


def test_dividends_exempt_until_2025_and_withheld_above_threshold_from_2026() -> None:
    assert DEFAULT_RULE_BOOK.rate(TaxRegime.DIVIDEND_WITHHOLDING, 0, date(2025, 6, 1)) == 0.0
    assert DEFAULT_RULE_BOOK.rate(TaxRegime.DIVIDEND_WITHHOLDING, 0, TODAY) == 0.10


def test_default_registry_keeps_exemptions_after_mp_1303_lapsed() -> None:
    assert DEFAULT_RULE_BOOK.rate(TaxRegime.FIXED_INCOME_EXEMPT, 900, TODAY) == 0.0
    assert DEFAULT_RULE_BOOK.rule(TaxRegime.FIXED_INCOME_REGRESSIVE, TODAY).brackets == (
        REGRESSIVE_IR_BRACKETS
    )
    assert DEFAULT_RULE_BOOK.rate(TaxRegime.FOREIGN_ANNUAL, 0, TODAY) == 0.15


def test_dates_before_the_first_rule_use_it() -> None:
    assert DEFAULT_RULE_BOOK.rate(TaxRegime.FOREIGN_ANNUAL, 0, date(2020, 1, 1)) == 0.15
    assert regressive_ir_rate(10, on=date(1999, 1, 1)) == 0.225


def test_legal_change_is_a_new_record() -> None:
    old = TaxRule(
        TaxRegime.FIXED_INCOME_REGRESSIVE,
        TaxKind.INCOME_TAX,
        REGRESSIVE_IR_BRACKETS,
        date(2005, 1, 1),
        date(2029, 12, 31),
    )
    single = TaxRule(
        TaxRegime.FIXED_INCOME_REGRESSIVE,
        TaxKind.INCOME_TAX,
        (TaxBracket(None, 0.175),),
        date(2030, 1, 1),
    )
    book = rule_book([old, single])
    assert regressive_ir_rate(10, on=date(2029, 12, 31), rules=book) == 0.225
    assert regressive_ir_rate(10, on=date(2030, 1, 1), rules=book) == 0.175
    # Regimes absent from storage come from the built-in registry.
    assert book.rate(TaxRegime.JCP_WITHHOLDING, 0, TODAY) == 0.175


def test_engine_reads_the_rule_in_force_on_the_valuation_date() -> None:
    term = FixedIncomeTermEntity(
        instrument_kind=FixedIncomeInstrumentKind.CDB,
        indexer=FixedIncomeIndexer.PRE,
        contracted_rate=Decimal("0.12"),
        issue_date=date(2026, 1, 2),
    )
    buy = TransactionEntity(
        asset_id=1,
        kind=TransactionKind.BUY,
        trade_date=date(2026, 1, 2),
        quantity=Decimal("1"),
        unit_price=Decimal("1000"),
        id=1,
    )
    flat = rule_book(
        [
            TaxRule(
                TaxRegime.FIXED_INCOME_REGRESSIVE,
                TaxKind.INCOME_TAX,
                (TaxBracket(None, 0.10),),
                date(2005, 1, 1),
            )
        ]
    )
    default = value_fixed_income_position([buy], term, date(2026, 10, 1))
    custom = value_fixed_income_position([buy], term, date(2026, 10, 1), tax_rules=flat)
    assert default.income_tax_rate == 0.2
    assert custom.income_tax_rate == 0.1
    assert custom.gross_value == default.gross_value
    assert custom.income_tax == pytest.approx(default.gross_yield * 0.10, abs=0.01)


def test_next_bracket() -> None:
    rule = DEFAULT_RULE_BOOK.rule(TaxRegime.FIXED_INCOME_REGRESSIVE, TODAY)
    assert rule.next_bracket(0) == NextBracket(181, 0.2)
    assert rule.next_bracket(180) == NextBracket(181, 0.2)
    assert rule.next_bracket(181) == NextBracket(361, 0.175)
    assert rule.next_bracket(720) == NextBracket(721, 0.15)
    assert rule.next_bracket(721) is None
    flat = DEFAULT_RULE_BOOK.rule(TaxRegime.STOCK_SWING_TRADE, TODAY)
    assert flat.next_bracket(10) is None
    assert not flat.is_holding_period_based
    assert rule.is_holding_period_based


@pytest.mark.parametrize(
    "brackets",
    [
        (),
        (TaxBracket(None, 0.1), TaxBracket(None, 0.2)),
        (TaxBracket(10, 0.1), TaxBracket(5, 0.2), TaxBracket(None, 0.1)),
        (TaxBracket(10, 0.1),),
        (TaxBracket(None, 1.5),),
    ],
)
def test_invalid_brackets_are_rejected(brackets: tuple[TaxBracket, ...]) -> None:
    with pytest.raises(ValidationError):
        TaxRule(TaxRegime.FOREIGN_ANNUAL, TaxKind.INCOME_TAX, brackets, date(2024, 1, 1))


def test_rule_ending_before_it_starts_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TaxRule(
            TaxRegime.FOREIGN_ANNUAL,
            TaxKind.INCOME_TAX,
            (TaxBracket(None, 0.15),),
            date(2024, 1, 1),
            date(2023, 1, 1),
        )


def test_overlapping_rules_are_rejected() -> None:
    open_rule = TaxRule(
        TaxRegime.FOREIGN_ANNUAL, TaxKind.INCOME_TAX, (TaxBracket(None, 0.15),), date(2024, 1, 1)
    )
    later = TaxRule(
        TaxRegime.FOREIGN_ANNUAL, TaxKind.INCOME_TAX, (TaxBracket(None, 0.2),), date(2027, 1, 1)
    )
    with pytest.raises(ValidationError) as exc:
        TaxRuleBook([open_rule, later])
    assert exc.value.code == "OVERLAPPING_TAX_RULES"


def test_gap_between_records_keeps_the_last_rule() -> None:
    first = TaxRule(
        TaxRegime.FOREIGN_ANNUAL,
        TaxKind.INCOME_TAX,
        (TaxBracket(None, 0.15),),
        date(2024, 1, 1),
        date(2024, 12, 31),
    )
    book = TaxRuleBook([first])
    assert book.rate(TaxRegime.FOREIGN_ANNUAL, 0, date(2026, 1, 1)) == 0.15


def test_unknown_regime_raises_not_found() -> None:
    with pytest.raises(TaxRuleNotFoundError):
        TaxRuleBook([]).rule(TaxRegime.JCP_WITHHOLDING, TODAY)
    assert not TaxRuleBook([]).has(TaxRegime.JCP_WITHHOLDING)
    assert DEFAULT_RULE_BOOK.has(TaxRegime.JCP_WITHHOLDING)


def test_empty_storage_falls_back_to_the_built_in_registry() -> None:
    assert rule_book([]) is DEFAULT_RULE_BOOK
    assert rule_book(None) is DEFAULT_RULE_BOOK
    assert len(DEFAULT_RULE_BOOK.rules) == len(DEFAULT_TAX_RULES)


def test_regimes_by_asset_type() -> None:
    exempt = FixedIncomeTermEntity(
        instrument_kind=FixedIncomeInstrumentKind.LCA,
        indexer=FixedIncomeIndexer.CDI,
        contracted_rate=Decimal("0.95"),
        issue_date=TODAY,
        tax_exempt=True,
    )
    assert regimes_for(AssetType.FIXED_INCOME, exempt)[0] == TaxRegime.FIXED_INCOME_EXEMPT
    assert TaxRegime.JCP_WITHHOLDING in regimes_for(AssetType.STOCK_BR)
    assert regimes_for(AssetType.FII) == (
        TaxRegime.FII_CAPITAL_GAIN,
        TaxRegime.FII_DISTRIBUTION,
    )
    assert regimes_for(AssetType.REIT) == (TaxRegime.FOREIGN_ANNUAL,)
    assert regimes_for(AssetType.BDR) == (TaxRegime.ETF_BDR_SWING_TRADE,)
    assert all(regimes_for(t) for t in AssetType)
