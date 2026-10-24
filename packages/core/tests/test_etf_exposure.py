"""Unit tests for ARCA class suggestion by exposure (finding A-02)."""

from __future__ import annotations

import pytest
from fincontrol_core.catalog.etf_exposure import (
    SOURCE_ASSET_TYPE,
    SOURCE_CATALOG,
    suggest_arca_class,
)
from fincontrol_core.domain.enums import ArcaClass, AssetType


@pytest.mark.parametrize(
    ("ticker", "expected"),
    [
        ("IVVB11", ArcaClass.ATIVOS_INTERNACIONAIS),
        ("imab11.sa", ArcaClass.CAIXA),
        ("XFIX11", ArcaClass.REAL_ESTATE),
        ("HASH11", ArcaClass.ATIVOS_INTERNACIONAIS),
    ],
)
def test_catalog_overrides_listing_venue(ticker: str, expected: ArcaClass) -> None:
    suggestion = suggest_arca_class(ticker, AssetType.ETF_BR)
    assert suggestion.arca_class == expected
    assert suggestion.source == SOURCE_CATALOG
    assert "investe em" in suggestion.reason


def test_unknown_ticker_uses_asset_type_default() -> None:
    suggestion = suggest_arca_class("WEGE3", AssetType.STOCK_BR)
    assert suggestion.arca_class == ArcaClass.ACOES
    assert suggestion.source == SOURCE_ASSET_TYPE
