"""Worker side of the Garimpo (Phase 43): build the monthly panel and store the signals.

The panel is the valuation layer's (42.3) on the mining universe: each company's statements by
delivery date, its split-adjusted monthly prices and splits, and its monthly return over the
Ações class (the excess over the CDI minus the class's), which feeds momentum and, from 43.3, the
outcome the weights are estimated on.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from domain.disclosures.statements import delivery_history
from domain.forecast.valuation_model import CompanyInput, Month, month_end, month_of
from domain.mining.repositories import MiningSignal
from domain.mining.signals import mining_signals, month_list
from domain.mining.universe import MIN_DAILY_VOLUME, MiningMember, mining_universe
from domain.shared.enums import ArcaClass
from domain.shared.unit_of_work import AbstractUnitOfWork
from domain.simulation.candidates import monthly_excess
from domain.simulation.data import (
    SIMULATION_HISTORY_START,
    build_market_history,
    px_symbol,
    split_symbol,
)
from domain.simulation.scenarios import CLASS_ORDER, InsufficientHistory, class_sample


def _monthly_prices(uow: AbstractUnitOfWork, ticker: str, end: date) -> dict[Month, float]:
    out: dict[Month, float] = {}
    for p in uow.market_series.list_series(
        px_symbol(ticker), date_from=SIMULATION_HISTORY_START, date_to=end
    ):
        out[month_of(p.reference_date)] = p.value
    return out


def mining_panel(
    uow: AbstractUnitOfWork, members: list[MiningMember], today: date
) -> tuple[dict[str, CompanyInput], dict[str, dict[Month, float]]]:
    """Companies with statements and prices, and their monthly return over the Ações class."""
    companies: dict[str, CompanyInput] = {}
    for m in members:
        facts = uow.cvm_statements.facts_for(m.cnpj)
        prices = _monthly_prices(uow, m.ticker, today)
        if not facts or not prices:
            continue
        companies[m.ticker] = CompanyInput(
            ticker=m.ticker,
            sector=m.sector,
            snapshots=list(reversed(delivery_history(facts))),
            prices=prices,
            splits=[
                (p.reference_date, p.value)
                for p in uow.market_series.list_series(split_symbol(m.ticker))
            ],
        )
    if not companies:
        return {}, {}
    history = build_market_history(
        uow.market_series, sorted(companies), start=SIMULATION_HISTORY_START, end=today
    )
    try:
        sample = class_sample(history, [ArcaClass.ACOES])
    except InsufficientHistory:
        return companies, {}
    k = CLASS_ORDER.index(ArcaClass.ACOES)
    alphas: dict[str, dict[Month, float]] = {}
    for ticker in companies:
        excess, mask = monthly_excess(history, ticker, sample)
        alphas[ticker] = {
            month_of(sample.months[i]): float(excess[i] - sample.excess[i, k])
            for i in range(sample.size)
            if mask[i]
        }
    return companies, alphas


def refresh_signals(
    uow: AbstractUnitOfWork,
    *,
    min_daily_volume: float = MIN_DAILY_VOLUME,
    today: date | None = None,
) -> dict[str, Any]:
    """Recompute and store the signal panel of the mining universe."""
    as_of = today or date.today()
    members = mining_universe(uow, min_daily_volume)
    companies, alphas = mining_panel(uow, members, as_of)
    if not companies:
        return {"universe": len(members), "companies": 0, "signals": 0}
    first = min(min(c.prices) for c in companies.values())
    months = month_list(first, as_of)
    panel = mining_signals(companies, alphas, months)
    rows = [
        MiningSignal(ticker=t, month=month_end(m), signal=name, z=z)
        for t, by_month in panel.items()
        for m, values in by_month.items()
        for name, z in values.items()
    ]
    stored = uow.mining.replace_signals(rows)
    return {
        "universe": len(members),
        "companies": len(companies),
        "signals": stored,
        "last_month": max((r.month for r in rows), default=None),
    }
