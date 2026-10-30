"""Event study of the CVM disclosures (Phase 42.4): what usually happens to the price after each
kind of event.

For every event (a classified document of a company with prices), the market model is estimated
on trading days -250 to -21 before it (the asset's daily total return on the Ibovespa's, at least
120 days). The abnormal return is what the model did not expect; summed from the first trading
day on or after the delivery (day 0) it gives the cumulative abnormal return (CAR) over 1, 5 and
20 days. The volatility ratio compares the spread of the abnormal returns in the 20 days after
with the spread in the estimation window.

Care taken:
- several documents of a company on the same day are one event; when their classes differ the
  event is MIXED;
- an event within a few days of a DFP/ITR delivery is confounded with the results and kept out
  of the class effects (it is still measured and shown);
- the effect of a class is the mean CAR shrunk to zero, empirical Bayes across the classes: most
  kinds of events have no systematic effect, and a class with few events barely moves.

Layer C of the forecast (Phase 42.5) uses a class only if its 20-day effect passed out of sample:
each year the study is redone with the earlier years and predicts the CAR of that year's events;
the class enters if it beat "no effect" in total and in most years and if the sign of its effect
is clear after discounting the number of classes tested (Bonferroni). A recent event of a class
that passed adds what is still to come of the effect to the first month of the forecast, and
its volatility ratio to the spread of that month.
"""

from __future__ import annotations

import bisect
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import date, timedelta
from typing import Any

import numpy as np

from domain.disclosures.entities import EventEffect

HORIZONS = (1, 5, 20)
ESTIMATION_START = 250  # trading days before the event
ESTIMATION_END = 21
MIN_ESTIMATION_DAYS = 120
CONFOUND_BEFORE_DAYS = 3  # calendar days around a DFP/ITR delivery
CONFOUND_AFTER_DAYS = 5
MIN_CLASS_EVENTS = 5
MIXED = "MIXED"
# Gate of layer C (42.5): the 20-day effect, yearly rolling origin.
GATE_HORIZON = 20
MIN_TRAIN_YEARS = 3
MIN_GATE_ORIGINS = 5
MIN_GATE_WIN_SHARE = 0.55
GATE_SIGN_ALPHA = 0.10  # split over the classes tested
VOLATILITY_RATIO_BOUNDS = (0.5, 3.0)

Series = Sequence[tuple[date, float]]


def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@dataclass(frozen=True)
class AlignedReturns:
    """Daily returns of an asset and of the market on the days both traded."""

    dates: list[date]
    asset: np.ndarray
    market: np.ndarray


def align(asset: Series, market: Series) -> AlignedReturns:
    market_by_day = dict(market)
    days = [d for d, _ in asset if d in market_by_day]
    asset_by_day = dict(asset)
    levels_a = np.array([asset_by_day[d] for d in days], dtype=float)
    levels_m = np.array([market_by_day[d] for d in days], dtype=float)
    if len(days) < 2:
        return AlignedReturns([], np.array([]), np.array([]))
    return AlignedReturns(
        days[1:], levels_a[1:] / levels_a[:-1] - 1.0, levels_m[1:] / levels_m[:-1] - 1.0
    )


@dataclass(frozen=True)
class EventInput:
    document_ids: tuple[int, ...]
    ticker: str
    delivery: date
    event_class: str


def group_events(rows: Sequence[tuple[int, str, date, str]]) -> list[EventInput]:
    """(document id, ticker, delivery date, class) rows: one event per company and day."""
    by_day: dict[tuple[str, date], list[tuple[int, str]]] = defaultdict(list)
    for doc_id, ticker, day, cls in rows:
        by_day[(ticker, day)].append((doc_id, cls))
    out = []
    for (ticker, day), items in sorted(by_day.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        classes = {c for _, c in items}
        out.append(
            EventInput(
                tuple(i for i, _ in items),
                ticker,
                day,
                classes.pop() if len(classes) == 1 else MIXED,
            )
        )
    return out


def measure(
    event: EventInput, returns: AlignedReturns, results_days: Sequence[date] = ()
) -> list[EventEffect]:
    """The reaction to one event (one row per document of the event); empty without data."""
    t0 = bisect.bisect_left(returns.dates, event.delivery)
    if t0 >= len(returns.dates) or t0 - ESTIMATION_START < 0:
        return []
    window = slice(t0 - ESTIMATION_START, t0 - ESTIMATION_END)
    ra, rm = returns.asset[window], returns.market[window]
    ok = np.isfinite(ra) & np.isfinite(rm)
    if ok.sum() < MIN_ESTIMATION_DAYS:
        return []
    beta, alpha = np.polyfit(rm[ok], ra[ok], 1)
    resid = ra[ok] - (alpha + beta * rm[ok])
    sd_before = float(np.std(resid, ddof=2))
    after = returns.asset[t0 : t0 + max(HORIZONS)] - (
        alpha + beta * returns.market[t0 : t0 + max(HORIZONS)]
    )
    cars = {h: float(after[:h].sum()) if len(after) >= h else None for h in HORIZONS}
    ratio = (
        float(np.std(after, ddof=1)) / sd_before
        if len(after) == max(HORIZONS) and sd_before > 0
        else None
    )
    confounded = any(
        event.delivery - timedelta(days=CONFOUND_BEFORE_DAYS)
        <= day
        <= event.delivery + timedelta(days=CONFOUND_AFTER_DAYS)
        for day in results_days
    )
    return [
        EventEffect(
            document_id=doc_id,
            ticker=event.ticker,
            event_date=returns.dates[t0],
            event_class=event.event_class,
            car_1=cars[1],
            car_5=cars[5],
            car_20=cars[20],
            volatility_ratio=ratio,
            confounded=confounded,
        )
        for doc_id in event.document_ids
    ]


# --- class effects ----------------------------------------------------------------------------


@dataclass(frozen=True)
class HorizonEffect:
    horizon: int
    events: int
    mean: float  # raw mean CAR
    se: float
    effect: float  # shrunk to zero (empirical Bayes across the classes)
    effect_sd: float
    sign_probability: float


@dataclass(frozen=True)
class ClassEffect:
    event_class: str
    events: int
    horizons: list[HorizonEffect]
    volatility_ratio: float | None  # median after / before


@dataclass(frozen=True)
class ClassGate:
    """Out-of-sample check of a class's 20-day effect (Phase 42.5)."""

    event_class: str
    origins: int  # years predicted with the earlier ones
    test_events: int
    mse_model: float
    mse_zero: float
    improvement: float  # 1 - mse_model / mse_zero
    win_share: float  # share of the years (where the prediction was not zero) it did better
    sign_probability: float
    passed: bool
    reason: str


@dataclass(frozen=True)
class EventStudy:
    as_of: date
    events: int  # measured, one per company and day
    confounded: int
    classes: list[ClassEffect] = field(default_factory=list)
    tau: dict[str, float] = field(default_factory=dict)  # spread of the true class effects
    gates: list[ClassGate] = field(default_factory=list)
    sign_threshold: float | None = None  # sign confidence a class needs, after Bonferroni

    def effect(self, event_class: str, horizon: int) -> HorizonEffect | None:
        found = self.class_effect(event_class)
        return next((h for h in found.horizons if h.horizon == horizon), None) if found else None

    def class_effect(self, event_class: str) -> ClassEffect | None:
        return next((c for c in self.classes if c.event_class == event_class), None)

    def gate(self, event_class: str) -> ClassGate | None:
        return next((g for g in self.gates if g.event_class == event_class), None)

    def passed(self, event_class: str) -> bool:
        found = self.gate(event_class)
        return found is not None and found.passed

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["as_of"] = self.as_of.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EventStudy:
        payload = dict(data)
        payload["as_of"] = date.fromisoformat(payload["as_of"])
        payload["classes"] = [
            ClassEffect(
                event_class=c["event_class"],
                events=c["events"],
                horizons=[HorizonEffect(**h) for h in c["horizons"]],
                volatility_ratio=c.get("volatility_ratio"),
            )
            for c in payload.get("classes", [])
        ]
        payload["gates"] = [ClassGate(**g) for g in payload.get("gates", [])]
        return cls(**payload)


def _one_per_event(effects: Sequence[EventEffect]) -> list[EventEffect]:
    events: dict[tuple[str, date], EventEffect] = {}
    for e in effects:
        events.setdefault((e.ticker, e.event_date), e)  # one per event, not per document
    return list(events.values())


def study(effects: Sequence[EventEffect], *, as_of: date) -> EventStudy:
    """Class effects of the unconfounded events, shrunk to zero across the classes."""
    measured = _one_per_event(effects)
    clean = [e for e in measured if not e.confounded and e.event_class != MIXED]
    by_class: dict[str, list[EventEffect]] = defaultdict(list)
    for e in clean:
        by_class[e.event_class].append(e)

    raw: dict[str, dict[int, tuple[int, float, float]]] = defaultdict(dict)
    taus: dict[str, float] = {}
    for h in HORIZONS:
        stats = []
        for cls, items in by_class.items():
            values = np.array([v for e in items if (v := getattr(e, f"car_{h}")) is not None])
            if values.size < MIN_CLASS_EVENTS:
                continue
            se = float(np.std(values, ddof=1) / math.sqrt(values.size))
            raw[cls][h] = (int(values.size), float(values.mean()), max(se, 1e-9))
            stats.append((float(values.mean()), se))
        if len(stats) >= 3:
            means = np.array([m for m, _ in stats])
            noise = float(np.mean([s * s for _, s in stats]))
            taus[str(h)] = math.sqrt(max(float(np.var(means, ddof=1)) - noise, 0.0))
        else:
            taus[str(h)] = 0.0

    classes = []
    for cls, by_h in sorted(raw.items()):
        horizons = []
        for h, (n, mean, se) in sorted(by_h.items()):
            tau = taus[str(h)]
            weight = tau * tau / (tau * tau + se * se) if tau > 0 else 0.0
            effect = weight * mean
            effect_sd = math.sqrt(weight) * se if tau > 0 else 0.0
            sign = _phi(abs(effect) / effect_sd) if effect_sd > 0 else 0.5
            horizons.append(
                HorizonEffect(
                    h,
                    n,
                    round(mean, 6),
                    round(se, 6),
                    round(effect, 6),
                    round(effect_sd, 6),
                    round(sign, 4),
                )
            )
        ratios = [e.volatility_ratio for e in by_class[cls] if e.volatility_ratio is not None]
        classes.append(
            ClassEffect(
                event_class=cls,
                events=len(by_class[cls]),
                horizons=horizons,
                volatility_ratio=round(float(np.median(ratios)), 4) if ratios else None,
            )
        )
    return EventStudy(
        as_of=as_of,
        events=len(measured),
        confounded=sum(1 for e in measured if e.confounded),
        classes=classes,
        tau={k: round(v, 6) for k, v in taus.items()},
    )


# --- layer C: the gate and the recent events (42.5) --------------------------------------------


def _gate_verdict(
    origins: int, improvement: float, win_share: float, sign: float, threshold: float, tested: int
) -> tuple[bool, str]:
    if origins < MIN_GATE_ORIGINS:
        return False, f"Só {origins} anos fora da amostra; são precisos {MIN_GATE_ORIGINS}."
    if improvement <= 0:
        return False, "Fora da amostra, o efeito não previu melhor do que zero."
    if win_share < MIN_GATE_WIN_SHARE:
        return False, f"Melhorou a previsão em só {win_share:.0%} dos anos."
    if sign < threshold:
        return False, (
            f"O sentido do efeito tem {sign:.1%} de confiança; com {tested} tipos testados, "
            f"são precisos {threshold:.1%}."
        )
    return True, (
        f"Passou fora da amostra: erro {improvement:.1%} menor que prever zero, melhor em "
        f"{win_share:.0%} dos anos."
    )


def gate(effects: Sequence[EventEffect], found: EventStudy) -> EventStudy:
    """The study with each class's out-of-sample gate on the 20-day effect (yearly origins)."""
    clean = [
        e
        for e in _one_per_event(effects)
        if not e.confounded and e.event_class != MIXED and e.car_20 is not None
    ]
    # class -> year -> [squared error of the model, of zero, events]
    stats: dict[str, dict[int, list[float]]] = defaultdict(dict)
    for year in sorted({e.event_date.year for e in clean}):
        train = [e for e in clean if e.event_date.year < year]
        if len({e.event_date.year for e in train}) < MIN_TRAIN_YEARS:
            continue
        past = study(train, as_of=date(year, 1, 1))
        for e in clean:
            if e.event_date.year != year or e.car_20 is None:
                continue
            h = past.effect(e.event_class, GATE_HORIZON)
            prediction = h.effect if h is not None else 0.0
            row = stats[e.event_class].setdefault(year, [0.0, 0.0, 0.0])
            row[0] += (e.car_20 - prediction) ** 2
            row[1] += e.car_20 * e.car_20
            row[2] += 1

    tested = [c for c in found.classes if found.effect(c.event_class, GATE_HORIZON) is not None]
    threshold = 1.0 - GATE_SIGN_ALPHA / max(len(tested), 1)
    gates = []
    for c in found.classes:
        h20 = found.effect(c.event_class, GATE_HORIZON)
        by_year = stats.get(c.event_class, {})
        sse_model = sum(r[0] for r in by_year.values())
        sse_zero = sum(r[1] for r in by_year.values())
        n = int(sum(r[2] for r in by_year.values()))
        decided = [r for r in by_year.values() if not math.isclose(r[0], r[1])]
        win_share = sum(r[0] < r[1] for r in decided) / len(decided) if decided else 0.0
        improvement = 1.0 - sse_model / sse_zero if sse_zero > 0 else 0.0
        sign = h20.sign_probability if h20 is not None else 0.5
        if h20 is None:
            passed, reason = False, "Poucos eventos para medir o efeito em 20 pregões."
        else:
            passed, reason = _gate_verdict(
                len(by_year), improvement, win_share, sign, threshold, len(tested)
            )
        gates.append(
            ClassGate(
                event_class=c.event_class,
                origins=len(by_year),
                test_events=n,
                mse_model=round(float(sse_model) / n, 8) if n else 0.0,
                mse_zero=round(float(sse_zero) / n, 8) if n else 0.0,
                improvement=round(float(improvement), 4),
                win_share=round(float(win_share), 4),
                sign_probability=sign,
                passed=passed,
                reason=reason,
            )
        )
    return replace(found, gates=gates, sign_threshold=round(threshold, 4))


@dataclass(frozen=True)
class RecentEvent:
    """A CVM event of the last 20 trading days and what it adds to the forecast (42.5)."""

    event_class: str
    event_date: date  # delivery
    days_after: int  # trading days since the delivery
    effect: float  # what is still to come of the class effect (abnormal return, first month)
    effect_sd: float
    volatility_factor: float  # multiplies the spread of the first month
    used: bool
    note: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["event_date"] = self.event_date.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RecentEvent:
        return cls(**{**data, "event_date": date.fromisoformat(data["event_date"])})


def effect_so_far(effects: Mapping[int, float], days: int) -> float:
    """The class CAR expected after `days` trading days, linear between the measured horizons."""
    points = [(0, 0.0), *sorted(effects.items())]
    return float(np.interp(days, [p[0] for p in points], [p[1] for p in points]))


def _results_near(day: date, results_days: Sequence[date]) -> bool:
    return any(
        day - timedelta(days=CONFOUND_BEFORE_DAYS) <= r <= day + timedelta(days=CONFOUND_AFTER_DAYS)
        for r in results_days
    )


def recent_events(
    events: Sequence[EventInput],
    found: EventStudy | None,
    *,
    today: date,
    results_days: Sequence[date] = (),
    labels: Mapping[str, str] | None = None,
) -> list[RecentEvent]:
    """The events of the last 20 trading days, newest first, with the effect still to come."""
    names = labels or {}
    out = []
    for event in sorted(events, key=lambda e: e.delivery, reverse=True):
        days = int(np.busday_count(event.delivery, today))
        if event.delivery > today or days >= GATE_HORIZON:
            continue
        label = names.get(event.event_class, event.event_class)
        base = RecentEvent(event.event_class, event.delivery, days, 0.0, 0.0, 1.0, False, "")
        effect = found.class_effect(event.event_class) if found is not None else None
        h20 = found.effect(event.event_class, GATE_HORIZON) if found is not None else None
        if event.event_class == MIXED:
            note = "Comunicados de tipos diferentes no mesmo dia: sem efeito isolado."
        elif _results_near(event.delivery, results_days):
            note = f"{label}: perto da entrega de balanço, o efeito se confunde com o resultado."
        elif found is None:
            note = f"{label}: o estudo de eventos ainda não foi calculado."
        elif effect is None or h20 is None or not found.passed(event.event_class):
            verdict = found.gate(event.event_class)
            note = f"{label}: sem efeito comprovado." + (f" {verdict.reason}" if verdict else "")
        else:
            left = 1.0 - days / GATE_HORIZON
            so_far = effect_so_far({h.horizon: h.effect for h in effect.horizons}, days)
            remaining = h20.effect - so_far
            low, high = VOLATILITY_RATIO_BOUNDS
            ratio = min(max(effect.volatility_ratio or 1.0, low), high)
            out.append(
                replace(
                    base,
                    effect=round(remaining, 6),
                    effect_sd=round(h20.effect_sd * left, 6),
                    volatility_factor=round(math.sqrt(1.0 + (ratio * ratio - 1.0) * left), 4),
                    used=True,
                    note=(
                        f"{label} em {event.delivery:%d/%m}: efeito típico de "
                        f"{h20.effect:+.1%} em 20 pregões; faltam {remaining:+.1%}."
                    ),
                )
            )
            continue
        out.append(replace(base, note=note))
    return out
