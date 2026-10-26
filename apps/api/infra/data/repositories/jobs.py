"""SQLAlchemy repositories: worker job runs.

They take and return pure domain entities and never commit
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.errors import NotFoundError
from domain.shared.entities import (
    JobRunEntity,
)
from domain.shared.repositories import (
    AbstractJobRunRepository,
)
from infra.data.mappers.jobs import to_job_run_entity
from infra.data.models.jobs import JobRunModel


class SqlAlchemyJobRunRepository(AbstractJobRunRepository):
    """SQLAlchemy implementation of AbstractJobRunRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, run: JobRunEntity) -> JobRunEntity:
        model = JobRunModel(
            job_name=run.job_name,
            status=run.status.value,
            attempts=run.attempts,
            started_at=run.started_at,
            finished_at=run.finished_at,
            details=dict(run.details),
            error=run.error,
        )
        self.session.add(model)
        self.session.flush()
        return to_job_run_entity(model)

    def update(self, run: JobRunEntity) -> JobRunEntity:
        model = self.session.get(JobRunModel, run.id) if run.id else None
        if model is None:
            raise NotFoundError(f"Job run id={run.id} not found")
        model.status = run.status.value
        model.attempts = run.attempts
        model.finished_at = run.finished_at
        model.details = dict(run.details)
        model.error = run.error
        self.session.flush()
        return to_job_run_entity(model)

    def latest_per_job(self) -> list[JobRunEntity]:
        latest = (
            select(JobRunModel.job_name, func.max(JobRunModel.id).label("max_id"))
            .group_by(JobRunModel.job_name)
            .subquery()
        )
        stmt = (
            select(JobRunModel)
            .join(latest, JobRunModel.id == latest.c.max_id)
            .order_by(JobRunModel.job_name.asc())
        )
        return [to_job_run_entity(m) for m in self.session.scalars(stmt).all()]
