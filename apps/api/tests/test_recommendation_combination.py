"""Phase 45.3: AHP weights, the decision matrix and the premises in the policy."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from core.errors import ValidationError
from domain.policy.services.policy import InvestmentPolicy, RecommendationPolicy
from domain.recommendation.ahp import (
    DEFAULT_MATRICES,
    check_consistency,
    gaussian_weights,
    priority,
    validate,
)
from domain.recommendation.combination import ClassMatrix, combine_class, compare_rows
from domain.recommendation.gates import FAIL, PASS, AssetGates, GateResult
from domain.recommendation.keys import (
    CERRADO,
    DIVIDENDS,
    GROWTH,
    INCOME,
    LENSES,
    MIXED,
    QUALITY,
    VALUATION,
)
from domain.recommendation.lenses import CERRADO_OFF, NOT_ANALYZED, AssetLenses, LensScore
from domain.shared.enums import ArcaClass

TODAY = date(2026, 10, 31)


# --- AHP ---------------------------------------------------------------------------------------


def test_pre_configured_matrices_give_the_design_weights() -> None:
    expected = {
        GROWTH: {CERRADO: 0.160, QUALITY: 0.181, INCOME: 0.029},
        DIVIDENDS: {CERRADO: 0.138, QUALITY: 0.157, INCOME: 0.272},
        MIXED: {CERRADO: 0.134, QUALITY: 0.236, VALUATION: 0.177, INCOME: 0.134},
    }
    for objective, weights in expected.items():
        found = priority(DEFAULT_MATRICES[objective])
        assert sum(found.weights.values()) == pytest.approx(1.0, abs=1e-5)
        assert found.consistency_ratio <= 0.011
        for lens, w in weights.items():
            assert found.weights[lens] == pytest.approx(w, abs=0.001)


def test_validate_refuses_bad_matrices() -> None:
    good = [list(row) for row in DEFAULT_MATRICES[MIXED]]
    assert validate(good) == DEFAULT_MATRICES[MIXED]
    with pytest.raises(ValidationError, match="8x8"):
        validate(good[:7])
    not_reciprocal = [list(row) for row in good]
    not_reciprocal[0][1] = 3.0  # its inverse stays 2
    with pytest.raises(ValidationError, match="reciprocal"):
        validate(not_reciprocal)
    off_scale = [list(row) for row in good]
    off_scale[0][1], off_scale[1][0] = 12.0, 1 / 12
    with pytest.raises(ValidationError, match="Saaty"):
        validate(off_scale)


def test_inconsistent_judgements_are_refused_with_the_pairs() -> None:
    # Cerrado > Quality > Valuation, but Valuation > Cerrado: a cycle.
    labels = ("A", "B", "C")
    cycle = [[1, 5, 1 / 5], [1 / 5, 1, 5], [5, 1 / 5, 1]]
    assert priority(cycle, labels=labels).consistency_ratio > 0.10
    with pytest.raises(ValidationError, match="inconsistent"):
        check_consistency(cycle, labels=labels)


def test_gaussian_ahp_rewards_the_lens_that_separates_the_assets() -> None:
    weights = gaussian_weights({"flat": [0.5, 0.5, 0.5], "spread": [0.2, 0.5, 0.8]})
    assert weights == {"flat": 0.0, "spread": 1.0}
    assert gaussian_weights({"x": [0.5]}) == {"x": 0.0}


# --- combination -------------------------------------------------------------------------------


def _item(ticker: str, values: dict[str, float | None], **extra) -> AssetLenses:
    lenses = []
    for lens in LENSES:
        v = values.get(lens)
        flags = extra.get("flags", {}).get(lens, [])
        lenses.append(
            LensScore(lens, v, v, 1.0 if v is not None else 0.0, f"{lens} {ticker}", flags)
        )
    return AssetLenses(ticker, TODAY, "WATCHLIST", "ACOES", "Setor", lenses)


def _gates(*tickers: str, failed: tuple[str, ...] = ()) -> dict[str, AssetGates]:
    out = {}
    for t in tickers:
        status = FAIL if t in failed else PASS
        out[t] = AssetGates(t, [GateResult("LIQUIDITY", status, f"liquidez de {t}")])
    return out


def _combine(items, gates) -> ClassMatrix:
    found = priority(DEFAULT_MATRICES[MIXED])
    return combine_class(
        arca_class="ACOES",
        objective=MIXED,
        as_of=TODAY,
        weights=found.weights,
        consistency_ratio=found.consistency_ratio,
        scale_annual=0.06,
        items=items,
        gates=gates,
    )


def test_the_matrix_ranks_the_eligible_and_explains_the_rest() -> None:
    strong = _item("AAAA3", dict.fromkeys(LENSES, 0.8))
    weak = _item("BBBB3", dict.fromkeys(LENSES, 0.3))
    illiquid = _item("CCCC3", dict.fromkeys(LENSES, 1.0))
    matrix = _combine(
        [weak, strong, illiquid], _gates("AAAA3", "BBBB3", "CCCC3", failed=("CCCC3",))
    )

    assert [r.ticker for r in matrix.rows] == ["AAAA3", "BBBB3"]
    top = matrix.rows[0]
    assert top.rank == 1 and top.score == pytest.approx(0.8)
    assert top.expected == pytest.approx((0.8 - 0.5) / 0.5 * 0.06)
    assert top.expected_low == pytest.approx(top.expected)  # full confidence: no range
    assert sum(c.weight for c in top.cells) == pytest.approx(1.0)
    assert [(e.ticker, e.reasons) for e in matrix.excluded] == [("CCCC3", ["liquidez de CCCC3"])]
    assert ClassMatrix.from_dict(matrix.to_dict()) == matrix


def test_missing_data_is_neutral_and_widens_the_range() -> None:
    blind = _item("AAAA3", {CERRADO: 0.0})  # only the Cerrado (not analysed), nothing else
    matrix = _combine([blind], _gates("AAAA3"))
    [row] = matrix.rows
    cells = {c.lens: c for c in row.cells}
    assert cells[CERRADO].value == 0.0 and cells[QUALITY].value == 0.5
    assert row.expected_high - row.expected_low > 0.1


def test_cerrado_switched_off_leaves_the_score_and_not_analysed_weighs_against() -> None:
    values = dict.fromkeys(LENSES, 0.7)
    off = _item("OFFF3", {**values, CERRADO: None}, flags={CERRADO: [CERRADO_OFF]})
    unanalysed = _item("ZERO3", {**values, CERRADO: 0.0}, flags={CERRADO: [NOT_ANALYZED]})
    matrix = _combine([off, unanalysed], _gates("OFFF3", "ZERO3"))
    rows = {r.ticker: r for r in matrix.rows}
    assert CERRADO not in {c.lens for c in rows["OFFF3"].cells}
    assert rows["OFFF3"].score == pytest.approx(0.7)
    assert rows["ZERO3"].score < rows["OFFF3"].score
    assert rows["ZERO3"].flags == [NOT_ANALYZED]


def test_a_and_not_b_lens_by_lens() -> None:
    a = _item("AAAA3", {**dict.fromkeys(LENSES, 0.5), QUALITY: 0.9})
    b = _item("BBBB3", {**dict.fromkeys(LENSES, 0.5), INCOME: 0.8})
    matrix = _combine([a, b], _gates("AAAA3", "BBBB3"))
    rows = {r.ticker: r for r in matrix.rows}
    diffs = compare_rows(rows["AAAA3"], rows["BBBB3"])
    assert diffs[0].lens == QUALITY and diffs[0].difference > 0
    assert diffs[1].lens == INCOME and diffs[1].difference < 0


# --- the premises in the policy ----------------------------------------------------------------


def test_policy_defaults_and_validation() -> None:
    premises = InvestmentPolicy().recommendation
    assert premises.objectives[ArcaClass.ACOES] == MIXED
    assert premises.objectives[ArcaClass.REAL_ESTATE] == DIVIDENDS
    with pytest.raises(ValidationError):
        RecommendationPolicy(objectives={ArcaClass.ACOES: "SPECULATION"})
    with pytest.raises(ValidationError):
        RecommendationPolicy(matrices={MIXED: DEFAULT_MATRICES[MIXED]})  # one per objective
    with pytest.raises(ValidationError):
        RecommendationPolicy(score_scale_annual=0.9)


def test_policy_api_keeps_the_premises_unless_sent(api: SimpleNamespace) -> None:
    current = api.client.get("/api/v1/policy").json()
    assert current["recommendation"]["objectives"]["ACOES"] == "MIXED"
    assert len(current["recommendation"]["matrices"]["MIXED"]) == 8

    changed = {
        **current["recommendation"],
        "objectives": {**current["recommendation"]["objectives"], "ACOES": "GROWTH"},
        "score_scale_annual": 0.04,
    }
    saved = api.client.put("/api/v1/policy", json={**current, "recommendation": changed}).json()
    assert saved["recommendation"]["objectives"]["ACOES"] == "GROWTH"

    # The policy screen sends no recommendation: the new version keeps it.
    plain = {k: v for k, v in saved.items() if k != "recommendation"}
    again = api.client.put("/api/v1/policy", json=plain).json()
    assert again["version"] == saved["version"] + 1
    assert again["recommendation"]["objectives"]["ACOES"] == "GROWTH"
    assert again["recommendation"]["score_scale_annual"] == 0.04

    broken = [list(row) for row in DEFAULT_MATRICES[MIXED]]
    broken[1][4], broken[4][1] = 1 / 9, 9.0  # momentum far above quality: contradicts the rest
    bad = {**changed, "matrices": {**changed["matrices"], "MIXED": broken}}
    response = api.client.put("/api/v1/policy", json={**current, "recommendation": bad})
    assert response.status_code == 400 and response.json()["code"] == "INCONSISTENT_AHP_MATRIX"
