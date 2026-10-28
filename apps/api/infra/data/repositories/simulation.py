"""SQLAlchemy repository of the simulation runs and their results.

It takes and returns pure domain entities and never commits
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from domain.simulation.entities import SimulationResult, SimulationRun, SimulationStatus
from domain.simulation.repositories import AbstractSimulationRepository
from infra.data.mappers.simulation import (
    apply_simulation_run,
    to_simulation_result,
    to_simulation_result_model,
    to_simulation_run,
)
from infra.data.models.simulation import SimulationResultModel, SimulationRunModel


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
        return to_simulation_run(model) if model is not None else None

    def list_recent(self, limit: int = 20) -> list[SimulationRun]:
        stmt = select(SimulationRunModel).order_by(SimulationRunModel.id.desc()).limit(limit)
        return [to_simulation_run(m) for m in self.session.scalars(stmt).all()]

    def next_pending(self) -> SimulationRun | None:
        stmt = (
            select(SimulationRunModel)
            .where(SimulationRunModel.status == SimulationStatus.PENDING.value)
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
