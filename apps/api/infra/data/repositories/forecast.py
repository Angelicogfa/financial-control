"""SQLAlchemy repository of the price forecasts (Phase 42.1).

It takes and returns pure domain entities and never commits
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.forecast.repositories import (
    AbstractForecastRepository,
    StoredCalibration,
    StoredForecast,
)
from infra.data.models.forecast import AssetForecastModel, ForecastCalibrationModel


class SqlAlchemyForecastRepository(AbstractForecastRepository):
    """SQLAlchemy implementation of AbstractForecastRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(
        self, ticker: str, as_of: date, payload: dict[str, Any], *, model_version: str
    ) -> None:
        key = ticker.strip().upper()
        row = self.session.get(AssetForecastModel, (key, as_of))
        if row is None:
            row = AssetForecastModel(ticker=key, as_of=as_of)
            self.session.add(row)
        row.payload = payload
        row.model_version = model_version
        row.created_at = datetime.now(UTC)
        self.session.flush()

    def latest(self, ticker: str) -> StoredForecast | None:
        row = self.session.scalars(
            select(AssetForecastModel)
            .where(AssetForecastModel.ticker == ticker.strip().upper())
            .order_by(AssetForecastModel.as_of.desc())
            .limit(1)
        ).first()
        if row is None:
            return None
        return StoredForecast(
            ticker=row.ticker,
            as_of=row.as_of,
            payload=dict(row.payload),
            model_version=row.model_version,
            created_at=row.created_at,
        )

    def save_calibration(self, as_of: date, payload: dict[str, Any]) -> None:
        self.session.add(ForecastCalibrationModel(as_of=as_of, payload=payload))
        self.session.flush()

    def latest_calibration(self) -> StoredCalibration | None:
        row = self.session.scalars(
            select(ForecastCalibrationModel).order_by(ForecastCalibrationModel.id.desc()).limit(1)
        ).first()
        if row is None:
            return None
        return StoredCalibration(
            as_of=row.as_of, payload=dict(row.payload), created_at=row.created_at
        )
