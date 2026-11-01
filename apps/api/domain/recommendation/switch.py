"""The contribution follows the recommendation (Phase 45.6b): the targets of each class.

For each class the latest weekly run built (45.4), the target weights are the construction pulled
toward the current weights by the confidence (decision 10.6), and the assets the portfolio report
does not list (catalog stocks, decision 10.4) come with their stored price. A class without a
run, or with a run older than two weeks (the worker stopped), keeps the policy's strategy: the
contribution never follows stale targets.
"""

from __future__ import annotations

from datetime import date

from domain.policy.services.policy import InvestmentPolicy
from domain.portfolio.services.consolidation import (
    LEDGER_VALID,
    ConsolidatedPortfolioReport,
    RecommendedCandidate,
    RecommendedClass,
)
from domain.recommendation.construction import pulled_targets
from domain.shared.enums import ArcaClass, AssetPurpose, AssetType
from domain.shared.unit_of_work import AbstractUnitOfWork
from domain.simulation.data import px_symbol

MAX_RUN_AGE_DAYS = 14


def _price(uow: AbstractUnitOfWork, ticker: str) -> float:
    data = uow.market_data.get_many([ticker]).get(ticker)
    if data is not None and data.quote is not None and data.quote.price > 0:
        return float(data.quote.price)
    points = uow.market_series.list_series(px_symbol(ticker))
    return float(points[-1].value) if points else 0.0


def recommended_classes(
    uow: AbstractUnitOfWork,
    report: ConsolidatedPortfolioReport,
    policy: InvestmentPolicy,
    *,
    today: date | None = None,
) -> dict[ArcaClass, RecommendedClass]:
    """The recommendation's targets of each class it covers, ready for the contribution plan."""
    run = uow.recommendation.latest_lens_date()
    if run is None or ((today or date.today()) - run).days > MAX_RUN_AGE_DAYS:
        return {}
    catalog = {i.ticker.upper(): i for i in uow.catalog.list_all()}
    out: dict[ArcaClass, RecommendedClass] = {}
    for construction in uow.recommendation.constructions(run):
        if not construction.selected:
            continue
        arca_class = ArcaClass(construction.arca_class)
        positions = {
            p.ticker: p
            for p in report.positions
            if p.arca_class == arca_class
            and p.ledger_status == LEDGER_VALID
            and p.purpose == AssetPurpose.ARCA
        }
        current = {t: p.current_value_brl for t, p in positions.items() if p.current_value_brl > 0}
        targets = pulled_targets(construction, current)
        candidates = {}
        for ticker in targets:
            if ticker in positions:
                continue
            registered = uow.assets.get_by_ticker(ticker)
            item = catalog.get(ticker)
            candidates[ticker] = RecommendedCandidate(
                ticker=ticker,
                name=(registered.name if registered else None) or (item.name if item else ticker),
                asset_type=registered.asset_type if registered else AssetType.STOCK_BR,
                asset_id=registered.id if registered and registered.is_active else None,
                unit_brl=_price(uow, ticker),
            )
        out[arca_class] = RecommendedClass(
            targets=targets,
            candidates=candidates,
            min_lot_brl=policy.recommendation.min_lot_brl,
            as_of=run.isoformat(),
        )
    return out


def recent_gate_eligibility(uow: AbstractUnitOfWork, today: date | None = None) -> dict[str, bool]:
    """Whether each asset of the latest run passed its gates (empty when the run is stale)."""
    run = uow.recommendation.latest_lens_date()
    if run is None or ((today or date.today()) - run).days > MAX_RUN_AGE_DAYS:
        return {}
    return {g.ticker: g.eligible for g in uow.recommendation.gates(as_of=run)}
