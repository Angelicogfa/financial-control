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
"""

from __future__ import annotations

import bisect
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
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
class EventStudy:
    as_of: date
    events: int  # measured, one per company and day
    confounded: int
    classes: list[ClassEffect] = field(default_factory=list)
    tau: dict[str, float] = field(default_factory=dict)  # spread of the true class effects

    def effect(self, event_class: str, horizon: int) -> HorizonEffect | None:
        for c in self.classes:
            if c.event_class == event_class:
                return next((h for h in c.horizons if h.horizon == horizon), None)
        return None

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
        return cls(**payload)


def study(effects: Sequence[EventEffect], *, as_of: date) -> EventStudy:
    """Class effects of the unconfounded events, shrunk to zero across the classes."""
    events: dict[tuple[str, date], EventEffect] = {}
    for e in effects:
        events.setdefault((e.ticker, e.event_date), e)  # one per event, not per document
    measured = list(events.values())
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
