"""Phase 25: manual answer validity, statement reopening, indicator sanity and normalized Bazin."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from domain.alerts.services.evaluator import (
    AlertKind,
    data_quality_alerts,
    valuation_alerts,
)
from domain.assets.services.cerrado import (
    AnswerFreshness,
    StaleReason,
    answer_freshness,
    evaluate,
    latest_statement_seen,
    stale_reason,
)
from domain.assets.services.history import FundamentalPeriod, FundamentalSnapshot
from domain.assets.services.valuation import (
    ValuationVerdict,
    normalized_dividends,
    value_asset,
)
from domain.market.entities import Fundamentals
from domain.market.services.fundamentals_sanity import (
    check_fundamentals,
    divergence_flags,
    range_flags,
)
from domain.policy.services.lifecycle import is_eligible
from domain.policy.services.policy import EligibilityPolicy
from domain.shared.entities import ChecklistAnswer
from domain.shared.enums import (
    AnswerSource,
    AnswerValue,
    AssetLifecycle,
    AssetType,
    ChecklistProfile,
)
from infra.cache.redis_cache import InMemoryCache
from infra.providers.gateway import CachedMarketGateway

API_DIR = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 28)
ANSWERED = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)


def _manual(
    qid: str, value: AnswerValue = AnswerValue.YES, when: datetime = ANSWERED
) -> ChecklistAnswer:
    return ChecklistAnswer(qid, value, AnswerSource.MANUAL, None, when)


def _statement(year: int, seen: datetime | None = None, **metrics: float) -> FundamentalSnapshot:
    return FundamentalSnapshot(
        ticker="WEGE3",
        reference_date=date(year, 12, 31),
        period=FundamentalPeriod.ANNUAL,
        metrics=metrics,
        first_seen_at=seen,
    )


# --- answer validity and reopening ------------------------------------------------------------


def test_stale_reason_expiry_and_new_statement() -> None:
    fresh = AnswerFreshness(as_of=date(2026, 3, 1), validity_months=12)
    expired = AnswerFreshness(as_of=TODAY, validity_months=12)
    reopened = AnswerFreshness(
        as_of=date(2025, 7, 1), statement_seen_at=datetime(2025, 6, 20, tzinfo=UTC)
    )

    assert stale_reason(_manual("roe"), fresh) is None
    assert stale_reason(_manual("roe"), expired) == StaleReason.EXPIRED
    assert stale_reason(_manual("roe"), reopened) == StaleReason.NEW_STATEMENT
    assert stale_reason(_manual("roe"), None) is None
    auto = ChecklistAnswer("roe", AnswerValue.YES, AnswerSource.AUTO, None, ANSWERED)
    assert stale_reason(auto, expired) is None
    naive = ChecklistAnswer("roe", AnswerValue.YES, AnswerSource.MANUAL, None, datetime(2025, 6, 1))
    assert stale_reason(naive, reopened) == StaleReason.NEW_STATEMENT


def test_stale_answers_count_or_leave_the_score_by_policy() -> None:
    answers = {"governance": _manual("governance"), "age_30y": _manual("age_30y", AnswerValue.NO)}
    kept = evaluate(ChecklistProfile.STOCK, answers, freshness=AnswerFreshness(as_of=TODAY))
    dropped = evaluate(
        ChecklistProfile.STOCK, answers, freshness=AnswerFreshness(as_of=TODAY, drop_stale=True)
    )
    current = evaluate(ChecklistProfile.STOCK, answers)

    assert kept.stale == 2 and kept.answered == current.answered == 2
    assert dropped.stale == 2 and dropped.answered == 0
    flagged = {a.question_id: a.stale_reason for a in kept.answers if a.stale_reason}
    assert flagged == {"governance": StaleReason.EXPIRED, "age_30y": StaleReason.EXPIRED}
    assert current.stale == 0


def test_stale_answers_send_the_asset_to_review_unless_disabled() -> None:
    evaluation = evaluate(
        ChecklistProfile.STOCK,
        {"governance": _manual("governance")},
        freshness=AnswerFreshness(as_of=TODAY),
    )
    assert is_eligible(evaluation, EligibilityPolicy()) is False
    assert is_eligible(evaluation, EligibilityPolicy(review_on_expired_answers=False)) is True


def test_latest_statement_seen_uses_the_newest_fiscal_year() -> None:
    old = _statement(2023, seen=datetime(2026, 9, 1, tzinfo=UTC))
    new = _statement(2025, seen=datetime(2026, 3, 1, tzinfo=UTC))
    assert latest_statement_seen([old, new]) == datetime(2026, 3, 1, tzinfo=UTC)
    assert latest_statement_seen([]) is None
    freshness = answer_freshness(EligibilityPolicy(answer_validity_months=6), TODAY, [old, new])
    assert freshness.validity_months == 6
    assert freshness.statement_seen_at == datetime(2026, 3, 1, tzinfo=UTC)


def test_policy_validates_the_validity_window() -> None:
    from core.errors import ValidationError

    with pytest.raises(ValidationError):
        EligibilityPolicy(answer_validity_months=0)


# --- indicator sanity ---------------------------------------------------------------------------


def test_range_flags_by_type() -> None:
    stock = Fundamentals("ITSA4", dividend_yield=3.0, profit_margin=4.2, price_to_book=1.2)
    fii = Fundamentals("HGLG11", price_to_book=7.0, dividend_yield=0.09)

    flags = range_flags(stock, AssetType.STOCK_BR)
    assert set(flags) == {"dividend_yield", "profit_margin"}
    assert "300,0%" in flags["dividend_yield"]
    assert set(range_flags(fii, AssetType.FII)) == {"price_to_book"}
    assert range_flags(Fundamentals("AAPL", return_on_equity=1.6), AssetType.STOCK_INTL) == {}


def test_divergence_between_sources() -> None:
    brapi = Fundamentals("ITSA4", price_to_earnings=8.0, dividend_yield=0.07, price_to_book=1.5)
    yahoo = Fundamentals("ITSA4", price_to_earnings=8.5, dividend_yield=0.14, price_to_book=None)

    flags = divergence_flags(brapi, yahoo)
    assert set(flags) == {"dividend_yield"}
    assert "brapi 7,0% × Yahoo 14,0%" in flags["dividend_yield"]
    assert divergence_flags(brapi, None) == {}
    checked = check_fundamentals(brapi, AssetType.STOCK_BR, yahoo)
    assert set(checked.suspicious) == {"dividend_yield"}


class _Fundamentals:
    def __init__(self, fund: Fundamentals | None) -> None:
        self.fund = fund

    def get_fundamentals(self, symbol: str, market: object = None) -> Fundamentals | None:
        return self.fund


def test_gateway_flags_b3_fundamentals_with_a_second_opinion() -> None:
    gateway = CachedMarketGateway(
        brapi=_Fundamentals(Fundamentals("ITSA4", dividend_yield=0.07)),  # type: ignore[arg-type]
        yfinance=_Fundamentals(Fundamentals("ITSA4", dividend_yield=0.20)),  # type: ignore[arg-type]
        cache=InMemoryCache(),
    )
    fund = gateway.get_fundamentals("ITSA4", asset_type=AssetType.STOCK_BR)
    assert fund is not None and set(fund.suspicious) == {"dividend_yield"}
    cached = gateway.get_fundamentals("ITSA4", asset_type=AssetType.STOCK_BR)
    assert cached is not None and cached.suspicious == fund.suspicious


# --- valuation -----------------------------------------------------------------------------------


def _dividend_history(*paid: float) -> list[FundamentalSnapshot]:
    return [_statement(2020 + i, dividends_paid=-v) for i, v in enumerate(paid)]


def test_normalized_dividends_need_three_years_and_flag_one_offs() -> None:
    fund = Fundamentals("WEGE3", market_cap=1000.0, dividend_yield=0.05)
    assert normalized_dividends(_dividend_history(10, 12), 10.0, fund) is None
    steady = normalized_dividends(_dividend_history(40, 50, 45, 55, 50), 10.0, fund)
    assert steady is not None
    assert steady.years == 5
    assert steady.per_share == pytest.approx(50 / 100)  # median 50 over 100 shares
    assert steady.extraordinary is False
    one_off = normalized_dividends(_dividend_history(10, 12, 11), 10.0, fund)
    assert one_off is not None and one_off.extraordinary is True  # trailing 0.50 vs 0.11


def test_bazin_uses_normalized_dividends_and_marks_suspicious_inputs() -> None:
    fund = Fundamentals(
        "WEGE3",
        market_cap=1000.0,
        dividend_yield=0.05,
        earnings_per_share=1.0,
        book_value_per_share=5.0,
        price_to_earnings=10.0,
        suspicious={"dividend_yield": "fora da faixa"},
    )
    valuation = value_asset(
        ChecklistProfile.STOCK, 10.0, fund, statements=_dividend_history(40, 50, 45, 55, 50)
    )

    bazin = next(m for m in valuation.methods if m.method == "BAZIN")
    assert bazin.value == pytest.approx(0.5 / 0.06, abs=0.01)
    assert "mediana de 5 anos" in bazin.note and "dado suspeito" in bazin.note
    assert valuation.suspicious_inputs == ("dividend_yield",)
    assert valuation.extraordinary_dividends is False
    trailing = value_asset(ChecklistProfile.STOCK, 10.0, fund)
    assert next(m for m in trailing.methods if m.method == "BAZIN").note.startswith(
        "Proventos dos últimos 12 meses"
    )


def test_ceiling_alert_is_suppressed_for_suspicious_data() -> None:
    fund = Fundamentals(
        "WEGE3", dividend_yield=0.30, earnings_per_share=5.0, book_value_per_share=20.0
    )
    clean = value_asset(ChecklistProfile.STOCK, 10.0, fund)
    flagged = value_asset(
        ChecklistProfile.STOCK,
        10.0,
        check_fundamentals(
            Fundamentals(
                "WEGE3", dividend_yield=0.9, earnings_per_share=5.0, book_value_per_share=20.0
            ),
            AssetType.STOCK_BR,
        ),
    )
    assert clean.verdict == ValuationVerdict.DISCOUNTED
    assert flagged.verdict == ValuationVerdict.DISCOUNTED
    lifecycles = {"WEGE3": AssetLifecycle.HELD}
    assert len(valuation_alerts({"WEGE3": clean}, lifecycles, {"WEGE3": 1})) == 1
    assert valuation_alerts({"WEGE3": flagged}, lifecycles, {"WEGE3": 1}) == []

    quality = data_quality_alerts(
        {"WEGE3": Fundamentals("WEGE3", suspicious={"dividend_yield": "DY fora da faixa."})},
        lifecycles,
        {"WEGE3": 1},
    )
    assert [a.kind for a in quality] == [AlertKind.SUSPICIOUS_DATA]
    assert (
        data_quality_alerts(
            {"WEGE3": Fundamentals("WEGE3", suspicious={"x": "y"})},
            {"WEGE3": AssetLifecycle.WATCHLIST},
            {},
        )
        == []
    )


# --- integration ---------------------------------------------------------------------------------


def test_script_00022_backfills_first_seen(tmp_path: Path) -> None:
    db_url = f"sqlite:///{(tmp_path / 'fs.db').as_posix()}"
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "infra" / "data" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    engine = create_engine(db_url, future=True)
    try:
        command.upgrade(cfg, "script_00022")
        assert "first_seen_at" in {
            c["name"] for c in inspect(engine).get_columns("fundamental_snapshots")
        }
        command.downgrade(cfg, "script_00021")
        assert "first_seen_at" not in {
            c["name"] for c in inspect(engine).get_columns("fundamental_snapshots")
        }
    finally:
        engine.dispose()


def test_refresh_keeps_the_first_seen_date(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        uow.fundamentals.upsert([_statement(2024, revenue=1.0)])
        uow.commit()
        first = uow.fundamentals.list_for("WEGE3")[0].first_seen_at
    with api.uow_factory() as uow:
        uow.fundamentals.upsert([_statement(2024, revenue=2.0)])
        uow.commit()
        again = uow.fundamentals.list_for("WEGE3")[0]
    assert first is not None
    assert again.first_seen_at == first
    assert again.value("revenue") == 2.0


def test_new_statement_reopens_answers_and_flags_the_position(api: SimpleNamespace) -> None:
    created = api.client.post(
        "/api/v1/assets",
        json={"ticker": "WEGE3", "name": "WEG", "asset_type": "STOCK_BR", "manual_price": "40"},
    ).json()
    asset_id = created["id"]
    api.client.post(
        "/api/v1/transactions",
        json={
            "asset_id": asset_id,
            "kind": "BUY",
            "trade_date": "2026-01-05",
            "quantity": "10",
            "unit_price": "40",
        },
    )
    saved = api.client.put(
        f"/api/v1/assets/{asset_id}/checklist",
        json={"cerrado_answers": {"governance": "YES", "age_30y": "YES"}},
    )
    assert saved.status_code == 200, saved.text
    before = api.client.get(f"/api/v1/assets/{asset_id}/analysis").json()["checklist"]
    assert before["stale"] == 0

    with api.uow_factory() as uow:
        uow.fundamentals.upsert([_statement(datetime.now(UTC).year, revenue=10.0)])
        uow.commit()

    after = api.client.get(f"/api/v1/assets/{asset_id}/analysis").json()["checklist"]
    reasons = {a["question_id"]: a["stale_reason"] for a in after["answers"] if a["stale_reason"]}
    assert after["stale"] == 2
    assert reasons == {"governance": "NEW_STATEMENT", "age_30y": "NEW_STATEMENT"}
    position = api.client.get("/api/v1/portfolio").json()["positions"][0]
    assert position["lifecycle_status"] == "REVIEW"
    kinds = {a["kind"] for a in api.client.get("/api/v1/alerts").json()["alerts"]}
    assert "CHECKLIST_EXPIRED" in kinds


def test_policy_round_trips_the_validity_fields(api: SimpleNamespace) -> None:
    policy = api.client.get("/api/v1/policy").json()
    assert policy["eligibility"]["answer_validity_months"] == 12
    policy["eligibility"].update(answer_validity_months=6, drop_expired_answers=True)
    saved = api.client.put("/api/v1/policy", json=policy).json()
    assert saved["eligibility"]["answer_validity_months"] == 6
    assert saved["eligibility"]["drop_expired_answers"] is True
    assert saved["eligibility"]["review_on_expired_answers"] is True
