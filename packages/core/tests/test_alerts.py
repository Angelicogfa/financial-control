"""Unit tests for the alerts engine (item 12.2)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from fincontrol_core.alerts import (
    Alert,
    AlertDismissal,
    AlertKind,
    AlertSeverity,
    data_alerts,
    portfolio_alerts,
    valuation_alerts,
    visible_alerts,
)
from fincontrol_core.arca.allocation import ArcaTargets
from fincontrol_core.domain.entities import AssetEntity, JobRunEntity, TransactionEntity
from fincontrol_core.domain.enums import (
    AssetLifecycle,
    AssetType,
    ChecklistProfile,
    JobRunStatus,
    TransactionKind,
)
from fincontrol_core.fundamentals.valuation import AssetValuation, ValuationVerdict
from fincontrol_core.market.series_status import SeriesStatus
from fincontrol_core.policy import EligibilityPolicy
from fincontrol_core.portfolio.consolidation import consolidate_portfolio

TODAY = date(2026, 3, 10)


def _asset(ticker: str, *trades: tuple[str, str, str], **kw: object) -> AssetEntity:
    return AssetEntity(
        ticker=ticker,
        name=ticker,
        asset_type=AssetType.STOCK_BR,
        id=hash(ticker) % 1000,
        transactions=tuple(
            TransactionEntity(
                asset_id=1,
                kind=TransactionKind(kind),
                trade_date=date(2026, 1, 5),
                quantity=Decimal(qty),
                unit_price=Decimal(price),
            )
            for kind, qty, price in trades
        ),
        **kw,  # type: ignore[arg-type]
    )


def test_portfolio_alerts_cover_ledger_review_fallback_and_bands() -> None:
    report = consolidate_portfolio(
        [
            _asset("OVER3", ("BUY", "1", "10"), ("SELL", "5", "10")),
            _asset("REVW3", ("BUY", "10", "10"), cerrado_answers={"roe": False, "debt": False}),
            _asset("GOOD3", ("BUY", "10", "10")),
        ],
        ArcaTargets.default(),
        eligibility=EligibilityPolicy(min_score=1),
        as_of_date=TODAY,
    )
    alerts = {a.key: a for a in portfolio_alerts(report)}
    assert alerts["ledger:OVER3"].severity == AlertSeverity.CRITICAL
    assert alerts["review:REVW3"].kind == AlertKind.ASSET_IN_REVIEW
    assert alerts["fallback:GOOD3"].route.startswith("/assets/")
    assert "fallback:OVER3" not in alerts
    below = [a for a in alerts.values() if a.kind == AlertKind.CLASS_OUT_OF_BAND]
    assert {a.subject for a in below} >= {"CAIXA", "REAL_ESTATE"}
    above = alerts["band:ACOES:ABOVE"]
    assert above.route == "/portfolio" and "acima" in above.title


def test_valuation_alerts_only_for_eligible_or_held_discounts() -> None:
    def valuation(verdict: ValuationVerdict, margin: float | None) -> AssetValuation:
        return AssetValuation(ChecklistProfile.STOCK, True, 30.0, (), 40.0, margin, verdict)

    alerts = valuation_alerts(
        {
            "A3": valuation(ValuationVerdict.DISCOUNTED, 0.25),
            "B3": valuation(ValuationVerdict.DISCOUNTED, 0.3),
            "C3": valuation(ValuationVerdict.FAIR, 0.05),
        },
        {"A3": AssetLifecycle.HELD, "B3": AssetLifecycle.WATCHLIST, "C3": AssetLifecycle.HELD},
        {"A3": 7},
    )
    assert [(a.key, a.route) for a in alerts] == [("discount:A3", "/assets/7")]
    assert alerts[0].detail == "Preço 30,00 abaixo do valor estimado (margem 25,0%)."


def test_data_alerts_for_series_snapshots_and_jobs() -> None:
    stale = SeriesStatus("CDI", None, 10, date(2025, 1, 2), date(2026, 2, 1), True, 0)
    fresh = SeriesStatus("IPCA", None, 10, date(2025, 1, 2), date(2026, 2, 1), False, 0)
    failed = JobRunEntity(
        job_name="sync_bcb_and_benchmarks",
        started_at=datetime(2026, 3, 9, tzinfo=UTC),
        status=JobRunStatus.FAILED,
        error="timeout",
        id=42,
    )
    ok = JobRunEntity(job_name="x", started_at=datetime(2026, 3, 9, tzinfo=UTC), id=1)
    alerts = data_alerts(
        [stale, fresh],
        latest_snapshot=date(2026, 3, 5),
        has_positions=True,
        job_runs=[failed, ok],
        today=TODAY,
    )
    assert [a.key for a in alerts] == [
        "series:CDI:2026-02-01",
        "snapshot:2026-03-09",
        "job:sync_bcb_and_benchmarks:42",
    ]
    assert alerts[2].detail == "timeout"
    quiet = data_alerts(
        [], latest_snapshot=date(2026, 3, 9), has_positions=True, job_runs=[], today=TODAY
    )
    assert quiet == []
    assert (
        data_alerts([], latest_snapshot=None, has_positions=False, job_runs=[], today=TODAY) == []
    )


def test_visible_alerts_respect_dismissals_and_order() -> None:
    alerts = [
        Alert("i", AlertKind.SNAPSHOT_MISSING, AlertSeverity.INFO, "t", "d"),
        Alert("w", AlertKind.STALE_SERIES, AlertSeverity.WARNING, "t", "d", "CDI"),
        Alert("c", AlertKind.INVALID_LEDGER, AlertSeverity.CRITICAL, "t", "d", "X"),
        Alert("gone", AlertKind.JOB_FAILED, AlertSeverity.WARNING, "t", "d"),
        Alert("back", AlertKind.JOB_FAILED, AlertSeverity.WARNING, "t", "d", "z"),
    ]
    now = datetime(2026, 3, 1, tzinfo=UTC)
    dismissals = [
        AlertDismissal("gone", now, None),
        AlertDismissal("back", now, date(2026, 3, 9)),
    ]
    assert [a.key for a in visible_alerts(alerts, dismissals, today=TODAY)] == [
        "c",
        "back",
        "w",
        "i",
    ]
