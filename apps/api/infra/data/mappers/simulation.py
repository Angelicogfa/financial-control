"""Mapping between the simulation ORM models and the pure domain entities."""

from __future__ import annotations

from domain.simulation.entities import (
    SimulationKind,
    SimulationResult,
    SimulationRun,
    SimulationStatus,
    SimulationStudy,
)
from infra.data.models.simulation import (
    SimulationResultModel,
    SimulationRunModel,
    SimulationStudyModel,
)


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
        study_id=model.study_id,
        chapter=model.chapter,
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
    model.study_id = run.study_id
    model.chapter = run.chapter
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


def to_simulation_study(model: SimulationStudyModel) -> SimulationStudy:
    return SimulationStudy(
        label=model.label,
        question=model.question,
        premises=dict(model.premises),
        version=model.version,
        origin_id=model.origin_id,
        variation_of=model.variation_of,
        notes=list(model.notes or []),
        created_at=model.created_at,
        id=model.id,
    )


def apply_simulation_study(
    model: SimulationStudyModel, study: SimulationStudy
) -> SimulationStudyModel:
    model.label = study.label
    model.question = study.question
    model.premises = dict(study.premises)
    model.version = study.version
    model.origin_id = study.origin_id
    model.variation_of = study.variation_of
    model.notes = list(study.notes)
    if study.created_at is not None:
        model.created_at = study.created_at
    return model
