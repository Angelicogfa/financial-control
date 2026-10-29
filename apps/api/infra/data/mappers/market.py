"""ORM model <-> domain entity mappers: market series, fundamentals and the B3 catalog."""

from __future__ import annotations

from domain.assets.services.history import FundamentalPeriod, FundamentalSnapshot
from domain.market.entities import (
    Fundamentals,
    PricePoint,
    Quote,
    QuoteDay,
    StoredMarketData,
    TreasuryBond,
    distributions_from_dict,
)
from domain.shared.entities import (
    CatalogInstrument,
    MarketSeriesPoint,
)
from domain.shared.enums import (
    AssetType,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    FixedIncomeLiquidity,
    SeriesUnit,
)
from infra.data.models.market import (
    AssetPriceHistoryModel,
    FundamentalSnapshotModel,
    InstrumentCatalogModel,
    MarketDataModel,
    MarketQuoteHistoryModel,
    MarketSeriesModel,
    TreasuryCatalogModel,
)


def to_market_series_point(model: MarketSeriesModel) -> MarketSeriesPoint:
    return MarketSeriesPoint(
        id=model.id,
        symbol=model.symbol,
        reference_date=model.reference_date,
        value=float(model.value),
        unit=SeriesUnit(model.unit),
    )


def to_fundamental_snapshot(model: FundamentalSnapshotModel) -> FundamentalSnapshot:
    return FundamentalSnapshot(
        id=model.id,
        ticker=model.ticker,
        reference_date=model.reference_date,
        period=FundamentalPeriod(model.period),
        metrics=dict(model.metrics or {}),
        source=model.source,
        first_seen_at=model.first_seen_at,
    )


def to_catalog_instrument(model: InstrumentCatalogModel) -> CatalogInstrument:
    return CatalogInstrument(
        ticker=model.ticker,
        name=model.name,
        asset_type=AssetType(model.asset_type) if model.asset_type else None,
        sector=model.sector,
        close=model.close,
        change_pct=model.change_pct,
        volume_brl=model.volume_brl,
        market_cap=model.market_cap,
        logo_url=model.logo_url,
        updated_at=model.updated_at,
    )


def to_treasury_bond(model: TreasuryCatalogModel) -> TreasuryBond:
    return TreasuryBond(
        symbol=model.symbol,
        name=model.name,
        bond_type=model.bond_type,
        instrument_kind=FixedIncomeInstrumentKind(model.instrument_kind),
        indexer=FixedIncomeIndexer(model.indexer),
        raw_indexer=model.raw_indexer,
        coupon_type=model.coupon_type,
        maturity_date=model.maturity_date,
        duration_days=model.duration_days,
        base_date=model.base_date,
        buy_rate=model.buy_rate,
        sell_rate=model.sell_rate,
        buy_price=model.buy_price,
        sell_price=model.sell_price,
        base_price=model.base_price,
        rate_type=model.rate_type,
        rate_unit=model.rate_unit,
        rate_description=model.rate_description,
        contracted_rate_percent=model.contracted_rate_percent,
        liquidity=FixedIncomeLiquidity(model.liquidity),
        source=model.source,
        updated_at=model.updated_at,
    )


def to_stored_market_data(model: MarketDataModel) -> StoredMarketData:
    return StoredMarketData(
        ticker=model.ticker,
        quote=Quote.from_dict(model.quote) if model.quote else None,
        quote_fetched_at=model.quote_fetched_at,
        fundamentals=Fundamentals.from_dict(model.fundamentals) if model.fundamentals else None,
        fundamentals_fetched_at=model.fundamentals_fetched_at,
        distributions=(
            distributions_from_dict(model.distributions)
            if model.distributions is not None
            else None
        ),
        distributions_fetched_at=model.distributions_fetched_at,
        history_loaded_at=model.history_loaded_at,
    )


def to_quote_day(model: MarketQuoteHistoryModel) -> QuoteDay:
    return QuoteDay(
        ticker=model.ticker,
        day=model.day,
        price=model.price,
        currency=model.currency,
        provider=model.provider,
        freshness=model.freshness,
        fetched_at=model.fetched_at,
    )


def to_price_point(model: AssetPriceHistoryModel) -> PricePoint:
    return PricePoint(
        date=model.day,
        close=model.close,
        open=model.open,
        high=model.high,
        low=model.low,
        adj_close=model.adj_close,
        volume=model.volume,
    )
