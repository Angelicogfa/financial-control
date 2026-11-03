"""Roles of the worker processes: ingestion and processing run apart.

The ingestion worker talks to the outside (Yahoo, Brapi, BCB, CVM, B3, Tesouro) and stores what
it fetched; the processing worker computes from the database only (snapshots, checklists,
simulations, forecasts, the Garimpo and the recommendation). Run apart, a long download never
holds back a calculation and the heavy calculations use another core (one Python process shares
one interpreter lock among its threads). `all` keeps both in one process, as before.

Both use the same Redis lock per job, so a job never runs twice at once, and a manual request is
served by the worker of its role.
"""

from __future__ import annotations

ALL = "all"
INGEST = "ingest"
PROCESS = "process"
ROLES = (ALL, INGEST, PROCESS)

INGEST_JOBS = frozenset(
    {
        "sync_bcb_and_benchmarks",
        "ensure_series_coverage",
        "warm_portfolio_quotes",
        "refresh_watchlist_quotes",
        "refresh_fundamentals",
        "sync_instrument_catalog",
        "sync_simulation_history",
        "sync_cvm_documents",
        "sync_cvm_statements",
        "sync_cvm_event_history",
        "sync_price_history",
        "refresh_distributions",
        "refresh_catalog_fundamentals",
        "sync_treasury_catalog",
        "sync_treasury_prices",
        "sync_mining_universe",
    }
)

PROCESS_JOBS = frozenset(
    {
        "record_daily_snapshot",
        "backfill_snapshots",
        "record_checklist_evaluations",
        "run_pending_simulations",
        "refresh_asset_forecasts",
        "calibrate_forecasts",
        "estimate_forecast_models",
        "run_mining",
        "refresh_asset_lenses",
        "backtest_recommendation",
        "update_comparison_portfolios",
        "evaluate_alert_rules",
    }
)


def job_name(job_id: str) -> str:
    """The job behind a scheduler entry (manual requests are scheduled as `manual_<job>`)."""
    return job_id.removeprefix("manual_")


def runs_here(job_id: str, role: str) -> bool:
    """Whether the worker of `role` runs this job (an unknown job runs only under `all`)."""
    name = job_name(job_id)
    if role == INGEST:
        return name in INGEST_JOBS
    if role == PROCESS:
        return name in PROCESS_JOBS
    return True
