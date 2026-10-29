"""Phase 33.10: the whole simulation, from the history load to every view, through the API.

One flow over the same database, the way the app runs it: the history load (fake provider)
queues the calibration; the worker runs every queued run; then the backtest with variants
(Past and Robustness with the statistical validation), the projection fed by the calibration
weights (Future), the candidates (layer D) and the laboratory (layer C).
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np

from domain.market.entities import PricePoint
from domain.policy.services.policy import ArcaPolicy, ClassPolicy, InvestmentPolicy
from domain.shared.entities import MarketSeriesPoint
from domain.shared.enums import ArcaClass, SeriesUnit
from worker.jobs import run_pending_simulations_job, sync_simulation_history_job

TODAY = date.today()
START = TODAY - timedelta(days=10 * 365)


def _weekdays() -> list[date]:
    days, day = [], START
    while day <= TODAY:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


class FakeHistoryGateway:
    """What the weekly history load reads from Yahoo and the BCB, generated."""

    def __init__(self) -> None:
        self.days = _weekdays()
        rng = np.random.default_rng(11)
        n = len(self.days)
        market = rng.normal(0.0004, 0.012, n)
        self.series = {
            "^BVSP": 100_000.0 * np.cumprod(1.0 + market),
            "^SP500TR": 5_000.0 * np.cumprod(1.0 + rng.normal(0.0005, 0.01, n)),
            "USDBRL=X": 5.0 * np.cumprod(1.0 + rng.normal(0.0, 0.004, n)),
            "WEGE3": 40.0 * np.cumprod(1.0 + 0.0002 + 1.1 * market + rng.normal(0.0, 0.01, n)),
            "ITUB4": 30.0 * np.cumprod(1.0 + 0.9 * market + rng.normal(0.0, 0.009, n)),
        }

    def get_full_history(self, symbol: str, **_kw: object) -> list[PricePoint]:
        values = self.series.get(symbol)
        if values is None:
            return []
        return [
            PricePoint(date=d, close=float(v), adj_close=float(v))
            for d, v in zip(self.days, values, strict=True)
        ]

    def fetch_bcb_series(
        self, symbol: str, start_date: date | None = None, end_date: date | None = None
    ) -> list[MarketSeriesPoint]:
        return [
            MarketSeriesPoint(symbol, d, 0.04, SeriesUnit.PERCENT_PER_DAY)
            for d in self.days
            if (start_date is None or d >= start_date) and (end_date is None or d <= end_date)
        ]


def test_the_whole_simulation_flow(api: SimpleNamespace) -> None:
    post, get = api.client.post, api.client.get
    # WEGE3 held (bought 10 years ago), ITUB4 followed in the watchlist.
    wege = post(
        "/api/v1/assets", json={"ticker": "WEGE3", "name": "WEG", "asset_type": "STOCK_BR"}
    ).json()
    post("/api/v1/assets", json={"ticker": "ITUB4", "name": "Itaú", "asset_type": "STOCK_BR"})
    post(
        "/api/v1/transactions",
        json={
            "asset_id": wege["id"],
            "kind": "BUY",
            "trade_date": (START + timedelta(days=5)).isoformat(),
            "quantity": "100",
            "unit_price": "40.00",
        },
    )
    targets = {ArcaClass.ACOES: 60.0, ArcaClass.CAIXA: 40.0}
    with api.uow_factory() as uow:
        uow.policies.add(
            InvestmentPolicy(
                arca=ArcaPolicy({c: ClassPolicy(target_pct=targets.get(c, 0.0)) for c in ArcaClass})
            )
        )
        uow.commit()

    # 33.1 + 33.6: the history load stores the series and queues the calibration.
    counts = sync_simulation_history_job(api.uow_factory, FakeHistoryGateway(), start=START)
    assert counts["WEGE3"] > 0 and counts["IBOV"] > 0 and counts["calibration_run"] > 0
    coverage = get(
        "/api/v1/simulations/coverage",
        params={"start": START.isoformat(), "end": TODAY.isoformat()},
    ).json()
    assert "IBOV" not in coverage["missing"]

    # 33.2-33.4 + 33.8: backtest with variants.
    backtest = post(
        "/api/v1/simulations/backtests",
        json={
            "start": (START + timedelta(days=40)).isoformat(),
            "end": (TODAY - timedelta(days=1)).isoformat(),
            "monthly_contribution": 1000.0,
            "benchmarks": ["CDI", "IBOV"],
            "variants": True,
        },
    ).json()
    # 33.5 + 33.6: projection with the calibrated mixture.
    projection_request = {
        "horizon_years": 5,
        "monthly_contribution": 1000.0,
        "initial_by_class": {"ACOES": 10_000.0, "CAIXA": 5000.0},
        "cdi_rate": 0.10,
        "ipca_rate": 0.04,
        "wealth_goal": 100_000.0,
        "paths": 300,
    }
    # 33.7: candidates; 33.9: laboratory.
    candidates = post(
        "/api/v1/simulations/candidates",
        json={**projection_request, "include_screener": False, "include_ineligible": True},
    ).json()
    lab = post("/api/v1/simulations/lab").json()

    # The calibration runs first (it was queued first), so the projection can use it.
    done = run_pending_simulations_job(api.uow_factory, timeout_seconds=300)
    assert done == {"DONE": 4}
    projection = post("/api/v1/simulations/projections", json=projection_request).json()
    assert run_pending_simulations_job(api.uow_factory, timeout_seconds=300) == {"DONE": 1}

    calibration = get("/api/v1/simulations/calibration").json()
    assert calibration["status"] == "DONE" and calibration["windows"] > 0

    past = get(f"/api/v1/simulations/{backtest['id']}").json()
    assert [r["key"] for r in past["results"]][:3] == [
        "strategy",
        "benchmark:CDI",
        "benchmark:IBOV",
    ]
    robustness = get(f"/api/v1/simulations/{backtest['id']}/robustness").json()
    assert robustness["trials_in_run"] == 8 and robustness["validation"] is not None

    future = get(f"/api/v1/simulations/{projection['id']}/projection").json()
    assert future["calibration_run"] == calibration["run_id"]
    base = future["scenarios"][1]
    assert (
        base["wealth_goal"]["low"]
        <= base["wealth_goal"]["probability"]
        <= base["wealth_goal"]["high"]
    )

    found = get(f"/api/v1/simulations/{candidates['id']}/candidates").json()
    assert [c["ticker"] for c in found["candidates"]] == ["ITUB4"]  # WEGE3 is held
    assert found["candidates"][0]["fit"]["beta"] > 0.5

    lab_result = get("/api/v1/simulations/lab").json()
    assert lab_result["run_id"] == lab["id"] and lab_result["trials"] == 6
    assert lab_result["verdict"]

    kinds = {r["kind"] for r in get("/api/v1/simulations", params={"limit": 20}).json()}
    assert kinds == {"BACKTEST", "PROJECTION", "CANDIDATES", "CALIBRATION", "LAB"}
