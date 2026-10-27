"""Integration test for GET /market/series-status."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from core.helpers.calendar import previous_business_day
from domain.shared.enums import SeriesUnit


def test_series_status_reports_every_tracked_series(api: SimpleNamespace) -> None:
    last = previous_business_day(date.today())
    with api.uow_factory() as uow:
        uow.market_series.upsert_points("CDI", [(last, 0.055)], unit=SeriesUnit.PERCENT_PER_DAY)
        uow.market_series.upsert_points(
            "IBOV", [(date.today() - timedelta(days=30), 120_000.0)], unit=SeriesUnit.INDEX_POINTS
        )
        uow.commit()

    body = {row["symbol"]: row for row in api.client.get("/api/v1/market/series-status").json()}

    assert list(body) == ["CDI", "SELIC", "IPCA", "IBOV", "IFIX", "SP500"]
    assert body["CDI"]["stale"] is False
    assert body["CDI"]["unit"] == "PERCENT_PER_DAY"
    assert body["IBOV"]["stale"] is True
    assert body["SELIC"] == {
        "symbol": "SELIC",
        "unit": None,
        "points": 0,
        "first_date": None,
        "last_date": None,
        "stale": True,
        "missing_business_days": 0,
    }


def test_job_runs_lists_latest_execution_per_job(api: SimpleNamespace) -> None:
    from datetime import UTC, datetime

    from domain.shared.entities import JobRunEntity
    from domain.shared.enums import JobRunStatus

    with api.uow_factory() as uow:
        for status in (JobRunStatus.FAILED, JobRunStatus.SUCCESS):
            uow.job_runs.add(
                JobRunEntity(
                    job_name="sync_bcb_and_benchmarks",
                    started_at=datetime(2025, 1, 2, tzinfo=UTC),
                    status=status,
                    attempts=1,
                    details={"CDI": 2},
                )
            )
        uow.commit()

    (run,) = api.client.get("/api/v1/market/job-runs").json()

    assert run["job_name"] == "sync_bcb_and_benchmarks"
    assert run["status"] == "SUCCESS"
    assert run["details"] == {"CDI": 2}


def test_worker_errors_list_resolve_one_and_resolve_all(api: SimpleNamespace) -> None:
    from datetime import UTC, datetime

    from domain.shared.entities import WorkerRequestErrorEntity

    now = datetime(2026, 10, 26, 21, 0, tzinfo=UTC)
    with api.uow_factory() as uow:
        e1 = uow.worker_errors.add(
            WorkerRequestErrorEntity(
                job_name="warm_portfolio_quotes",
                provider="brapi",
                operation="quote",
                target="PETR4",
                request_url="https://brapi.dev/api/quote/PETR4",
                status_code=502,
                error_type="HTTP 502",
                error_detail="HTTP 502 from brapi: Bad Gateway",
                occurred_at=now,
            )
        )
        e2 = uow.worker_errors.add(
            WorkerRequestErrorEntity(
                job_name="sync_bcb_and_benchmarks",
                provider="bcb",
                operation="series",
                target="CDI (2026-01-01..2026-10-26)",
                request_url="https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados",
                status_code=None,
                error_type="ConnectTimeout",
                error_detail="Timed out connecting to BCB SGS",
                occurred_at=now,
            )
        )
        uow.commit()

    resp = api.client.get("/api/v1/market/worker-errors")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["unresolved_count"] == 2
    assert len(payload["errors"]) == 2
    assert {e["provider"] for e in payload["errors"]} == {"brapi", "bcb"}

    # Resolve single error
    del_one = api.client.delete(f"/api/v1/market/worker-errors/{e1.id}")
    assert del_one.status_code == 204

    after_one = api.client.get("/api/v1/market/worker-errors").json()
    assert after_one["unresolved_count"] == 1
    assert [e["id"] for e in after_one["errors"]] == [e2.id]

    # Including resolved brings both back
    with_resolved = api.client.get(
        "/api/v1/market/worker-errors", params={"include_resolved": "true"}
    ).json()
    assert with_resolved["unresolved_count"] == 1
    assert len(with_resolved["errors"]) == 2

    # Non-existent error returns 404
    assert api.client.delete("/api/v1/market/worker-errors/99999").status_code == 404

    # Resolve all remaining errors
    del_all = api.client.delete("/api/v1/market/worker-errors")
    assert del_all.status_code == 204

    after_all = api.client.get("/api/v1/market/worker-errors").json()
    assert after_all["unresolved_count"] == 0
    assert after_all["errors"] == []


def test_script_00017_migration_upgrade_and_downgrade(tmp_path) -> None:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    persistence_dir = Path(__file__).resolve().parents[1]
    db_url = f"sqlite:///{(tmp_path / 'mig17.db').as_posix()}"
    cfg = Config(str(persistence_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(persistence_dir / "infra" / "data" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    engine = create_engine(db_url, future=True)

    command.upgrade(cfg, "script_00016")
    assert "worker_request_errors" not in inspect(engine).get_table_names()

    command.upgrade(cfg, "script_00017")
    assert "worker_request_errors" in inspect(engine).get_table_names()

    command.downgrade(cfg, "script_00016")
    assert "worker_request_errors" not in inspect(engine).get_table_names()
    engine.dispose()
