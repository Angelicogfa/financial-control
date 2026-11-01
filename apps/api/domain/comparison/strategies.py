"""Strategies of the live scoreboard (decision 10.1.5): each one says, on a day, what to hold.

A strategy answers with the weights inside each ARCA class, using only what was known that
day. The split between classes is the policy's (the ARCA targets), except for the references
outside the ARCA (the CDI). A class the strategy leaves empty is held in the CDI.

When each one decides (decision 10.1.11): the recommendation by its latest weekly run; the
others by a quarterly review, so the same quarter always gets the same answer.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from domain.shared.enums import ArcaClass, AssetType
from domain.simulation.data import CDI_KEY, IBOV_KEY, IFIX_KEY, SP500_BRL_KEY
from domain.simulation.market import PointInTimeView

Holdings = dict[ArcaClass, dict[str, float]]  # class -> symbol -> weight inside the class

RECOMMENDATION = "RECOMMENDATION"
OPTIMIZED = "OPTIMIZED"
CERRADO_RULE = "CERRADO_RULE"
EQUAL = "EQUAL"
INDEX_ARCA = "INDEX_ARCA"
RANDOM = "RANDOM"
CDI = "CDI"
YOURS = "YOURS"

LABELS = {
    YOURS: "Sua carteira",
    RECOMMENDATION: "Recomendação",
    OPTIMIZED: "Otimizador",
    CERRADO_RULE: "Regra antiga (Cerrado)",
    EQUAL: "Pesos iguais",
    INDEX_ARCA: "Índices por classe",
    RANDOM: "Aleatórias",
    CDI: "CDI",
}
RANDOM_PORTFOLIOS = 200  # decision 10.1.6
RANDOM_PER_CLASS = 5
RANDOM_SEED = 4581

# The class index of each ARCA class (BOVA11, XFIX11, IVVB11 and Tesouro Selic, by their index).
CLASS_INDEX = {
    ArcaClass.ACOES: IBOV_KEY,
    ArcaClass.REAL_ESTATE: IFIX_KEY,
    ArcaClass.ATIVOS_INTERNACIONAIS: SP500_BRL_KEY,
    ArcaClass.CAIXA: CDI_KEY,
}


@dataclass(frozen=True)
class Candidate:
    """An asset a strategy may buy: its series symbol, class and lot rule."""

    symbol: str
    arca_class: ArcaClass
    asset_type: AssetType


class Strategy(Protocol):
    key: str
    label: str

    def class_targets(self, policy_targets: Mapping[ArcaClass, float]) -> dict[ArcaClass, float]:
        """Share of the money in each class (fractions adding to 1)."""
        ...

    def decide(self, day: date, view: PointInTimeView) -> Holdings | None:
        """What to hold on `day`; None while the strategy has nothing to say yet."""
        ...


def quarter_start(day: date) -> date:
    return date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)


def listed(view: PointInTimeView, symbol: str, on: date) -> bool:
    """Whether the series of `symbol` had started by `on` (never later than the view)."""
    series = view.history.series.get(symbol)
    first = series.first_date if series else None
    return first is not None and first <= min(on, view.as_of)


def _arca(policy_targets: Mapping[ArcaClass, float]) -> dict[ArcaClass, float]:
    total = sum(v for v in policy_targets.values() if v > 0)
    return {c: v / total for c, v in policy_targets.items() if v > 0} if total else {}


def _by_class(universe: Sequence[Candidate]) -> dict[ArcaClass, list[Candidate]]:
    out: dict[ArcaClass, list[Candidate]] = {}
    for c in universe:
        out.setdefault(c.arca_class, []).append(c)
    return out


@dataclass(frozen=True)
class EqualWeights:
    """Equal weights over the assets of each class that had prices at the quarter's start."""

    universe: Sequence[Candidate]
    key: str = EQUAL
    label: str = LABELS[EQUAL]

    def class_targets(self, policy_targets: Mapping[ArcaClass, float]) -> dict[ArcaClass, float]:
        return _arca(policy_targets)

    def decide(self, day: date, view: PointInTimeView) -> Holdings | None:
        start = quarter_start(day)
        out: Holdings = {}
        for arca_class, members in _by_class(self.universe).items():
            live = [m.symbol for m in members if listed(view, m.symbol, start)]
            if live:
                out[arca_class] = dict.fromkeys(live, 1.0 / len(live))
        return out


@dataclass(frozen=True)
class RandomPicks:
    """Random assets of each class (fixed seed), equal weights, drawn again every quarter."""

    universe: Sequence[Candidate]
    index: int
    per_class: int = RANDOM_PER_CLASS
    seed: int = RANDOM_SEED
    key: str = RANDOM
    label: str = LABELS[RANDOM]

    def class_targets(self, policy_targets: Mapping[ArcaClass, float]) -> dict[ArcaClass, float]:
        return _arca(policy_targets)

    def decide(self, day: date, view: PointInTimeView) -> Holdings | None:
        start = quarter_start(day)
        rng = random.Random(f"{self.seed}:{self.index}:{start.isoformat()}")
        out: Holdings = {}
        for arca_class in sorted(_by_class(self.universe)):
            members = _by_class(self.universe)[arca_class]
            live = sorted(m.symbol for m in members if listed(view, m.symbol, start))
            if not live:
                continue
            picked = rng.sample(live, min(self.per_class, len(live)))
            out[arca_class] = dict.fromkeys(picked, 1.0 / len(picked))
        return out


@dataclass(frozen=True)
class IndexArca:
    """Each class in its index, in the ARCA proportions: the passive portfolio of the policy."""

    key: str = INDEX_ARCA
    label: str = LABELS[INDEX_ARCA]

    def class_targets(self, policy_targets: Mapping[ArcaClass, float]) -> dict[ArcaClass, float]:
        return _arca(policy_targets)

    def decide(self, day: date, view: PointInTimeView) -> Holdings | None:
        return {
            c: {symbol: 1.0}
            for c, symbol in CLASS_INDEX.items()
            if listed(view, symbol, quarter_start(day))
        }


@dataclass(frozen=True)
class AllCdi:
    """Everything in the CDI, outside the ARCA: the classic reference."""

    key: str = CDI
    label: str = LABELS[CDI]

    def class_targets(self, policy_targets: Mapping[ArcaClass, float]) -> dict[ArcaClass, float]:
        return {ArcaClass.CAIXA: 1.0}

    def decide(self, day: date, view: PointInTimeView) -> Holdings | None:
        return {ArcaClass.CAIXA: {CDI_KEY: 1.0}}


@dataclass(frozen=True)
class CerradoRule:
    """The old rule of the contribution: registered assets weighted by their Cerrado score.

    `scores(day)` gives the score of each registered asset with the answers in force that day;
    the review is quarterly, like the other references.
    """

    universe: Sequence[Candidate]
    scores: Callable[[date], Mapping[str, float]]
    key: str = CERRADO_RULE
    label: str = LABELS[CERRADO_RULE]

    def class_targets(self, policy_targets: Mapping[ArcaClass, float]) -> dict[ArcaClass, float]:
        return _arca(policy_targets)

    def decide(self, day: date, view: PointInTimeView) -> Holdings | None:
        start = quarter_start(day)
        scores = self.scores(start)
        out: Holdings = {}
        for arca_class, members in _by_class(self.universe).items():
            scored = {
                m.symbol: float(scores[m.symbol])
                for m in members
                if scores.get(m.symbol, 0.0) > 0 and listed(view, m.symbol, start)
            }
            total = sum(scored.values())
            if total > 0:
                out[arca_class] = {s: v / total for s, v in scored.items()}
        return out


@dataclass(frozen=True)
class RecommendationRuns:
    """The recommendation: the targets of the latest weekly run on or before the day.

    Before the first stored run it has nothing to say: it starts with the first run.
    """

    runs: Sequence[tuple[date, Holdings]]
    key: str = RECOMMENDATION
    label: str = LABELS[RECOMMENDATION]
    _sorted: tuple[tuple[date, Holdings], ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_sorted", tuple(sorted(self.runs, key=lambda r: r[0])))

    @property
    def first_day(self) -> date | None:
        return self._sorted[0][0] if self._sorted else None

    def class_targets(self, policy_targets: Mapping[ArcaClass, float]) -> dict[ArcaClass, float]:
        return _arca(policy_targets)

    def decide(self, day: date, view: PointInTimeView) -> Holdings | None:
        chosen: Holdings | None = None
        for run_day, holdings in self._sorted:
            if run_day > day:
                break
            chosen = holdings
        return chosen
