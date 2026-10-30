"""Domain enumerations and default mappings for ARCA, assets, fixed income, and earnings."""

from __future__ import annotations

from enum import StrEnum


class ArcaClass(StrEnum):
    """ARCA allocation macro-classes (Thiago Nigro methodology)."""

    ACOES = "ACOES"
    REAL_ESTATE = "REAL_ESTATE"
    CAIXA = "CAIXA"
    ATIVOS_INTERNACIONAIS = "ATIVOS_INTERNACIONAIS"


ARCA_LABELS: dict[ArcaClass, str] = {
    ArcaClass.ACOES: "Ações Brasil",
    ArcaClass.REAL_ESTATE: "Real Estate",
    ArcaClass.CAIXA: "Caixa & Renda Fixa",
    ArcaClass.ATIVOS_INTERNACIONAIS: "Ativos Internacionais",
}


class AssetType(StrEnum):
    """Supported investment instrument types."""

    STOCK_BR = "STOCK_BR"
    ETF_BR = "ETF_BR"
    FII = "FII"
    BDR = "BDR"
    STOCK_INTL = "STOCK_INTL"
    ETF_INTL = "ETF_INTL"
    REIT = "REIT"
    CRYPTO = "CRYPTO"
    FIXED_INCOME = "FIXED_INCOME"
    TREASURY = "TREASURY"
    CASH = "CASH"


class Market(StrEnum):
    """Market routing destination for quotes and historical series."""

    B3 = "B3"
    US = "US"
    CRYPTO = "CRYPTO"
    INDEX = "INDEX"
    FIXED_INCOME_CURVE = "FIXED_INCOME_CURVE"
    MANUAL = "MANUAL"


class TransactionKind(StrEnum):
    """Trade direction."""

    BUY = "BUY"
    SELL = "SELL"


class EarningKind(StrEnum):
    """Income distributions received from assets."""

    DIVIDEND = "DIVIDEND"
    JCP = "JCP"
    FII_YIELD = "FII_YIELD"
    FIXED_INCOME_COUPON = "FIXED_INCOME_COUPON"
    RESTITUTION = "RESTITUTION"


class FixedIncomeInstrumentKind(StrEnum):
    """Fixed income instrument subcategories."""

    CDB = "CDB"
    LCI = "LCI"
    LCA = "LCA"
    CRI = "CRI"
    CRA = "CRA"
    DEBENTURE = "DEBENTURE"
    TESOURO_SELIC = "TESOURO_SELIC"
    TESOURO_IPCA = "TESOURO_IPCA"
    TESOURO_PRE = "TESOURO_PRE"
    SAVINGS_BOX = "SAVINGS_BOX"


class FixedIncomeIndexer(StrEnum):
    """Indexer used to calculate accrued fixed income curve value."""

    CDI = "CDI"
    IPCA = "IPCA"
    PRE = "PRE"
    SELIC = "SELIC"


class FixedIncomeLiquidity(StrEnum):
    """Redemption liquidity profile."""

    DAILY = "DAILY"
    AT_MATURITY = "AT_MATURITY"


class SeriesUnit(StrEnum):
    """Unit in which a market/macro series value is stored (ADR 0006)."""

    PERCENT_PER_DAY = "PERCENT_PER_DAY"
    PERCENT_PER_MONTH = "PERCENT_PER_MONTH"
    PERCENT_PER_YEAR = "PERCENT_PER_YEAR"
    PRICE = "PRICE"
    INDEX_POINTS = "INDEX_POINTS"
    RATIO = "RATIO"  # e.g. a split: shares after / shares before


class AccountKind(StrEnum):
    """Where positions are held (custody)."""

    BROKER = "BROKER"
    BANK = "BANK"
    EXCHANGE = "EXCHANGE"
    OTHER = "OTHER"


class AssetPurpose(StrEnum):
    """Why an asset is held; only ARCA assets take part in allocation and contributions."""

    ARCA = "ARCA"
    EMERGENCY_RESERVE = "EMERGENCY_RESERVE"
    OTHER = "OTHER"


class AssetLifecycle(StrEnum):
    """Operational status of an asset under the investment policy (ADR 0005)."""

    WATCHLIST = "WATCHLIST"
    ELIGIBLE = "ELIGIBLE"
    HELD = "HELD"
    REVIEW = "REVIEW"
    ARCHIVED = "ARCHIVED"


class JobRunStatus(StrEnum):
    """Lifecycle of a background job execution."""

    REQUESTED = "REQUESTED"  # asked for by hand; the worker turns it into the run
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class IntraClassStrategy(StrEnum):
    """How contributions are distributed among assets inside an ARCA class."""

    CERRADO = "CERRADO"
    MANUAL_WEIGHT = "MANUAL_WEIGHT"
    EQUAL_WEIGHT = "EQUAL_WEIGHT"


class ContributionClassReason(StrEnum):
    """Which first-level rule decided what an ARCA class receives from a contribution."""

    REFILL_BELOW_BAND = "REFILL_BELOW_BAND"  # below its band: refilled toward the target first
    BELOW_BAND_PRIORITY = "BELOW_BAND_PRIORITY"  # nothing left after refilling the others
    BELOW_TARGET = "BELOW_TARGET"  # share of the money in proportion to what it lacks
    ABOVE_TARGET = "ABOVE_TARGET"  # at or above its target: receives nothing
    NO_ELIGIBLE_ASSETS = "NO_ELIGIBLE_ASSETS"  # its share passes to the other classes


class ContributionOrderReason(StrEnum):
    """Why one asset of a contribution plan got (or did not get) a purchase."""

    BOUGHT = "BOUGHT"
    LEFTOVER_FILL = "LEFTOVER_FILL"  # bought only with the rounding leftovers of other assets
    PRICE_ABOVE_BUDGET = "PRICE_ABOVE_BUDGET"  # its share does not buy one unit
    ABOVE_TARGET = "ABOVE_TARGET"  # already at or above its weight inside the class
    ZERO_WEIGHT = "ZERO_WEIGHT"  # the class strategy gives it no weight
    NO_PRICE = "NO_PRICE"


class CorporateEventKind(StrEnum):
    """Share-count events. Factor = shares after / shares before (ex-date)."""

    SPLIT = "SPLIT"
    REVERSE_SPLIT = "REVERSE_SPLIT"
    BONUS = "BONUS"


class ContributionPlanStatus(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    DISCARDED = "DISCARDED"


class ChecklistProfile(StrEnum):
    """Fundamentalist checklist profile; each one asks the questions that fit the instrument."""

    STOCK = "STOCK"
    BANK = "BANK"
    FII_BRICK = "FII_BRICK"
    FII_PAPER = "FII_PAPER"
    ETF = "ETF"
    INTL_STOCK = "INTL_STOCK"
    CRYPTO = "CRYPTO"
    FIXED_INCOME = "FIXED_INCOME"


class AnswerValue(StrEnum):
    """Checklist answer: YES (+1), NO (-1) or NA (question does not apply to the asset)."""

    YES = "YES"
    NO = "NO"
    NA = "NA"


class AnswerSource(StrEnum):
    MANUAL = "MANUAL"
    AUTO = "AUTO"
    PENDING = "PENDING"


DEFAULT_ARCA_BY_TYPE: dict[AssetType, ArcaClass] = {
    AssetType.STOCK_BR: ArcaClass.ACOES,
    AssetType.ETF_BR: ArcaClass.ACOES,
    AssetType.FII: ArcaClass.REAL_ESTATE,
    AssetType.REIT: ArcaClass.REAL_ESTATE,
    AssetType.BDR: ArcaClass.ATIVOS_INTERNACIONAIS,
    AssetType.STOCK_INTL: ArcaClass.ATIVOS_INTERNACIONAIS,
    AssetType.ETF_INTL: ArcaClass.ATIVOS_INTERNACIONAIS,
    AssetType.CRYPTO: ArcaClass.ATIVOS_INTERNACIONAIS,
    AssetType.FIXED_INCOME: ArcaClass.CAIXA,
    AssetType.TREASURY: ArcaClass.CAIXA,
    AssetType.CASH: ArcaClass.CAIXA,
}

MARKET_BY_TYPE: dict[AssetType, Market] = {
    AssetType.STOCK_BR: Market.B3,
    AssetType.ETF_BR: Market.B3,
    AssetType.FII: Market.B3,
    AssetType.BDR: Market.B3,
    AssetType.STOCK_INTL: Market.US,
    AssetType.ETF_INTL: Market.US,
    AssetType.REIT: Market.US,
    AssetType.CRYPTO: Market.CRYPTO,
    AssetType.FIXED_INCOME: Market.FIXED_INCOME_CURVE,
    AssetType.TREASURY: Market.FIXED_INCOME_CURVE,
    AssetType.CASH: Market.MANUAL,
}

DEFAULT_CURRENCY_BY_TYPE: dict[AssetType, str] = {
    AssetType.STOCK_INTL: "USD",
    AssetType.ETF_INTL: "USD",
    AssetType.REIT: "USD",
    AssetType.CRYPTO: "USD",
}

DEFAULT_PROFILE_BY_TYPE: dict[AssetType, ChecklistProfile] = {
    AssetType.STOCK_BR: ChecklistProfile.STOCK,
    AssetType.ETF_BR: ChecklistProfile.ETF,
    AssetType.FII: ChecklistProfile.FII_BRICK,
    AssetType.REIT: ChecklistProfile.FII_BRICK,
    AssetType.BDR: ChecklistProfile.INTL_STOCK,
    AssetType.STOCK_INTL: ChecklistProfile.INTL_STOCK,
    AssetType.ETF_INTL: ChecklistProfile.ETF,
    AssetType.CRYPTO: ChecklistProfile.CRYPTO,
    AssetType.FIXED_INCOME: ChecklistProfile.FIXED_INCOME,
    AssetType.TREASURY: ChecklistProfile.FIXED_INCOME,
    AssetType.CASH: ChecklistProfile.FIXED_INCOME,
}

INTEGER_QUANTITY_TYPES: frozenset[AssetType] = frozenset(
    {AssetType.STOCK_BR, AssetType.ETF_BR, AssetType.FII, AssetType.BDR}
)


def default_arca_class(asset_type: AssetType) -> ArcaClass:
    """Return the default ARCA class for a given asset type."""
    return DEFAULT_ARCA_BY_TYPE[asset_type]


def market_for(asset_type: AssetType) -> Market:
    """Return the market routing destination for a given asset type."""
    return MARKET_BY_TYPE[asset_type]


def default_currency(asset_type: AssetType) -> str:
    """Return the default trading currency ('BRL' or 'USD') for a given asset type."""
    return DEFAULT_CURRENCY_BY_TYPE.get(asset_type, "BRL")


def default_checklist_profile(asset_type: AssetType) -> ChecklistProfile:
    """Checklist profile used when the asset does not choose one (e.g. BANK, FII_PAPER)."""
    return DEFAULT_PROFILE_BY_TYPE[asset_type]
