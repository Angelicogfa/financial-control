"""Phase 45.1: the lenses of the recommendation and the signals they add to the panel."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.assets.services.cerrado import (
    CerradoEvaluation,
    EvaluatedAnswer,
    Recommendation,
    StaleReason,
)
from domain.forecast.valuation_model import CompanyInput, add_months
from domain.portfolio.services.service import PortfolioApplicationService
from domain.recommendation.keys import LENSES
from domain.recommendation.lenses import (
    CATALOG,
    CERRADO,
    CERRADO_OFF,
    INCOME,
    NOT_ANALYZED,
    PARTIAL,
    PROJECTION,
    QUALITY,
    RISK,
    STALE,
    VALUATION,
    WATCHLIST,
    AssetLenses,
    asset_lenses,
    cerrado_lens,
    projection_lens,
    signal_lens,
)
from domain.recommendation.signals import registry_signals, regularity, risk_raw
from domain.shared.enums import AnswerSource, AnswerValue, ChecklistProfile
from tests.conftest import offline_gateway
from tests.test_mining_signals import _quarters, seed_panel
from worker.jobs import refresh_asset_lenses_job, run_mining_job

TODAY = date(2026, 10, 31)
NOW = datetime(2026, 10, 31, 20, 0, tzinfo=UTC)


def _answer(i: int, value: AnswerValue | None, **kwargs) -> EvaluatedAnswer:
    return EvaluatedAnswer(
        question_id=f"q{i}",
        text="",
        category="",
        hint="",
        value=value,
        source=AnswerSource.MANUAL if value else AnswerSource.PENDING,
        automatable=False,
        **kwargs,
    )


def _evaluation(answers: list[EvaluatedAnswer], *, use_cerrado: bool = True) -> CerradoEvaluation:
    yes = sum(a.value == AnswerValue.YES for a in answers)
    no = sum(a.value == AnswerValue.NO for a in answers)
    na = sum(a.value == AnswerValue.NA for a in answers)
    return CerradoEvaluation(
        ChecklistProfile.STOCK, use_cerrado, answers, yes, no, na, Recommendation.APTO
    )


# --- L0 Cerrado --------------------------------------------------------------------------------


def test_not_analysed_scores_zero_and_keeps_competing() -> None:
    for evaluation in (None, _evaluation([_answer(i, None) for i in range(4)])):
        lens = cerrado_lens(evaluation, validity_months=12, as_of=TODAY)
        assert lens.value == 0.0 and lens.normalized == 0.0
        assert lens.flags == [NOT_ANALYZED] and "pode ser reclassificado" in lens.note


def test_full_partial_stale_and_switched_off() -> None:
    full = _evaluation([_answer(i, AnswerValue.YES) for i in range(4)])
    assert cerrado_lens(full, validity_months=12, as_of=TODAY).value == 10.0

    # 3 yes and 1 no of 8 applicable (2 not applicable, 2 pending): 5 x (2/4 + 1) x 4/8.
    partial = _evaluation(
        [_answer(i, AnswerValue.YES) for i in range(3)]
        + [_answer(3, AnswerValue.NO), _answer(4, AnswerValue.NA), _answer(5, AnswerValue.NA)]
        + [_answer(6, None), _answer(7, None)]
    )
    lens = cerrado_lens(partial, validity_months=12, as_of=TODAY)
    assert partial.applicable == 6
    assert lens.value == pytest.approx(5 * 1.5 * 4 / 6, abs=0.01)
    assert lens.flags == [PARTIAL] and "Análise incompleta" in lens.note

    # An answer expired 6 months ago counts half; one expired over a year ago counts nothing.
    answered = datetime(2025, 5, 1, tzinfo=UTC)
    old = datetime(2024, 1, 1, tzinfo=UTC)
    stale = _evaluation(
        [
            _answer(0, AnswerValue.YES),
            _answer(1, AnswerValue.YES, answered_at=answered, stale_reason=StaleReason.EXPIRED),
            _answer(2, AnswerValue.YES, answered_at=old, stale_reason=StaleReason.EXPIRED),
        ]
    )
    lens = cerrado_lens(stale, validity_months=12, as_of=TODAY)
    assert STALE in lens.flags and "vencida" in lens.note
    assert 10 * 1.4 / 3 < lens.value < 10 * 1.6 / 3

    off = cerrado_lens(_evaluation([], use_cerrado=False), validity_months=12, as_of=TODAY)
    assert off.value is None and off.normalized is None and off.flags == [CERRADO_OFF]


# --- L1 to L7 ----------------------------------------------------------------------------------


def test_signal_lens_reads_the_panel() -> None:
    month = date(2026, 9, 30)
    good = signal_lens(QUALITY, 1.5, month=month, as_of=TODAY)
    assert good.normalized == pytest.approx(0.75) and good.confidence == 1.0
    assert good.note.startswith("Qualidade bem acima do setor (z +1,5")
    cheap = signal_lens(VALUATION, 0.5, month=month, as_of=TODAY)
    assert cheap.note.startswith("Preço mais barato que o setor")
    calm = signal_lens(RISK, -5.0, month=month, as_of=TODAY)
    assert calm.value == -3.0 and calm.normalized == 0.0 and "risco bem maior" in calm.note.lower()
    old = signal_lens(INCOME, 0.0, month=date(2025, 10, 31), as_of=TODAY)
    assert old.confidence < 0.5 and "na média do setor" in old.note
    missing = signal_lens(QUALITY, None, month=month, as_of=TODAY)
    assert missing.value is None and missing.normalized is None and missing.confidence == 0.0


def test_projection_leaves_the_valuation_layer_out() -> None:
    forecast = {
        "status": "OK",
        "as_of": "2026-10-30",
        "months_used": 120,
        "expected_total_return_annual": 0.20,
        "drivers": [
            {"key": "MARKET", "annual": 0.12},
            {"key": "OWN", "annual": 0.02},
            {"key": "VALUATION", "annual": 0.03},
            {"key": "EVENTS", "annual": None},
        ],
    }
    lens = projection_lens(forecast, as_of=TODAY)
    over = (1.20 / 1.03) / 1.12 - 1
    assert lens.value == pytest.approx(over / 0.05, abs=1e-3)
    assert lens.confidence == 1.0 and "sem o valuation" in lens.note
    assert projection_lens(None, as_of=TODAY).value is None
    assert projection_lens({"status": "INSUFFICIENT_HISTORY"}, as_of=TODAY).value is None


def test_asset_lenses_have_the_eight_in_order() -> None:
    item = asset_lenses(
        ticker="WEGE3",
        as_of=TODAY,
        source=WATCHLIST,
        arca_class="ACOES",
        sector="Bens industriais",
        evaluation=None,
        validity_months=12,
        signals={"QUALITY": 1.0, "VALUE": -0.5, "INCOME": 0.2, "RISK": 0.4},
        signal_month=date(2026, 9, 30),
        forecast=None,
    )
    assert [s.lens for s in item.lenses] == list(LENSES)
    assert item.lens(VALUATION).value == -0.5
    assert item.lens(PROJECTION).value is None
    assert AssetLenses.from_dict(item.to_dict()) == item


# --- signals added to the panel ----------------------------------------------------------------


def test_risk_is_low_volatility_and_low_drawdown() -> None:
    months = [add_months((2020, 1), i) for i in range(36)]
    calm = risk_raw({m: 0.01 for m in months}, months[-1])
    wild = risk_raw({m: (0.10 if i % 2 else -0.08) for i, m in enumerate(months)}, months[-1])
    assert calm["low_volatility"] == pytest.approx(0.0) and calm["low_drawdown"] == 0.0
    assert wild["low_volatility"] < calm["low_volatility"]
    assert wild["low_drawdown"] < calm["low_drawdown"]
    assert risk_raw({m: 0.01 for m in months[:10]}, months[9]) == {}  # below 24 months


def test_regularity_counts_the_deliveries_with_dividends() -> None:
    snaps = _quarters(date(2019, 3, 31), [100.0] * 20)
    company = CompanyInput("AAAA3", "X", snaps, {})
    assert regularity(company, (2023, 12)) == 1.0
    assert regularity(company, (2019, 12)) is None  # fewer than eight deliveries


def test_registry_signals_order_income_and_risk() -> None:
    companies, alphas = {}, {}
    months = [add_months((2019, 1), i) for i in range(60)]
    rng = np.random.default_rng(1)
    for c in range(12):
        ticker = f"C{c:02d}3"
        snaps = _quarters(date(2019, 3, 31), [100.0] * 20)
        companies[ticker] = CompanyInput(ticker, "AB"[c % 2], snaps, {m: 10.0 for m in months})
        alphas[ticker] = {m: float(rng.normal(0.0, 0.01 + 0.01 * c)) for m in months}
    panel = registry_signals(companies, alphas, months)
    month = months[-1]
    assert panel["C003"][month]["RISK"] > panel["C113"][month]["RISK"]  # less volatile
    assert "INCOME" in panel["C003"][month]


# --- worker, API and MCP -----------------------------------------------------------------------


def test_lenses_job_api_and_mcp(api: SimpleNamespace) -> None:
    assert api.client.get("/api/v1/recommendation/lenses").json()["status"] == "NOT_COMPUTED"
    seed_panel(api)
    run_mining_job(api.uow_factory, offline_gateway(), now=NOW)
    asset_id = api.client.post(
        "/api/v1/assets",
        json={
            "ticker": "C113",
            "name": "C11",
            "asset_type": "STOCK_BR",
            "cerrado_answers": {"governance": True, "perennial_sector": True},
        },
    ).json()["id"]
    assert asset_id

    result = refresh_asset_lenses_job(api.uow_factory, offline_gateway(), now=NOW)
    assert result["registered"] == 1 and result["catalog"] == 11

    board = api.client.get("/api/v1/recommendation/lenses").json()
    assert board["status"] == "OK" and board["counts"] == {"WATCHLIST": 1, "CATALOG": 11}
    mine = next(a for a in board["assets"] if a["ticker"] == "C113")
    lenses = {s["lens"]: s for s in mine["lenses"]}
    assert mine["source"] == WATCHLIST and mine["arca_class"] == "ACOES"
    assert list(lenses) == list(LENSES)
    assert lenses[CERRADO]["value"] > 0 and PARTIAL in lenses[CERRADO]["flags"]
    other = next(a for a in board["assets"] if a["source"] == CATALOG)
    assert {s["lens"]: s for s in other["lenses"]}[CERRADO]["flags"] == [NOT_ANALYZED]

    # Gates (45.2): liquid, years of prices, no ruin sign; the Cerrado is never one of them.
    assert result["eligible"] == 12 and board["eligible"] == 12
    gates = {g["gate"]: g for g in mine["gates"]}
    assert mine["eligible"] is True and list(gates) == [
        "LEDGER",
        "LIQUIDITY",
        "HISTORY",
        "RUIN",
        "DATA",
    ]
    assert gates["LEDGER"]["status"] == "PASS" and gates["LIQUIDITY"]["status"] == "PASS"
    assert gates["DATA"]["status"] == "NOT_APPLICABLE"
    assert {g["gate"]: g for g in other["gates"]}["LEDGER"]["status"] == "NOT_APPLICABLE"
    left_out = api.client.get("/api/v1/recommendation/lenses?eligible=false").json()
    assert left_out["assets"] == [] and left_out["eligible"] == 0

    only = api.client.get("/api/v1/recommendation/lenses?source=WATCHLIST").json()
    assert [a["ticker"] for a in only["assets"]] == ["C113"]

    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    op = CATALOG_BY_NAME["recommendation.lenses"]
    assert op.kind == "query"
    found = op.invoke(handlers, op.input_model(ticker="C113"))
    assert [a.ticker for a in found.assets] == ["C113"]

    # The decision matrix (45.3): the Ações class, objective MIXED, every eligible stock ranked.
    assert result["classes"] == 1
    board = api.client.get("/api/v1/recommendation/matrix").json()
    [acoes] = board["classes"]
    assert acoes["arca_class"] == "ACOES" and acoes["objective"] == "MIXED"
    assert acoes["consistency_ratio"] <= 0.011 and len(acoes["weights"]) == 8
    assert [r["rank"] for r in acoes["rows"]] == list(range(1, 13)) and acoes["excluded"] == []
    analysed = next(r for r in acoes["rows"] if r["ticker"] == "C113")
    assert analysed["flags"] != [NOT_ANALYZED]
    other_ticker = next(r["ticker"] for r in acoes["rows"] if r["ticker"] != "C113")
    compare = api.client.get(f"/api/v1/recommendation/compare?a=C113&b={other_ticker}").json()
    assert compare["status"] == "OK" and len(compare["differences"]) == 8
    assert {d["lens"] for d in compare["differences"]} == set(LENSES)
    missing = api.client.get("/api/v1/recommendation/compare?a=C113&b=ZZZZ3").json()
    assert missing["status"] == "NOT_COMPARABLE" and "ZZZZ3" in missing["reason"]
    matrix_op = CATALOG_BY_NAME["recommendation.matrix"]
    assert matrix_op.invoke(handlers, matrix_op.input_model(arca_class="ACOES")).classes
    compare_op = CATALOG_BY_NAME["recommendation.compare"]
    assert (
        compare_op.invoke(handlers, compare_op.input_model(a="C113", b=other_ticker)).status == "OK"
    )

    # The construction (45.4): dynamic K with its curve, every chosen asset with its reason.
    construction = acoes["construction"]
    assert result["selected"] == {"ACOES": construction["k"]} and construction["k"] >= 3
    assert sum(s["weight"] for s in construction["selected"]) == pytest.approx(1.0, abs=1e-4)
    assert construction["stop_reason"] and all(s["reason"] for s in construction["selected"])
    assert len(construction["curve"]) >= construction["k"]

    # Next to the current contribution, nothing saved.
    side = api.client.get("/api/v1/recommendation/contribution?amount_brl=100000").json()
    assert side["status"] == "OK" and side["amount"] == 100000
    by_class = {c["arca_class"]: c for c in side["classes"]}
    assert by_class["ACOES"]["covered"] and by_class["ACOES"]["budget"] > 0
    recommended = by_class["ACOES"]["recommended_orders"]
    assert {o["ticker"] for o in recommended} == {s["ticker"] for s in construction["selected"]}
    spent = sum(o["amount"] for o in recommended) + by_class["ACOES"]["recommended_leftover"]
    assert spent == pytest.approx(by_class["ACOES"]["budget"], abs=1.0)
    assert all(o["new"] for o in recommended)  # nothing is held in this portfolio
    assert not by_class["CAIXA"]["covered"] and "regra atual" in by_class["CAIXA"]["note"]
    with api.uow_factory() as uow:
        assert uow.contribution_plans.list_recent() == []  # nothing saved
    side_op = CATALOG_BY_NAME["recommendation.contribution"]
    assert side_op.invoke(handlers, side_op.input_model(amount_brl=5000)).status == "OK"

    # A second run the same day replaces it.
    again = refresh_asset_lenses_job(api.uow_factory, offline_gateway(), now=NOW)
    assert again["assets"] == result["assets"]
    later = NOW + timedelta(days=7)
    refresh_asset_lenses_job(api.uow_factory, offline_gateway(), now=later)
    assert api.client.get("/api/v1/recommendation/lenses").json()["as_of"] == "2026-11-07"

    # The history (45.5): one entry per run, newest first, with the policy it applied; any past
    # run can be read again by its date.
    runs = api.client.get("/api/v1/recommendation/runs").json()
    assert [r["as_of"] for r in runs] == ["2026-11-07", "2026-10-31"]
    assert runs[1]["policy_version"] == 1 and runs[1]["eligible"] == 12
    assert runs[1]["selected"]["ACOES"] == [s["ticker"] for s in construction["selected"]]
    past = api.client.get("/api/v1/recommendation/matrix?as_of=2026-10-31").json()
    assert (
        past["as_of"] == "2026-10-31"
        and past["classes"][0]["construction"]["k"] == construction["k"]
    )
    old_lenses = api.client.get("/api/v1/recommendation/lenses?as_of=2026-10-31").json()
    assert old_lenses["as_of"] == "2026-10-31"
    runs_op = CATALOG_BY_NAME["recommendation.runs"]
    assert len(runs_op.invoke(handlers, runs_op.input_model())) == 2
