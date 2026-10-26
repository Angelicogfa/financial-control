"""ORM model <-> domain entity mappers: worker job runs."""

from __future__ import annotations

from fincontrol_core.domain.entities import (
    JobRunEntity,
)
from fincontrol_core.domain.enums import (
    JobRunStatus,
)

from fincontrol_persistence.models.jobs import JobRunModel


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
