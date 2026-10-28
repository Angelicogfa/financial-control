"""Pydantic response DTOs for the simulation module (Phase 33)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from domain.simulation.data import CoverageStatus
from domain.simulation.entities import SimulationKind, SimulationStatus


class SeriesCoverageDTO(BaseModel):
    key: str
    label: str
    status: CoverageStatus
    first_date: date | None = None
    last_date: date | None = None
    points: int = 0
    months_expected: int = 0
    months_covered: int = 0
    share: float = 0.0
    longest_gap_days: int = 0
    note: str | None = None


class CoverageReportDTO(BaseModel):
    """Which stored series cover the simulation period (`missing`: no point at all)."""

    start: date
    end: date
    series: list[SeriesCoverageDTO] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class SimulationRunDTO(BaseModel):
    """A requested simulation and what makes it reproducible (params, data and code hashes)."""

    id: int
    kind: SimulationKind
    status: SimulationStatus
    label: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    params_hash: str
    data_hash: str | None = None
    code_version: str
    seed: int
    error: str | None = None
    reused_from: int | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class BacktestPointDTO(BaseModel):
    day: date
    contribution: float
    contributed: float
    market_value: float
    cash: float
    fees: float
    taxes: float = 0.0
    by_class: dict[str, float] = Field(default_factory=dict)


class BacktestSummaryDTO(BaseModel):
    final_value: float
    contributed: float
    gain: float
    money_weighted_return: float | None = None
    time_weighted_return: float
    annual_twr: float
    volatility: float
    max_drawdown: float
    trades: int
    fees: float
    taxes: float = 0.0
    sales: int = 0


class SimulationResultDTO(BaseModel):
    """One series of a run: `strategy` or `benchmark:<KEY>`."""

    key: str
    label: str
    summary: BacktestSummaryDTO
    points: list[BacktestPointDTO] = Field(default_factory=list)
    unavailable: list[str] = Field(default_factory=list)
    survivorship_bias: bool = False


class SimulationRunDetailDTO(SimulationRunDTO):
    results: list[SimulationResultDTO] = Field(default_factory=list)
