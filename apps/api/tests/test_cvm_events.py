"""Phase 42.4: event taxonomy, the disclosure history and the event study."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.disclosures.entities import CvmDocument, EventEffect, IssuerTicker
from domain.disclosures.events import (
    ACQUISITION,
    BUYBACK,
    DEBT_ISSUANCE,
    DIVIDENDS,
    MANAGEMENT,
    OTHER,
    RESTRUCTURING,
    STAKE_CHANGE,
    TAKEOVER,
    classify,
)
from domain.disclosures.services.events_sync import IPE, plan_years, sync_event_history
from domain.forecast.event_runs import EVENTS, run_event_study
from domain.forecast.events import (
    MIXED,
    AlignedReturns,
    EventInput,
    EventStudy,
    group_events,
    measure,
    study,
)
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.enums import SeriesUnit
from domain.simulation.data import index_symbol, tr_symbol
from tests.conftest import offline_gateway

FR = "Fato Relevante"
NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


# --- taxonomy --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("3º Programa de Recompra de Ações", BUYBACK),
        ("Recompra de Debêntures, de emissão da própria Cia.", DEBT_ISSUANCE),
        ("Pagamento JCP 4T24", DIVIDENDS),
        ("Deferimento do Processamento da Recuperação Judicial", RESTRUCTURING),
        ("OPA", TAKEOVER),
        ("Reorganização Societária - Incorporação, Cisão ou Fusão da Companhia", ACQUISITION),
        ("Mudanças na Diretoria Executiva", MANAGEMENT),
        ("Divulgação dos Resultados Financeiros Preliminares", "OPERATING_DATA"),
        ("Fato Relevante", OTHER),
    ],
)
def test_relevant_facts_are_classified_by_subject(subject: str, expected: str) -> None:
    assert classify(FR, "", subject) == expected


def test_only_some_documents_are_events() -> None:
    assert classify("Assembleia", "AGO", "Edital") is None
    assert (
        classify(
            "Comunicado ao Mercado",
            "Aquisição/Alienação de Participação Acionária (art. 12 da Instr. CVM nº 358)",
            "Gestora atinge 5%",
        )
        == STAKE_CHANGE
    )
    assert classify("Aviso aos Acionistas", "Outros avisos", "Pagamento de dividendos") == DIVIDENDS
    assert classify("Aviso aos Acionistas", "Outros avisos", "Data da AGO") is None
    assert (
        classify(
            "Informações de Companhias em Recuperação Judicial ou Extrajudicial",
            "",
            "Relatório mensal",
        )
        == RESTRUCTURING
    )


# --- history load ----------------------------------------------------------------------------

WEG = "84429695000111"


def _doc(
    protocol: str, delivered: date, subject: str, category: str = FR, cnpj: str = WEG
) -> CvmDocument:
    return CvmDocument(protocol, cnpj, "WEG", category, delivered, subject=subject)


def test_plan_years() -> None:
    assert plan_years({2010}, date(2026, 10, 30), first_year=2010)[:4] == [2026, 2025, 2011, 2012]


def test_history_loads_classifies_and_marks_old_news_read(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        uow.cvm_issuers.replace_all([IssuerTicker("WEGE3", WEG, "WEG")])
        uow.commit()
    files = {
        2026: [_doc("A", date(2026, 10, 28), "Programa de Recompra de Ações")],
        2015: [
            _doc("B", date(2015, 3, 2), "Aquisição de participação"),
            _doc("C", date(2015, 3, 2), "Edital", category="Assembleia"),
            _doc("X", date(2015, 3, 2), "OPA", cnpj="99999999000199"),  # not a listed company
        ],
    }
    calls: list[int] = []

    def fetch(year: int) -> list[CvmDocument]:
        calls.append(year)
        return files.get(year, [])

    result = sync_event_history(
        api.uow_factory,
        fetch_stamp=lambda y: "v1" if y in files else None,
        fetch_documents=fetch,
        today=date(2026, 10, 30),
        now=NOW,
        max_files=5,
    )
    assert calls == [2026, 2015]
    assert result.loaded == ["IPE 2026: 1", "IPE 2015: 2"]
    with api.uow_factory() as uow:
        events = {d.protocol: d for d in uow.cvm_documents.events()}
        assert set(events) == {"A", "B"}  # the meeting is stored but is not an event
        assert events["A"].event_class == BUYBACK and events["A"].read_at is None
        assert events["B"].event_class == ACQUISITION and events["B"].read_at is not None
        assert {load.year for load in uow.cvm_statements.loads() if load.doc_type == IPE} == {
            2015,
            2026,
        }
    again = sync_event_history(
        api.uow_factory,
        fetch_stamp=lambda y: "v1" if y in files else None,
        fetch_documents=fetch,
        today=date(2026, 10, 30),
        now=NOW,
    )
    assert again.unchanged == 1 and again.loaded == []  # 2015 is done; only 2026 is checked


def test_documents_stored_before_get_classified(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        uow.cvm_documents.upsert_many([_doc("OLD", date(2024, 5, 2), "Recompra")], seen_at=NOW)
        uow.session.execute(  # as if stored before Phase 42.4
            __import__("sqlalchemy").text("UPDATE cvm_documents SET event_class = NULL")
        )
        uow.commit()
    result = sync_event_history(
        api.uow_factory,
        fetch_stamp=lambda y: None,
        fetch_documents=lambda y: [],
        today=date(2026, 10, 30),
    )
    assert result.classified == 1
    with api.uow_factory() as uow:
        assert [d.event_class for d in uow.cvm_documents.events()] == [BUYBACK]


# --- event study -----------------------------------------------------------------------------


def _returns(days: int, seed: int, jumps: dict[int, float]) -> AlignedReturns:
    rng = np.random.default_rng(seed)
    start = date(2020, 1, 1)
    dates = [start + timedelta(days=i) for i in range(days)]
    market = rng.normal(0.0005, 0.01, days)
    asset = 0.0002 + 1.2 * market + rng.normal(0, 0.01, days)
    for i, jump in jumps.items():
        asset[i] += jump
    return AlignedReturns(dates, asset, market)


def test_measure_finds_the_abnormal_return() -> None:
    returns = _returns(400, 1, {300: 0.05})
    event = EventInput((7,), "AAAA3", returns.dates[300], BUYBACK)
    [effect] = measure(event, returns, results_days=[])
    assert effect.car_1 == pytest.approx(0.05, abs=0.025)
    assert effect.car_20 is not None and effect.volatility_ratio is not None
    assert not effect.confounded
    [late] = measure(event, returns, results_days=[returns.dates[302]])
    assert late.confounded
    early = EventInput((8,), "AAAA3", returns.dates[100], BUYBACK)
    assert measure(early, returns) == []  # not enough history before it


def test_same_day_documents_are_one_event() -> None:
    day = date(2024, 3, 1)
    events = group_events(
        [(1, "A3", day, BUYBACK), (2, "A3", day, DIVIDENDS), (3, "B3", day, BUYBACK)]
    )
    assert [(e.ticker, e.event_class, e.document_ids) for e in events] == [
        ("A3", MIXED, (1, 2)),
        ("B3", BUYBACK, (3,)),
    ]


def _effects(cls: str, values: list[float], start: int = 0) -> list[EventEffect]:
    return [
        EventEffect(
            start + i,
            f"T{start + i}",
            date(2020, 1, 1) + timedelta(days=start + i),
            cls,
            v,
            v,
            v,
            1.1,
            False,
        )
        for i, v in enumerate(values)
    ]


def test_study_shrinks_the_classes_to_zero() -> None:
    rng = np.random.default_rng(3)
    effects = (
        _effects(BUYBACK, list(rng.normal(0.03, 0.03, 80)), 0)
        + _effects(DIVIDENDS, list(rng.normal(0.0, 0.03, 80)), 100)
        + _effects(ACQUISITION, list(rng.normal(0.0, 0.03, 80)), 200)
        + _effects(MANAGEMENT, list(rng.normal(-0.02, 0.03, 3)), 300)  # too few
        + [EventEffect(999, "X", date(2021, 1, 1), MIXED, 0.5, 0.5, 0.5, None, False)]
        + [EventEffect(998, "Y", date(2021, 1, 2), BUYBACK, 0.9, 0.9, 0.9, None, True)]
    )
    found = study(effects, as_of=date(2026, 10, 30))
    assert found.events == 245 and found.confounded == 1
    buyback = found.effect(BUYBACK, 5)
    dividends = found.effect(DIVIDENDS, 5)
    assert buyback.effect > 0.02 and buyback.sign_probability > 0.9
    assert abs(dividends.effect) < abs(dividends.mean) + 1e-9
    assert found.effect(MANAGEMENT, 5) is None
    assert {c.event_class for c in found.classes} == {BUYBACK, DIVIDENDS, ACQUISITION}
    assert EventStudy.from_dict(found.to_dict()) == found


# --- runner, API and MCP ---------------------------------------------------------------------


def _seed(api: SimpleNamespace) -> int:
    asset_id = api.client.post(
        "/api/v1/assets", json={"ticker": "WEGE3", "name": "WEG", "asset_type": "STOCK_BR"}
    ).json()["id"]
    rng = np.random.default_rng(5)
    days = [date(2023, 1, 2) + timedelta(days=i) for i in range(700)]
    market = 100 * np.cumprod(1 + rng.normal(0.0004, 0.01, len(days)))
    asset_returns = 1.1 * np.diff(np.log(market), prepend=np.log(market[0])) + rng.normal(
        0, 0.01, len(days)
    )
    event_day = days[500]
    asset_returns[500] += 0.06
    asset = 50 * np.exp(np.cumsum(asset_returns))
    with api.uow_factory() as uow:
        uow.cvm_issuers.replace_all([IssuerTicker("WEGE3", WEG, "WEG")])
        uow.market_series.upsert_points(
            index_symbol("IBOV"), list(zip(days, market, strict=True)), unit=SeriesUnit.INDEX_POINTS
        )
        uow.market_series.upsert_points(
            tr_symbol("WEGE3"), list(zip(days, asset, strict=True)), unit=SeriesUnit.PRICE
        )
        uow.cvm_documents.upsert_many(
            [_doc("E1", event_day, "Programa de Recompra de Ações")], seen_at=NOW
        )
        uow.commit()
    return asset_id


def test_run_event_study_and_the_feed(api: SimpleNamespace) -> None:
    asset_id = _seed(api)
    with api.uow_factory() as uow:
        payload = run_event_study(uow, today=date(2026, 10, 30))
        uow.commit()
    assert payload["events"] == 1
    feed = api.client.get(f"/api/v1/disclosures?asset_id={asset_id}").json()
    [item] = feed["items"]
    assert item["event_class"] == BUYBACK and item["event_label"] == "Recompra de ações"
    assert item["reaction"]["car_1"] == pytest.approx(0.06, abs=0.03)
    assert item["typical_20"] is None  # one event is not a class effect
    study_dto = api.client.get("/api/v1/disclosures/event-study").json()
    assert study_dto["status"] == "OK" and study_dto["events"] == 1


def test_event_study_not_computed_and_mcp(api: SimpleNamespace) -> None:
    assert api.client.get("/api/v1/disclosures/event-study").json()["status"] == "NOT_COMPUTED"
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    op = CATALOG_BY_NAME["disclosures.event_study"]
    assert op.invoke(handlers, op.input_model()).status == "NOT_COMPUTED"
    _seed(api)
    with api.uow_factory() as uow:
        run_event_study(uow, today=date(2026, 10, 30))
        uow.commit()
        assert uow.forecasts.latest_model(EVENTS) is not None
    assert op.invoke(handlers, op.input_model()).events == 1
