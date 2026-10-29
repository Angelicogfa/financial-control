"""Stored laboratory runs (Phase 33.9): queue, execution and the trial count.

Every model scored in a computed run is a trial (design 7.2): the count of stored model rows
over computed runs feeds the deflated Sharpe of the next run, so the best of many attempts
cannot be picked in silence.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from domain.shared.unit_of_work import AbstractUnitOfWork
from domain.simulation.engine import ENGINE_VERSION
from domain.simulation.entities import (
    SimulationKind,
    SimulationResult,
    SimulationRun,
    SimulationStatus,
)
from domain.simulation.ml.lab import MIN_TRAIN_MONTHS, LabResult

LAB_SUMMARY_KEY = "lab:summary"
LAB_MODEL_PREFIX = "lab:model:"
LAB_LOOKUP = 20


def new_lab_run(*, seed: int, min_train: int = MIN_TRAIN_MONTHS) -> SimulationRun:
    params = {"min_train_months": min_train}
    from domain.simulation.runs import _digest  # the shared hash of the run modules

    return SimulationRun(
        kind=SimulationKind.LAB,
        params=params,
        params_hash=_digest({"kind": "LAB", **params}),
        code_version=ENGINE_VERSION,
        seed=seed,
        label="Laboratório de ML",
    )


def pending_lab(uow: AbstractUnitOfWork) -> SimulationRun | None:
    for run in uow.simulations.list_recent(LAB_LOOKUP, SimulationKind.LAB):
        if run.status in (SimulationStatus.PENDING, SimulationStatus.RUNNING):
            return run
    return None


def latest_lab(uow: AbstractUnitOfWork) -> tuple[SimulationRun, list[SimulationResult]] | None:
    for run in uow.simulations.list_recent(LAB_LOOKUP, SimulationKind.LAB):
        if run.status == SimulationStatus.DONE and run.id is not None:
            return run, uow.simulations.results(run.id)
    return None


def prior_trials(uow: AbstractUnitOfWork) -> int:
    return uow.simulations.count_results(LAB_MODEL_PREFIX)


def to_stored_lab(run_id: int, result: LabResult) -> list[SimulationResult]:
    summary: dict[str, Any] = asdict(result)
    regime = summary.pop("regime")
    models = summary.pop("models")
    cumulative = summary.pop("cumulative_gains", {})
    summary["first_forecast"] = result.first_forecast.isoformat()
    summary["last_forecast"] = result.last_forecast.isoformat()
    rows = [
        SimulationResult(
            run_id=run_id,
            key=LAB_SUMMARY_KEY,
            label="Laboratório de ML",
            summary=summary,
            points=[{**p, "month": p["month"].isoformat()} for p in regime],
        )
    ]
    rows.extend(
        SimulationResult(
            run_id=run_id,
            key=f"{LAB_MODEL_PREFIX}{m['key']}",
            label=m["label"],
            summary=m,
            points=[
                {"month": month.isoformat(), "value": value}
                for month, value in cumulative.get(m["key"], [])
            ],
        )
        for m in models
    )
    return rows
