"""Simulation runs and their stored results (Phase 33.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class SimulationStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class SimulationKind(StrEnum):
    BACKTEST = "BACKTEST"
    PROJECTION = "PROJECTION"


@dataclass(frozen=True)
class SimulationRun:
    """One requested simulation: its parameters and what makes it reproducible.

    The same `params_hash` and `data_hash` (inputs read from the database) and the same
    `code_version` always give the same results, so a finished run is reused.
    """

    kind: SimulationKind
    params: dict[str, Any]
    params_hash: str
    code_version: str
    seed: int
    status: SimulationStatus = SimulationStatus.PENDING
    label: str | None = None
    data_hash: str | None = None
    error: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    reused_from: int | None = None
    id: int | None = None


@dataclass(frozen=True)
class SimulationResult:
    """One series of a run: the strategy or a benchmark fed with the same contributions."""

    run_id: int
    key: str
    label: str
    summary: dict[str, Any]
    points: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    id: int | None = None
