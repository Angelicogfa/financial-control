"""Combination of the lenses into one score per asset (Phase 45.3, design N5).

Inside each ARCA class, every asset that passed the gates gets a row of the decision matrix:

- each lens enters by its value on [0, 1] pulled toward neutral (0.5) by its confidence, so a
  lens without data or with an old reading counts as neutral, never as good or bad;
- a Cerrado switched off for the asset takes the lens out and the other weights are rescaled
  (a Cerrado not analysed is 0 with full confidence: it weighs against, decision 10.2);
- the score is the weighted sum (AHP weights of the class's objective), on [0, 1];
- the expected return over the class is the score mapped to a declared scale (score 1 is
  +scale a year, 0 is -scale), with a range that widens as the confidence falls. The scale is a
  premise of the policy until the backtest (45.6) and the validated weights (45.7) calibrate it.

The Gaussian AHP ranking is computed on the same cells, as a reference only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from domain.recommendation.ahp import gaussian_weights
from domain.recommendation.gates import AssetGates
from domain.recommendation.keys import CERRADO, LENSES
from domain.recommendation.lenses import CERRADO_OFF, AssetLenses

NEUTRAL = 0.5


@dataclass(frozen=True)
class MatrixCell:
    lens: str
    value: float  # [0, 1] after the confidence pull
    weight: float  # the AHP weight used for this asset (rescaled without the Cerrado)
    contribution: float  # value x weight


@dataclass(frozen=True)
class MatrixRow:
    ticker: str
    source: str
    sector: str
    rank: int
    score: float
    expected: float  # a year over the class
    expected_low: float
    expected_high: float
    confidence: float  # weighted confidence of the lenses
    cells: list[MatrixCell]
    gaussian_score: float
    gaussian_rank: int
    flags: list[str] = field(default_factory=list)  # the Cerrado's highlights


@dataclass(frozen=True)
class ExcludedAsset:
    ticker: str
    source: str
    reasons: list[str]


@dataclass(frozen=True)
class ClassMatrix:
    arca_class: str
    objective: str
    as_of: date
    weights: dict[str, float]
    consistency_ratio: float
    scale_annual: float
    gaussian_weights: dict[str, float]
    rows: list[MatrixRow]
    excluded: list[ExcludedAsset]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["as_of"] = self.as_of.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ClassMatrix:
        payload = dict(data)
        payload["as_of"] = date.fromisoformat(payload["as_of"])
        payload["rows"] = [
            MatrixRow(**{**r, "cells": [MatrixCell(**c) for c in r["cells"]]})
            for r in payload["rows"]
        ]
        payload["excluded"] = [ExcludedAsset(**e) for e in payload["excluded"]]
        return cls(**payload)


def _cells(item: AssetLenses, weights: Mapping[str, float]) -> tuple[list[MatrixCell], float]:
    lenses = {s.lens: s for s in item.lenses}
    used = {
        lens: w
        for lens, w in weights.items()
        if not (lens == CERRADO and CERRADO_OFF in (lenses[lens].flags if lens in lenses else []))
    }
    total = sum(used.values()) or 1.0
    cells, confidence = [], 0.0
    for lens in LENSES:
        if lens not in used:
            continue
        w = used[lens] / total
        s = lenses.get(lens)
        conf = s.confidence if s is not None and s.normalized is not None else 0.0
        value = NEUTRAL + conf * (
            (s.normalized if s and s.normalized is not None else NEUTRAL) - NEUTRAL
        )
        cells.append(MatrixCell(lens, round(value, 4), round(w, 6), round(value * w, 6)))
        confidence += w * conf
    return cells, confidence


def _ranks(scores: Mapping[str, float]) -> dict[str, int]:
    order = sorted(scores, key=lambda t: (-scores[t], t))
    return {t: i for i, t in enumerate(order, start=1)}


def combine_class(
    *,
    arca_class: str,
    objective: str,
    as_of: date,
    weights: Mapping[str, float],
    consistency_ratio: float,
    scale_annual: float,
    items: Sequence[AssetLenses],
    gates: Mapping[str, AssetGates],
) -> ClassMatrix:
    """The decision matrix of one class: the eligible assets ranked, the others with the reason."""
    rows_in: list[tuple[AssetLenses, list[MatrixCell], float]] = []
    excluded = []
    for item in items:
        gate = gates.get(item.ticker)
        if gate is None:
            excluded.append(ExcludedAsset(item.ticker, item.source, ["Portões não calculados."]))
            continue
        if not gate.eligible:
            excluded.append(
                ExcludedAsset(item.ticker, item.source, [r.reason for r in gate.failed()])
            )
            continue
        cells, confidence = _cells(item, weights)
        rows_in.append((item, cells, confidence))

    scores = {item.ticker: sum(c.contribution for c in cells) for item, cells, _c in rows_in}
    columns = {
        lens: [
            next((c.value for c in cells if c.lens == lens), NEUTRAL) for _i, cells, _c in rows_in
        ]
        for lens in weights
    }
    g_weights = gaussian_weights(columns) if rows_in else dict.fromkeys(weights, 0.0)
    g_scores = {
        item.ticker: sum(g_weights.get(c.lens, 0.0) * c.value for c in cells)
        for item, cells, _c in rows_in
    }
    ranks, g_ranks = _ranks(scores), _ranks(g_scores)
    rows = []
    for item, cells, confidence in rows_in:
        score = scores[item.ticker]
        expected = (score - NEUTRAL) / NEUTRAL * scale_annual
        half = scale_annual * (1.0 - confidence)
        cerrado = item.lens(CERRADO)
        rows.append(
            MatrixRow(
                ticker=item.ticker,
                source=item.source,
                sector=item.sector,
                rank=ranks[item.ticker],
                score=round(score, 4),
                expected=round(expected, 4),
                expected_low=round(expected - half, 4),
                expected_high=round(expected + half, 4),
                confidence=round(confidence, 4),
                cells=cells,
                gaussian_score=round(g_scores[item.ticker], 4),
                gaussian_rank=g_ranks[item.ticker],
                flags=list(cerrado.flags) if cerrado is not None else [],
            )
        )
    rows.sort(key=lambda r: r.rank)
    return ClassMatrix(
        arca_class=arca_class,
        objective=objective,
        as_of=as_of,
        weights={k: round(v, 6) for k, v in weights.items()},
        consistency_ratio=consistency_ratio,
        scale_annual=scale_annual,
        gaussian_weights=g_weights,
        rows=rows,
        excluded=sorted(excluded, key=lambda e: e.ticker),
    )


@dataclass(frozen=True)
class CellDifference:
    lens: str
    a: float
    b: float
    weight: float
    difference: float  # (a - b) x weight: what this lens added to A's lead


def compare_rows(a: MatrixRow, b: MatrixRow) -> list[CellDifference]:
    """'A and not B', lens by lens, the largest gaps first."""
    cells_b = {c.lens: c for c in b.cells}
    out = []
    for c in a.cells:
        other = cells_b.get(c.lens)
        if other is None:
            continue
        out.append(
            CellDifference(
                c.lens,
                c.value,
                other.value,
                c.weight,
                round(c.contribution - other.contribution, 6),
            )
        )
    return sorted(out, key=lambda d: -abs(d.difference))
