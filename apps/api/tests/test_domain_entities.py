"""Unit tests for pure domain enums, entities, and pagination primitives."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.shared import (
    ArcaClass,
    AssetEntity,
    AssetType,
    EarningEntity,
    EarningKind,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    FixedIncomeTermEntity,
    Market,
    PageMeta,
    PaginationParams,
    TransactionEntity,
    TransactionKind,
    default_arca_class,
    default_currency,
    market_for,
)


@pytest.mark.unit
def test_default_arca_and_market_mappings() -> None:
    assert default_arca_class(AssetType.STOCK_BR) == ArcaClass.ACOES
    assert default_arca_class(AssetType.FII) == ArcaClass.REAL_ESTATE
    assert default_arca_class(AssetType.REIT) == ArcaClass.REAL_ESTATE
    assert default_arca_class(AssetType.FIXED_INCOME) == ArcaClass.CAIXA
    assert default_arca_class(AssetType.CRYPTO) == ArcaClass.ATIVOS_INTERNACIONAIS

    assert market_for(AssetType.STOCK_BR) == Market.B3
    assert market_for(AssetType.FIXED_INCOME) == Market.FIXED_INCOME_CURVE
    assert default_currency(AssetType.STOCK_INTL) == "USD"
    assert default_currency(AssetType.FII) == "BRL"


@pytest.mark.unit
def test_asset_entity_normalization_and_validation() -> None:
    asset = AssetEntity(
        ticker="  wege3 ",
        name="  WEG S.A. ",
        asset_type=AssetType.STOCK_BR,
    )
    assert asset.ticker == "WEGE3"
    assert asset.name == "WEG S.A."
    assert asset.arca_class == ArcaClass.ACOES
    assert asset.currency == "BRL"
    assert asset.market == Market.B3

    with pytest.raises(ValueError, match="ticker cannot be empty"):
        AssetEntity(ticker="   ", name="Invalid", asset_type=AssetType.STOCK_BR)

    with pytest.raises(ValueError, match="manual_price cannot be negative"):
        AssetEntity(
            ticker="CDB1",
            name="CDB",
            asset_type=AssetType.FIXED_INCOME,
            manual_price=Decimal("-1"),
        )


@pytest.mark.unit
def test_transaction_and_earning_entity_validation() -> None:
    tx = TransactionEntity(
        asset_id=1,
        kind=TransactionKind.BUY,
        trade_date=date(2026, 1, 10),
        quantity=Decimal("10"),
        unit_price=Decimal("45.50"),
    )
    assert tx.fx_rate == Decimal("1")

    with pytest.raises(ValueError, match="quantity must be positive"):
        TransactionEntity(
            asset_id=1,
            kind=TransactionKind.BUY,
            trade_date=date(2026, 1, 10),
            quantity=Decimal("0"),
            unit_price=Decimal("10"),
        )

    earning = EarningEntity(
        asset_id=1,
        kind=EarningKind.JCP,
        payment_date=date(2026, 2, 15),
        gross_amount=Decimal("100.00"),
        withholding_tax=Decimal("15.00"),
    )
    assert earning.net_amount == Decimal("85.00")

    term = FixedIncomeTermEntity(
        instrument_kind=FixedIncomeInstrumentKind.CDB,
        indexer=FixedIncomeIndexer.CDI,
        contracted_rate=Decimal("1.10"),
        issue_date=date(2026, 1, 1),
    )
    assert term.contracted_rate == Decimal("1.10")


@pytest.mark.unit
def test_pagination_params_and_meta() -> None:
    params = PaginationParams(page=2, page_size=5, sort_by="ticker", sort_order="desc")
    assert params.offset == 5
    assert params.is_descending is True

    meta = PageMeta.build(params, total_items=12)
    assert meta.total_pages == 3
    assert meta.has_prev is True
    assert meta.has_next is True

    with pytest.raises(ValueError, match="page must be >= 1"):
        PaginationParams(page=0)

    with pytest.raises(ValueError, match="sort_order must be"):
        PaginationParams(sort_order="invalid")
