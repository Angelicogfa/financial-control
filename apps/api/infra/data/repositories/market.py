"""SQLAlchemy repositories: market series, fundamentals and the B3 catalog.

They take and return pure domain entities and never commit
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain.assets.services.history import FundamentalPeriod, FundamentalSnapshot
from domain.market.entities import TreasuryBond
from domain.shared.entities import (
    CatalogInstrument,
    MarketSeriesPoint,
)
from domain.shared.enums import SeriesUnit
from domain.shared.repositories import (
    AbstractCatalogRepository,
    AbstractFundamentalsRepository,
    AbstractMarketSeriesRepository,
    AbstractTreasuryCatalogRepository,
)
from infra.data.mappers.market import (
    to_catalog_instrument,
    to_fundamental_snapshot,
    to_market_series_point,
    to_treasury_bond,
)
from infra.data.models.market import (
    FundamentalSnapshotModel,
    InstrumentCatalogModel,
    MarketSeriesModel,
    TreasuryCatalogModel,
)


class SqlAlchemyMarketSeriesRepository(AbstractMarketSeriesRepository):
    """SQLAlchemy implementation of AbstractMarketSeriesRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_points(
        self, symbol: str, points: list[tuple[date, float]], *, unit: SeriesUnit
    ) -> int:
        if not points:
            return 0
        normalized = symbol.strip().upper()
        dates = [ref_date for ref_date, _ in points]
        existing_rows = {
            row.reference_date: row
            for row in self.session.scalars(
                select(MarketSeriesModel).where(
                    MarketSeriesModel.symbol == normalized,
                    MarketSeriesModel.reference_date >= min(dates),
                    MarketSeriesModel.reference_date <= max(dates),
                )
            ).all()
        }
        for ref_date, value in points:
            row = existing_rows.get(ref_date)
            if row is not None:
                row.value = float(value)
                row.unit = unit.value
            else:
                row = MarketSeriesModel(
                    symbol=normalized,
                    reference_date=ref_date,
                    value=float(value),
                    unit=unit.value,
                )
                self.session.add(row)
                existing_rows[ref_date] = row
        self.session.flush()
        return len(points)

    def date_range(self, symbol: str) -> tuple[date, date] | None:
        stmt = select(
            func.min(MarketSeriesModel.reference_date),
            func.max(MarketSeriesModel.reference_date),
        ).where(MarketSeriesModel.symbol == symbol.strip().upper())
        first, last = self.session.execute(stmt).one()
        if first is None or last is None:
            return None
        return first, last

    def list_series(
        self,
        symbol: str,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[MarketSeriesPoint]:
        stmt = select(MarketSeriesModel).where(MarketSeriesModel.symbol == symbol.strip().upper())
        if date_from is not None:
            stmt = stmt.where(MarketSeriesModel.reference_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(MarketSeriesModel.reference_date <= date_to)
        stmt = stmt.order_by(MarketSeriesModel.reference_date.asc())
        return [to_market_series_point(m) for m in self.session.scalars(stmt).all()]


class SqlAlchemyFundamentalsRepository(AbstractFundamentalsRepository):
    """SQLAlchemy implementation of AbstractFundamentalsRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, snapshots: list[FundamentalSnapshot]) -> int:
        for snapshot in snapshots:
            ticker = snapshot.ticker.strip().upper()
            model = self.session.scalar(
                select(FundamentalSnapshotModel).where(
                    FundamentalSnapshotModel.ticker == ticker,
                    FundamentalSnapshotModel.reference_date == snapshot.reference_date,
                    FundamentalSnapshotModel.period == snapshot.period.value,
                )
            )
            if model is None:
                model = FundamentalSnapshotModel(
                    ticker=ticker,
                    reference_date=snapshot.reference_date,
                    period=snapshot.period.value,
                )
                self.session.add(model)
            model.metrics = dict(snapshot.metrics)
            model.source = snapshot.source
            model.fetched_at = datetime.now(UTC)
        self.session.flush()
        return len(snapshots)

    def list_for(
        self, ticker: str, *, period: FundamentalPeriod = FundamentalPeriod.ANNUAL
    ) -> list[FundamentalSnapshot]:
        return self.list_for_many([ticker], period=period).get(ticker.strip().upper(), [])

    def list_for_many(
        self, tickers: list[str], *, period: FundamentalPeriod = FundamentalPeriod.ANNUAL
    ) -> dict[str, list[FundamentalSnapshot]]:
        normalized = sorted({t.strip().upper() for t in tickers})
        if not normalized:
            return {}
        stmt = (
            select(FundamentalSnapshotModel)
            .where(
                FundamentalSnapshotModel.ticker.in_(normalized),
                FundamentalSnapshotModel.period == period.value,
            )
            .order_by(FundamentalSnapshotModel.reference_date.asc())
        )
        result: dict[str, list[FundamentalSnapshot]] = {}
        for model in self.session.scalars(stmt).all():
            result.setdefault(model.ticker, []).append(to_fundamental_snapshot(model))
        return result


class SqlAlchemyCatalogRepository(AbstractCatalogRepository):
    """SQLAlchemy implementation of AbstractCatalogRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, instruments: list[CatalogInstrument]) -> int:
        existing = {m.ticker: m for m in self.session.scalars(select(InstrumentCatalogModel))}
        for item in instruments:
            model = existing.get(item.ticker)
            if model is None:
                model = InstrumentCatalogModel(ticker=item.ticker)
                self.session.add(model)
                existing[item.ticker] = model
            model.name = item.name[:160]
            model.asset_type = item.asset_type.value if item.asset_type else None
            model.sector = item.sector[:80] if item.sector else None
            model.close = item.close
            model.change_pct = item.change_pct
            model.volume_brl = item.volume_brl
            model.market_cap = item.market_cap
            model.logo_url = item.logo_url[:255] if item.logo_url else None
            model.updated_at = item.updated_at or datetime.now(UTC)
        self.session.flush()
        return len(instruments)

    def get(self, ticker: str) -> CatalogInstrument | None:
        model = self.session.get(InstrumentCatalogModel, ticker.strip().upper())
        return to_catalog_instrument(model) if model else None

    def list_all(self) -> list[CatalogInstrument]:
        stmt = select(InstrumentCatalogModel).order_by(
            InstrumentCatalogModel.volume_brl.desc().nulls_last(),
            InstrumentCatalogModel.ticker.asc(),
        )
        return [to_catalog_instrument(m) for m in self.session.scalars(stmt).all()]


class SqlAlchemyTreasuryCatalogRepository(AbstractTreasuryCatalogRepository):
    """SQLAlchemy implementation of AbstractTreasuryCatalogRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, bonds: list[TreasuryBond]) -> int:
        existing = {m.symbol: m for m in self.session.scalars(select(TreasuryCatalogModel))}
        for item in bonds:
            sym = item.symbol.strip().lower()
            model = existing.get(sym)
            if model is None:
                model = TreasuryCatalogModel(symbol=sym)
                self.session.add(model)
                existing[sym] = model
            model.name = item.name[:160]
            model.bond_type = item.bond_type[:120]
            model.instrument_kind = item.instrument_kind.value
            model.indexer = item.indexer.value
            model.raw_indexer = item.raw_indexer[:32]
            model.coupon_type = item.coupon_type[:32]
            model.maturity_date = item.maturity_date
            model.duration_days = item.duration_days
            model.base_date = item.base_date
            model.buy_rate = item.buy_rate
            model.sell_rate = item.sell_rate
            model.buy_price = item.buy_price
            model.sell_price = item.sell_price
            model.base_price = item.base_price
            model.rate_type = item.rate_type[:64] if item.rate_type else None
            model.rate_unit = item.rate_unit[:32] if item.rate_unit else None
            model.rate_description = item.rate_description[:255] if item.rate_description else None
            model.contracted_rate_percent = item.contracted_rate_percent
            model.liquidity = item.liquidity.value
            model.source = item.source[:32] if item.source else None
            model.updated_at = item.updated_at or datetime.now(UTC)
        self.session.flush()
        return len(bonds)

    def get(self, symbol: str) -> TreasuryBond | None:
        model = self.session.get(TreasuryCatalogModel, symbol.strip().lower())
        return to_treasury_bond(model) if model else None

    def list_all(self) -> list[TreasuryBond]:
        stmt = select(TreasuryCatalogModel).order_by(
            TreasuryCatalogModel.maturity_date.asc(),
            TreasuryCatalogModel.symbol.asc(),
        )
        return [to_treasury_bond(m) for m in self.session.scalars(stmt).all()]
