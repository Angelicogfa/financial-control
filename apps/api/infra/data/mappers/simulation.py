"""Mapping between the simulation ORM models and the pure domain entities."""

from __future__ import annotations

from domain.simulation.entities import (
    SimulationKind,
    SimulationResult,
    SimulationRun,
    SimulationStatus,
)
from infra.data.models.simulation import SimulationResultModel, SimulationRunModel


def to_simulation_run(model: SimulationRunModel) -> SimulationRun:
    return SimulationRun(
        kind=SimulationKind(model.kind),
        params=dict(model.params),
        params_hash=model.params_hash,
        code_version=model.code_version,
        seed=model.seed,
        status=SimulationStatus(model.status),
        label=model.label,
        data_hash=model.data_hash,
        error=model.error,
        created_at=model.created_at,
        started_at=model.started_at,
        finished_at=model.finished_at,
        reused_from=model.reused_from,
        id=model.id,
    )


def apply_simulation_run(model: SimulationRunModel, run: SimulationRun) -> SimulationRunModel:
    model.kind = run.kind.value
    model.params = dict(run.params)
    model.params_hash = run.params_hash
    model.code_version = run.code_version
    model.seed = run.seed
    model.status = run.status.value
    model.label = run.label
    model.data_hash = run.data_hash
    model.error = run.error
    model.started_at = run.started_at
    model.finished_at = run.finished_at
    model.reused_from = run.reused_from
    if run.created_at is not None:
        model.created_at = run.created_at
    return model


def to_simulation_result(model: SimulationResultModel) -> SimulationResult:
    return SimulationResult(
        run_id=model.run_id,
        key=model.key,
        label=model.label,
        summary=dict(model.summary),
        points=list(model.points),
        extra=dict(model.extra or {}),
        id=model.id,
    )


def to_simulation_result_model(result: SimulationResult) -> SimulationResultModel:
    return SimulationResultModel(
        run_id=result.run_id,
        key=result.key,
        label=result.label,
        summary=dict(result.summary),
        points=list(result.points),
        extra=dict(result.extra),
    )
