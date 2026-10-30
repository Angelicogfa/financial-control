"""Tests for resilient job execution: locks, retries and the job_runs log (item 9.7)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.settings import Settings
from domain.shared.enums import JobRunStatus
from infra.data.unit_of_work import SqlAlchemyUnitOfWork
from worker.runner import (
    LocalJobLock,
    RedisJobLock,
    RetryPolicy,
    build_job_lock,
    run_job,
)
from worker.scheduler import create_scheduler

UoWFactory = Callable[[], SqlAlchemyUnitOfWork]


@pytest.fixture
def uow_factory(tmp_path: Path) -> UoWFactory:
    db_url = f"sqlite:///{(tmp_path / 'runner.db').as_posix()}"
    persistence_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(persistence_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(persistence_dir / "infra" / "data" / "migrations"))
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
    with uow_factory() as uow:
        assert uow.worker_errors.count_unresolved() == 1
        (err,) = uow.worker_errors.list_recent()
        assert err.job_name == "sync"
        assert err.job_run_id == run.id
        assert err.provider == "worker"
        assert err.error_type == "ValueError"
        assert "bad payload" in err.error_detail


def test_provider_errors_during_job_are_persisted_with_request_details(
    uow_factory: UoWFactory,
) -> None:
    import httpx

    from infra.cache.redis_cache import InMemoryCache
    from infra.providers.bcb import BcbSgsProvider
    from infra.providers.brapi import BrapiProvider
    from infra.providers.gateway import CachedMarketGateway
    from infra.providers.yfinance_provider import YFinanceProvider

    def brapi_503(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    def yf_down(_symbol: str) -> object:
        raise RuntimeError("Yahoo upstream connection reset")

    def bcb_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("BCB SGS timed out", request=request)

    gateway = CachedMarketGateway(
        brapi=BrapiProvider(client=httpx.Client(transport=httpx.MockTransport(brapi_503))),
        yfinance=YFinanceProvider(ticker_factory=yf_down),
        bcb=BcbSgsProvider(client=httpx.Client(transport=httpx.MockTransport(bcb_timeout))),
        cache=InMemoryCache(),
    )

    def failing_requests_job() -> int:
        gateway.get_quote("WEGE3", bypass_cache=True)
        gateway.fetch_bcb_series("CDI")
        return 0

    run = run_job(
        "warm_portfolio_quotes",
        failing_requests_job,
        uow_factory=uow_factory,
        lock=LocalJobLock(),
        policy=POLICY,
    )

    assert run.status == JobRunStatus.SUCCESS
    with uow_factory() as uow:
        assert uow.worker_errors.count_unresolved() == 3
        errors = uow.worker_errors.list_recent()
        by_provider = {e.provider: e for e in errors}
        assert set(by_provider) == {"brapi", "yfinance", "bcb"}
        assert by_provider["brapi"].status_code == 503
        assert "/quote/WEGE3" in by_provider["brapi"].request_url
        assert by_provider["yfinance"].target == "WEGE3.SA"
        assert "Yahoo upstream connection reset" in by_provider["yfinance"].error_detail
        assert by_provider["bcb"].error_type == "ConnectTimeout"
        assert "bcdata.sgs.12" in by_provider["bcb"].request_url


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
        "refresh_watchlist_quotes",
        "manual_warm_portfolio_quotes",
        "sync_price_history",
        "manual_sync_price_history",
        "refresh_distributions",
        "manual_refresh_distributions",
        "refresh_catalog_fundamentals",
        "manual_refresh_catalog_fundamentals",
        "ensure_series_coverage",
        "sync_bcb_and_benchmarks",
        "record_daily_snapshot",
        "backfill_snapshots",
        "refresh_fundamentals",
        "record_checklist_evaluations",
        "sync_instrument_catalog",
        "sync_treasury_catalog",
        "sync_treasury_prices",
        "sync_simulation_history",
        "run_pending_simulations",
        "manual_sync_simulation_history",
        "sync_cvm_documents",
        "manual_sync_cvm_documents",
        "sync_cvm_statements",
        "manual_sync_cvm_statements",
        "sync_cvm_event_history",
        "manual_sync_cvm_event_history",
        "refresh_asset_forecasts",
        "manual_refresh_asset_forecasts",
        "calibrate_forecasts",
        "manual_calibrate_forecasts",
        "estimate_forecast_models",
        "manual_estimate_forecast_models",
        "sync_mining_universe",
        "manual_sync_mining_universe",
        "run_mining",
        "manual_run_mining",
        "refresh_asset_lenses",
        "manual_refresh_asset_lenses",
    }
    assert "sun" in str(jobs["refresh_fundamentals"].trigger)
    assert str(jobs["warm_portfolio_quotes"].trigger) == "interval[0:07:00]"
    assert str(jobs["backfill_snapshots"].trigger) == "interval[0:07:00]"
    snapshot_trigger = str(jobs["record_daily_snapshot"].trigger)
    assert "hour='20'" in snapshot_trigger and "minute='5'" in snapshot_trigger
    assert "day_of_week='mon-fri'" in snapshot_trigger
