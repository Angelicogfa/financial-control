"""Daily Tesouro Direto redemption prices stored as market series (Phase 26.1).

Each bond gets two series in `market_series`:
- `TD:<family>:<maturity yyyymmdd>`   - PU de venda (what the Treasury pays to buy it back), PRICE;
- `TD:<family>:<maturity yyyymmdd>:R` - taxa de venda in % a.a., PERCENT_PER_YEAR.

The family tells bonds with the same maturity apart (Tesouro IPCA+ 2032 and Tesouro IPCA+
com Juros Semestrais 2032 share the date). Symbols stay within the 32 characters of the column.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date

from domain.shared.entities import AssetEntity
from domain.shared.enums import AssetType, FixedIncomeInstrumentKind

SERIES_PREFIX = "TD"
RATE_SUFFIX = "R"


@dataclass(frozen=True)
class TreasuryPricePoint:
    """One row of the Tesouro Transparente price history (`PrecoTaxaTesouroDireto.csv`)."""

    bond_type: str
    maturity_date: date
    base_date: date
    sell_price: float | None
    sell_rate: float | None
    buy_price: float | None = None
    buy_rate: float | None = None


def _ascii_upper(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).upper()


def bond_family(bond_type: str) -> str:
    """Short family code of a Tesouro bond type (`Tesouro IPCA+ com Juros Semestrais` -> IPCA-S)."""
    upper = _ascii_upper(bond_type)
    semiannual = "SEMESTRA" in upper
    if "EDUCA" in upper:
        return "EDUCA"
    if "RENDA" in upper:
        return "RENDA"
    if "SELIC" in upper or "LFT" in upper:
        return "SELIC"
    if "IGPM" in upper or "IGP-M" in upper:
        return "IGPM-S"
    if "PREFIXADO" in upper or "LTN" in upper or "NTN-F" in upper:
        return "PRE-S" if semiannual else "PRE"
    return "IPCA-S" if semiannual else "IPCA"


def price_symbol(family: str, maturity_date: date) -> str:
    return f"{SERIES_PREFIX}:{family}:{maturity_date.strftime('%Y%m%d')}"


def rate_symbol(family: str, maturity_date: date) -> str:
    return f"{price_symbol(family, maturity_date)}:{RATE_SUFFIX}"


def asset_family(asset: AssetEntity) -> str | None:
    """Family of a registered Treasury asset, from its terms and name (None for other assets)."""
    term = asset.fixed_income_term
    if asset.asset_type != AssetType.TREASURY or term is None or term.maturity_date is None:
        return None
    name = _ascii_upper(asset.name)
    if "EDUCA" in name:
        return "EDUCA"
    if "RENDA" in name:
        return "RENDA"
    if term.instrument_kind == FixedIncomeInstrumentKind.TESOURO_SELIC:
        return "SELIC"
    if "IGPM" in name or "IGP-M" in name:
        return "IGPM-S"
    semiannual = term.semiannual_coupons
    if term.instrument_kind == FixedIncomeInstrumentKind.TESOURO_PRE:
        return "PRE-S" if semiannual else "PRE"
    return "IPCA-S" if semiannual else "IPCA"


def asset_price_symbol(asset: AssetEntity) -> str | None:
    family = asset_family(asset)
    term = asset.fixed_income_term
    if family is None or term is None or term.maturity_date is None:
        return None
    return price_symbol(family, term.maturity_date)


def asset_rate_symbol(asset: AssetEntity) -> str | None:
    symbol = asset_price_symbol(asset)
    return f"{symbol}:{RATE_SUFFIX}" if symbol else None
