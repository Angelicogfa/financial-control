"""Ingestion and processing in separate worker processes (worker/roles.py)."""

from __future__ import annotations

from core.settings import Settings
from domain.market.services.use_cases import MANUAL_JOBS
from worker.roles import INGEST, INGEST_JOBS, PROCESS, PROCESS_JOBS, job_name, runs_here
from worker.runner import LocalJobLock
from worker.scheduler import create_scheduler


def _jobs(role: str) -> set[str]:
    settings = Settings(_env_file=None, tz="America/Sao_Paulo", worker_role=role)
    scheduler = create_scheduler(object(), settings=settings, lock=LocalJobLock())  # type: ignore[arg-type]
    return {job.id for job in scheduler.get_jobs()}


def test_every_job_has_exactly_one_role() -> None:
    everything = _jobs("all")
    names = {job_name(j) for j in everything} | set(MANUAL_JOBS)
    assert not INGEST_JOBS & PROCESS_JOBS
    assert names == INGEST_JOBS | PROCESS_JOBS, names ^ (INGEST_JOBS | PROCESS_JOBS)


def test_each_worker_schedules_only_its_jobs_and_serves_its_manual_requests() -> None:
    everything, ingest, process = _jobs("all"), _jobs(INGEST), _jobs(PROCESS)
    assert ingest | process == everything and not ingest & process
    assert "sync_cvm_statements" in ingest and "manual_sync_cvm_statements" in ingest
    assert "run_mining" in process and "manual_run_mining" in process
    assert "run_pending_simulations" in process
    assert not any(job_name(j) in PROCESS_JOBS for j in ingest)


def test_runs_here() -> None:
    assert runs_here("manual_refresh_asset_lenses", PROCESS)
    assert not runs_here("manual_refresh_asset_lenses", INGEST)
    assert runs_here("anything", "all") and not runs_here("anything", INGEST)
