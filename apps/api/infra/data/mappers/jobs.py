"""ORM model <-> domain entity mappers: worker job runs."""

from __future__ import annotations

from domain.shared.entities import (
    JobRunEntity,
    WorkerRequestErrorEntity,
)
from domain.shared.enums import (
    JobRunStatus,
)
from infra.data.models.jobs import JobRunModel, WorkerRequestErrorModel


def to_job_run_entity(model: JobRunModel) -> JobRunEntity:
    return JobRunEntity(
        id=model.id,
        job_name=model.job_name,
        status=JobRunStatus(model.status),
        attempts=model.attempts,
        started_at=model.started_at,
        finished_at=model.finished_at,
        details=dict(model.details or {}),
        error=model.error,
    )


def to_worker_request_error_entity(model: WorkerRequestErrorModel) -> WorkerRequestErrorEntity:
    return WorkerRequestErrorEntity(
        id=model.id,
        job_run_id=model.job_run_id,
        job_name=model.job_name,
        provider=model.provider,
        operation=model.operation,
        target=model.target,
        request_url=model.request_url,
        status_code=model.status_code,
        error_type=model.error_type,
        error_detail=model.error_detail,
        occurred_at=model.occurred_at,
        resolved_at=model.resolved_at,
    )
