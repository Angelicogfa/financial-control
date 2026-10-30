"""Findings of a run and the record of the past ones (Phases 43.4 and 43.5).

A finding is one of the `FINDINGS` best scores of the last month with signals. When the gate of
the model passed, it is a finding; otherwise the same list is kept as a ranking under
observation, so the record can say later whether the gate was right to hold it back.

The record measures, for every past run, how the listed companies did against the whole
universe in the 3, 6 and 12 months after the month of their signals: the share that beat the
universe (with its credible interval) and the average difference, separately for findings and
for rankings under observation.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

import numpy as np

from domain.forecast.valuation_model import MIN_COMPANIES, Month, add_months, month_end, month_of
from domain.mining.model import FINDINGS, MiningModel, ranking
from domain.mining.repositories import MiningFinding
from domain.mining.signals import IMPROVEMENT, MOMENTUM, QUALITY, VALUE
from domain.simulation.bayes import credible_interval

RECORD_HORIZONS = (3, 6, 12)

_PHRASES = {
    VALUE: ("barata frente ao próprio histórico e ao setor", "cara frente ao histórico e ao setor"),
    QUALITY: ("qualidade alta (retorno, margem, dívida)", "qualidade baixa"),
    IMPROVEMENT: ("resultados melhorando", "resultados piorando"),
    MOMENTUM: ("preço forte frente à classe em 12 meses", "preço fraco frente à classe"),
}


def last_month(panel: Mapping[str, Mapping[Month, Mapping[str, float]]]) -> Month | None:
    """The latest month with signals for enough companies."""
    counts: dict[Month, int] = defaultdict(int)
    for by_month in panel.values():
        for month, values in by_month.items():
            if len(values) >= 2:
                counts[month] += 1
    months = [m for m, n in counts.items() if n >= MIN_COMPANIES]
    return max(months) if months else None


def reason(values: Mapping[str, float], weights: Mapping[str, float]) -> str:
    """The two signals that pushed the score the most, in words, with their z."""
    contributions = sorted(
        ((name, weights.get(name, 0.0) * z, z) for name, z in values.items()),
        key=lambda c: -c[1],
    )
    parts = []
    for name, contribution, z in contributions[:2]:
        if contribution <= 0:
            continue
        good, bad = _PHRASES.get(name, (name, name))
        parts.append(f"{good if z > 0 else bad} (z {z:+.1f})".replace(".", ","))
    return "; ".join(parts).capitalize() if parts else "Sem sinal que se destaque."


def ranking_weights(model: MiningModel) -> dict[str, float]:
    """The weights used to rank: the gated ones, or the estimates while every one is zero."""
    if any(model.weights.values()):
        return dict(model.weights)
    return {s.signal: s.estimate for s in model.signals}


def run_findings(
    panel: Mapping[str, Mapping[Month, Mapping[str, float]]],
    model: MiningModel,
    found_on: date,
) -> list[MiningFinding]:
    month = last_month(panel)
    if month is None:
        return []
    weights = ranking_weights(model)
    out = []
    for rank, (ticker, value) in enumerate(ranking(panel, month, weights)[:FINDINGS], start=1):
        values = dict(panel[ticker][month])
        out.append(
            MiningFinding(
                found_on=found_on,
                month=month_end(month),
                rank=rank,
                ticker=ticker,
                score=round(value, 6),
                trusted=model.passed,
                signals={k: round(v, 3) for k, v in values.items()},
                reason=reason(values, weights),
            )
        )
    return out


@dataclass(frozen=True)
class RecordLine:
    horizon: int  # months after the signals
    trusted: bool
    runs: int
    findings: int
    beat: int  # findings that beat the universe
    beat_low: float
    beat_high: float
    mean_excess: float  # monthly, over the universe

    @property
    def beat_share(self) -> float:
        return self.beat / self.findings if self.findings else 0.0


def _window(alphas: Mapping[Month, float], month: Month, horizon: int) -> float | None:
    values = [alphas.get(add_months(month, k)) for k in range(1, horizon + 1)]
    if any(v is None for v in values):
        return None
    return float(np.mean(values))  # type: ignore[arg-type]


def record(
    findings: Sequence[MiningFinding], alphas: Mapping[str, Mapping[Month, float]]
) -> list[RecordLine]:
    """How past findings did against the universe, by horizon and by trusted or not."""
    by_run: dict[tuple[date, bool], list[MiningFinding]] = defaultdict(list)
    for f in findings:
        by_run[(f.found_on, f.trusted)].append(f)
    lines = []
    for horizon in RECORD_HORIZONS:
        for trusted in (True, False):
            runs = beat = total = 0
            excesses: list[float] = []
            for (_day, flag), items in by_run.items():
                if flag != trusted:
                    continue
                month = month_of(items[0].month)
                universe = [
                    v for a in alphas.values() if (v := _window(a, month, horizon)) is not None
                ]
                if len(universe) < MIN_COMPANIES:
                    continue
                centre = float(np.mean(universe))
                realised = [
                    v - centre
                    for f in items
                    if (v := _window(alphas.get(f.ticker, {}), month, horizon)) is not None
                ]
                if not realised:
                    continue
                runs += 1
                total += len(realised)
                beat += sum(1 for v in realised if v > 0)
                excesses.extend(realised)
            if total == 0:
                continue
            low, high = credible_interval(beat, total)
            lines.append(
                RecordLine(
                    horizon=horizon,
                    trusted=trusted,
                    runs=runs,
                    findings=total,
                    beat=beat,
                    beat_low=low,
                    beat_high=high,
                    mean_excess=round(float(np.mean(excesses)), 6),
                )
            )
    return lines


def record_to_dicts(lines: Sequence[RecordLine]) -> list[dict[str, Any]]:
    return [asdict(line) for line in lines]
