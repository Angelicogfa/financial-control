"""ARCA class suggestion by economic exposure, not by listing venue (finding A-02).

`asset_type` says where an instrument trades (an ETF listed on B3 is ETF_BR); the ARCA class
must follow what it is exposed to. IVVB11 is listed on B3 but holds the S&P 500, so it belongs
to Ativos Internacionais; IMAB11 holds Treasury IPCA+ bonds, so it belongs to Caixa.

The curated list covers widely traded B3 ETFs. Anything else falls back to the default class
of its asset type, and the user can always override the suggestion.
"""

from __future__ import annotations

from dataclasses import dataclass

from fincontrol_core.domain.enums import ArcaClass, AssetType, default_arca_class

SOURCE_CATALOG = "CATALOG"
SOURCE_ASSET_TYPE = "ASSET_TYPE"

# ticker -> (ARCA class by exposure, what the fund holds)
ETF_EXPOSURE: dict[str, tuple[ArcaClass, str]] = {
    # International equities listed on B3
    "IVVB11": (ArcaClass.ATIVOS_INTERNACIONAIS, "S&P 500 (EUA)"),
    "SPXI11": (ArcaClass.ATIVOS_INTERNACIONAIS, "S&P 500 (EUA)"),
    "NASD11": (ArcaClass.ATIVOS_INTERNACIONAIS, "Nasdaq-100 (EUA)"),
    "WRLD11": (ArcaClass.ATIVOS_INTERNACIONAIS, "Ações globais"),
    "ACWI11": (ArcaClass.ATIVOS_INTERNACIONAIS, "MSCI ACWI (ações globais)"),
    "EURP11": (ArcaClass.ATIVOS_INTERNACIONAIS, "Ações europeias"),
    "XINA11": (ArcaClass.ATIVOS_INTERNACIONAIS, "Ações chinesas"),
    # Crypto index ETFs listed on B3 (crypto is part of Ativos Internacionais)
    "HASH11": (ArcaClass.ATIVOS_INTERNACIONAIS, "Índice de criptoativos"),
    "QBTC11": (ArcaClass.ATIVOS_INTERNACIONAIS, "Bitcoin"),
    "BITH11": (ArcaClass.ATIVOS_INTERNACIONAIS, "Bitcoin"),
    # Brazilian fixed income ETFs
    "IMAB11": (ArcaClass.CAIXA, "Tesouro IPCA+ (IMA-B)"),
    "B5P211": (ArcaClass.CAIXA, "Tesouro IPCA+ curto (IMA-B 5)"),
    "IB5M11": (ArcaClass.CAIXA, "Tesouro IPCA+ longo (IMA-B 5+)"),
    "IRFM11": (ArcaClass.CAIXA, "Tesouro Prefixado (IRF-M)"),
    "FIXA11": (ArcaClass.CAIXA, "Juros futuros prefixados"),
    "LFTS11": (ArcaClass.CAIXA, "Tesouro Selic"),
    # Brazilian real estate
    "XFIX11": (ArcaClass.REAL_ESTATE, "Índice de fundos imobiliários (IFIX)"),
    # Brazilian equities (same as the asset-type default, listed for clarity)
    "BOVA11": (ArcaClass.ACOES, "Ibovespa"),
    "SMAL11": (ArcaClass.ACOES, "Small caps brasileiras"),
    "DIVO11": (ArcaClass.ACOES, "Ações brasileiras pagadoras de dividendos"),
}


@dataclass(frozen=True)
class ArcaSuggestion:
    arca_class: ArcaClass
    source: str
    reason: str


def suggest_arca_class(ticker: str, asset_type: AssetType) -> ArcaSuggestion:
    """Suggested ARCA class for an instrument, explaining where the suggestion comes from."""
    normalized = ticker.strip().upper().removesuffix(".SA")
    if normalized in ETF_EXPOSURE:
        arca_class, exposure = ETF_EXPOSURE[normalized]
        return ArcaSuggestion(arca_class, SOURCE_CATALOG, f"{normalized} investe em {exposure}")
    default = default_arca_class(asset_type)
    return ArcaSuggestion(default, SOURCE_ASSET_TYPE, f"Classe padrão para {asset_type.value}")
