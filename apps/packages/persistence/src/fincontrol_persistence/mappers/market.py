"""ORM model <-> domain entity mappers: market series, fundamentals and the B3 catalog."""

from __future__ import annotations

from fincontrol_core.domain.entities import (
    CatalogInstrument,
    MarketSeriesPoint,
)
from fincontrol_core.domain.enums import (
    AssetType,
    SeriesUnit,
)
from fincontrol_core.fundamentals.history import FundamentalPeriod, FundamentalSnapshot

from fincontrol_persistence.models.market import (
    FundamentalSnapshotModel,
    InstrumentCatalogModel,
    MarketSeriesModel,
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
