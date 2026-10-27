"""Capture and report failed upstream provider requests made during worker executions.

Uses a `ContextVar` so any provider call running inside a worker job (including across
a `ThreadPoolExecutor` when context is copied or explicitly bound) records structured
failure details without changing the return contract of the market providers.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime

import httpx

from domain.shared.entities import WorkerRequestErrorEntity


class WorkerErrorRecorder:
    """Thread-safe collector for upstream request failures during a single worker job run."""

    def __init__(self, job_name: str, job_run_id: int | None = None) -> None:
        self.job_name = job_name
        self.job_run_id = job_run_id
        self._lock = threading.Lock()
        self._errors: list[WorkerRequestErrorEntity] = []

    def record(
        self,
        *,
        provider: str,
        operation: str,
        target: str,
        request_url: str,
        error_type: str,
        error_detail: str,
        status_code: int | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        entry = WorkerRequestErrorEntity(
            job_run_id=self.job_run_id,
            job_name=self.job_name,
            provider=provider,
            operation=operation,
            target=target,
            request_url=request_url,
            status_code=status_code,
            error_type=error_type,
            error_detail=error_detail,
            occurred_at=occurred_at or datetime.now(UTC),
        )
        with self._lock:
            self._errors.append(entry)

    def drain(self) -> list[WorkerRequestErrorEntity]:
        with self._lock:
            items = list(self._errors)
            self._errors.clear()
            return items


_ACTIVE_RECORDER: ContextVar[WorkerErrorRecorder | None] = ContextVar(
    "active_worker_error_recorder", default=None
)


def current_error_recorder() -> WorkerErrorRecorder | None:
    """Return the active `WorkerErrorRecorder` in the current execution context, if any."""
    return _ACTIVE_RECORDER.get()


@contextmanager
def capture_worker_request_errors(
    job_name: str, job_run_id: int | None = None
) -> Iterator[WorkerErrorRecorder]:
    """Context manager that activates a `WorkerErrorRecorder` for the duration of a job."""
    recorder = WorkerErrorRecorder(job_name=job_name, job_run_id=job_run_id)
    token = _ACTIVE_RECORDER.set(recorder)
    try:
        yield recorder
    finally:
        _ACTIVE_RECORDER.reset(token)


def report_provider_error(
    *,
    provider: str,
    operation: str,
    target: str,
    request_url: str,
    exc: BaseException | None = None,
    status_code: int | None = None,
    error_type: str | None = None,
    error_detail: str | None = None,
) -> None:
    """Record a provider request failure if a worker error recorder is active."""
    recorder = _ACTIVE_RECORDER.get()
    if recorder is None:
        return

    resolved_status = status_code
    resolved_url = request_url
    resolved_type = error_type
    resolved_detail = error_detail

    if isinstance(exc, httpx.HTTPStatusError):
        resolved_status = resolved_status or exc.response.status_code
        resolved_url = str(exc.request.url) if exc.request is not None else resolved_url
        resolved_type = resolved_type or f"HTTP {exc.response.status_code}"
        body_preview = (exc.response.text or "").strip()[:240]
        resolved_detail = resolved_detail or (
            f"HTTP {exc.response.status_code} from {provider}: {body_preview}"
            if body_preview
            else f"HTTP {exc.response.status_code} from {provider}"
        )
    elif isinstance(exc, httpx.RequestError):
        if exc.request is not None:
            resolved_url = str(exc.request.url)
        resolved_type = resolved_type or type(exc).__name__
        resolved_detail = resolved_detail or (str(exc) or type(exc).__name__)
    elif exc is not None:
        resolved_type = resolved_type or type(exc).__name__
        resolved_detail = resolved_detail or (str(exc) or type(exc).__name__)

    recorder.record(
        provider=provider,
        operation=operation,
        target=target,
        request_url=resolved_url,
        status_code=resolved_status,
        error_type=resolved_type or "ProviderError",
        error_detail=resolved_detail or "Request failed without details",
    )
