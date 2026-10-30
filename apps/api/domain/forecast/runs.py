"""Worker side of the price forecasts (Phase 42.1): compute, store and calibrate.

The inputs are the simulation's own (Phase 33): the long total-return history in
`market_series`, the class sample, the calibrated mixture of generators. The estimation
universe is the portfolio, the watchlist and the most traded catalog instruments (decision
42.0-3); forecasts are stored for the registered assets only.

Layer B (42.3): `estimate_valuation_model` measures, weekly, how much the valuation of the
statements delivered to the CVM said about the next 12 months, with an out-of-sample gate; the
daily forecast pulls each company's α to γ·z instead of zero when the gate passed.

Layer C (42.5): the event study (`domain.forecast.event_runs`, weekly) keeps the gate of each
class; the daily forecast adds the effect of the company's events of the last 20 trading days
whose class passed.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np

from domain.disclosures.events import EVENT_LABELS
from domain.disclosures.services.sync import base_ticker
from domain.disclosures.statements import delivery_history
from domain.forecast.calibration import calibrate
from domain.forecast.event_runs import EVENTS
from domain.forecast.events import EventStudy, RecentEvent, group_events, recent_events
from domain.forecast.model import (
    DEFAULT_PATHS,
    HORIZONS,
    MODEL_VERSION,
    dividend_drag,
    forecast_asset,
)
from domain.forecast.valuation_model import (
    CompanyInput,
    Month,
    ValuationModel,
    company_yields,
    estimate,
    forward_alpha,
    month_of,
    value_scores,
)
from domain.market.entities import Quote
from domain.shared.entities import AssetEntity
from domain.shared.enums import ArcaClass, default_arca_class
from domain.shared.unit_of_work import AbstractUnitOfWork
from domain.simulation.candidates import (
    MIN_HISTORY_MONTHS,
    FactorFit,
    class_tau,
    fit_asset,
    monthly_excess,
    shrink,
)
from domain.simulation.data import (
    SIMULATION_HISTORY_START,
    build_market_history,
    px_symbol,
    simulation_universe,
    split_symbol,
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

VALUATION = "VALUATION"
DEFAULT_SEED = 42
DRAG_MONTHS = 36
MEAN_BLOCK_MONTHS = 12.0
# An asset the user asked for by itself is forecast from 12 months on, with a warning; the
# rest need the 36 months of the candidates model (decision 42.0-5).
REQUESTED_MIN_MONTHS = 12
RECENT_EVENT_DAYS = 35  # calendar days that hold the last 20 trading days


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


def _fits(
    universe: _Universe,
    requested: Collection[str] = (),
    prior_means: Mapping[str, float] | None = None,
) -> dict[str, FactorFit]:
    raw: dict[str, FactorFit] = {}
    for ticker, cls in universe.classes.items():
        if cls in universe.sample.classes:
            minimum = REQUESTED_MIN_MONTHS if ticker in requested else MIN_HISTORY_MONTHS
            fit = fit_asset(ticker, cls, universe.history, universe.sample, min_months=minimum)
            if fit is not None:
                raw[ticker] = fit
    # The spread of the class comes from the full histories only.
    taus = {
        cls: class_tau(
            [f for f in raw.values() if f.arca_class == cls and f.months >= MIN_HISTORY_MONTHS]
        )
        for cls in {f.arca_class for f in raw.values()}
    }
    means = prior_means or {}
    return {t: shrink(f, taus[f.arca_class], means.get(t, 0.0)) for t, f in raw.items()}


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
    tickers: Collection[str] | None = None,
    on_demand: bool = False,
) -> dict[str, int]:
    """Forecast every registered asset with history and store it; the rest get a status.

    `tickers` limits the run to those assets; `on_demand` marks them as asked for by the user,
    which lowers the history needed and keeps them shown with a warning on later runs too.
    """
    as_of = today or date.today()
    try:
        universe = _universe(uow, catalog_top=catalog_top, today=as_of)
    except InsufficientHistory:
        return {"forecasts": 0, "insufficient": 0, "skipped": 1}
    wanted = {t.upper() for t in tickers} if tickers is not None else None
    targets = [a for a in universe.registered if wanted is None or a.ticker.upper() in wanted]
    requested = {
        a.ticker.upper()
        for a in targets
        if (on_demand and wanted is not None)
        or (
            (prior := uow.forecasts.latest(a.ticker)) is not None and prior.payload.get("on_demand")
        )
    }
    model, sectors = _valuation_inputs(uow)
    prior_means, notes = _valuation_priors(model, sectors, universe.classes)
    fits = _fits(universe, requested, prior_means)
    events, events_note = _recent_events(uow, [a.ticker.upper() for a in targets], as_of)
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
    for asset in targets:
        if deadline is not None and deadline():
            break
        ticker = asset.ticker.upper()
        flag = {"on_demand": True} if ticker in requested else {}
        cls = universe.classes.get(ticker)
        fit = fits.get(ticker)
        if cls is None:
            continue
        if fit is None:
            months = int(monthly_excess(universe.history, ticker, universe.sample)[1].sum())
            uow.forecasts.save(
                ticker,
                as_of,
                {"status": "INSUFFICIENT_HISTORY", "months": months, **flag},
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
            valuation_note=notes.get(ticker),
            events=events.get(ticker, []),
            events_note=events_note,
        )
        uow.forecasts.save(
            ticker,
            as_of,
            {"status": "OK", **forecast.to_dict(), **flag},
            model_version=MODEL_VERSION,
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


# --- layer C: recent events (42.5) ---------------------------------------------------------------


def _recent_events(
    uow: AbstractUnitOfWork, tickers: Collection[str], today: date
) -> tuple[dict[str, list[RecentEvent]], str | None]:
    """The recent CVM events of each ticker with what they add, and the note when none apply."""
    stored = uow.forecasts.latest_model(EVENTS)
    found = EventStudy.from_dict(stored.payload) if stored is not None else None
    cnpjs = uow.cvm_issuers.cnpjs_for([base_ticker(t) for t in tickers])
    by_cnpj = {c: t for t in tickers if (c := cnpjs.get(base_ticker(t))) is not None}
    if not by_cnpj:
        return {}, None
    documents = uow.cvm_documents.events(
        sorted(by_cnpj), since=today - timedelta(days=RECENT_EVENT_DAYS)
    )
    rows = [
        (d.id, by_cnpj[d.cnpj], d.delivery_date, d.event_class or "")
        for d in documents
        if d.id is not None and d.cnpj in by_cnpj
    ]
    out: dict[str, list[RecentEvent]] = {}
    grouped: dict[str, list] = {}
    for event in group_events(rows):
        grouped.setdefault(event.ticker, []).append(event)
    cnpj_of = {t: c for c, t in by_cnpj.items()}
    for ticker, items in grouped.items():
        results = [d.delivered_on for d in uow.cvm_statements.docs_for(cnpj_of[ticker])]
        found_events = recent_events(
            items, found, today=today, results_days=results, labels=EVENT_LABELS
        )
        if found_events:
            out[ticker] = found_events
    note = None if found is not None else "O estudo de eventos ainda não foi calculado."
    return out, note


# --- layer B: valuation (42.3) ----------------------------------------------------------------


def _monthly_prices(
    uow: AbstractUnitOfWork, symbol: str, start: date, end: date
) -> dict[Month, float]:
    out: dict[Month, float] = {}
    for p in uow.market_series.list_series(symbol, date_from=start, date_to=end):
        out[month_of(p.reference_date)] = p.value
    return out


def _sectors(uow: AbstractUnitOfWork) -> dict[str, str]:
    return {i.ticker.upper(): (i.sector or "") for i in uow.catalog.list_all()}


def _valuation_inputs(uow: AbstractUnitOfWork) -> tuple[ValuationModel | None, dict[str, str]]:
    stored = uow.forecasts.latest_model(VALUATION)
    model = ValuationModel.from_dict(stored.payload) if stored is not None else None
    return model, _sectors(uow) if model is not None else {}


def _valuation_priors(
    model: ValuationModel | None, sectors: Mapping[str, str], tickers: Collection[str]
) -> tuple[dict[str, float], dict[str, str]]:
    """Monthly prior mean of α (γ·z) and the note of the driver, per ticker."""
    if model is None:
        return {}, {}
    means: dict[str, float] = {}
    notes: dict[str, str] = {}
    for ticker in tickers:
        score = model.scores.get(ticker)
        if score is None:
            continue
        z = float(score["z"])
        side = "mais barata" if z > 0 else "mais cara"
        if model.passed:
            means[ticker] = model.gamma_for(sectors.get(ticker)) * z
            notes[ticker] = (
                f"z de valuation {z:+.1f} ({side} que o próprio histórico e o setor, "
                f"balanços até {score['month']}). {model.reason}"
            )
        else:
            notes[ticker] = f"z de valuation {z:+.1f} ({side}). {model.reason}"
    return means, notes


def valuation_panel(
    uow: AbstractUnitOfWork, universe: _Universe, today: date
) -> tuple[dict[str, CompanyInput], dict[str, dict[Month, float]]]:
    """Companies with statements and prices, and their monthly α over the class."""
    tickers = sorted(universe.classes)
    cnpjs = uow.cvm_issuers.cnpjs_for([base_ticker(t) for t in tickers])
    sectors = _sectors(uow)
    companies: dict[str, CompanyInput] = {}
    alphas: dict[str, dict[Month, float]] = {}
    seen: set[str] = set()
    for ticker in tickers:
        cnpj = cnpjs.get(base_ticker(ticker))
        if cnpj is None or cnpj in seen:  # one share class per company
            continue
        facts = uow.cvm_statements.facts_for(cnpj)
        if not facts:
            continue
        seen.add(cnpj)
        companies[ticker] = CompanyInput(
            ticker=ticker,
            sector=sectors.get(ticker, ""),
            snapshots=list(reversed(delivery_history(facts))),
            prices=_monthly_prices(uow, px_symbol(ticker), SIMULATION_HISTORY_START, today),
            splits=[
                (p.reference_date, p.value)
                for p in uow.market_series.list_series(split_symbol(ticker))
            ],
        )
        cls = universe.classes[ticker]
        if cls in universe.sample.classes:
            k = CLASS_ORDER.index(cls)
            excess, mask = monthly_excess(universe.history, ticker, universe.sample)
            alphas[ticker] = {
                month_of(universe.sample.months[i]): float(excess[i] - universe.sample.excess[i, k])
                for i in range(universe.sample.size)
                if mask[i]
            }
    return companies, alphas


def estimate_valuation_model(
    uow: AbstractUnitOfWork, *, catalog_top: int = 0, today: date | None = None
) -> dict[str, Any] | None:
    """Estimate layer B on the universe and store it (None without a usable universe)."""
    as_of = today or date.today()
    try:
        universe = _universe(uow, catalog_top=catalog_top, today=as_of)
    except InsufficientHistory:
        return None
    companies, alphas = valuation_panel(uow, universe, as_of)
    if not companies:
        return None
    yields = {t: company_yields(c) for t, c in companies.items()}
    sectors = {t: c.sector for t, c in companies.items()}
    scores = value_scores(yields, sectors)
    forward = {t: forward_alpha(a) for t, a in alphas.items()}
    model = estimate(scores, forward, sectors, as_of=as_of)
    payload = model.to_dict()
    uow.forecasts.save_model(VALUATION, as_of, payload)
    return payload
