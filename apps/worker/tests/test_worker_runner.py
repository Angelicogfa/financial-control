"""Tests for resilient job execution: locks, retries and the job_runs log (item 9.7)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fincontrol_config import Settings
from fincontrol_core.domain.enums import JobRunStatus
from fincontrol_persistence.unit_of_work import SqlAlchemyUnitOfWork
from fincontrol_worker.runner import (
    LocalJobLock,
    RedisJobLock,
    RetryPolicy,
    build_job_lock,
    run_job,
)
from fincontrol_worker.scheduler import create_scheduler
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

UoWFactory = Callable[[], SqlAlchemyUnitOfWork]


@pytest.fixture
def uow_factory(tmp_path: Path) -> UoWFactory:
    db_url = f"sqlite:///{(tmp_path / 'runner.db').as_posix()}"
    persistence_dir = Path(__file__).resolve().parents[3] / "packages" / "persistence"
    cfg = Config(str(persistence_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(persistence_dir / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")
    factory = sessionmaker(bind=create_engine(db_url), expire_on_commit=False)
    return lambda: SqlAlchemyUnitOfWork(session_factory=factory)


POLICY = RetryPolicy(max_retries=2, backoff_seconds=10.0, lock_ttl_seconds=60)


def test_success_is_recorded_with_details(uow_factory: UoWFactory) -> None:
    run = run_job(
        "sync", lambda: {"CDI": 3}, uow_factory=uow_factory, lock=LocalJobLock(), policy=POLICY
    )

    assert run.status == JobRunStatus.SUCCESS
    assert run.attempts == 1
    assert run.details == {"CDI": 3}
    with uow_factory() as uow:
        (latest,) = uow.job_runs.latest_per_job()
    assert latest.status == JobRunStatus.SUCCESS and latest.finished_at is not None


def test_transient_failure_is_retried_with_exponential_backoff(uow_factory: UoWFactory) -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def flaky() -> int:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("BCB timeout")
        return 7

    run = run_job(
        "sync",
        flaky,
        uow_factory=uow_factory,
        lock=LocalJobLock(),
        policy=POLICY,
        sleep=sleeps.append,
    )

    assert run.status == JobRunStatus.SUCCESS
    assert run.attempts == 3
    assert run.details == {"count": 7}
    assert sleeps == [10.0, 20.0]


def test_permanent_failure_is_recorded_and_not_raised(uow_factory: UoWFactory) -> None:
    def broken() -> None:
        raise ValueError("bad payload")

    run = run_job(
        "sync",
        broken,
        uow_factory=uow_factory,
        lock=LocalJobLock(),
        policy=POLICY,
        sleep=lambda _s: None,
    )

    assert run.status == JobRunStatus.FAILED
    assert run.attempts == 3
    assert run.error == "ValueError: bad payload"


def test_concurrent_run_is_skipped_and_lock_released_after(uow_factory: UoWFactory) -> None:
    lock = LocalJobLock()
    held = lock.acquire("sync", 60)
    assert held is not None

    skipped = run_job("sync", lambda: 1, uow_factory=uow_factory, lock=lock, policy=POLICY)
    lock.release("sync", held)
    ran = run_job("sync", lambda: 1, uow_factory=uow_factory, lock=lock, policy=POLICY)

    assert skipped.status == JobRunStatus.SKIPPED
    assert ran.status == JobRunStatus.SUCCESS
    assert lock.acquire("sync", 60) is not None


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, key: str, value: str, nx: bool, ex: int) -> bool:
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def eval(self, _script: str, _keys: int, key: str, token: str) -> int:
        if self.store.get(key) == token:
            del self.store[key]
            return 1
        return 0


def test_redis_lock_is_exclusive_and_owner_released() -> None:
    lock = RedisJobLock(_FakeRedis())
    first = lock.acquire("snapshot", 60)
    assert first is not None
    assert lock.acquire("snapshot", 60) is None
    lock.release("snapshot", "someone-else")
    assert lock.acquire("snapshot", 60) is None
    lock.release("snapshot", first)
    assert lock.acquire("snapshot", 60) is not None


def test_build_job_lock_and_scheduler_use_settings() -> None:
    assert isinstance(build_job_lock(None), LocalJobLock)
    assert isinstance(build_job_lock("redis://localhost:6379/0"), RedisJobLock)

    settings = Settings(
        _env_file=None,
        tz="America/Sao_Paulo",
        quote_refresh_minutes=7,
        snapshot_cron_hour=20,
        snapshot_cron_minute=5,
    )
    scheduler = create_scheduler(object(), settings=settings, lock=LocalJobLock())  # type: ignore[arg-type]

    jobs = {job.id: job for job in scheduler.get_jobs()}
    assert set(jobs) == {
        "warm_portfolio_quotes",
        "ensure_series_coverage",
        "sync_bcb_and_benchmarks",
        "record_daily_snapshot",
    }
    assert str(jobs["warm_portfolio_quotes"].trigger) == "interval[0:07:00]"
    snapshot_trigger = str(jobs["record_daily_snapshot"].trigger)
    assert "hour='20'" in snapshot_trigger and "minute='5'" in snapshot_trigger
    assert "day_of_week='mon-fri'" in snapshot_trigger
