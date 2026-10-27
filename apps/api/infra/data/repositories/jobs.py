"""SQLAlchemy repositories: worker job runs.

They take and return pure domain entities and never commit
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from core.errors import NotFoundError
from domain.shared.entities import (
    JobRunEntity,
    WorkerRequestErrorEntity,
)
from domain.shared.repositories import (
    AbstractJobRunRepository,
    AbstractWorkerErrorRepository,
)
from infra.data.mappers.jobs import to_job_run_entity, to_worker_request_error_entity
from infra.data.models.jobs import JobRunModel, WorkerRequestErrorModel


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


class SqlAlchemyWorkerErrorRepository(AbstractWorkerErrorRepository):
    """SQLAlchemy implementation of AbstractWorkerErrorRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, error: WorkerRequestErrorEntity) -> WorkerRequestErrorEntity:
        model = WorkerRequestErrorModel(
            job_run_id=error.job_run_id,
            job_name=error.job_name[:64],
            provider=error.provider[:32],
            operation=error.operation[:64],
            target=error.target[:128],
            request_url=error.request_url[:512],
            status_code=error.status_code,
            error_type=error.error_type[:64],
            error_detail=error.error_detail,
            occurred_at=error.occurred_at,
            resolved_at=error.resolved_at,
        )
        self.session.add(model)
        self.session.flush()
        return to_worker_request_error_entity(model)

    def add_many(self, errors: list[WorkerRequestErrorEntity]) -> int:
        if not errors:
            return 0
        for error in errors:
            self.session.add(
                WorkerRequestErrorModel(
                    job_run_id=error.job_run_id,
                    job_name=error.job_name[:64],
                    provider=error.provider[:32],
                    operation=error.operation[:64],
                    target=error.target[:128],
                    request_url=error.request_url[:512],
                    status_code=error.status_code,
                    error_type=error.error_type[:64],
                    error_detail=error.error_detail,
                    occurred_at=error.occurred_at,
                    resolved_at=error.resolved_at,
                )
            )
        self.session.flush()
        return len(errors)

    def list_recent(
        self, *, include_resolved: bool = False, limit: int = 100
    ) -> list[WorkerRequestErrorEntity]:
        stmt = select(WorkerRequestErrorModel)
        if not include_resolved:
            stmt = stmt.where(WorkerRequestErrorModel.resolved_at.is_(None))
        stmt = stmt.order_by(
            WorkerRequestErrorModel.occurred_at.desc(),
            WorkerRequestErrorModel.id.desc(),
        ).limit(limit)
        return [to_worker_request_error_entity(m) for m in self.session.scalars(stmt).all()]

    def count_unresolved(self) -> int:
        stmt = select(func.count(WorkerRequestErrorModel.id)).where(
            WorkerRequestErrorModel.resolved_at.is_(None)
        )
        return int(self.session.scalar(stmt) or 0)

    def resolve(self, error_id: int, resolved_at: datetime) -> bool:
        model = self.session.get(WorkerRequestErrorModel, error_id)
        if model is None:
            return False
        if model.resolved_at is None:
            model.resolved_at = resolved_at
            self.session.flush()
        return True

    def resolve_all(self, resolved_at: datetime) -> int:
        stmt = (
            update(WorkerRequestErrorModel)
            .where(WorkerRequestErrorModel.resolved_at.is_(None))
            .values(resolved_at=resolved_at)
        )
        res = self.session.execute(stmt)
        self.session.flush()
        return int(res.rowcount or 0)
