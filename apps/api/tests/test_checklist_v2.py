"""Unit tests for the profile-based checklist with N/A, evidence and history (11.2-11.4)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from core.errors import ValidationError
from domain.assets.services.cerrado import (
    STATEMENT_PROFILES,
    AnswerSource,
    AnswerValue,
    ChecklistProfile,
    Recommendation,
    evaluate,
    evaluation_record,
    history_for_assets,
    questions_for,
)
from domain.assets.services.history import (
    FundamentalPeriod,
    FundamentalSnapshot,
    historical_metrics,
)
from domain.market.entities import Fundamentals
from domain.shared.entities import AssetEntity, ChecklistAnswer
from domain.shared.enums import AssetType, default_checklist_profile


def _history(net_incomes: list[float], dividends: list[float]) -> list[FundamentalSnapshot]:
    return [
        FundamentalSnapshot(
            "WEGE3",
            date(2020 + i, 12, 31),
            FundamentalPeriod.ANNUAL,
            {
                "revenue": 100.0 * (1.1**i),
                "net_income": ni,
                "equity": 100.0,
                "dividends_paid": -d,
            },
        )
        for i, (ni, d) in enumerate(zip(net_incomes, dividends, strict=True))
    ]


@pytest.mark.parametrize(
    ("asset_type", "profile"),
    [
        (AssetType.STOCK_BR, ChecklistProfile.STOCK),
        (AssetType.ETF_BR, ChecklistProfile.ETF),
        (AssetType.FII, ChecklistProfile.FII_BRICK),
        (AssetType.BDR, ChecklistProfile.INTL_STOCK),
        (AssetType.ETF_INTL, ChecklistProfile.ETF),
        (AssetType.CRYPTO, ChecklistProfile.CRYPTO),
        (AssetType.TREASURY, ChecklistProfile.FIXED_INCOME),
    ],
)
def test_default_profile_per_asset_type(asset_type: AssetType, profile: ChecklistProfile) -> None:
    assert default_checklist_profile(asset_type) == profile
    assert questions_for(asset_type) == questions_for(profile)


def test_every_profile_has_unique_question_ids() -> None:
    for profile in ChecklistProfile:
        ids = [q.id for q in questions_for(profile)]
        assert ids and len(ids) == len(set(ids)), profile


def test_asset_profile_override_and_answer_normalization() -> None:
    asset = AssetEntity(
        ticker="itub4",
        name="Itaú",
        asset_type=AssetType.STOCK_BR,
        checklist_profile=ChecklistProfile.BANK,
        cerrado_answers={"basel": True, "npl": "NA", "age_30y": None, "governance": "no"},
    )
    assert asset.profile == ChecklistProfile.BANK
    assert {q: a.value for q, a in asset.cerrado_answers.items()} == {
        "basel": AnswerValue.YES,
        "npl": AnswerValue.NA,
        "governance": AnswerValue.NO,
    }
    assert AssetEntity(ticker="X", name="X", asset_type=AssetType.FII).profile == (
        ChecklistProfile.FII_BRICK
    )
    with pytest.raises(ValidationError):
        ChecklistAnswer.coerce("roe", "maybe")


def test_na_is_excluded_from_score_and_coverage() -> None:
    evaluation = evaluate(
        ChecklistProfile.CRYPTO,
        {"top10": True, "age_5y": "NA", "decentralized": False, "real_adoption": True},
    )
    assert (evaluation.yes, evaluation.no, evaluation.not_applicable) == (2, 1, 1)
    assert evaluation.applicable == 4
    assert evaluation.score == 1
    assert evaluation.max_score == 4
    assert evaluation.pending == 1
    assert evaluation.normalized_score == pytest.approx(0.25)
    assert evaluation.coverage_pct == pytest.approx(75.0)
    assert evaluation.recommendation == Recommendation.APTO


def test_all_na_profile_has_no_normalized_score() -> None:
    answers = {q.id: AnswerValue.NA for q in questions_for(ChecklistProfile.FIXED_INCOME)}
    evaluation = evaluate(ChecklistProfile.FIXED_INCOME, answers)
    assert evaluation.applicable == 0
    assert evaluation.normalized_score is None
    assert evaluation.coverage_pct == 0.0
    assert evaluation.recommendation == Recommendation.INCOMPLETO


def test_history_answers_carry_evidence_and_beat_ttm() -> None:
    history = historical_metrics(_history([10, 12, -1, 14, 16], [5, 6, 0, 7, 8]))
    ttm = Fundamentals(symbol="WEGE3", return_on_equity=0.01, profit_margin=0.2)
    evaluation = evaluate(ChecklistProfile.STOCK, {}, ttm, history=history)
    by_id = {a.question_id: a for a in evaluation.answers}

    assert by_id["roe"].value == AnswerValue.YES
    assert by_id["roe"].source == AnswerSource.AUTO
    assert by_id["roe"].evidence == "ROE médio 10,2% em 5 anos (2020-2024)"
    assert by_id["profitable"].value == AnswerValue.NO
    assert by_id["profitable"].evidence == "Lucro em 4 de 5 anos"
    assert by_id["dividends"].value == AnswerValue.YES
    assert by_id["dividends"].evidence == "Proventos em 4 de 5 anos"
    assert by_id["revenue_growth"].evidence.startswith("CAGR da receita 10,0%")


def test_short_history_falls_back_to_ttm_indicators() -> None:
    history = historical_metrics(_history([10, 12], [5, 6]))
    ttm = Fundamentals(
        symbol="WEGE3",
        return_on_equity=0.04,
        net_debt_to_ebitda=2.5,
        avg_daily_volume=3_000_000.0,
    )
    by_id = {
        a.question_id: a for a in evaluate(ChecklistProfile.STOCK, {}, ttm, history=history).answers
    }
    assert by_id["roe"].value == AnswerValue.NO
    assert by_id["roe"].evidence == "ROE TTM 4,0% <= 5,0%"
    assert by_id["debt"].evidence == "Dív. Líq./EBITDA 2,50"
    assert by_id["liquidity"].evidence == "Volume financeiro médio 3,0 mi > 2,0 mi"


def test_manual_answer_overrides_auto_with_its_evidence() -> None:
    answered_at = datetime(2026, 1, 2, tzinfo=UTC)
    manual = ChecklistAnswer(
        "pvp", AnswerValue.NA, evidence="Fundo em liquidação", answered_at=answered_at
    )
    evaluation = evaluate(
        ChecklistProfile.FII_PAPER,
        {"pvp": manual},
        Fundamentals(symbol="KNCR11", price_to_book=0.98, dividend_yield=0.12),
    )
    by_id = {a.question_id: a for a in evaluation.answers}
    assert by_id["pvp"].value == AnswerValue.NA
    assert by_id["pvp"].source == AnswerSource.MANUAL
    assert by_id["pvp"].evidence == "Fundo em liquidação"
    assert by_id["pvp"].answered_at == answered_at
    assert by_id["dy"].value == AnswerValue.YES
    assert by_id["dy"].evidence == "Dividend yield 12m 12,0% > 9,0%"


def test_evaluation_record_and_history_for_assets() -> None:
    evaluation = evaluate(ChecklistProfile.CRYPTO, {"top10": True})
    at = datetime(2026, 3, 1, tzinfo=UTC)
    record = evaluation_record(7, evaluation, at)
    assert (record.asset_id, record.evaluated_at, record.score) == (7, at, 1)
    assert record.coverage_pct == pytest.approx(20.0)
    assert record.recommendation == "APTO"
    assert record.same_result(evaluation_record(7, evaluation, datetime.now(UTC)))
    other = evaluation_record(7, evaluate(ChecklistProfile.CRYPTO, {"top10": False}), at)
    assert not record.same_result(other)

    stock = AssetEntity(ticker="WEGE3", name="WEG", asset_type=AssetType.STOCK_BR)
    fii = AssetEntity(ticker="HGLG11", name="CSHG", asset_type=AssetType.FII)
    snapshots = {"WEGE3": _history([1, 2, 3], [0, 0, 1]), "HGLG11": _history([1], [1])}
    histories = history_for_assets([stock, fii], snapshots)
    assert set(histories) == {"WEGE3"}
    assert histories["WEGE3"].years == 3
    assert ChecklistProfile.FII_BRICK not in STATEMENT_PROFILES
