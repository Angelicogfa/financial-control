"""Jobs run by hand: the API queues a request, the worker serves it, the CLI runs it now."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from core.settings import Settings
from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.market.services.use_cases import MANUAL_JOBS
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.enums import JobRunStatus
from tests.conftest import offline_gateway
from worker import run_now as cli
from worker.runner import LocalJobLock, RetryPolicy, run_requested
from worker.scheduler import manual_jobs

NAME = "sync_simulation_history"
URL = f"/api/v1/market/job-runs/{NAME}/request"
POLICY = RetryPolicy(max_retries=0, backoff_seconds=0.0, lock_ttl_seconds=60)


def _requested(api: SimpleNamespace) -> list[Any]:
    with api.uow_factory() as uow:
        return uow.job_runs.requested(NAME)


def _serve(api: SimpleNamespace, job: Any, lock: LocalJobLock | None = None) -> Any:
    return run_requested(
        NAME, job, uow_factory=api.uow_factory, lock=lock or LocalJobLock(), policy=POLICY
    )


def test_the_api_queues_one_request_per_job(api: SimpleNamespace) -> None:
    first = api.client.post(URL)
    assert first.status_code == 202
    assert first.json()["status"] == "REQUESTED" and first.json()["job_name"] == NAME
    # A request still waiting is returned again, not duplicated.
    assert api.client.post(URL).status_code == 202
    assert len(_requested(api)) == 1
    latest = api.client.get("/api/v1/market/job-runs").json()
    assert [(j["job_name"], j["status"]) for j in latest] == [(NAME, "REQUESTED")]

    refused = api.client.post("/api/v1/market/job-runs/refresh_fundamentals/request")
    assert refused.status_code == 400 and refused.json()["code"] == "JOB_NOT_MANUAL"


def test_the_worker_turns_the_request_into_the_run(api: SimpleNamespace) -> None:
    assert _serve(api, lambda: {"x": 1}) is None  # nothing requested: no run, no row

    queued = api.client.post(URL).json()
    run = _serve(api, lambda: {"series": 3})
    assert run is not None and run.status == JobRunStatus.SUCCESS
    assert run.details == {"series": 3} and run.attempts == 1
    assert run.finished_at is not None
    assert _requested(api) == []
    latest = api.client.get("/api/v1/market/job-runs").json()
    assert [(j["job_name"], j["status"]) for j in latest] == [(NAME, "SUCCESS")]
    assert latest[0]["started_at"] >= queued["started_at"]

    def broken() -> None:
        raise RuntimeError("yahoo down")

    api.client.post(URL)
    failed = _serve(api, broken)
    assert failed is not None and failed.status == JobRunStatus.FAILED
    assert "yahoo down" in (failed.error or "")


def test_a_request_during_the_scheduled_run_is_skipped(api: SimpleNamespace) -> None:
    lock = LocalJobLock()
    assert lock.acquire(NAME, 60) is not None  # the weekly run holds the lock
    api.client.post(URL)
    run = _serve(api, lambda: None, lock)
    assert run is not None and run.status == JobRunStatus.SKIPPED and run.finished_at
    assert _requested(api) == []


def test_every_manual_job_has_a_worker_implementation() -> None:
    assert set(manual_jobs(Settings(_env_file=None))) == set(MANUAL_JOBS)


def test_the_cli_runs_the_job_and_reports_it(
    api: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    outcome: dict[str, Any] = {"result": {"assets": 2}}

    def job(_uow_factory: Any, _gateway: Any) -> Any:
        if isinstance(outcome["result"], Exception):
            raise outcome["result"]
        return outcome["result"]

    monkeypatch.setattr(cli, "manual_jobs", lambda _settings: {NAME: job})
    settings = Settings(_env_file=None, job_max_retries=0, job_retry_backoff_seconds=0.0)

    def run() -> int:
        return cli.run_now(
            NAME,
            settings=settings,
            uow_factory=api.uow_factory,
            gateway=object(),  # type: ignore[arg-type]
            lock=LocalJobLock(),
        )

    assert run() == 0
    out = capsys.readouterr().out
    assert f"{NAME}: SUCCESS" in out and '"assets": 2' in out

    outcome["result"] = RuntimeError("sem rede")
    assert run() == 1
    assert "sem rede" in capsys.readouterr().out

    with pytest.raises(SystemExit):
        cli.main(["refresh_fundamentals"])


def test_mcp_request_job(api: SimpleNamespace) -> None:
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    spec = CATALOG_BY_NAME["market.request_job"]
    assert spec.kind == "command"
    run = spec.invoke(handlers, spec.input_model(job_name=NAME))
    assert run.status == "REQUESTED"
    with pytest.raises(ValueError):
        spec.input_model(job_name="refresh_fundamentals")
