"""Acompanhar (Phase 48.R6): alert rules on any ticker and the thesis notes of each asset."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.market.entities import Fundamentals, Quote, StoredMarketData
from domain.shared.entities import CatalogInstrument
from domain.shared.enums import AssetType
from domain.watch.entities import AlertRule, AssetNote, RuleMetric, RuleOperator
from domain.watch.rules import describe, holds, metric_value, read_rules
from domain.watch.services import thesis_alerts
from tests.conftest import offline_gateway
from worker.jobs import evaluate_alert_rules_job

NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)


def _rule(metric: RuleMetric, op: RuleOperator, threshold: str, **kw) -> AlertRule:
    return AlertRule(
        ticker=kw.pop("ticker", "PETR4"),
        metric=metric,
        operator=op,
        threshold=Decimal(threshold),
        **kw,
    )


def _stored(price: float | None = None, **fundamentals) -> StoredMarketData:
    return StoredMarketData(
        ticker="PETR4",
        quote=Quote("PETR4", price) if price is not None else None,
        quote_fetched_at=NOW,
        fundamentals=Fundamentals("PETR4", **fundamentals) if fundamentals else None,
        fundamentals_fetched_at=NOW,
        distributions=None,
        distributions_fetched_at=None,
        history_loaded_at=None,
    )


# --- rules (pure) -----------------------------------------------------------------------------


def test_metric_values_come_from_the_database() -> None:
    catalog = CatalogInstrument(ticker="PETR4", name="Petrobras", close=38.5)
    assert metric_value(RuleMetric.PRICE, _stored(40.0), catalog) == 40.0
    assert metric_value(RuleMetric.PRICE, None, catalog) == 38.5  # catalog close fallback
    assert metric_value(RuleMetric.PRICE, None, None) is None
    stored = _stored(40.0, dividend_yield=0.12, price_to_earnings=4.2, price_to_book=1.1)
    assert metric_value(RuleMetric.DIVIDEND_YIELD, stored, None) == 0.12
    assert metric_value(RuleMetric.PRICE_TO_EARNINGS, stored, None) == 4.2
    assert metric_value(RuleMetric.PRICE_TO_BOOK, _stored(40.0), None) is None


def test_rules_hold_at_the_threshold_and_never_without_data() -> None:
    below = _rule(RuleMetric.PRICE, RuleOperator.BELOW, "30")
    above = _rule(RuleMetric.DIVIDEND_YIELD, RuleOperator.ABOVE, "0.1")
    assert holds(below, 30.0) and holds(below, 29.9) and not holds(below, 30.1)
    assert holds(above, 0.1) and not holds(above, 0.09)
    assert not holds(below, None)

    inactive = _rule(RuleMetric.PRICE, RuleOperator.BELOW, "50", is_active=False)
    [reading] = read_rules([inactive], {"PETR4": _stored(40.0)}, {})
    assert reading.value == 40.0 and not reading.triggered


def test_rules_in_words() -> None:
    assert (
        describe(_rule(RuleMetric.PRICE, RuleOperator.BELOW, "1234.5"))
        == "Preço de PETR4 abaixo de R$ 1.234,50"
    )
    assert (
        describe(_rule(RuleMetric.DIVIDEND_YIELD, RuleOperator.ABOVE, "0.08"))
        == "Dividend yield de PETR4 acima de 8,00%"
    )
    assert (
        describe(_rule(RuleMetric.PRICE_TO_BOOK, RuleOperator.BELOW, "1"))
        == "P/VP de PETR4 abaixo de 1,00"
    )


def test_thesis_alert_when_the_review_date_arrives() -> None:
    today = date(2026, 11, 2)
    notes = [
        AssetNote(
            id=1,
            asset_id=7,
            written_on=date(2026, 5, 1),
            text="Tese: margem volta em 2026",
            review_at=today,
        ),
        AssetNote(
            id=2,
            asset_id=7,
            written_on=date(2026, 5, 1),
            text="Futuro",
            review_at=today + timedelta(days=1),
        ),
        AssetNote(id=3, asset_id=7, written_on=date(2026, 5, 1), text="Sem revisão"),
        AssetNote(
            id=4, asset_id=99, written_on=date(2026, 5, 1), text="Ativo apagado", review_at=today
        ),
    ]
    [alert] = thesis_alerts(notes, {7: "WEGE3"}, today)
    assert alert.title == "Revisar a tese de WEGE3"
    assert alert.route == "/ativo/WEGE3?capitulo=tese"


# --- API --------------------------------------------------------------------------------------


def _seed(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        uow.catalog.upsert(
            [
                CatalogInstrument(
                    ticker="PETR4", name="Petrobras PN", asset_type=AssetType.STOCK_BR, close=38.5
                )
            ]
        )
        uow.commit()


def test_alert_rules_crud_and_the_alert_they_raise(api: SimpleNamespace) -> None:
    _seed(api)
    created = api.client.post(
        "/api/v1/alert-rules",
        json={
            "ticker": "petr4",
            "metric": "PRICE",
            "operator": "BELOW",
            "threshold": "40",
            "note": "comprar",
        },
    )
    assert created.status_code == 201, created.text
    rule = created.json()
    assert rule["ticker"] == "PETR4"
    assert rule["current_value"] == 38.5 and rule["triggered"] is True
    assert rule["description"] == "Preço de PETR4 abaixo de R$ 40,00"

    alerts = api.client.get("/api/v1/alerts").json()["alerts"]
    mine = [a for a in alerts if a["kind"] == "USER_RULE"]
    assert [(a["title"], a["route"]) for a in mine] == [
        ("Preço de PETR4 abaixo de R$ 40,00", "/ativo/PETR4")
    ]
    assert mine[0]["detail"] == "Agora: R$ 38,50. comprar"

    paused = api.client.put(f"/api/v1/alert-rules/{rule['id']}", json={"is_active": False}).json()
    assert paused["triggered"] is False
    assert not [
        a for a in api.client.get("/api/v1/alerts").json()["alerts"] if a["kind"] == "USER_RULE"
    ]

    assert api.client.delete(f"/api/v1/alert-rules/{rule['id']}").status_code == 204
    assert api.client.get("/api/v1/alert-rules").json() == []
    assert api.client.delete(f"/api/v1/alert-rules/{rule['id']}").status_code == 404


def test_alert_rules_reject_unknown_tickers_and_negative_limits(api: SimpleNamespace) -> None:
    _seed(api)
    unknown = api.client.post(
        "/api/v1/alert-rules",
        json={"ticker": "ZZZZ3", "metric": "PRICE", "operator": "BELOW", "threshold": "1"},
    )
    assert unknown.status_code == 404 and unknown.json()["code"] == "INSTRUMENT_NOT_FOUND"
    negative = api.client.post(
        "/api/v1/alert-rules",
        json={"ticker": "PETR4", "metric": "PRICE", "operator": "BELOW", "threshold": "-1"},
    )
    assert negative.status_code == 422
    treasury = api.client.post(
        "/api/v1/alert-rules",
        json={
            "ticker": "tesouro-ipca-2035",
            "metric": "PRICE",
            "operator": "BELOW",
            "threshold": "1",
        },
    )
    assert treasury.status_code == 400


def test_worker_records_when_a_rule_fires_and_clears_it(api: SimpleNamespace) -> None:
    _seed(api)
    rule_id = api.client.post(
        "/api/v1/alert-rules",
        json={"ticker": "PETR4", "metric": "PRICE", "operator": "BELOW", "threshold": "40"},
    ).json()["id"]

    assert evaluate_alert_rules_job(api.uow_factory, offline_gateway(), now=NOW) == {
        "checked": 1,
        "fired": 1,
    }
    first = api.client.get("/api/v1/alert-rules").json()[0]
    assert first["triggered_at"].startswith("2026-11-02") and first["last_checked_at"]
    # Still true later: the firing time is kept.
    assert (
        evaluate_alert_rules_job(api.uow_factory, offline_gateway(), now=NOW + timedelta(hours=1))[
            "fired"
        ]
        == 0
    )
    assert api.client.get("/api/v1/alert-rules").json()[0]["triggered_at"] == first["triggered_at"]

    api.client.put(f"/api/v1/alert-rules/{rule_id}", json={"threshold": "10"})
    evaluate_alert_rules_job(api.uow_factory, offline_gateway(), now=NOW + timedelta(hours=2))
    assert api.client.get("/api/v1/alert-rules").json()[0]["triggered_at"] is None


def _asset(api: SimpleNamespace, ticker: str = "WEGE3") -> int:
    return api.client.post(
        "/api/v1/assets", json={"ticker": ticker, "name": ticker, "asset_type": "STOCK_BR"}
    ).json()["id"]


def test_notes_crud_due_list_and_thesis_alert(api: SimpleNamespace) -> None:
    asset_id = _asset(api)
    today = date.today()
    created = api.client.post(
        f"/api/v1/assets/{asset_id}/notes",
        json={
            "text": "Compro pela margem; revisar no balanço",
            "written_on": (today - timedelta(days=90)).isoformat(),
            "review_at": today.isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    note = created.json()
    assert note["due"] is True
    later = api.client.post(
        f"/api/v1/assets/{asset_id}/notes",
        json={"text": "Outra", "review_at": (today + timedelta(days=30)).isoformat()},
    ).json()

    assert [n["id"] for n in api.client.get(f"/api/v1/assets/{asset_id}/notes").json()] == [
        later["id"],
        note["id"],
    ]
    due = api.client.get("/api/v1/notes?due_only=true").json()
    assert [(n["id"], n["ticker"]) for n in due] == [(note["id"], "WEGE3")]
    assert [n["id"] for n in api.client.get("/api/v1/notes").json()] == [note["id"], later["id"]]

    thesis = [
        a for a in api.client.get("/api/v1/alerts").json()["alerts"] if a["kind"] == "THESIS_REVIEW"
    ]
    assert [a["title"] for a in thesis] == ["Revisar a tese de WEGE3"]

    updated = api.client.put(
        f"/api/v1/assets/{asset_id}/notes/{note['id']}",
        json={"text": "Revisada: mantenho", "review_at": (today + timedelta(days=180)).isoformat()},
    ).json()
    assert updated["text"] == "Revisada: mantenho" and updated["due"] is False
    assert api.client.delete(f"/api/v1/assets/{asset_id}/notes/{note['id']}").status_code == 204
    assert api.client.delete(f"/api/v1/assets/{asset_id}/notes/{note['id']}").status_code == 404


def test_notes_validate_text_dates_and_owner(api: SimpleNamespace) -> None:
    asset_id = _asset(api)
    other = _asset(api, "ITSA4")
    empty = api.client.post(f"/api/v1/assets/{asset_id}/notes", json={"text": "   "})
    assert empty.status_code == 400 and empty.json()["code"] == "EMPTY_NOTE"
    backwards = api.client.post(
        f"/api/v1/assets/{asset_id}/notes",
        json={"text": "x", "written_on": "2026-10-01", "review_at": "2026-09-01"},
    )
    assert backwards.json()["code"] == "INVALID_REVIEW_DATE"
    note_id = api.client.post(f"/api/v1/assets/{asset_id}/notes", json={"text": "minha"}).json()[
        "id"
    ]
    assert (
        api.client.put(f"/api/v1/assets/{other}/notes/{note_id}", json={"text": "x"}).status_code
        == 404
    )
    assert api.client.get("/api/v1/assets/999/notes").status_code == 404


def test_mcp_creates_a_rule_and_lists_due_notes(api: SimpleNamespace) -> None:
    _seed(api)
    handlers = AgenticRuntimeHandlers(uow_factory=api.uow_factory, portfolio_service=None)  # type: ignore[arg-type]
    spec = CATALOG_BY_NAME["watch.rules_create"]
    created = spec.invoke(
        handlers,
        spec.input_model(
            ticker="PETR4", metric="DIVIDEND_YIELD", operator="ABOVE", threshold="0.1"
        ),
    )
    assert created.description == "Dividend yield de PETR4 acima de 10,00%"
    assert created.current_value is None and created.triggered is False  # no fundamentals stored
    notes = CATALOG_BY_NAME["watch.notes_list"]
    assert notes.invoke(handlers, notes.input_model(due_only=True)) == []
