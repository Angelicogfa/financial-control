"""Pydantic response DTOs for the simulation module (Phase 33)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from domain.simulation.data import CoverageStatus


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
