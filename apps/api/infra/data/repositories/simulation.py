"""SQLAlchemy repository of the simulation runs and their results.

It takes and returns pure domain entities and never commits
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from domain.simulation.entities import (
    SimulationKind,
    SimulationResult,
    SimulationRun,
    SimulationStatus,
    SimulationStudy,
)
from domain.simulation.repositories import (
    AbstractSimulationRepository,
    AbstractSimulationStudyRepository,
)
from infra.data.mappers.simulation import (
    apply_simulation_run,
    apply_simulation_study,
    to_simulation_result,
    to_simulation_result_model,
    to_simulation_run,
    to_simulation_study,
)
from infra.data.models.simulation import (
    SimulationResultModel,
    SimulationRunModel,
    SimulationStudyModel,
)


class SqlAlchemySimulationRepository(AbstractSimulationRepository):
    """SQLAlchemy implementation of AbstractSimulationRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, run: SimulationRun) -> SimulationRun:
        model = apply_simulation_run(SimulationRunModel(), run)
        self.session.add(model)
        self.session.flush()
        return to_simulation_run(model)

    def update(self, run: SimulationRun) -> SimulationRun:
        if run.id is None:
            raise ValueError("A run must be stored before it is updated.")
        model = self.session.get(SimulationRunModel, run.id)
        if model is None:
            raise ValueError(f"Simulation run {run.id} not found.")
        apply_simulation_run(model, run)
        self.session.flush()
        return to_simulation_run(model)

    def get(self, run_id: int) -> SimulationRun | None:
        model = self.session.get(SimulationRunModel, run_id)
        if model is None or model.deleted_at is not None:
            return None
        return to_simulation_run(model)

    def attach(self, run_id: int, *, study_id: int, chapter: str) -> None:
        model = self.session.get(SimulationRunModel, run_id)
        if model is None:
            raise ValueError(f"Simulation run {run_id} not found.")
        model.study_id = study_id
        model.chapter = chapter
        self.session.flush()

    def list_for_study(self, study_id: int) -> list[SimulationRun]:
        stmt = (
            select(SimulationRunModel)
            .where(
                SimulationRunModel.study_id == study_id,
                SimulationRunModel.deleted_at.is_(None),
            )
            .order_by(SimulationRunModel.id.asc())
        )
        return [to_simulation_run(m) for m in self.session.scalars(stmt).all()]

    def mark_deleted(self, run_id: int, *, deleted_at: datetime) -> bool:
        model = self.session.get(SimulationRunModel, run_id)
        if model is None or model.deleted_at is not None:
            return False
        model.deleted_at = deleted_at
        self.session.flush()
        return True

    def list_recent(
        self, limit: int = 20, kind: SimulationKind | None = None
    ) -> list[SimulationRun]:
        stmt = (
            select(SimulationRunModel)
            .where(SimulationRunModel.deleted_at.is_(None))
            .order_by(SimulationRunModel.id.desc())
            .limit(limit)
        )
        if kind is not None:
            stmt = stmt.where(SimulationRunModel.kind == kind.value)
        return [to_simulation_run(m) for m in self.session.scalars(stmt).all()]

    def next_pending(self) -> SimulationRun | None:
        stmt = (
            select(SimulationRunModel)
            .where(
                SimulationRunModel.status == SimulationStatus.PENDING.value,
                SimulationRunModel.deleted_at.is_(None),
            )
            .order_by(SimulationRunModel.id.asc())
            .limit(1)
        )
        model = self.session.scalars(stmt).first()
        return to_simulation_run(model) if model is not None else None

    def find_done(
        self, params_hash: str, data_hash: str, code_version: str
    ) -> SimulationRun | None:
        stmt = (
            select(SimulationRunModel)
            .where(
                SimulationRunModel.status == SimulationStatus.DONE.value,
                SimulationRunModel.params_hash == params_hash,
                SimulationRunModel.data_hash == data_hash,
                SimulationRunModel.code_version == code_version,
                SimulationRunModel.reused_from.is_(None),
                SimulationRunModel.deleted_at.is_(None),
            )
            .order_by(SimulationRunModel.id.desc())
            .limit(1)
        )
        model = self.session.scalars(stmt).first()
        return to_simulation_run(model) if model is not None else None

    def save_results(self, run_id: int, results: list[SimulationResult]) -> None:
        self.session.execute(
            delete(SimulationResultModel).where(SimulationResultModel.run_id == run_id)
        )
        for result in results:
            self.session.add(to_simulation_result_model(result))
        self.session.flush()

    def results(self, run_id: int) -> list[SimulationResult]:
        stmt = (
            select(SimulationResultModel)
            .where(SimulationResultModel.run_id == run_id)
            .order_by(SimulationResultModel.id.asc())
        )
        return [to_simulation_result(m) for m in self.session.scalars(stmt).all()]

    def count_results(self, key_prefix: str) -> int:
        stmt = (
            select(func.count(SimulationResultModel.id))
            .join(SimulationRunModel, SimulationRunModel.id == SimulationResultModel.run_id)
            .where(
                SimulationResultModel.key.startswith(key_prefix, autoescape=True),
                SimulationRunModel.reused_from.is_(None),
            )
        )
        return int(self.session.scalar(stmt) or 0)


class SqlAlchemySimulationStudyRepository(AbstractSimulationStudyRepository):
    """SQLAlchemy implementation of AbstractSimulationStudyRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, study: SimulationStudy) -> SimulationStudy:
        model = apply_simulation_study(SimulationStudyModel(), study)
        self.session.add(model)
        self.session.flush()
        return to_simulation_study(model)

    def update(self, study: SimulationStudy) -> SimulationStudy:
        model = self.session.get(SimulationStudyModel, study.id)
        if model is None or model.deleted_at is not None:
            raise ValueError(f"Simulation study {study.id} not found.")
        apply_simulation_study(model, study)
        self.session.flush()
        return to_simulation_study(model)

    def get(self, study_id: int) -> SimulationStudy | None:
        model = self.session.get(SimulationStudyModel, study_id)
        if model is None or model.deleted_at is not None:
            return None
        return to_simulation_study(model)

    def list_recent(self, limit: int = 50) -> list[SimulationStudy]:
        alive = SimulationStudyModel.deleted_at.is_(None)
        family = func.coalesce(SimulationStudyModel.origin_id, SimulationStudyModel.id)
        newest = (
            select(func.max(SimulationStudyModel.id))
            .where(alive)
            .group_by(family)
            .scalar_subquery()
        )
        stmt = (
            select(SimulationStudyModel)
            .where(alive, SimulationStudyModel.id.in_(newest))
            .order_by(SimulationStudyModel.id.desc())
            .limit(limit)
        )
        return [to_simulation_study(m) for m in self.session.scalars(stmt).all()]

    def versions(self, origin_id: int) -> list[SimulationStudy]:
        stmt = (
            select(SimulationStudyModel)
            .where(
                SimulationStudyModel.deleted_at.is_(None),
                (SimulationStudyModel.id == origin_id)
                | (SimulationStudyModel.origin_id == origin_id),
            )
            .order_by(SimulationStudyModel.version.asc(), SimulationStudyModel.id.asc())
        )
        return [to_simulation_study(m) for m in self.session.scalars(stmt).all()]

    def mark_deleted(self, study_id: int, *, deleted_at: datetime) -> bool:
        model = self.session.get(SimulationStudyModel, study_id)
        if model is None or model.deleted_at is not None:
            return False
        model.deleted_at = deleted_at
        self.session.flush()
        return True
