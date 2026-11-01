"""The Garimpo never flips a signal: a premium that hurt gets no weight (analysis P0, item 1)."""

from __future__ import annotations

from datetime import date

from domain.mining.findings import ranking_weights
from domain.mining.model import MiningModel, SignalWeight, weights_from

MONTHS = [(2015 + i // 12, i % 12 + 1) for i in range(120)]


def _table(value_slope: float, quality_slope: float) -> dict:
    return {m: {"VALUE": value_slope, "QUALITY": quality_slope} for m in MONTHS}


def test_a_firm_negative_premium_gets_no_weight() -> None:
    found = weights_from(_table(-0.01, 0.01), MONTHS, ["VALUE", "QUALITY"])
    value, quality = found["VALUE"], found["QUALITY"]
    assert value.estimate < 0 and value.sign_probability < 0.1  # the chance that it helps
    assert value.weight == 0.0
    assert quality.sign_probability > 0.9 and quality.weight > 0


def _model(*estimates: tuple[str, float]) -> MiningModel:
    return MiningModel(
        as_of=date(2026, 11, 1),
        weights={name: 0.0 for name, _ in estimates},
        signals=[SignalWeight(name, e, 0.01, 0.5, 0.0, 60) for name, e in estimates],
    )


def test_the_provisional_ranking_leaves_out_what_hurt() -> None:
    weights = ranking_weights(_model(("VALUE", -0.0035), ("QUALITY", 0.002)))
    assert weights == {"VALUE": 0.0, "QUALITY": 0.002}  # an expensive stock is not rewarded
    assert ranking_weights(_model(("VALUE", -0.003), ("QUALITY", -0.001))) == {
        "VALUE": 1.0,
        "QUALITY": 1.0,
    }
