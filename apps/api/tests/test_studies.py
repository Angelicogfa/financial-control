"""Phase 41: simulation studies — premises once, chapters, seals, conclusion and versions."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

from controllers.simulation.responses import (
    BacktestSummaryDTO,
    CalibrationDTO,
    CandidateBaseDTO,
    CandidateEffectDTO,
    CandidateFitDTO,
    CandidateResultDTO,
    CandidatesDTO,
    CrisisDTO,
    DistributionDTO,
    GeneratorCalibrationDTO,
    GoalOutcomeDTO,
    PercentilesDTO,
    ProjectionDTO,
    ProjectionScenarioDTO,
    RateScenarioDTO,
    RobustnessDTO,
    SimulationResultDTO,
    SimulationRunDetailDTO,
    VariantDTO,
    WindowOutcomeDTO,
)
from domain.agentic.services.catalog import CATALOG_BY_NAME
from domain.shared.entities import ChecklistAnswer
from domain.shared.enums import AnswerValue, ArcaClass, AssetType
from domain.simulation.engine import SimulatedAsset, answers_on
from domain.simulation.entities import SimulationKind, SimulationRun, SimulationStatus
from domain.simulation.services.studies import StudyHandler
from domain.simulation.studies import (
    FutureFacts,
    ImproveFacts,
    PastFacts,
    StudyPremises,
    conclusion,
    confidence_seal,
    future_lead,
    improve_lead,
    money,
    past_lead,
    premise_differences,
    robustness_seal,
    suggested_contribution,
)

# --- pure story -----------------------------------------------------------------------------------


def test_money_and_premises_round_trip() -> None:
    assert money(1_310_000) == "R$ 1,31 mi"
    assert money(412_300) == "R$ 412 mil"
    assert money(980) == "R$ 980,00"
    premises = StudyPremises(monthly_contribution=1500, wealth_goal=1_200_000)
    again = StudyPremises.from_dict(premises.to_dict())
    assert again == premises
    changed = premises.with_changes({"monthly_contribution": 1800})
    assert [d[0] for d in premise_differences(premises, changed)] == ["monthly_contribution"]
    assert suggested_contribution(1500) == 1800


def test_seals_follow_the_four_levels() -> None:
    assert robustness_seal(11, 12).level == 4
    assert robustness_seal(9, 12, ("Pandemia 2020", -0.24)).label == "Confiável"
    assert "caiu 24%" in robustness_seal(9, 12, ("Pandemia 2020", -0.24)).text
    assert robustness_seal(0, 0).level == 0
    assert confidence_seal(0.89, 120, "CALIBRATED", None).level == 4
    trusted = confidence_seal(0.85, 120, "CALIBRATED", date(2026, 11, 3))
    assert (trusted.level, trusted.label) == (3, "Confiável, um pouco otimista")
    assert "03/11/2026" in trusted.text
    assert confidence_seal(0.9, 10, "CALIBRATED", None).level == 1  # short sample
    assert confidence_seal(None, 0, None, None).level == 0


def test_leads_and_conclusion_tell_one_story() -> None:
    premises = StudyPremises(monthly_contribution=1500, wealth_goal=1_200_000)
    past = PastFacts(
        final_value=412_000,
        contributed=250_000,
        cdi_final=374_000,
        best_label="S&P 500 (R$)",
        best_final=455_000,
    )
    future = FutureFacts(
        end_year=2040,
        p50=1_310_000,
        p5=780_000,
        target=1_200_000,
        probability=0.64,
        low=0.57,
        high=0.71,
    )
    improve = ImproveFacts(
        evaluated=20,
        improving=6,
        ticker="TAEE11",
        base_probability=0.64,
        new_probability=0.66,
        p_improve=0.71,
    )
    assert past_lead(past).text.startswith(
        "Seguindo suas regras você teria R$ 412 mil, R$ 38 mil acima"
    )
    assert past_lead(past).tone == "positive"
    assert "é de 64% (entre 57% e 71%)" in future_lead(future).text
    assert future_lead(future).tone == "caution"
    assert improve_lead(improve).text.startswith(
        "Incluir TAEE11 no próximo aporte eleva a chance da meta de 64% para 66%"
    )
    text, actions = conclusion(
        premises,
        past,
        robustness_seal(9, 12),
        future,
        confidence_seal(0.87, 120, "CALIBRATED", None),
        improve,
    )
    assert text.startswith("Suas regras teriam funcionado: R$ 38 mil acima do CDI desde 2012")
    assert "não dependeu de um período sortudo" in text
    assert (
        "chance de chegar a R$ 1,20 mi é de 64%, com chances confiável, um pouco otimista" in text
    )
    assert "TAEE11 (+2 p.p.)" in text
    assert [a.kind for a in actions] == ["VARIATION", "COMPARE_ASSET", "CONTRIBUTE"]
    assert actions[0].changes == {"monthly_contribution": 1800.0}


def test_no_goal_offers_to_set_one_and_no_candidate_is_a_valid_answer() -> None:
    future = FutureFacts(end_year=2040, p50=900_000, p5=500_000)
    assert "Defina uma meta" in future_lead(future).text
    _text, actions = conclusion(
        StudyPremises(monthly_contribution=1000), None, None, future, None, None
    )
    assert "SET_GOAL" in [a.kind for a in actions]
    assert "manter o plano atual" in improve_lead(ImproveFacts(evaluated=8, improving=0)).text


def test_today_answers_count_on_every_past_date() -> None:
    answered = datetime(2026, 5, 1, tzinfo=UTC)
    asset = SimulatedAsset(
        ticker="WEGE3",
        name="WEG",
        asset_type=AssetType.STOCK_BR,
        arca_class=ArcaClass.ACOES,
        answers=(ChecklistAnswer(question_id="roe", value=AnswerValue.YES, answered_at=answered),),
    )
    assert answers_on(asset, date(2015, 3, 31)) == {}
    today_for_all = answers_on(asset, date(2015, 3, 31), today_for_all=True)
    assert today_for_all["roe"].value == AnswerValue.YES
    assert today_for_all["roe"].answered_at.date() == date(2015, 3, 31)  # type: ignore[union-attr]


# --- lifecycle through the API ---------------------------------------------------------------


def _create(api: SimpleNamespace, **overrides: object) -> dict:
    body = {"label": "Aposentadoria 2040", "monthly_contribution": 1500, "wealth_goal": 1_200_000}
    body.update(overrides)
    response = api.client.post("/api/v1/studies", json=body)
    assert response.status_code == 202, response.text
    return response.json()


def test_a_complete_study_queues_its_chapters_with_the_same_premises(api: SimpleNamespace) -> None:
    study = _create(api)
    chapters = {c["key"]: c for c in study["chapters"]}
    assert list(chapters) == ["PAST", "FUTURE", "IMPROVE"]
    assert chapters["PAST"]["status"] == "PENDING" and chapters["FUTURE"]["status"] == "PENDING"
    # No watchlist yet: chapter 3 cannot run, and the study says why.
    assert chapters["IMPROVE"]["run_id"] is None
    assert any("capítulo 3" in n for n in study["notes"])
    assert study["status"] == "PENDING"
    past = api.client.get(f"/api/v1/simulations/{chapters['PAST']['run_id']}").json()
    assert past["params"]["answers_mode"] == "TODAY" and past["params"]["variants"] is True
    assert past["params"]["monthly_contribution"] == 1500
    future = api.client.get(f"/api/v1/simulations/{chapters['FUTURE']['run_id']}").json()
    assert future["label"] == "Aposentadoria 2040 · Para onde vamos"


def test_versions_variations_compare_and_delete(api: SimpleNamespace) -> None:
    first = _create(api, question="GOAL")
    refreshed = api.client.post(f"/api/v1/studies/{first['id']}/refresh").json()
    assert (refreshed["version"], refreshed["origin_id"]) == (2, first["id"])
    listed = api.client.get("/api/v1/studies").json()
    assert [s["id"] for s in listed] == [refreshed["id"]]  # only the latest version is listed
    versions = api.client.get(f"/api/v1/studies/{first['id']}/versions").json()
    assert [v["version"] for v in versions] == [1, 2]

    variation = api.client.post(
        f"/api/v1/studies/{refreshed['id']}/variations",
        json={"changes": {"monthly_contribution": 1800}},
    ).json()
    assert variation["label"] == "Aposentadoria 2040 · aporte R$ 2 mil"
    assert variation["variation_of"] == refreshed["id"]
    bad = api.client.post(
        f"/api/v1/studies/{refreshed['id']}/variations", json={"changes": {"horizon_years": 99}}
    )
    assert bad.status_code == 400

    compared = api.client.get(
        "/api/v1/studies/compare", params={"a": refreshed["id"], "b": variation["id"]}
    ).json()
    assert [d["key"] for d in compared["differences"]] == ["monthly_contribution"]
    assert compared["headline"] == "Os dois estudos diferem em: aporte mensal."

    assert api.client.delete(f"/api/v1/studies/{variation['id']}").status_code == 204
    assert api.client.get(f"/api/v1/studies/{variation['id']}").status_code == 404
    run_id = variation["chapters"][0]["run_id"]
    assert api.client.get(f"/api/v1/simulations/{run_id}").status_code == 404
    for name in ("study.create", "study.get", "study.list", "study.compare", "study.delete"):
        assert name in CATALOG_BY_NAME


# --- the story from finished chapters -------------------------------------------------------


def _summary(final: float) -> BacktestSummaryDTO:
    return BacktestSummaryDTO(
        final_value=final,
        contributed=250_000,
        gain=final - 250_000,
        money_weighted_return=0.118,
        time_weighted_return=1.2,
        annual_twr=0.11,
        volatility=0.15,
        max_drawdown=-0.24,
        trades=100,
        fees=50,
    )


class _FinishedSimulations:
    """Stands in for the SimulationHandler with finished results."""

    def __init__(self, uow_factory) -> None:  # noqa: ANN001
        self.uow_factory = uow_factory

    def get_run(self, run_id: int) -> SimulationRunDetailDTO:
        return SimulationRunDetailDTO(
            id=run_id,
            kind=SimulationKind.BACKTEST,
            status=SimulationStatus.DONE,
            params={"answers_mode": "TODAY"},
            params_hash="h",
            code_version="41",
            seed=7,
            results=[
                SimulationResultDTO(key="strategy", label="Estratégia", summary=_summary(412_000)),
                SimulationResultDTO(key="benchmark:CDI", label="CDI", summary=_summary(374_000)),
                SimulationResultDTO(
                    key="benchmark:SP500_BRL", label="S&P 500 (R$)", summary=_summary(455_000)
                ),
            ],
        )

    def robustness(self, run_id: int) -> RobustnessDTO:
        window = WindowOutcomeDTO(covered=True, months=12)
        variants = [
            VariantDTO(
                key=f"v{i}",
                label=f"v{i}",
                band_pct=5,
                rebalance=False,
                summary=_summary(400_000 if i < 9 else 300_000),
                selection=window,
                holdout=window,
            )
            for i in range(12)
        ]
        crisis = CrisisDTO(
            key="covid",
            label="Pandemia de 2020",
            start=date(2020, 2, 1),
            end=date(2020, 4, 30),
            outcomes={"strategy": WindowOutcomeDTO(covered=True, months=3, max_drawdown=-0.24)},
        )
        empty = DistributionDTO(count=0)
        return RobustnessDTO(
            run_id=run_id,
            status=SimulationStatus.DONE,
            crises=[crisis],
            variants=variants,
            annual_twr_distribution=empty,
            selection_distribution=empty,
            holdout_distribution=empty,
        )

    def projection(self, run_id: int) -> ProjectionDTO:
        pctl = PercentilesDTO(
            p5=780_000, p25=1_000_000, p50=1_310_000, p75=1_500_000, p95=1_900_000
        )
        scenario = ProjectionScenarioDTO(
            key="BASE",
            label="Juros na premissa",
            scenario=RateScenarioDTO(
                name="Juros na premissa", annual_cdi_rate=0.1, annual_ipca_rate=0.04
            ),
            paths=100,
            horizon_months=180,
            final_wealth=pctl,
            final_net_wealth=pctl,
            final_income=pctl,
            max_drawdown=pctl,
            contributed=270_000,
            wealth_goal=GoalOutcomeDTO(
                target=1_200_000, probability=0.64, standard_error=0.01, low=0.57, high=0.71
            ),
        )
        return ProjectionDTO(run_id=run_id, status=SimulationStatus.DONE, scenarios=[scenario])

    def calibration(self) -> CalibrationDTO:
        return CalibrationDTO(
            run_id=1,
            finished_at=datetime(2026, 11, 3, tzinfo=UTC),
            generators=[
                GeneratorCalibrationDTO(
                    key="STACKED",
                    label="Combinado",
                    weight=1,
                    windows=120,
                    effective_windows=110,
                    coverage=0.87,
                    coverage_low=0.8,
                    coverage_high=0.92,
                    status="CALIBRATED",
                    mean_pit=0.5,
                    brier_loss=0.18,
                    brier_beat_cdi=0.1,
                    log_score=0.0,
                )
            ],
        )

    def candidates(self, run_id: int) -> CandidatesDTO:
        fit = CandidateFitDTO(
            months=60,
            alpha_annual=0,
            alpha_post_annual=0,
            alpha_post_sd_annual=0,
            beta=1,
            beta_post=1,
            beta_post_sd=0,
            shrinkage=0.5,
            residual_vol_annual=0.2,
        )

        def effect(ticker: str, delta: float, p: float, rank: int) -> CandidateEffectDTO:
            return CandidateEffectDTO(
                ticker=ticker,
                share_in_class=0.1,
                weight=0.02,
                delta_final_wealth=10_000,
                p_improve=p,
                p_improve_low=p - 0.1,
                p_improve_high=p + 0.1,
                delta_goal_probability=delta,
                delta_cvar_12m=0,
                delta_drawdown=0,
                delta_diversification=0,
                delta_income_yield=0,
                rank=rank,
            )

        def result(ticker: str, delta: float, p: float, rank: int) -> CandidateResultDTO:
            return CandidateResultDTO(
                ticker=ticker,
                name=ticker,
                arca_class="ACOES",
                asset_type="STOCK_BR",
                source="WATCHLIST",
                fit=fit,
                effect=effect(ticker, delta, p, rank),
            )

        return CandidatesDTO(
            run_id=run_id,
            status=SimulationStatus.DONE,
            base=CandidateBaseDTO(
                final_net_wealth_p50=1_310_000,
                cvar_12m=-0.2,
                drawdown_median=-0.3,
                diversification=1.2,
                goal_probability=0.64,
            ),
            candidates=[
                result("IVVB11", 0.0, 0.52, 3),
                result("TAEE11", 0.02, 0.71, 1),
                result("HGLG11", 0.01, 0.63, 2),
            ],
            evaluated=20,
        )


def test_a_finished_study_tells_its_story(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        from domain.simulation.entities import SimulationStudy

        study = uow.simulation_studies.add(
            SimulationStudy(
                label="Aposentadoria 2040",
                question="COMPLETE",
                premises=StudyPremises(monthly_contribution=1500, wealth_goal=1_200_000).to_dict(),
            )
        )
        for chapter, kind in (
            ("PAST", SimulationKind.BACKTEST),
            ("FUTURE", SimulationKind.PROJECTION),
            ("IMPROVE", SimulationKind.CANDIDATES),
        ):
            run = uow.simulations.add(
                SimulationRun(
                    kind=kind,
                    params={},
                    params_hash=chapter,
                    code_version="41",
                    seed=7,
                    status=SimulationStatus.DONE,
                )
            )
            uow.simulations.attach(run.id, study_id=study.id, chapter=chapter)  # type: ignore[arg-type]
        uow.commit()
    handler = StudyHandler(api.uow_factory, _FinishedSimulations(api.uow_factory))  # type: ignore[arg-type]
    dto = handler.get(study.id)  # type: ignore[arg-type]
    assert dto.status == "DONE"
    past, future, improve = dto.chapters
    assert past.seal is not None and (past.seal.level, past.seal.label) == (3, "Confiável")
    assert "9 das 12" in past.seal.text and "Pandemia de 2020" in past.seal.text
    assert past.notes and "checklist de hoje" in past.notes[0]
    assert future.seal is not None and future.seal.label == "Confiável, um pouco otimista"
    assert improve.lead is not None and improve.lead.startswith("Incluir TAEE11")
    assert dto.goal_probability == 0.64
    assert dto.conclusion is not None and "TAEE11 (+2 p.p.)" in dto.conclusion
    assert [a.kind for a in dto.actions] == ["VARIATION", "COMPARE_ASSET", "CONTRIBUTE"]
    summary = handler.list()[0]
    assert summary.chapters_done == 3 and summary.goal_probability == 0.64


# --- migration ------------------------------------------------------------------------------------


def test_migration_turns_existing_runs_into_one_chapter_studies(tmp_path) -> None:  # noqa: ANN001
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    from tests.conftest import API_DIR

    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "infra" / "data" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "script_00028")
    engine = create_engine(url)
    with engine.begin() as conn:
        for kind, label, params, deleted in (
            (
                "BACKTEST",
                "Regras desde 2015",
                {"start": "2015-01-01", "monthly_contribution": 1000},
                None,
            ),
            ("PROJECTION", None, {"monthly_contribution": 500, "horizon_months": 240}, None),
            ("LAB", "Laboratório", {}, None),
            (
                "BACKTEST",
                "Excluída",
                {"start": "2015-01-01", "monthly_contribution": 1},
                "2026-10-29 10:00:00",
            ),
        ):
            conn.execute(
                text(
                    "INSERT INTO simulation_runs (kind, status, label, params, params_hash,"
                    " code_version, seed, created_at, deleted_at)"
                    " VALUES (:k, 'DONE', :l, :p, 'h', '33', 7,"
                    " '2026-10-01 10:00:00', :d)"
                ),
                {"k": kind, "l": label, "p": json.dumps(params), "d": deleted},
            )
    command.upgrade(cfg, "script_00029")
    with engine.connect() as conn:
        studies = conn.execute(
            text("SELECT id, label, question, premises FROM simulation_studies ORDER BY id")
        ).all()
        runs = dict(
            conn.execute(text("SELECT kind || '-' || id, chapter FROM simulation_runs")).all()
        )
    engine.dispose()
    assert [(s[1], s[2]) for s in studies] == [
        ("Regras desde 2015", "PAST"),
        ("Vou chegar à minha meta?", "GOAL"),
    ]
    premises = json.loads(studies[1][3]) if isinstance(studies[1][3], str) else studies[1][3]
    assert premises == {"monthly_contribution": 500.0, "horizon_years": 20}
    assert runs["BACKTEST-1"] == "PAST" and runs["PROJECTION-2"] == "FUTURE"
    assert runs["LAB-3"] is None and runs["BACKTEST-4"] is None
