"""A level jump in a price series is not a monthly return (analysis P0, item 2)."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from domain.market.services.price_sanity import plausible_month
from domain.recommendation.runs import monthly_returns
from domain.shared.entities import MarketSeriesPoint
from domain.simulation.candidates import monthly_excess
from domain.simulation.market import MarketHistory, PriceSeries
from domain.simulation.scenarios import ClassSample


def test_plausible_month_keeps_crashes_and_drops_level_jumps() -> None:
    assert plausible_month(100.0, 23.0)  # a real 77% crash stays
    assert plausible_month(10.0, 35.0)
    assert not plausible_month(0.01, 250.0)  # an unapplied reverse split
    assert not plausible_month(100.0, 1.0)  # an unapplied split
    assert not plausible_month(0.0, 1.0)
    assert not plausible_month(None, 1.0)


def _month_ends(n: int) -> list[date]:
    out = []
    for i in range(n):
        y, m = 2020 + i // 12, i % 12 + 1
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        out.append(nxt - timedelta(days=1))
    return out


def test_monthly_excess_leaves_out_the_jump() -> None:
    ends = _month_ends(6)
    prices = [10.0, 11.0, 1100.0, 1150.0, 1200.0, 1210.0]  # x100 between months 2 and 3
    history = MarketHistory(
        {"AAAA3": PriceSeries.from_points(list(zip(ends, prices, strict=True)))}
    )
    sample = ClassSample(
        months=tuple(ends[1:]), excess=np.zeros((5, 1)), cdi=np.zeros(5), classes=()
    )
    excess, mask = monthly_excess(history, "AAAA3", sample)
    assert mask.tolist() == [True, False, True, True, True]
    assert float(excess.max()) < 0.2


class _Series:
    def __init__(self, points: list[MarketSeriesPoint]) -> None:
        self.points = points

    def list_series(self, symbol: str, **_kw) -> list[MarketSeriesPoint]:
        return self.points if symbol.startswith("SIM:TR:") else []


def test_recommendation_returns_drop_the_jump_and_bad_prints() -> None:
    ends = _month_ends(5)
    values = [10.0, 11.0, 1100.0, 1150.0, 1160.0]
    points = [MarketSeriesPoint("SIM:TR:AAAA3", d, v) for d, v in zip(ends, values, strict=True)]
    uow = SimpleNamespace(market_series=_Series(points))
    found = monthly_returns(uow, ["AAAA3"], ends[-1])  # type: ignore[arg-type]
    months = found["AAAA3"]
    assert (2020, 3) not in months  # the x100 month
    assert months[(2020, 2)] == pytest.approx(0.1)
    assert months[(2020, 4)] == pytest.approx(1150 / 1100 - 1)
