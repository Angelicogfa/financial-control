"""Repository port of the price forecasts (Phase 42.1)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class StoredForecast:
    ticker: str
    as_of: date
    payload: dict[str, Any]  # PriceForecast.to_dict(), or {"status": ..., "months": ...}
    model_version: str
    created_at: datetime | None = None


@dataclass(frozen=True)
class StoredCalibration:
    as_of: date
    payload: dict[str, Any]  # ForecastCalibration.to_dict()
    created_at: datetime | None = None


@dataclass(frozen=True)
class StoredModel:
    kind: str  # VALUATION (42.3); EVENTS later
    as_of: date
    payload: dict[str, Any]
    created_at: datetime | None = None


class AbstractForecastRepository(ABC):
    """One forecast per ticker and day (the history stays, for audit) and the calibrations."""

    @abstractmethod
    def save(
        self, ticker: str, as_of: date, payload: dict[str, Any], *, model_version: str
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def latest(self, ticker: str) -> StoredForecast | None:
        raise NotImplementedError

    @abstractmethod
    def save_calibration(self, as_of: date, payload: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def latest_calibration(self) -> StoredCalibration | None:
        raise NotImplementedError

    @abstractmethod
    def save_model(self, kind: str, as_of: date, payload: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def latest_model(self, kind: str) -> StoredModel | None:
        raise NotImplementedError
