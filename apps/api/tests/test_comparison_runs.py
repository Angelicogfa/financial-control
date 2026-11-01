"""Live scoreboard (Phase 45.8a): the daily routine, the stored record, the API and the MCP."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.comparison import runs as comparison_runs
from domain.comparison.runs import cerrado_score
from domain.comparison.strategies import (
    CDI,
    EQUAL,
    OPTIMIZED,
    RANDOM,
    RANDOM_PORTFOLIOS,
    RECOMMENDATION,
    WITH_CERRADO,
    WITHOUT_CERRADO,
    YOURS,
)
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.entities import AssetEntity, ChecklistAnswer, TransactionEntity
from domain.shared.enums import (
    AnswerValue,
    ArcaClass,
    AssetPurpose,
    AssetType,
    SeriesUnit,
    TransactionKind,
)
from domain.simulation.data import px_symbol, tr_symbol
from tests.conftest import offline_gateway
from worker.jobs import update_comparison_portfolios_job

START = date(2024, 1, 2)
NOW = datetime(2024, 9, 30, 21, tzinfo=UTC)


def _days(n: int) -> list[date]:
    return [START + timedelta(days=i) for i in range(n)]


def _seed(api: SimpleNamespace) -> int:
    days = _days(300)
    with api.uow_factory() as uow:
        uow.market_series.upsert_points(
            "CDI", [(d, 0.04) for d in days], unit=SeriesUnit.PERCENT_PER_DAY
        )
        for ticker, growth in (("AAAA3", 0.0008), ("BBBB3", 0.0002)):
            prices = [(d, 20.0 * (1 + growth) ** i) for i, d in enumerate(days)]
            uow.market_series.upsert_points(tr_symbol(ticker), prices, unit=SeriesUnit.PRICE)
            uow.market_series.upsert_points(px_symbol(ticker), prices, unit=SeriesUnit.PRICE)
        held = uow.assets.add(
            AssetEntity(
                ticker="AAAA3",
                name="A",
                asset_type=AssetType.STOCK_BR,
                arca_class=ArcaClass.ACOES,
            )
        )
        uow.assets.add(
            AssetEntity(
                ticker="BBBB3", name="B", asset_type=AssetType.STOCK_BR, arca_class=ArcaClass.ACOES
            )
        )
        reserve = uow.assets.add(
            AssetEntity(
                ticker="RESV11",
                name="R",
                asset_type=AssetType.ETF_BR,
                arca_class=ArcaClass.CAIXA,
                purpose=AssetPurpose.EMERGENCY_RESERVE,
            )
        )
        for asset_id, day, qty in (
            (held.id, date(2024, 1, 10), "50"),
            (held.id, date(2024, 4, 10), "40"),
            (reserve.id, date(2024, 2, 5), "100"),
        ):
            uow.transactions.add(
                TransactionEntity(
                    asset_id=asset_id,
                    kind=TransactionKind.BUY,
                    trade_date=day,
                    quantity=Decimal(qty),
                    unit_price=Decimal("20"),
                )
            )
        uow.commit()
        return held.id  # type: ignore[return-value]


def test_cerrado_score_uses_the_answers_in_force_on_the_day() -> None:
    def answer(q: str, value: AnswerValue | None, day: date) -> ChecklistAnswer:
        return ChecklistAnswer(
            question_id=q,
            value=value,
            answered_at=datetime(day.year, day.month, day.day, tzinfo=UTC),
        )

    history = [
        answer("q1", AnswerValue.YES, date(2024, 1, 5)),
        answer("q2", AnswerValue.NO, date(2024, 3, 5)),
        answer("q2", None, date(2024, 5, 5)),
    ]
    assert cerrado_score(history, date(2024, 1, 1), 2) is None
    assert cerrado_score(history, date(2024, 2, 1), 2) == 5.0  # all yes, half covered
    assert cerrado_score(history, date(2024, 4, 1), 2) == 5.0  # one yes, one no, all covered
    assert cerrado_score(history, date(2024, 6, 1), 2) == 5.0  # the "no" was cleared


def test_routine_builds_the_record_and_only_appends_after(api: SimpleNamespace) -> None:
    assert api.client.get("/api/v1/recommendation/live").json()["status"] == "NOT_COMPUTED"
    held = _seed(api)
    first = update_comparison_portfolios_job(api.uow_factory, offline_gateway(), now=NOW)
    # No recommendation run yet: your portfolio, four references and the random portfolios.
    assert first["status"] == "OK" and first["created"] == 4 + RANDOM_PORTFOLIOS
    with api.uow_factory() as uow:
        yours = uow.comparison.get(YOURS)
        equal = uow.comparison.get(EQUAL)
        cdi = uow.comparison.get(CDI)
    assert yours is not None and equal is not None and cdi is not None
    assert yours.points[-1].contributed == 1800.0  # the reserve stays out of the ARCA flow
    assert equal.points[-1].contributed == pytest.approx(1800.0)
    assert equal.created_on == NOW.date() and equal.points[0].day == date(2024, 1, 10)
    assert cdi.points[-1].value > 1800.0

    # The next day only adds the new day; a trade registered late enters as money that day.
    with api.uow_factory() as uow:
        uow.transactions.add(
            TransactionEntity(
                asset_id=held,
                kind=TransactionKind.BUY,
                trade_date=date(2024, 6, 3),
                quantity=Decimal("10"),
                unit_price=Decimal("20"),
            )
        )
        uow.commit()
    later = NOW + timedelta(days=1)
    second = update_comparison_portfolios_job(api.uow_factory, offline_gateway(), now=later)
    assert second["created"] == 0 and second["updated"] == 4 + RANDOM_PORTFOLIOS
    with api.uow_factory() as uow:
        again = uow.comparison.get(EQUAL)
        yours = uow.comparison.get(YOURS)
    assert again is not None and yours is not None
    assert [p.to_dict() for p in again.points[:-1]] == [p.to_dict() for p in equal.points]
    assert again.points[-1].day == later.date() and again.points[-1].flow == pytest.approx(200.0)
    assert yours.points[-1].contributed == 2000.0

    data = api.client.get("/api/v1/recommendation/live").json()
    assert data["status"] == "OK"
    assert data["prospective_since"] == NOW.date().isoformat()
    # The API reads today's date: the verdict waits for 12 months of prospective record.
    assert data["verdict_ready"] == (data["prospective_months"] >= 12)
    keys = {line["key"] for line in data["lines"]}
    assert keys == {"CERRADO_RULE", EQUAL, "INDEX_ARCA", CDI}
    assert all(line["retroactive"] for line in data["lines"])
    assert data["randoms"]["portfolios"] == RANDOM_PORTFOLIOS
    assert 0.0 <= data["randoms"]["rank"]["share"] <= 1.0
    assert data["curve"] and data["curve"][-1]["random_low"] is not None

    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    op = CATALOG_BY_NAME["recommendation.live"]
    assert op.kind == "query"
    assert op.invoke(handlers, op.input_model()).status == "OK"


def test_recommendation_starts_at_its_first_run_with_your_patrimony(
    api: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(api)
    first_run = date(2024, 5, 6)
    monkeypatch.setattr(
        comparison_runs,
        "recommendation_runs",
        lambda uow: [(first_run, {ArcaClass.ACOES: {"BBBB3": 1.0}})],
    )
    monkeypatch.setattr(
        comparison_runs,
        "optimized_runs",
        lambda uow: [(first_run, {ArcaClass.ACOES: {"AAAA3": 0.6, "BBBB3": 0.4}})],
    )
    monkeypatch.setattr(
        comparison_runs,
        "variant_runs",
        lambda uow, key: (
            [(first_run, {ArcaClass.ACOES: {"AAAA3": 1.0}})] if key == WITHOUT_CERRADO else []
        ),
    )
    update_comparison_portfolios_job(api.uow_factory, offline_gateway(), now=NOW)
    with api.uow_factory() as uow:
        rec = uow.comparison.get(RECOMMENDATION)
        yours = uow.comparison.get(YOURS)
        randoms = [r for r in uow.comparison.list_all() if r.key == RANDOM]
    assert rec is not None and yours is not None and len(randoms) == RANDOM_PORTFOLIOS
    opening = [p for p in yours.points if p.day < rec.points[0].day][-1].value
    assert rec.points[0].day >= first_run
    assert rec.points[0].flow == pytest.approx(opening)
    assert set(rec.state["book"]["units"]) <= {"BBBB3", "CDI"}
    with api.uow_factory() as uow:
        optimized = uow.comparison.get(OPTIMIZED)
    assert optimized is not None and optimized.points[0].day == rec.points[0].day
    assert set(optimized.state["book"]["units"]) <= {"AAAA3", "BBBB3", "CDI"}
    with api.uow_factory() as uow:
        assert uow.comparison.get(WITHOUT_CERRADO) is not None
        assert uow.comparison.get(WITH_CERRADO) is None  # no run kept that variant
