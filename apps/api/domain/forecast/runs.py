"""Worker side of the price forecasts (Phase 42.1): compute, store and calibrate.

The inputs are the simulation's own (Phase 33): the long total-return history in
`market_series`, the class sample, the calibrated mixture of generators. The estimation
universe is the portfolio, the watchlist and the most traded catalog instruments (decision
42.0-3); forecasts are stored for the registered assets only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np

from domain.forecast.calibration import calibrate
from domain.forecast.model import (
    DEFAULT_PATHS,
    HORIZONS,
    MODEL_VERSION,
    dividend_drag,
    forecast_asset,
)
from domain.market.entities import Quote
from domain.shared.entities import AssetEntity
from domain.shared.enums import ArcaClass, default_arca_class
from domain.shared.unit_of_work import AbstractUnitOfWork
from domain.simulation.candidates import FactorFit, class_tau, fit_asset, monthly_excess, shrink
from domain.simulation.data import (
    SIMULATION_HISTORY_START,
    build_market_history,
    px_symbol,
    simulation_universe,
    tr_symbol,
)
from domain.simulation.generators import draw_mixture, sample_posterior
from domain.simulation.market import MarketHistory
from domain.simulation.runs import STACKED, mixture_weights
from domain.simulation.scenarios import (
    CLASS_ORDER,
    ClassSample,
    InsufficientHistory,
    annual_to_monthly,
    class_sample,
)

DEFAULT_SEED = 42
DRAG_MONTHS = 36
MEAN_BLOCK_MONTHS = 12.0


@dataclass(frozen=True)
class _Universe:
    registered: list[AssetEntity]
    classes: dict[str, ArcaClass]
    history: MarketHistory
    sample: ClassSample


def _class_of(asset: AssetEntity) -> ArcaClass | None:
    if asset.arca_class is not None:
        return asset.arca_class
    try:
        return default_arca_class(asset.asset_type)
    except (KeyError, TypeError):
        return None


def _universe(uow: AbstractUnitOfWork, *, catalog_top: int, today: date) -> _Universe:
    assets = simulation_universe(uow, catalog_top)
    registered_ids = {a.id for a in uow.assets.list_all(active_only=True)}
    classes = {
        a.ticker.upper(): cls
        for a in assets
        if (cls := _class_of(a)) is not None and cls != ArcaClass.CAIXA
    }
    currencies = {a.ticker.upper(): (a.currency or "BRL") for a in assets}
    history = build_market_history(
        uow.market_series,
        sorted(classes),
        start=SIMULATION_HISTORY_START,
        end=today,
        currency_by_ticker=currencies,
    )
    needed = [c for c in CLASS_ORDER if c in set(classes.values())]
    sample = class_sample(history, needed)
    registered = [a for a in assets if a.id is not None and a.id in registered_ids]
    return _Universe(registered, classes, history, sample)


def _fits(universe: _Universe) -> dict[str, FactorFit]:
    raw: dict[str, FactorFit] = {}
    for ticker, cls in universe.classes.items():
        if cls in universe.sample.classes:
            fit = fit_asset(ticker, cls, universe.history, universe.sample)
            if fit is not None:
                raw[ticker] = fit
    taus = {
        cls: class_tau([f for f in raw.values() if f.arca_class == cls])
        for cls in {f.arca_class for f in raw.values()}
    }
    return {t: shrink(f, taus[f.arca_class]) for t, f in raw.items()}


def _monthly_points(uow: AbstractUnitOfWork, symbol: str, start: date, end: date) -> list[float]:
    """The last value of each month of a stored series (raw currency)."""
    by_month: dict[tuple[int, int], float] = {}
    for p in uow.market_series.list_series(symbol, date_from=start, date_to=end):
        by_month[(p.reference_date.year, p.reference_date.month)] = p.value
    return [by_month[k] for k in sorted(by_month)]


def _drag(uow: AbstractUnitOfWork, ticker: str, today: date) -> float:
    start = today - timedelta(days=31 * (DRAG_MONTHS + 1))
    return dividend_drag(
        _monthly_points(uow, tr_symbol(ticker), start, today),
        _monthly_points(uow, px_symbol(ticker), start, today),
    )


def _price_now(
    uow: AbstractUnitOfWork, asset: AssetEntity, today: date, usd_brl: float
) -> float | None:
    """Today's price in reais: the stored quote, else the last stored price of the series."""
    data = uow.market_data.get_many([asset.ticker]).get(asset.ticker.upper())
    quote: Quote | None = data.quote if data else None
    price = quote.price if quote is not None and quote.price > 0 else None
    if price is None:
        points = uow.market_series.list_series(
            px_symbol(asset.ticker), date_from=today - timedelta(days=15), date_to=today
        )
        price = points[-1].value if points else None
    if price is None:
        return None
    return price * usd_brl if (asset.currency or "BRL").upper() == "USD" else price


def refresh_forecasts(
    uow: AbstractUnitOfWork,
    *,
    cdi_annual: float,
    usd_brl: float,
    catalog_top: int = 0,
    today: date | None = None,
    seed: int = DEFAULT_SEED,
    paths: int = DEFAULT_PATHS,
    deadline: Callable[[], bool] | None = None,
) -> dict[str, int]:
    """Forecast every registered asset with history and store it; the rest get a status."""
    as_of = today or date.today()
    try:
        universe = _universe(uow, catalog_top=catalog_top, today=as_of)
    except InsufficientHistory:
        return {"forecasts": 0, "insufficient": 0, "skipped": 1}
    fits = _fits(universe)
    weights, _run, _note = mixture_weights(uow, STACKED, universe.sample)
    excess, _labels = draw_mixture(
        universe.sample,
        weights,
        paths,
        max(HORIZONS),
        mean_block=MEAN_BLOCK_MONTHS,
        seed=seed,
        posterior=sample_posterior(universe.sample),
    )
    cdi_m = annual_to_monthly(cdi_annual)
    counts = {"forecasts": 0, "insufficient": 0, "skipped": 0}
    for asset in universe.registered:
        if deadline is not None and deadline():
            break
        ticker = asset.ticker.upper()
        cls = universe.classes.get(ticker)
        fit = fits.get(ticker)
        if cls is None:
            continue
        if fit is None:
            months = int(monthly_excess(universe.history, ticker, universe.sample)[1].sum())
            uow.forecasts.save(
                ticker,
                as_of,
                {"status": "INSUFFICIENT_HISTORY", "months": months},
                model_version=MODEL_VERSION,
            )
            counts["insufficient"] += 1
            continue
        price = _price_now(uow, asset, as_of, usd_brl)
        if price is None:
            counts["skipped"] += 1
            continue
        k = CLASS_ORDER.index(cls)
        forecast = forecast_asset(
            fit,
            excess[:, :, k],
            cdi_monthly=cdi_m,
            price_now=price,
            drag_monthly=_drag(uow, ticker, as_of),
            as_of=as_of,
            seed=seed + k,
            class_expected_excess_monthly=float(np.mean(universe.sample.excess[:, k])),
        )
        uow.forecasts.save(
            ticker, as_of, {"status": "OK", **forecast.to_dict()}, model_version=MODEL_VERSION
        )
        counts["forecasts"] += 1
    return counts


def run_calibration(
    uow: AbstractUnitOfWork,
    *,
    catalog_top: int = 0,
    today: date | None = None,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any] | None:
    """Score past forecasts of the whole universe and store the calibration."""
    as_of = today or date.today()
    try:
        universe = _universe(uow, catalog_top=catalog_top, today=as_of)
    except InsufficientHistory:
        return None
    excess_by_asset = {}
    for ticker, cls in universe.classes.items():
        excess, mask = monthly_excess(universe.history, ticker, universe.sample)
        excess_by_asset[ticker] = (cls, excess, mask)
    result = calibrate(excess_by_asset, universe.sample, as_of=as_of, seed=seed)
    if result is None:
        return None
    payload = result.to_dict()
    uow.forecasts.save_calibration(as_of, payload)
    return payload
