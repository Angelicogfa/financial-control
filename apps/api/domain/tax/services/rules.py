"""Built-in tax rule registry (legislation verified in Oct/2026) and asset regime mapping.

The same records are seeded into the `tax_rules` table (migration `script_00019`); the
database is the source of truth at runtime and this registry is the fallback used by pure
domain calculations and by an empty table. A legal change is a new record with its own
`valid_from`, ending the previous one with `valid_to`.

Notes on the legislation:
- MP 1.303/2025 (single 17.5% rate on investments, taxation of LCI/LCA) lapsed on
  2025-10-08 and never took effect: the regressive table and the exemptions remain.
- JCP withholding rose from 15% to 17.5% for payments from 2026-01-01 (LC 224/2025).
- Dividends above R$ 50 thousand per month from the same company to the same individual
  are withheld at 10% from 2026-01-01 (Lei 15.270/2025); below that they stay exempt.
- Applications abroad are taxed at 15% on the annual gain (Lei 14.754/2023, from 2024).
"""

from __future__ import annotations

from datetime import date

from domain.shared.entities import FixedIncomeTermEntity
from domain.shared.enums import AssetType
from domain.tax.entities import TaxBracket, TaxKind, TaxRegime, TaxRule, TaxRuleBook

# Official Brazilian IOF regressive table for redemptions between 1 and 29 calendar days
IOF_TABLE: tuple[float, ...] = (
    0.96, 0.93, 0.90, 0.86, 0.83, 0.80, 0.76, 0.73, 0.70, 0.66,
    0.63, 0.60, 0.56, 0.53, 0.50, 0.46, 0.43, 0.40, 0.36, 0.33,
    0.30, 0.26, 0.23, 0.20, 0.16, 0.13, 0.10, 0.06, 0.03,
)  # fmt: skip

REGRESSIVE_IR_BRACKETS: tuple[TaxBracket, ...] = (
    TaxBracket(180, 0.225),
    TaxBracket(360, 0.200),
    TaxBracket(720, 0.175),
    TaxBracket(None, 0.150),
)

IOF_BRACKETS: tuple[TaxBracket, ...] = (
    TaxBracket(0, 0.0),
    *(TaxBracket(day, rate) for day, rate in enumerate(IOF_TABLE, start=1)),
    TaxBracket(None, 0.0),
)


def _flat(rate: float) -> tuple[TaxBracket, ...]:
    return (TaxBracket(None, rate),)


DEFAULT_TAX_RULES: tuple[TaxRule, ...] = (
    TaxRule(
        TaxRegime.FIXED_INCOME_REGRESSIVE,
        TaxKind.INCOME_TAX,
        REGRESSIVE_IR_BRACKETS,
        date(2005, 1, 1),
        legal_basis="Lei 11.033/2004, art. 1º",
        description="Renda fixa tributada: IR regressivo sobre o rendimento, retido no resgate.",
    ),
    TaxRule(
        TaxRegime.FIXED_INCOME_EXEMPT,
        TaxKind.INCOME_TAX,
        _flat(0.0),
        date(2005, 1, 1),
        legal_basis="Lei 11.033/2004, art. 3º; Lei 12.431/2011",
        description="LCI, LCA, CRI, CRA e debêntures incentivadas: rendimento isento para PF.",
    ),
    TaxRule(
        TaxRegime.IOF_REGRESSIVE,
        TaxKind.IOF,
        IOF_BRACKETS,
        date(2008, 1, 1),
        legal_basis="Decreto 6.306/2007, art. 32",
        description="IOF regressivo sobre o rendimento de resgates com menos de 30 dias.",
    ),
    TaxRule(
        TaxRegime.STOCK_SWING_TRADE,
        TaxKind.INCOME_TAX,
        _flat(0.15),
        date(2005, 1, 1),
        legal_basis="Lei 11.033/2004, art. 2º; Lei 11.196/2005, art. 38",
        description=(
            "Ações: 15% sobre o lucro de operações comuns, apurado mensalmente (DARF); "
            "isento quando as vendas do mês somam até R$ 20 mil. Day trade: 20%."
        ),
    ),
    TaxRule(
        TaxRegime.ETF_BDR_SWING_TRADE,
        TaxKind.INCOME_TAX,
        _flat(0.15),
        date(2005, 1, 1),
        legal_basis="Lei 11.033/2004, art. 2º; IN RFB 1.585/2015",
        description=(
            "ETFs de renda variável e BDRs: 15% sobre o lucro, apurado mensalmente, sem a "
            "isenção de R$ 20 mil. Day trade: 20%."
        ),
    ),
    TaxRule(
        TaxRegime.FII_CAPITAL_GAIN,
        TaxKind.INCOME_TAX,
        _flat(0.20),
        date(2005, 1, 1),
        legal_basis="Lei 8.668/1993, art. 18; Lei 11.033/2004",
        description="FIIs e Fiagros: 20% sobre o lucro na venda das cotas, sem isenção.",
    ),
    TaxRule(
        TaxRegime.FII_DISTRIBUTION,
        TaxKind.INCOME_TAX,
        _flat(0.0),
        date(2005, 1, 1),
        legal_basis="Lei 11.033/2004, art. 3º, III",
        description=(
            "Rendimentos de FII isentos para PF (fundo com 100+ cotistas, cotas em bolsa e "
            "participação abaixo de 10%)."
        ),
    ),
    TaxRule(
        TaxRegime.DIVIDEND_WITHHOLDING,
        TaxKind.INCOME_TAX,
        _flat(0.0),
        date(1996, 1, 1),
        date(2025, 12, 31),
        legal_basis="Lei 9.249/1995, art. 10",
        description="Dividendos isentos para PF.",
    ),
    TaxRule(
        TaxRegime.DIVIDEND_WITHHOLDING,
        TaxKind.INCOME_TAX,
        _flat(0.10),
        date(2026, 1, 1),
        legal_basis="Lei 15.270/2025",
        description=(
            "Dividendos: 10% retidos sobre o que exceder R$ 50 mil por mês da mesma empresa "
            "para a mesma PF; abaixo disso seguem isentos."
        ),
    ),
    TaxRule(
        TaxRegime.JCP_WITHHOLDING,
        TaxKind.INCOME_TAX,
        _flat(0.15),
        date(1996, 1, 1),
        date(2025, 12, 31),
        legal_basis="Lei 9.249/1995, art. 9º, § 2º",
        description="Juros sobre capital próprio: 15% retidos na fonte.",
    ),
    TaxRule(
        TaxRegime.JCP_WITHHOLDING,
        TaxKind.INCOME_TAX,
        _flat(0.175),
        date(2026, 1, 1),
        legal_basis="LC 224/2025",
        description="Juros sobre capital próprio: 17,5% retidos na fonte a partir de 2026.",
    ),
    TaxRule(
        TaxRegime.FOREIGN_ANNUAL,
        TaxKind.INCOME_TAX,
        _flat(0.15),
        date(2024, 1, 1),
        legal_basis="Lei 14.754/2023",
        description=(
            "Aplicações no exterior: 15% sobre ganhos e rendimentos, apurados anualmente na "
            "declaração de ajuste."
        ),
    ),
    TaxRule(
        TaxRegime.CRYPTO_CAPITAL_GAIN,
        TaxKind.INCOME_TAX,
        _flat(0.15),
        date(2005, 1, 1),
        legal_basis="Lei 8.981/1995, art. 21; Lei 13.259/2016",
        description=(
            "Criptoativos: ganho de capital a partir de 15% (progressivo até 22,5% pelo "
            "valor do ganho); isento quando as vendas do mês somam até R$ 35 mil."
        ),
    ),
)

DEFAULT_RULE_BOOK = TaxRuleBook(DEFAULT_TAX_RULES)

REGIMES_BY_ASSET_TYPE: dict[AssetType, tuple[TaxRegime, ...]] = {
    AssetType.STOCK_BR: (
        TaxRegime.STOCK_SWING_TRADE,
        TaxRegime.DIVIDEND_WITHHOLDING,
        TaxRegime.JCP_WITHHOLDING,
    ),
    AssetType.ETF_BR: (TaxRegime.ETF_BDR_SWING_TRADE,),
    AssetType.BDR: (TaxRegime.ETF_BDR_SWING_TRADE,),
    AssetType.FII: (TaxRegime.FII_CAPITAL_GAIN, TaxRegime.FII_DISTRIBUTION),
    AssetType.STOCK_INTL: (TaxRegime.FOREIGN_ANNUAL,),
    AssetType.ETF_INTL: (TaxRegime.FOREIGN_ANNUAL,),
    AssetType.REIT: (TaxRegime.FOREIGN_ANNUAL,),
    AssetType.CRYPTO: (TaxRegime.CRYPTO_CAPITAL_GAIN,),
    AssetType.FIXED_INCOME: (TaxRegime.FIXED_INCOME_REGRESSIVE, TaxRegime.IOF_REGRESSIVE),
    AssetType.TREASURY: (TaxRegime.FIXED_INCOME_REGRESSIVE, TaxRegime.IOF_REGRESSIVE),
    AssetType.CASH: (TaxRegime.FIXED_INCOME_REGRESSIVE, TaxRegime.IOF_REGRESSIVE),
}


def rule_book(rules: tuple[TaxRule, ...] | list[TaxRule] | None) -> TaxRuleBook:
    """Rule book from persisted rules, completed by the built-in registry for missing regimes."""
    if not rules:
        return DEFAULT_RULE_BOOK
    stored = {rule.regime for rule in rules}
    defaults = [rule for rule in DEFAULT_TAX_RULES if rule.regime not in stored]
    return TaxRuleBook([*rules, *defaults])


def income_tax_regime(*, tax_exempt: bool) -> TaxRegime:
    """Income tax regime of a fixed income position."""
    return TaxRegime.FIXED_INCOME_EXEMPT if tax_exempt else TaxRegime.FIXED_INCOME_REGRESSIVE


def regimes_for(
    asset_type: AssetType, term: FixedIncomeTermEntity | None = None
) -> tuple[TaxRegime, ...]:
    """Informative regimes of an asset type (fixed income honours the term's exemption)."""
    if term is not None:
        return (income_tax_regime(tax_exempt=term.tax_exempt), TaxRegime.IOF_REGRESSIVE)
    return REGIMES_BY_ASSET_TYPE[asset_type]
