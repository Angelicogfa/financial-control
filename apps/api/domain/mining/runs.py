"""Worker side of the Garimpo (Phase 43): panel, signals, model, findings and record.

The panel is the valuation layer's (42.3) on the mining universe: each company's statements by
delivery date, its split-adjusted monthly prices and splits, and its monthly return over the
Ações class (the excess over the CDI minus the class's), which feeds momentum and, from 43.3, the
outcome the weights are estimated on.

The stored panel is the one register of point-in-time signals (Phase 45.1): besides the four of
the Garimpo it keeps the recommendation's INCOME and RISK, computed in the same run. The
Garimpo's model, findings and record use only its four.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Any

from domain.disclosures.statements import delivery_history
from domain.forecast.valuation_model import (
    CompanyInput,
    Month,
    forward_alpha,
    month_end,
    month_of,
)
from domain.mining.findings import record, record_to_dicts, run_findings
from domain.mining.model import estimate_mining_model
from domain.mining.repositories import MiningSignal
from domain.mining.signals import mining_signals, month_list
from domain.mining.universe import MIN_DAILY_VOLUME, MiningMember, mining_universe
from domain.recommendation.signals import registry_signals
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


Panel = tuple[dict[str, CompanyInput], dict[str, dict[Month, float]], dict[str, dict[Month, float]]]


def mining_panel(uow: AbstractUnitOfWork, members: list[MiningMember], today: date) -> Panel:
    """Companies with statements and prices, their monthly return over the Ações class and over
    the CDI."""
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
        return {}, {}, {}
    history = build_market_history(
        uow.market_series, sorted(companies), start=SIMULATION_HISTORY_START, end=today
    )
    try:
        sample = class_sample(history, [ArcaClass.ACOES])
    except InsufficientHistory:
        return companies, {}, {}
    k = CLASS_ORDER.index(ArcaClass.ACOES)
    alphas: dict[str, dict[Month, float]] = {}
    over_cdi: dict[str, dict[Month, float]] = {}
    for ticker in companies:
        excess, mask = monthly_excess(history, ticker, sample)
        over_cdi[ticker] = {
            month_of(sample.months[i]): float(excess[i]) for i in range(sample.size) if mask[i]
        }
        alphas[ticker] = {
            month_of(sample.months[i]): float(excess[i] - sample.excess[i, k])
            for i in range(sample.size)
            if mask[i]
        }
    return companies, alphas, over_cdi


MINING = "MINING"


def run_mining(
    uow: AbstractUnitOfWork,
    *,
    min_daily_volume: float = MIN_DAILY_VOLUME,
    today: date | None = None,
) -> dict[str, Any]:
    """Signals of the universe, the gated model, this week's findings and the record."""
    as_of = today or date.today()
    members = mining_universe(uow, min_daily_volume)
    companies, alphas, over_cdi = mining_panel(uow, members, as_of)
    if not companies:
        return {"universe": len(members), "companies": 0, "signals": 0}
    first = min(min(c.prices) for c in companies.values())
    months = month_list(first, as_of)
    panel = mining_signals(companies, alphas, months)
    extra = registry_signals(companies, over_cdi, months)
    rows = [
        MiningSignal(ticker=t, month=month_end(m), signal=name, z=z)
        for source in (panel, extra)
        for t, by_month in source.items()
        for m, values in by_month.items()
        for name, z in values.items()
    ]
    stored = uow.mining.replace_signals(rows)

    forward = {t: forward_alpha(a) for t, a in alphas.items()}
    model = estimate_mining_model(panel, forward, as_of=as_of)
    findings = run_findings(panel, model, as_of)
    uow.mining.replace_run(as_of, findings)
    past = uow.mining.all_findings()
    model = replace(model, record=record_to_dicts(record(past, alphas)))
    uow.forecasts.save_model(MINING, as_of, model.to_dict())
    return {
        "universe": len(members),
        "companies": len(companies),
        "signals": stored,
        "last_month": max((r.month for r in rows), default=None),
        "findings": len(findings),
        "trusted": model.passed,
    }
