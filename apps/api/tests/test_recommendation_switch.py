"""Phase 45.6b: the contribution follows the recommendation."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from domain.recommendation.gates import FAIL, AssetGates, GateResult
from domain.recommendation.keys import RECOMMENDATION_BACKTEST
from domain.recommendation.optimizer import optimized_of, target_weights
from domain.recommendation.switch import MAX_RUN_AGE_DAYS, recent_gate_eligibility
from tests.conftest import offline_gateway
from tests.test_mining_signals import seed_panel
from worker.jobs import refresh_asset_lenses_job, run_mining_job

TODAY = date.today()
NOW = datetime.now(UTC)


def _prepare(api: SimpleNamespace) -> int:
    seed_panel(api)
    asset_id = api.client.post(
        "/api/v1/assets",
        json={
            "ticker": "C113",
            "name": "C11",
            "asset_type": "STOCK_BR",
            "cerrado_answers": {"governance": True, "perennial_sector": True},
        },
    ).json()["id"]
    run_mining_job(api.uow_factory, offline_gateway(), now=NOW)
    refresh_asset_lenses_job(api.uow_factory, offline_gateway(), now=NOW)
    return asset_id


def _acoes(plan: dict) -> dict:
    return next(r for r in plan["class_rationale"] if r["arca_class"] == "ACOES")


def test_the_contribution_follows_the_recommendation(api: SimpleNamespace) -> None:
    _prepare(api)
    construction = api.client.get("/api/v1/recommendation/matrix").json()["classes"][0][
        "construction"
    ]
    chosen = {s["ticker"] for s in construction["selected"]}

    plan = api.client.post("/api/v1/portfolio/contribution", json={"amount_brl": 50000}).json()
    assert plan["recommendation_as_of"] == TODAY.isoformat()
    assert _acoes(plan)["recommendation_as_of"] == TODAY.isoformat()
    caixa = next(r for r in plan["class_rationale"] if r["arca_class"] == "CAIXA")
    assert caixa["recommendation_as_of"] is None  # Caixa keeps the policy's strategy
    acoes = [o for o in plan["orders"] if o["arca_class"] == "ACOES"]
    assert {o["ticker"] for o in acoes} == chosen
    bought = [o for o in acoes if o["recommended_quantity"] > 0]
    assert bought and all(o["new"] for o in bought)
    # Catalog stocks are not registered yet while simulating; C113 is (watchlist).
    assert any(o["asset_id"] is None for o in acoes if o["ticker"] != "C113")

    # Saving the draft registers them in the watchlist; confirming buys them.
    draft = api.client.post("/api/v1/contributions", json={"amount_brl": 50000}).json()
    saved = [o for o in draft["plan"]["orders"] if o["recommended_quantity"] > 0]
    assert saved and all(o["asset_id"] for o in saved)
    assert draft["plan"]["recommendation_as_of"] == TODAY.isoformat()
    confirmed = api.client.post(
        f"/api/v1/contributions/{draft['id']}/confirm", json={"trade_date": TODAY.isoformat()}
    )
    assert confirmed.status_code == 200, confirmed.json()
    assert len(confirmed.json()["transaction_ids"]) == len(saved)
    tickers = {a["ticker"] for a in api.client.get("/api/v1/assets?page_size=200").json()["items"]}
    assert {o["ticker"] for o in saved} <= tickers


def test_old_rules_stay_as_a_reference_and_a_stale_run_is_not_followed(
    api: SimpleNamespace,
) -> None:
    _prepare(api)
    old = api.client.post(
        "/api/v1/portfolio/contribution",
        json={"amount_brl": 50000, "strategy_override": "EQUAL_WEIGHT"},
    ).json()
    assert old["recommendation_as_of"] is None
    assert {o["ticker"] for o in old["orders"] if o["arca_class"] == "ACOES"} == {"C113"}

    # A run older than two weeks (the worker stopped) is not followed.
    later = NOW + timedelta(days=MAX_RUN_AGE_DAYS + 1)
    with api.uow_factory() as uow:
        assert recent_gate_eligibility(uow, later.date()) == {}
        assert recent_gate_eligibility(uow, TODAY)["C113"] is True


def test_the_minimum_lot_and_the_lifecycle_by_the_gates(api: SimpleNamespace) -> None:
    asset_id = _prepare(api)
    plan = api.client.post("/api/v1/portfolio/contribution", json={"amount_brl": 800}).json()
    acoes = [o for o in plan["orders"] if o["arca_class"] == "ACOES"]
    assert any(o["reason"] == "BELOW_MIN_LOT" for o in acoes)

    # A gate that fails takes C113 out of the contribution: the lifecycle follows the gates.
    report = api.client.get("/api/v1/portfolio").json()
    position = next(p for p in report["positions"] if p["asset_id"] == asset_id)
    assert position["eligible"] is True
    with api.uow_factory() as uow:
        run = uow.recommendation.latest_lens_date()
        gates = uow.recommendation.gates(as_of=run)
        others = [g for g in gates if g.ticker != "C113"]
        uow.recommendation.replace_gates(
            run, [*others, AssetGates("C113", [GateResult("RUIN", FAIL, "Recuperação judicial.")])]
        )
        uow.commit()
    report = api.client.get("/api/v1/portfolio").json()
    position = next(p for p in report["positions"] if p["asset_id"] == asset_id)
    assert position["eligible"] is False


def test_the_optimizer_sets_the_targets_only_after_passing_its_test(api: SimpleNamespace) -> None:
    _prepare(api)
    data = api.client.get("/api/v1/recommendation/matrix").json()
    acoes = next(c for c in data["classes"] if c["arca_class"] == "ACOES")
    built = {s["ticker"] for s in acoes["construction"]["selected"]}
    optimized = acoes["construction"]["optimized"]
    assert optimized["status"] == "OK" and optimized["assets"]
    assert data["optimizer_in_use"] is False
    with api.uow_factory() as uow:
        construction = next(
            c for c in uow.recommendation.constructions() if c.arca_class == "ACOES"
        )
    assert set(target_weights(construction, False)) == built
    assert target_weights(construction, True) == optimized_of(construction).weights  # type: ignore[union-attr]

    before = api.client.post("/api/v1/portfolio/contribution", json={"amount_brl": 50000}).json()
    assert {o["ticker"] for o in before["orders"] if o["arca_class"] == "ACOES"} == built
    with api.uow_factory() as uow:
        uow.forecasts.save_model(
            RECOMMENDATION_BACKTEST, TODAY, {"backtest": {"optimizer_passed": True}}
        )
        uow.commit()
    after = api.client.post("/api/v1/portfolio/contribution", json={"amount_brl": 50000}).json()
    assert {o["ticker"] for o in after["orders"] if o["arca_class"] == "ACOES"} == {
        a["ticker"] for a in optimized["assets"]
    }
    assert api.client.get("/api/v1/recommendation/matrix").json()["optimizer_in_use"] is True
