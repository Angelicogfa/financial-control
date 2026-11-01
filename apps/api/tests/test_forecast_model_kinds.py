"""Every kind stored in `forecast_models` fits the column (SQLite does not check lengths)."""

from __future__ import annotations

from domain.forecast.event_runs import EVENTS
from domain.forecast.runs import VALUATION
from domain.mining.runs import MINING
from domain.recommendation.backtest_runs import RECOMMENDATION_BACKTEST
from domain.recommendation.validation import LENS_WEIGHTS
from infra.data.models.forecast import ForecastModelModel


def test_every_forecast_model_kind_fits_the_column() -> None:
    length = ForecastModelModel.__table__.c.kind.type.length
    for kind in (EVENTS, VALUATION, MINING, RECOMMENDATION_BACKTEST, LENS_WEIGHTS):
        assert len(kind) <= length, kind
